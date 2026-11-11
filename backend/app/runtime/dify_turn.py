"""The Dify engine: one chat turn through `eduagent-triage` then `eduagent-runner` (contracts/dify-apps.md).

    consent gate ─▶ redact() ─▶ triage (safety + routing) ──block──▶ notice(guard_blocked), done(blocked)
                                     │ allow / support
                                     ▼
                     handle (app/tools/context.py) ─▶ runner stream ─▶ text_delta / text_reset / tool ─▶ done

The platform keeps what is authorization or privacy rather than content guardrails (FR-015): the guardian consent
gate, personal data redaction before anything leaves the platform, and the tool guard behind the MCP handle. Triage
fails closed: if it errors, the runner is never called. Tool events reach the SSE stream through the handle's queue,
which the MCP handler fills while Dify's agent runs.
"""

import asyncio
import json
import logging
import time
import uuid
from collections.abc import AsyncIterator
from contextlib import aclosing
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

import httpx
from sqlalchemy import select

from app import tracing
from app.agents.manifest import FALLBACK_SLUG
from app.agents.service import ResolvedAgent, available_agents
from app.audit.models import GuardEvent
from app.auth.models import User
from app.chat.models import ChatMessage, Conversation
from app.chat.router import record_usage, sse
from app.classes import service as classes
from app.classes.models import ClassRoom
from app.config import get_settings
from app.db import session_factory
from app.guard import dify_rules, rules
from app.llm.base import Usage
from app.runtime.dify_client import DifyClient, DifyConversationNotFound, DifyError, RunnerEvent
from app.runtime.prompts import build_system_prompt
from app.tools import context as handles
from app.tools import registry

if TYPE_CHECKING:
    from app.chat.router import ChatIn

log = logging.getLogger("eduagent.dify")

MAX_SYSTEM_PROMPT = 12000
CONSENT_REQUIRED = (
    "Lớp này cần phụ huynh đồng ý trước khi em dùng agent. Hãy đưa mã liên kết trong mục “Lớp của tôi” cho bố mẹ "
    "và nhờ bố mẹ bật đồng ý nhé."
)
REDACTED = (
    "Mình đã ẩn thông tin cá nhân (số điện thoại, mật khẩu, địa chỉ…) trong tin nhắn trước khi gửi cho agent và "
    "không lưu lại."
)
CONTEXT_RESET = "Agent không còn nhớ ngữ cảnh cũ của cuộc trò chuyện này."
# Dify unreachable, timed out or failed before any text (quickstart scenario 13).
TURN_FAILED = "Hệ thống trợ lý đang bận, em thử lại sau ít phút nhé."
SEVERITY = {"self_harm_method": "high", "self_harm_risk": "high", "dangerous": "high"}


def utf16_len(text: str) -> int:
    return len(text.encode("utf-16-le")) // 2


def make_client() -> DifyClient:
    """A client for one turn; tests replace this with one over httpx.MockTransport."""
    return DifyClient(httpx.AsyncClient())


def roster_of(agents: list[ResolvedAgent]) -> str:
    return json.dumps(
        [
            {
                "slug": agent.slug,
                "name": agent.manifest.name,
                "description": agent.manifest.description,
                "capabilities": list(agent.manifest.capabilities),
                "subjects": list(agent.manifest.subjects),
            }
            for agent in agents
        ],
        ensure_ascii=False,
    )


def pick_agent(agents: list[ResolvedAgent], slug: str) -> ResolvedAgent:
    """Triage's choice if it is one of the agents available here, else the class assistant."""
    by_slug = {agent.slug: agent for agent in agents}
    return by_slug.get(slug) or by_slug.get(FALLBACK_SLUG) or agents[0]


class Turn:
    """What one turn accumulates for the stored message, guard events and usage."""

    def __init__(self, db, user: User, role: str, room: ClassRoom | None, conversation: Conversation, kind: str):
        self.db = db
        self.user = user
        self.role = role
        self.room = room
        self.conversation = conversation
        self.kind = kind
        self.message_id = str(uuid.uuid4())
        self.usage: list[tuple[str, Usage, int]] = []
        self.guard: list[dict[str, str]] = []
        self.trace: tracing.Trace | None = None
        # The class in the database (None in personal chat and in a simulated certification class).
        self.class_id: str | None = room.id if room else None
        # fast | full (feature 002): stored in the message meta, the `done` event and every usage row of the turn.
        self.path = "fast"
        # Set by `_finish`: ok | blocked | error.
        self.final_status = ""

    def log(
        self,
        stage: str,
        verdict: str,
        category: str,
        detector: str,
        reason: str,
        text: str,
        agent_slug: str | None = None,
    ) -> None:
        excerpt, _ = rules.redact(text)
        self.db.add(
            GuardEvent(
                source=self.kind,
                class_id=self.class_id,
                user_id=self.user.id,
                role=self.role,
                conversation_id=self.conversation.id,
                message_id=self.message_id,
                agent_slug=agent_slug,
                stage=stage,
                verdict=verdict,
                category=category,
                detector=detector,
                severity=SEVERITY.get(category, "medium" if verdict == "block" else "low"),
                reason=reason[:300],
                excerpt=excerpt[:300],
            )
        )
        self.guard.append({"stage": stage, "verdict": verdict, "category": category})


async def run_dify_turn(
    user_id: str,
    class_id: str | None,
    role: str,
    payload: "ChatIn",
    *,
    agents_override: list[ResolvedAgent] | None = None,
    kind: str = "chat",
    simulated_room: ClassRoom | None = None,
    force_path: str | None = None,
) -> AsyncIterator[str]:
    """One chat turn on Dify, streamed with the platform's SSE protocol (contracts/chat-sse.md).

    `force_path` ("fast" | "full") is internal, for eval only: it overrides triage's path choice (research R14)."""
    operation_id = str(uuid.uuid4())
    yield sse({"type": "operation", "operation_id": operation_id, "resume_supported": False})
    async with session_factory()() as db:
        user = await db.get(User, user_id)
        # Certification and eval run in an unsaved, simulated class (its policy applies; there is no membership).
        room = await db.get(ClassRoom, class_id) if class_id else simulated_room
        assert user is not None

        # Consent gate (FR-015): without a guardian's consent nothing is sent to Dify and nothing is stored.
        if role == "student" and class_id and not await classes.student_can_use_agents(db, room, user.id):
            yield sse(
                {"type": "notice", "message_id": operation_id, "kind": "consent_required", "text": CONSENT_REQUIRED}
            )
            yield sse({"type": "done", "message_id": operation_id, "status": "consent_required"})
            return

        if payload.conversation_id:
            conversation = await db.get(Conversation, payload.conversation_id)
        else:
            conversation = Conversation(
                user_id=user.id, class_id=class_id, title=payload.message.strip()[:80], kind=kind
            )
            db.add(conversation)
            await db.flush()
        assert conversation is not None
        turn = Turn(db, user, role, room, conversation, kind)
        turn.class_id = class_id  # None for a simulated class: nothing to reference in the database
        turn.message_id = operation_id
        yield sse({"type": "conversation", "conversation_id": conversation.id})

        # Personal data never leaves the platform (FR-016): Dify, the stored message and guard excerpts get the
        # redacted text.
        text, found = rules.redact(payload.message)
        if found:
            turn.log("input", "redact", "pii", "privacy", "Đã ẩn: " + ", ".join(found), text)
            yield sse({"type": "notice", "message_id": turn.message_id, "kind": "redacted", "text": REDACTED})

        previous_agent = await db.scalar(
            select(ChatMessage.agent_slug)
            .where(
                ChatMessage.conversation_id == conversation.id,
                ChatMessage.role == "assistant",
                ChatMessage.agent_slug.is_not(None),
            )
            .order_by(ChatMessage.created_at.desc())
            .limit(1)
        )
        user_message = ChatMessage(conversation_id=conversation.id, role="user", content=text)
        db.add(user_message)
        # Committed before Dify runs: MCP tools use their own sessions, and the question survives a crashed turn.
        await db.commit()

        agents = agents_override or await available_agents(db, user, room, role)
        client = make_client()
        with tracing.start_trace(
            kind,
            user_id=user.id,
            session_id=conversation.id,
            tags=[kind, role, "dify"],
            metadata={"class_id": class_id, "message_id": turn.message_id, "engine": "dify"},
            input=text,
        ) as trace:
            turn.trace = trace
            answer = _answer(turn, client, agents, text, payload, previous_agent, user_message, force_path)
            try:
                async for event in answer:
                    yield event
            finally:
                # Close the inner generator first: when the client went away it still has to call Dify's stop API.
                await answer.aclose()
                await client.http.aclose()


async def _answer(
    turn: Turn,
    client: DifyClient,
    agents: list[ResolvedAgent],
    text: str,
    payload: "ChatIn",
    previous_agent: str | None,
    user_message: ChatMessage,
    force_path: str | None = None,
) -> AsyncIterator[str]:
    message_id = turn.message_id
    started = time.perf_counter()

    if not agents:
        yield sse({"type": "error", "message_id": message_id, "message": "Chưa có agent nào khả dụng."})
        yield sse({"type": "done", "message_id": message_id, "status": "error"})
        return

    # The sandbox tests one draft agent: the roster holds only it, and it is the requested agent.
    requested = payload.agent or (agents[0].slug if len(agents) == 1 else "")
    try:
        triage_started = time.perf_counter()
        with tracing.node(turn.trace, "triage", as_type="chain", input=text) as span:
            triage = await client.run_triage(
                {
                    "query": text,
                    "role": turn.role,
                    "roster": roster_of(agents),
                    "requested_agent": requested if requested in {a.slug for a in agents} else "",
                    "previous_agent": previous_agent or "",
                },
                user=turn.user.id,
            )
            if span is not None:
                span.update(output={"verdict": triage.verdict, "category": triage.category, "agent": triage.agent})
        if triage.usage:
            turn.usage.append(("triage", triage.usage, int((time.perf_counter() - triage_started) * 1000)))
    except DifyError as error:
        # Fail closed: a message nobody screened never reaches the agent.
        log.warning("triage failed: %s", error)
        reply = TURN_FAILED
        yield sse({"type": "error", "message_id": message_id, "message": reply})
        await _store(turn, None, reply, "error", {"error": str(error)[:300]}, started, [])
        yield sse({"type": "done", "message_id": message_id, "status": "error", "agent": None})
        return

    route_reason = triage.route_reason
    if triage.verdict == "block":
        turn.log("input", "block", triage.category, "dify_classifier", triage.reason, text)
        presets = dify_rules.presets()
        reply = presets["self_harm_support" if triage.category == "self_harm_method" else "input_blocked"]
        yield sse({"type": "notice", "message_id": message_id, "kind": "guard_blocked", "text": reply})
        user_message.status = "blocked"
        await _store(turn, None, reply, "blocked", {"blocked_stage": "input"}, started, [])
        yield sse({"type": "done", "message_id": message_id, "status": "blocked", "agent": None})
        return
    support = triage.verdict == "support"
    if support:
        turn.log("input", "support", triage.category, "dify_classifier", triage.reason, text)

    if takes_full_path(turn, triage, force_path):
        from app.orchestrator import conductor  # the orchestrator imports this module

        # The agent the user picked or @mentioned leads the plan (FR-005); triage reports it as ui / mention.
        chosen = triage.agent if triage.route_reason in ("ui", "mention") else ""
        outcome = conductor.FullPath()
        async with aclosing(
            conductor.run_full(turn, client, agents, text, chosen, user_message, started, outcome)
        ) as full:
            async for event in full:
                yield event
        if not outcome.fell_back:
            return

    agent = pick_agent(agents, triage.agent)
    if agent.slug != triage.agent:
        route_reason = "fallback"
    yield agent_event(message_id, agent, route_reason)

    context = tool_context(turn, agent, text)
    system_prompt = build_system_prompt(agent, turn.room, turn.role, agents, safety_note=support)
    result = RunnerResult()
    # aclosing: when the client goes away, the inner stream must stop its Dify task before the HTTP client closes.
    async with aclosing(
        _stream_runner(turn, client, agent, context, system_prompt, text, result, safety_note=support)
    ) as stream:
        async for event in stream:
            yield event
    async with aclosing(
        _finish(turn, client, agent, text, result, context, started, user_message, {"route_reason": route_reason})
    ) as finish:
        async for event in finish:
            yield event


def takes_full_path(turn: Turn, triage, force_path: str | None = None) -> bool:
    """The full path only when every condition of research R2 holds; anything else answers on the fast path.

    Self-harm signals (verdict `support`) and blocked messages never get a plan (FR-038). Certification and the
    sandbox stay on the fast path unless eval forces the full one (research R14). A class can switch it off (FR-046);
    personal space cannot. Without a planner key the feature is off."""
    if triage.verdict != "allow" or not get_settings().dify_planner_key:
        return False
    if force_path is not None:
        return force_path == "full"
    if turn.kind != "chat" or triage.path != "full":
        return False
    if turn.room is not None and (turn.room.policy or {}).get("multi_step", True) is False:
        return False
    return True


def agent_event(message_id: str, agent: ResolvedAgent, reason: str) -> str:
    return sse(
        {
            "type": "agent",
            "message_id": message_id,
            "agent": agent.slug,
            "name": agent.manifest.name,
            "avatar": agent.manifest.avatar,
            "reason": reason,
        }
    )


def tool_context(turn: Turn, agent: ResolvedAgent, excerpt: str, **extra: Any) -> registry.ToolContext:
    """The tool handle's context for one runner call of `agent` in this turn (`mode`, `step_key`… via extra)."""
    return registry.ToolContext(
        user_id=turn.user.id,
        role=turn.role,
        class_id=turn.room.id if turn.room else None,
        grade=turn.room.grade if turn.room else None,
        conversation_id=turn.conversation.id,
        agent_slug=agent.slug,
        allowed_tools=frozenset(agent.manifest.tools),
        log_calls=True,
        message_id=turn.message_id,
        source=turn.kind,
        dataset_id=turn.room.dify_dataset_id if turn.room else None,
        excerpt=excerpt,
        **extra,
    )


@dataclass
class RunnerResult:
    """What one streamed runner call left behind, for `_finish`."""

    text: str = ""
    blocked_stage: str | None = None
    dify_message_id: str | None = None
    error_text: str = ""
    tool_events: list[dict[str, Any]] = field(default_factory=list)


async def _stream_runner(
    turn: Turn,
    client: DifyClient,
    agent: ResolvedAgent,
    context: registry.ToolContext,
    system_prompt: str,
    query: str,
    result: RunnerResult,
    *,
    safety_note: bool = False,
    purpose: str = "agent",
    span: str = "run_agent",
) -> AsyncIterator[str]:
    """Streams one runner call on the conversation's main Dify conversation to the user: `text_delta`,
    `text_reset`, `tool` and `notice(context_reset)`. Used by the fast path and by the full path's synthesis
    (research R8). What happened is left in `result`; usage is booked on the turn under `purpose`.

    When the client goes away mid-stream the Dify task is stopped too (FR-006, FR-040)."""
    message_id = turn.message_id
    out: asyncio.Queue[Any] = asyncio.Queue()
    # The MCP handler puts `tool` events here; the runner pump below puts RunnerEvents in the same queue, so both come
    # out in the order they happened.
    context.events = out
    handle = handles.register(context)
    inputs = {
        "system_prompt": system_prompt[:MAX_SYSTEM_PROMPT],
        "ctx": handle,
        "safety_note": "true" if safety_note else "false",
    }
    task_id = ""
    finished = False

    async def pump() -> None:
        # Runs in its own task without yields, so the span stays current for its whole run.
        with tracing.node(turn.trace, span, as_type="agent", input=query):
            await stream()

    async def stream() -> None:
        conversation_id = turn.conversation.dify_conversation_id or ""
        try:
            try:
                async for event in client.stream_runner(query, inputs, conversation_id, turn.user.id):
                    await out.put(event)
            except DifyConversationNotFound:
                # Dify lost the conversation (rebuilt or data deleted): start a new one and say so (research R5).
                await out.put("context_reset")
                async for event in client.stream_runner(query, inputs, "", turn.user.id):
                    await out.put(event)
        except DifyError as error:
            await out.put(RunnerEvent("error", text=str(error)))
        finally:
            await out.put(None)

    runner_started = time.perf_counter()
    task = asyncio.create_task(pump())
    shown = ""
    generation = 0
    try:
        while True:
            item = await out.get()
            if item is None:
                break
            if isinstance(item, dict):  # a tool event from the MCP handler
                result.tool_events.append({"name": item["name"], "status": item["status"]})
                yield sse(item)
                continue
            if item == "context_reset":
                yield sse({"type": "notice", "message_id": message_id, "kind": "context_reset", "text": CONTEXT_RESET})
                continue
            event: RunnerEvent = item
            if event.kind == "start":
                task_id = event.task_id
                if event.conversation_id and event.conversation_id != turn.conversation.dify_conversation_id:
                    turn.conversation.dify_conversation_id = event.conversation_id
            elif event.kind == "delta":
                yield sse(
                    {
                        "type": "text_delta",
                        "message_id": message_id,
                        "generation": generation,
                        "text_offset": utf16_len(shown),
                        "delta": event.text,
                    }
                )
                shown += event.text
            elif event.kind == "replace":
                # The runner's output moderation replaced the streamed answer.
                turn.log(
                    "output", "block", "moderation", "dify_moderation", "Kiểm duyệt đầu ra của Dify", shown, agent.slug
                )
                generation = 1
                shown = event.text
                result.blocked_stage = "output"
                yield sse({"type": "text_reset", "message_id": message_id, "generation": generation})
                yield sse(
                    {
                        "type": "text_delta",
                        "message_id": message_id,
                        "generation": generation,
                        "text_offset": 0,
                        "delta": shown,
                    }
                )
            elif event.kind == "end":
                result.dify_message_id = event.message_id or None
                if event.conversation_id:
                    turn.conversation.dify_conversation_id = event.conversation_id
                if event.usage:
                    turn.usage.append((purpose, event.usage, int((time.perf_counter() - runner_started) * 1000)))
            elif event.kind == "error":
                result.error_text = event.text
        finished = True
    finally:
        result.text = shown
        if not finished:
            # The client went away (or the turn was cancelled): stop Dify's run too (FR-006).
            task.cancel()
            if task_id:
                try:
                    await asyncio.wait_for(client.stop(task_id, turn.user.id), timeout=5)
                except Exception as error:  # best effort
                    log.warning("could not stop Dify task %s: %s", task_id, error)
        handles.release(handle)


async def _finish(
    turn: Turn,
    client: DifyClient,
    agent: ResolvedAgent,
    question: str,
    result: RunnerResult,
    context: registry.ToolContext,
    started: float,
    user_message: ChatMessage,
    meta_extra: dict[str, Any],
    done_extra: dict[str, Any] | None = None,
) -> AsyncIterator[str]:
    """After the streamed answer: status, the policy review, sources, follow-up questions, the stored message and
    `done` (FR-030). The same for a fast-path answer and a full-path synthesis."""
    message_id = turn.message_id
    shown = result.text
    reply = shown
    blocked_stage = result.blocked_stage
    if result.error_text:
        log.warning("runner failed: %s", result.error_text)
        status = "error"
        if not shown:
            reply = TURN_FAILED
            yield sse({"type": "error", "message_id": message_id, "message": reply})
    elif blocked_stage == "output":
        status = "blocked"
    elif dify_rules.is_preset_input_block(shown):
        # The runner's own input moderation answered with its preset refusal.
        turn.log("input", "block", "moderation", "dify_moderation", "Kiểm duyệt đầu vào của Dify", question)
        status, blocked_stage = "blocked", "input"
        user_message.status = "blocked"
    else:
        status = "ok"
    if status == "ok" and shown.strip():
        verdict = await _review(client, turn, question, shown)
        if verdict is not None:
            # Retract the streamed answer, as the old engine's output guard did.
            turn.log("output", "block", verdict.category, "dify_review", verdict.reason, shown, agent.slug)
            presets = dify_rules.presets()
            shown = presets["answer_withheld" if verdict.category == "academic_integrity" else "output_blocked"]
            reply = shown
            status, blocked_stage = "blocked", "output"
            yield sse({"type": "text_reset", "message_id": message_id, "generation": 1})
            yield sse(
                {"type": "text_delta", "message_id": message_id, "generation": 1, "text_offset": 0, "delta": shown}
            )
    extras: dict[str, Any] = {}
    if status == "ok":
        # Sources and follow-up questions only for an answer that stands (not blocked, not replaced).
        if context.citations:
            extras["citations"] = context.citations
            yield sse({"type": "citations", "message_id": message_id, "items": context.citations})
        suggestions = await _suggestions(client, result.dify_message_id, turn.user.id)
        if suggestions:
            extras["suggestions"] = suggestions
            yield sse({"type": "suggestions", "message_id": message_id, "items": suggestions})
    meta = {
        "dify_message_id": result.dify_message_id,
        "path": turn.path,
        **meta_extra,
        "tools": result.tool_events,
        **extras,
        **({"blocked_stage": blocked_stage} if blocked_stage else {}),
        **({"error": result.error_text[:300]} if result.error_text else {}),
    }
    if turn.trace is not None:
        turn.trace.update(
            output=reply,
            level={"blocked": "WARNING", "error": "ERROR"}.get(status),
            metadata={
                "status": status,
                "agent": agent.slug,
                "path": turn.path,
                "dify_message_id": result.dify_message_id,
                "dify_conversation_id": turn.conversation.dify_conversation_id,
            },
        )
    turn.final_status = status
    await _store(turn, agent, reply, status, meta, started, context.usage)
    yield sse(
        {
            "type": "done",
            "message_id": message_id,
            "status": status,
            "agent": agent.slug,
            "path": turn.path,
            **(done_extra or {}),
        }
    )


MAX_SUGGESTIONS = 3


async def _review(client: DifyClient, turn: Turn, question: str, answer: str):
    """eduagent-review for students and parents (teachers get answer keys by design). Returns the blocking verdict, or
    None to keep the answer; a failed review keeps it too, as the old engine did (the runner's keyword moderation
    already ran)."""
    if turn.role == "teacher" or not client.settings.dify_review_key:
        return None
    no_answers = bool((turn.room.policy or {}).get("no_direct_answers", True)) if turn.room else False
    started = time.perf_counter()
    try:
        with tracing.node(turn.trace, "review", as_type="guardrail", input=answer[:2000]):
            result = await client.run_review(
                {
                    "question": question[:4000],
                    "reply": answer[:12000],
                    "role": turn.role,
                    "no_direct_answers": "true" if no_answers and turn.role == "student" else "false",
                },
                user=turn.user.id,
            )
    except DifyError as error:
        log.warning("review failed, answer kept: %s", error)
        return None
    if result.usage:
        turn.usage.append(("output_guard", result.usage, int((time.perf_counter() - started) * 1000)))
    return result if result.verdict == "block" else None


async def _suggestions(client: DifyClient, dify_message_id: str | None, user_id: str) -> list[str]:
    """Dify's follow-up questions, filtered with the runner's own keyword moderation (FR-022). Failures are skipped."""
    if not dify_message_id:
        return []
    try:
        questions = await client.get_suggested(dify_message_id, user_id)
    except (DifyError, httpx.HTTPError) as error:
        log.info("no suggested questions: %s", error)
        return []
    kept = [q.strip()[:200] for q in questions if q.strip() and not dify_rules.contains_blocked_keyword(q)]
    return kept[:MAX_SUGGESTIONS]


async def _store(
    turn: Turn,
    agent: ResolvedAgent | None,
    reply: str,
    status: str,
    meta: dict[str, Any],
    started: float,
    tool_usage: list[tuple[str, Usage]],
) -> None:
    turn.db.add(
        ChatMessage(
            id=turn.message_id,
            conversation_id=turn.conversation.id,
            role="assistant",
            content=reply,
            agent_slug=agent.slug if agent else None,
            agent_version_id=agent.version_id if agent else None,
            status=status,
            meta={
                "engine": "dify",
                **meta,
                "guard": turn.guard,
                "latency_ms": int((time.perf_counter() - started) * 1000),
            },
        )
    )
    turn.conversation.updated_at = datetime.now(UTC)
    usage = turn.usage + [(purpose, item, 0) for purpose, item in tool_usage]
    record_usage(turn.db, turn.user.id, turn.class_id, turn.conversation.id, usage, path=turn.path)
    turn.usage = []  # booked; a turn that stores twice (a paused run) does not count it again
    await turn.db.commit()
