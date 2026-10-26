"""The per-message runtime as a LangGraph graph.

    select_agent -> run_agent -> END

Week 7 replaces `select_agent`'s fallback with an LLM router; week 8 adds input and output guards around
`run_agent`. Nodes stream UI events through LangGraph's custom stream writer, which the chat endpoint relays as SSE.
"""

import re
import time
from dataclasses import dataclass, field
from typing import Any, TypedDict

from langgraph.config import get_stream_writer
from langgraph.graph import END, START, StateGraph
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.manifest import FALLBACK_SLUG
from app.agents.service import ResolvedAgent
from app.auth.models import User
from app.chat.models import Conversation, ToolCallLog
from app.classes.models import ClassRoom
from app.llm.base import ChatModel, Completion, LLMError, Message, TextDelta, Usage
from app.runtime.prompts import build_system_prompt
from app.tools import registry as tools

MAX_TOOL_ROUNDS = 4
MENTION = re.compile(r"(?<![\w@])@([a-z0-9]+(?:-[a-z0-9]+)*)")


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
    usage: list[tuple[str, Usage, int]] = field(default_factory=list)


class ChatState(TypedDict, total=False):
    ctx: RunContext
    text: str
    requested_agent: str | None
    history: list[Message]
    agent: ResolvedAgent
    route_reason: str
    reply: str
    status: str
    tool_events: list[dict[str, Any]]


def utf16_len(text: str) -> int:
    return len(text.encode("utf-16-le")) // 2


def find_mention(text: str, agents: list[ResolvedAgent]) -> ResolvedAgent | None:
    by_slug = {agent.slug: agent for agent in agents}
    for slug in MENTION.findall(text):
        if slug in by_slug:
            return by_slug[slug]
    return None


async def select_agent(state: ChatState) -> ChatState:
    ctx = state["ctx"]
    by_slug = {agent.slug: agent for agent in ctx.agents}
    agent = None
    reason = ""
    requested = state.get("requested_agent")
    if requested and requested in by_slug:
        agent, reason = by_slug[requested], "chosen"
    if agent is None:
        mentioned = find_mention(state["text"], ctx.agents)
        if mentioned:
            agent, reason = mentioned, "mention"
    if agent is None:
        agent, reason = by_slug.get(FALLBACK_SLUG) or ctx.agents[0], "fallback"
    get_stream_writer()(
        {
            "type": "agent",
            "message_id": ctx.message_id,
            "agent": agent.slug,
            "name": agent.manifest.name,
            "avatar": agent.manifest.avatar,
            "reason": reason,
        }
    )
    return {"agent": agent, "route_reason": reason}


async def run_agent(state: ChatState) -> ChatState:
    ctx = state["ctx"]
    agent = state["agent"]
    write = get_stream_writer()
    system = build_system_prompt(agent, ctx.room, ctx.role, ctx.agents)
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
        ctx.usage.append(("agent", final.usage, int((time.perf_counter() - started) * 1000)))
        if final.stop_reason == "refusal":
            notice = "Mình không thể hỗ trợ yêu cầu này."
            if not shown:
                emit(notice)
            return {"reply": shown, "status": "blocked", "tool_events": tool_events}
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
            ctx.usage.extend(("tool", usage, 0) for usage in outcome.usage)
            status = "denied" if outcome.denied else ("error" if outcome.is_error else "done")
            tool_events.append({"name": call.name, "status": status})
            write({"type": "tool", "message_id": ctx.message_id, "name": call.name, "status": status})
            messages.append(
                Message(role="tool", content=outcome.content, tool_call_id=call.id, is_error=outcome.is_error)
            )
    return {"reply": shown, "status": "ok", "tool_events": tool_events}


def build_graph():
    graph = StateGraph(ChatState)
    graph.add_node("select_agent", select_agent)
    graph.add_node("run_agent", run_agent)
    graph.add_edge(START, "select_agent")
    graph.add_edge("select_agent", "run_agent")
    graph.add_edge("run_agent", END)
    return graph.compile()


GRAPH = build_graph()
