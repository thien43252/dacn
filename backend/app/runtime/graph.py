"""The per-message runtime as a LangGraph graph.

    screen ──blocked──────────────────────────────▶ END
      │ (rules: jailbreak, self-harm, PII redaction, class blocked topics)
      ├──▶ classify ─────┐   (LLM input guard)        run in parallel, so the guard adds no latency
      └──▶ select_agent ─┤   (orchestrator / router)  on top of routing
                         ▼
                        gate ──blocked──────────────▶ END
                         │
                      run_agent      (agent + tool loop; the tool guard checks every call)
                         │
                      review         (output guard: rules, then LLM; may retract the streamed reply)
                         ▼
                        END

Nodes stream UI events through LangGraph's custom stream writer, which the chat endpoint relays as SSE. Every guard
decision other than "allow" is written to guard_events.
"""

import time
from dataclasses import dataclass, field
from typing import Any, TypedDict

from langgraph.config import get_stream_writer
from langgraph.graph import END, START, StateGraph
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.service import ResolvedAgent
from app.audit.models import GuardEvent
from app.auth.models import User
from app.chat.models import Conversation, ToolCallLog
from app.classes.models import ClassRoom
from app.guard import classifier, rules
from app.guard.rules import Verdict
from app.llm.base import ChatModel, Completion, LLMError, Message, TextDelta, Usage
from app.runtime.prompts import build_system_prompt
from app.runtime.router import route
from app.tools import registry as tools

MAX_TOOL_ROUNDS = 4

INPUT_BLOCKED = (
    "Mình không thể hỗ trợ yêu cầu này vì nó vi phạm quy tắc an toàn của nền tảng. "
    "Nếu bạn cần giúp về bài học, cứ hỏi mình nhé!"
)
TOPIC_BLOCKED = (
    "Chủ đề “{topic}” không được trao đổi trong lớp này theo chính sách của giáo viên. Mình cùng quay lại bài học nhé!"
)
REDACTED = "Mình đã ẩn thông tin cá nhân (số điện thoại, mật khẩu, địa chỉ…) trong tin nhắn trước khi gửi cho agent và không lưu lại."
OUTPUT_BLOCKED = (
    "Câu trả lời vừa rồi đã được lớp bảo vệ của nền tảng thu hồi vì chưa phù hợp. Bạn thử hỏi theo cách khác nhé."
)
ANSWER_WITHHELD = (
    "Theo chính sách của lớp, mình không đưa đáp án hay lời giải hoàn chỉnh. "
    "Em thử làm bước đầu tiên rồi gửi mình xem, mình sẽ gợi ý tiếp từng bước nhé!"
)


@dataclass
class RunContext:
    db: AsyncSession
    user: User
    role: str
    room: ClassRoom | None
    conversation: Conversation
    agents: list[ResolvedAgent]
    chat_model: ChatModel
    message_id: str
    # chat | sandbox | certify
    source: str = "chat"
    guard_mode: str = "full"
    router_mode: str = "llm"
    usage: list[tuple[str, Usage, int]] = field(default_factory=list)
    events: list[GuardEvent] = field(default_factory=list)

    def log(self, stage: str, verdict: Verdict, text: str, agent_slug: str | None = None) -> None:
        excerpt, _ = rules.redact(text)
        event = GuardEvent(
            source=self.source,
            class_id=self.room.id if self.room else None,
            user_id=self.user.id,
            role=self.role,
            conversation_id=self.conversation.id,
            message_id=self.message_id,
            agent_slug=agent_slug,
            stage=stage,
            verdict=verdict.action,
            category=verdict.category,
            detector=verdict.detector,
            severity=verdict.severity,
            reason=verdict.reason[:300],
            excerpt=excerpt[:300],
        )
        self.db.add(event)
        self.events.append(event)

    def timed(self, purpose: str, usage: Usage | None, started: float) -> None:
        if usage is not None:
            self.usage.append((purpose, usage, int((time.perf_counter() - started) * 1000)))


class ChatState(TypedDict, total=False):
    ctx: RunContext
    # The message as the agent sees it (personal data already redacted by `screen`).
    text: str
    requested_agent: str | None
    previous_agent: str | None
    history: list[Message]
    support: bool
    llm_verdict: Verdict
    agent: ResolvedAgent
    route_reason: str
    reply: str
    status: str
    blocked_stage: str
    tool_events: list[dict[str, Any]]


def utf16_len(text: str) -> int:
    return len(text.encode("utf-16-le")) // 2


def _blocked(ctx: RunContext, stage: str, text: str) -> ChatState:
    get_stream_writer()({"type": "notice", "message_id": ctx.message_id, "kind": "guard_blocked", "text": text})
    return {"reply": text, "status": "blocked", "blocked_stage": stage}


async def screen(state: ChatState) -> ChatState:
    ctx = state["ctx"]
    if ctx.guard_mode != "full":
        return {}
    text = state["text"]
    verdict = rules.screen_input(text)
    if verdict.blocks:
        ctx.log("input", verdict, text)
        return _blocked(ctx, "input", rules.SELF_HARM_REPLY if verdict.category == "self_harm" else INPUT_BLOCKED)
    topic = rules.policy_topics(text, (ctx.room.policy or {}).get("blocked_topics", []) if ctx.room else [])
    if topic:
        ctx.log("input", Verdict("block", "class_policy", f"Chủ đề bị chặn trong lớp: {topic}", "policy"), text)
        return _blocked(ctx, "input", TOPIC_BLOCKED.format(topic=topic))
    if verdict.action == "redact" and verdict.text is not None:
        ctx.log("input", verdict, verdict.text)
        get_stream_writer()({"type": "notice", "message_id": ctx.message_id, "kind": "redacted", "text": REDACTED})
        return {"text": verdict.text}
    if verdict.action == "support":
        ctx.log("input", verdict, text)
        return {"support": True}
    return {}


def after_screen(state: ChatState) -> str | list[str]:
    return END if state.get("status") == "blocked" else ["classify", "select_agent"]


async def classify(state: ChatState) -> ChatState:
    ctx = state["ctx"]
    if ctx.guard_mode != "full":
        return {}
    started = time.perf_counter()
    verdict, usage = await classifier.classify_input(ctx.chat_model, state["text"], ctx.role)
    ctx.timed("input_guard", usage, started)
    return {"llm_verdict": verdict}


async def select_agent(state: ChatState) -> ChatState:
    ctx = state["ctx"]
    started = time.perf_counter()
    chosen, usage = await route(
        state["text"],
        ctx.agents,
        role=ctx.role,
        requested=state.get("requested_agent"),
        previous=state.get("previous_agent"),
        model=ctx.chat_model,
        mode=ctx.router_mode,
    )
    ctx.timed("router", usage, started)
    return {"agent": chosen.agent, "route_reason": chosen.reason}


async def gate(state: ChatState) -> ChatState:
    ctx = state["ctx"]
    verdict = state.get("llm_verdict")
    update: ChatState = {}
    if verdict is not None and verdict.blocks:
        ctx.log("input", verdict, state["text"])
        return _blocked(ctx, "input", rules.SELF_HARM_REPLY if verdict.category == "self_harm" else INPUT_BLOCKED)
    if verdict is not None and verdict.action == "support" and not state.get("support"):
        ctx.log("input", verdict, state["text"])
        update["support"] = True
    agent = state["agent"]
    get_stream_writer()(
        {
            "type": "agent",
            "message_id": ctx.message_id,
            "agent": agent.slug,
            "name": agent.manifest.name,
            "avatar": agent.manifest.avatar,
            "reason": state.get("route_reason", ""),
        }
    )
    return update


def after_gate(state: ChatState) -> str:
    return END if state.get("status") == "blocked" else "run_agent"


async def run_agent(state: ChatState) -> ChatState:
    ctx = state["ctx"]
    agent = state["agent"]
    write = get_stream_writer()
    system = build_system_prompt(
        agent,
        ctx.room,
        ctx.role,
        ctx.agents,
        platform_rules=ctx.guard_mode != "off",
        safety_note=bool(state.get("support")),
    )
    specs = tools.specs_for(agent.manifest, ctx.role, ctx.room)
    messages = [*state.get("history", []), Message(role="user", content=state["text"])]
    shown = ""
    tool_events: list[dict[str, Any]] = []

    def emit(delta: str) -> None:
        nonlocal shown
        write(
            {
                "type": "text_delta",
                "message_id": ctx.message_id,
                "generation": 0,
                "text_offset": utf16_len(shown),
                "delta": delta,
            }
        )
        shown += delta

    final: Completion | None = None
    for round_index in range(MAX_TOOL_ROUNDS + 1):
        offer = specs if round_index < MAX_TOOL_ROUNDS else None
        started = time.perf_counter()
        try:
            async for event in ctx.chat_model.stream(
                messages, system=system, tools=offer or None, tier="main", max_tokens=4096
            ):
                if isinstance(event, TextDelta):
                    emit(event.text)
                else:
                    final = event
        except LLMError as error:
            return {"reply": shown or str(error), "status": "error", "tool_events": tool_events}
        assert final is not None
        ctx.timed("agent", final.usage, started)
        if final.stop_reason == "refusal":
            if not shown:
                emit("Mình không thể hỗ trợ yêu cầu này.")
            return {"reply": shown, "status": "blocked", "blocked_stage": "model", "tool_events": tool_events}
        if not final.message.tool_calls:
            break
        messages.append(final.message)
        if shown and not shown.endswith("\n"):
            emit("\n\n")
        for call in final.message.tool_calls:
            write({"type": "tool", "message_id": ctx.message_id, "name": call.name, "status": "start"})
            outcome = await tools.execute(call, tools.ToolContext.from_run(ctx, agent))
            ctx.db.add(
                ToolCallLog(
                    conversation_id=ctx.conversation.id,
                    message_id=ctx.message_id,
                    agent_slug=agent.slug,
                    tool=call.name,
                    arguments=call.arguments,
                    result=outcome.content[:20000],
                    is_error=outcome.is_error,
                    denied_reason=outcome.denied,
                    latency_ms=outcome.latency_ms,
                )
            )
            if outcome.denied:
                denial = Verdict("block", "tool_denied", f"{call.name}: {outcome.denied}", "policy")
                ctx.log("tool", denial, state["text"], agent.slug)
            ctx.usage.extend(("tool", usage, 0) for usage in outcome.usage)
            status = "denied" if outcome.denied else ("error" if outcome.is_error else "done")
            tool_events.append({"name": call.name, "status": status})
            write({"type": "tool", "message_id": ctx.message_id, "name": call.name, "status": status})
            messages.append(
                Message(role="tool", content=outcome.content, tool_call_id=call.id, is_error=outcome.is_error)
            )
    return {"reply": shown, "status": "ok", "tool_events": tool_events}


def _replace(ctx: RunContext, text: str) -> None:
    """Retracts the streamed reply and shows `text` instead (chatStream.ts handles text_reset)."""
    write = get_stream_writer()
    write({"type": "text_reset", "message_id": ctx.message_id, "generation": 1})
    write({"type": "text_delta", "message_id": ctx.message_id, "generation": 1, "text_offset": 0, "delta": text})


async def review(state: ChatState) -> ChatState:
    ctx = state["ctx"]
    reply = state.get("reply", "")
    if ctx.guard_mode != "full" or state.get("status") != "ok" or not reply.strip():
        return {}
    agent = state["agent"]
    verdict = rules.screen_output(reply, state["text"])
    if verdict.blocks:
        ctx.log("output", verdict, reply, agent.slug)
        _replace(ctx, OUTPUT_BLOCKED)
        return {"reply": OUTPUT_BLOCKED, "status": "blocked", "blocked_stage": "output"}
    if verdict.action == "redact" and verdict.text is not None:
        ctx.log("output", verdict, verdict.text, agent.slug)
        _replace(ctx, verdict.text)
        reply = verdict.text
    # Teachers get answer keys and full solutions by design; the model review protects students and parents.
    if ctx.role == "teacher":
        return {"reply": reply}
    no_answers = bool((ctx.room.policy or {}).get("no_direct_answers", True)) if ctx.room else False
    started = time.perf_counter()
    verdict, usage = await classifier.review_output(ctx.chat_model, reply, state["text"], ctx.role, no_answers)
    ctx.timed("output_guard", usage, started)
    if verdict.blocks:
        ctx.log("output", verdict, reply, agent.slug)
        replacement = ANSWER_WITHHELD if verdict.category == "academic_integrity" else OUTPUT_BLOCKED
        _replace(ctx, replacement)
        return {"reply": replacement, "status": "blocked", "blocked_stage": "output"}
    if verdict.action == "flag":
        ctx.log("output", verdict, reply, agent.slug)
    return {"reply": reply}


def build_graph():
    graph = StateGraph(ChatState)
    graph.add_node("screen", screen)
    graph.add_node("classify", classify)
    graph.add_node("select_agent", select_agent)
    graph.add_node("gate", gate)
    graph.add_node("run_agent", run_agent)
    graph.add_node("review", review)
    graph.add_edge(START, "screen")
    graph.add_conditional_edges("screen", after_screen, ["classify", "select_agent", END])
    graph.add_edge(["classify", "select_agent"], "gate")
    graph.add_conditional_edges("gate", after_gate, ["run_agent", END])
    graph.add_edge("run_agent", "review")
    graph.add_edge("review", END)
    return graph.compile()


GRAPH = build_graph()
