"""The full path of a chat turn (specs/002-multi-agent-orchestration research R1, R7, R8, R10).

    step(analyze) ─▶ planner ─▶ plan ─▶ step(sN running/done…)* ─▶ step(synthesis) ─▶ agent(lead) ─▶ text ─▶ done
         │                        └── missing information ─▶ ask ─▶ done(awaiting_user)      (the run waits)
         └── no usable plan ─▶ step(analyze, skipped), the caller answers on the fast path (FR-006)

    next request with a waiting run ─▶ resume(): planner(resume) ─▶ plan(resumed) ─▶ steps ─▶ synthesis ─▶ done
                                     └── a different request ─▶ notice(pending_cancelled), handled as a new one

The backend keeps the state (turn_runs, run_steps) and the limits; every model call still runs on Dify. The
synthesis streams through the fast path's own code (`_stream_runner`, `_finish`), so review, sources, follow-up
questions and storage behave the same (FR-030).
"""

import asyncio
import json
import logging
import time
from collections.abc import AsyncIterator
from contextlib import aclosing
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

from sqlalchemy import delete, select, update

from app import tracing
from app.agents.service import ResolvedAgent
from app.chat.models import ChatMessage
from app.chat.router import sse
from app.config import get_settings
from app.guard import rules
from app.orchestrator import planner as planning
from app.orchestrator.models import OPEN_STATUSES, RunStep, TurnRun
from app.orchestrator.prompts import build_synthesis_prompt, build_synthesis_query
from app.orchestrator.steps import agent_ref, ref_of, run_plan, step_event
from app.runtime.dify_client import DifyClient
from app.runtime.prompts import build_system_prompt

if TYPE_CHECKING:
    from app.chat.router import ReplyIn
    from app.runtime.dify_turn import Turn

log = logging.getLogger("eduagent.orchestrator")

ALL_STEPS_FAILED = "Các agent chưa làm được yêu cầu này. Em thử lại sau ít phút hoặc hỏi ngắn gọn hơn nhé."
ASK_CLARIFY = "Để làm đúng ý, mình cần hỏi thêm một chút:"
ASK_ACTION = "Cần bạn xác nhận trước khi mình thực hiện:"
ASK_INTERPRETATION = "Mình hiểu yêu cầu như sau, đúng không?"
INTERPRETATION_REJECTED = "Mình chưa làm gì cả. Hãy nói rõ lại yêu cầu để mình làm đúng ý nhé."
PENDING_EXPIRED = "Câu hỏi trước đã hết hạn, mình xử lý tin nhắn này như yêu cầu mới."
PENDING_CANCELLED = "Mình bỏ câu hỏi đang chờ và xử lý tin nhắn này như yêu cầu mới."
SKIPPED_QUESTION = "Chưa rõ “{question}”, mình chọn phương án hợp lý nhất."


class FullPath:
    """Outcome of `run_full` for the caller: `fell_back` means nothing was answered and the fast path should."""

    def __init__(self) -> None:
        self.fell_back = False
        self.run_id: str | None = None


@dataclass
class Resumed:
    """Outcome of `resume` for the caller: `new_request` means the waiting run was closed and the message is a new
    request, to be answered as usual."""

    new_request: bool = False


_ref = ref_of


def contributors_of(rows: list[RunStep], lead: str, by_slug: dict[str, ResolvedAgent]) -> list[dict[str, str]]:
    """The agents with a finished step, other than the lead, in plan order (FR-029). Shown by the UI, not written by
    a model."""
    slugs = dict.fromkeys(row.agent_slug for row in rows if row.status == "done" and row.agent_slug != lead)
    return [ref_of(slug, by_slug) for slug in slugs]


def process_of(rows: list[RunStep], lead: ResolvedAgent, started: float) -> dict[str, Any]:
    """`meta.process`: what the collapsed progress panel shows after a reload (FR-035)."""
    return {
        "duration_ms": int((time.perf_counter() - started) * 1000),
        "agents": len({row.agent_slug for row in rows} | {lead.slug}),
        "steps": [{"key": row.key, "title": row.title, "agent": row.agent_slug, "status": row.status} for row in rows],
    }


def notice_event(message_id: str, kind: str, text: str) -> str:
    return sse({"type": "notice", "message_id": message_id, "kind": kind, "text": text})


def _now() -> datetime:
    return datetime.now(UTC)


def _aware(value: datetime | None) -> datetime | None:
    # SQLite gives naive datetimes back.
    return value.replace(tzinfo=UTC) if value is not None and value.tzinfo is None else value


# --- Run state ------------------------------------------------------------------------------------------------------


async def waiting_run(db, conversation_id: str) -> TurnRun | None:
    """The run of this conversation that waits for the user, if any (at most one, research R7)."""
    return await db.scalar(
        select(TurnRun).where(TurnRun.conversation_id == conversation_id, TurnRun.status == "awaiting_user")
    )


def is_expired(run: TurnRun) -> bool:
    expires = _aware(run.expires_at)
    return expires is not None and expires <= _now()


async def close_pending(
    db, run: TurnRun, status: str, state: str, answers: dict[str, str] | None = None
) -> None:
    """Leaves awaiting_user in any direction: `pending` and `expires_at` are cleared and the question message records
    what became of it (`meta.ask.state`), so the card shows it and cannot be used again (FR-036). A tool confirmation
    that ends any other way than "Đồng ý" is recorded as not done, for the synthesis (FR-018)."""
    pending = run.pending or {}
    confirm = pending.get("confirm") or {}
    if pending.get("kind") == "confirm" and confirm.get("source") == "tool" and state != "approved":
        reason = {"rejected": "user_rejected"}.get(state, state)
        run.confirmations = [
            *(run.confirmations or []),
            {
                "tool": confirm.get("tool"),
                "args": confirm.get("args"),
                "summary": confirm.get("summary", ""),
                "decision": "reject" if state == "rejected" else state,
                "result": {"done": False, "reason": reason},
                "executed_at": None,
                "result_ref": None,
            },
        ]
    ask_id = pending.get("ask_message_id")
    if ask_id:
        message = await db.get(ChatMessage, ask_id)
        if message is not None:
            ask = {**((message.meta or {}).get("ask") or {}), "state": state}
            if answers is not None:
                ask["answers"] = answers
            message.meta = {**(message.meta or {}), "ask": ask}
    run.pending = None
    run.expires_at = None
    run.status = status


async def cancel_open_runs(db, conversation_id: str) -> None:
    """Every open run of the conversation is cancelled (consent withdrawn, blocked reply…)."""
    for run in await db.scalars(
        select(TurnRun).where(TurnRun.conversation_id == conversation_id, TurnRun.status.in_(OPEN_STATUSES))
    ):
        await close_pending(db, run, "cancelled", "cancelled")


async def _close_stale_runs(turn: "Turn") -> None:
    """A run left `running` by a crashed or abandoned turn would block the one-open-run-per-conversation index. A
    waiting run is never closed here: it is resumed or cancelled with a notice before a new run starts (R7)."""
    await turn.db.execute(
        update(TurnRun)
        .where(TurnRun.conversation_id == turn.conversation.id, TurnRun.status == "running")
        .values(status="cancelled", pending=None, expires_at=None)
    )


def _mark_handled(run: TurnRun, key: str) -> None:
    """A signal (`<step key>:<index>`) the orchestrator acted on; it is not acted on again after a resume."""
    plan = dict(run.plan or {})
    plan["handled"] = [*plan.get("handled", []), key]
    run.plan = plan


def _next_signal(run: TurnRun, rows: list[RunStep], kinds: tuple[str, ...]) -> tuple[str, RunStep, dict] | None:
    """The first signal of the given types not handled yet, in plan order. Only a step's first signal of each type
    counts (contracts/mcp-tools.md); a tool call held for confirmation is one signal per call."""
    handled = set((run.plan or {}).get("handled", []))
    for row in rows:
        seen: set[str] = set()
        for index, signal in enumerate(row.signals or []):
            kind = signal.get("type", "")
            first = kind == "confirm_tool" or kind not in seen
            seen.add(kind)
            key = f"{row.key}:{index}"
            if first and key not in handled and kind in kinds:
                return key, row, signal
    return None


def _signal_questions(signal: dict[str, Any], limit: int) -> list[dict[str, Any]]:
    """ask_user's questions in the card's shape (ids, at most `limit` questions and 6 options of 60 characters)."""
    return planning._questions(signal.get("questions"), limit)


def _new_rows(run: TurnRun, items: list[dict[str, Any]], by_slug: dict[str, ResolvedAgent]) -> list[RunStep]:
    rows = []
    for item in items:
        agent = by_slug[item["agent"]]
        rows.append(
            RunStep(
                run_id=run.id,
                key=item["key"],
                agent_slug=agent.slug,
                agent_version_id=agent.version_id,
                title=item["title"],
                task=item["task"],
                depends_on=list(item["depends_on"]),
                origin=item.get("origin", "plan"),
                requested_by=item.get("requested_by"),
                status="pending",
            )
        )
    return rows


async def _rows(db, run: TurnRun) -> list[RunStep]:
    rows = list(await db.scalars(select(RunStep).where(RunStep.run_id == run.id)))
    order = {key: index for index, key in enumerate(step["key"] for step in (run.plan or {}).get("steps", []))}
    return sorted(rows, key=lambda row: (order.get(row.key, len(order)), row.key))


def _plan_event(
    message_id: str, run: TurnRun, rows: list[RunStep], by_slug: dict[str, ResolvedAgent], resumed: bool
) -> str:
    return sse(
        {
            "type": "plan",
            "message_id": message_id,
            "run_id": run.id,
            "goal": run.goal,
            "lead": _ref(run.lead_agent or "", by_slug),
            "steps": [
                {
                    "key": row.key,
                    "title": row.title,
                    "agent": _ref(row.agent_slug, by_slug),
                    "depends_on": row.depends_on,
                    "status": row.status,
                }
                for row in rows
            ],
            "resumed": resumed,
        }
    )


async def _history(turn: "Turn", before: ChatMessage) -> str:
    rows = await turn.db.execute(
        select(ChatMessage.role, ChatMessage.content)
        .where(
            ChatMessage.conversation_id == turn.conversation.id,
            ChatMessage.id != before.id,
            ChatMessage.status.not_in(("blocked",)),
        )
        .order_by(ChatMessage.created_at.desc())
        .limit(planning.HISTORY_MESSAGES)
    )
    return planning.format_history([(role, content) for role, content in reversed(rows.all())])


async def _plan(turn: "Turn", client: DifyClient, agents: list[ResolvedAgent], text: str, **kwargs: Any):
    """eduagent-planner under a `plan` span; the usage is booked on the turn."""
    started = time.perf_counter()
    with tracing.node(turn.trace, "plan", as_type="chain", input=text) as span:
        plan, usage = await planning.plan_request(
            client,
            user_id=turn.user.id,
            query=text,
            role=turn.role,
            agents=agents,
            limits=planning.Limits.from_settings(get_settings()),
            **kwargs,
        )
        if span is not None:
            span.update(output=plan.as_dict() if plan else None)
    if usage:
        turn.usage.append(("planner", usage, int((time.perf_counter() - started) * 1000)))
    return plan


def _not_done(signal: dict[str, Any], reason: str) -> dict[str, Any]:
    decision = "reject" if reason in ("no_person", "user_rejected") else reason
    return {
        "tool": signal.get("tool"),
        "args": signal.get("args") or {},
        "summary": signal.get("summary", ""),
        "decision": decision,
        "result": {"done": False, "reason": reason},
        "executed_at": None,
        "result_ref": None,
    }


def _merge(existing: list[str], extra: list[str]) -> list[str]:
    return list(dict.fromkeys([*existing, *extra]))


async def _stop_all(client: DifyClient, task_ids: set[str], user_id: str) -> None:
    """Best effort: stops every Dify task still listed for the run (FR-040)."""
    for task_id in list(task_ids):
        try:
            await asyncio.wait_for(client.stop(task_id, user_id), timeout=5)
        except Exception as error:
            log.warning("could not stop Dify task %s: %s", task_id, error)


# --- Start ----------------------------------------------------------------------------------------------------------


async def run_full(
    turn: "Turn",
    client: DifyClient,
    agents: list[ResolvedAgent],
    text: str,
    requested_agent: str,
    user_message: ChatMessage,
    started: float,
    outcome: FullPath,
    *,
    interactive: bool = True,
) -> AsyncIterator[str]:
    """A new full-path request. Yields SSE events; sets `outcome.fell_back` when the planner gave nothing usable, in
    which case it has emitted only `step(analyze)` events and stored nothing.

    `interactive=False` (certification, sandbox, eval) means nobody can answer, so the run never pauses (FR-041)."""
    settings = get_settings()
    message_id = turn.message_id
    by_slug = {agent.slug: agent for agent in agents}

    # SC-006: the panel gets its first update as soon as triage is done, before the planner runs.
    yield step_event(message_id, "analyze", "running", title="Phân tích yêu cầu")
    planner_started = time.perf_counter()
    plan = await _plan(
        turn,
        client,
        agents,
        text,
        requested_agent=requested_agent,
        history=await _history(turn, user_message),
        interactive=interactive,
        can_ask=interactive and settings.orch_max_clarify_rounds > 0,
    )
    if plan is None:
        outcome.fell_back = True
        yield step_event(message_id, "analyze", "skipped")
        return

    turn.path = "full"
    lead = by_slug[plan.lead]
    await _close_stale_runs(turn)
    assumptions = list(plan.assumptions)
    if plan.missing and plan.confirm_interpretation:
        # Only the questions are asked; the interpretation becomes an assumption (research R7).
        assumptions.append(plan.confirm_interpretation)
    run = TurnRun(
        conversation_id=turn.conversation.id,
        user_id=turn.user.id,
        class_id=turn.class_id,
        status="running",
        request_message_id=user_message.id,
        request_text=text,
        lead_agent=lead.slug,
        goal=plan.goal,
        plan=plan.as_dict(),
        assumptions=assumptions,
        resume_answers=[],
        confirmations=[],
        interactive=interactive,
    )
    turn.db.add(run)
    await turn.db.flush()
    outcome.run_id = run.id
    rows = _new_rows(run, plan.steps, by_slug)
    turn.db.add_all(rows)
    await turn.db.commit()

    yield step_event(message_id, "analyze", "done", duration_ms=int((time.perf_counter() - planner_started) * 1000))
    yield _plan_event(message_id, run, rows, by_slug, resumed=False)

    if plan.missing or plan.confirm_interpretation:
        async with aclosing(
            pause_for_clarify(
                turn, run, lead, started, questions=plan.missing, interpretation=plan.confirm_interpretation
            )
        ) as paused:
            async for event in paused:
                yield event
        return

    async with aclosing(_execute(turn, client, agents, run, rows, started, user_message)) as stream:
        async for event in stream:
            yield event


async def confirmation_run(
    turn: "Turn",
    agent: ResolvedAgent,
    text: str,
    user_message: ChatMessage,
    signal: dict[str, Any],
    *,
    interactive: bool,
) -> TurnRun:
    """A run with no steps for a fast-path turn whose agent called a tool that needs confirmation (research R6). The
    caller then pauses on it; without a person (certification) the action is recorded as not done right away."""
    turn.path = "full"
    await _close_stale_runs(turn)
    run = TurnRun(
        conversation_id=turn.conversation.id,
        user_id=turn.user.id,
        class_id=turn.class_id,
        status="running" if interactive else "done",
        request_message_id=user_message.id,
        reply_message_id=None if interactive else turn.message_id,
        request_text=text,
        lead_agent=agent.slug,
        goal="",
        plan={"steps": [], "handled": ["fast:0"]},
        assumptions=[],
        resume_answers=[],
        confirmations=[] if interactive else [_not_done(signal, "no_person")],
        interactive=interactive,
    )
    turn.db.add(run)
    await turn.db.flush()
    return run


# --- Pause ----------------------------------------------------------------------------------------------------------


async def pause_for_clarify(
    turn: "Turn",
    run: TurnRun,
    lead: ResolvedAgent,
    started: float,
    *,
    questions: list[dict[str, Any]] | None = None,
    interpretation: str = "",
    step_key: str | None = None,
) -> AsyncIterator[str]:
    """Stops the run to ask: the questions (`kind="clarify"`), or, without questions, whether the request was
    understood right (`kind="confirm"`, `source="interpretation"`, FR-017). Both count as the turn's clarify round
    (FR-008). The question is an assistant message `awaiting_user` whose `meta.ask` rebuilds the card on reload."""
    from app.runtime.dify_turn import _store  # runtime imports the orchestrator

    settings = get_settings()
    message_id = turn.message_id
    if questions:
        intro = ASK_CLARIFY
        ask: dict[str, Any] = {"kind": "clarify", "questions": questions, "skippable": True}
        pending: dict[str, Any] = {"kind": "clarify", "questions": questions}
        content = intro + "\n" + "\n".join(f"{i}. {q['question']}" for i, q in enumerate(questions, 1))
    else:
        intro = ASK_INTERPRETATION
        confirm = {
            "tool": "",
            "agent": lead.slug,
            "args": {},
            "summary": interpretation,
            "impact": "",
            "source": "interpretation",
            "preview": {},
            "audience_count": None,
        }
        shown = {key: confirm[key] for key in ("tool", "summary", "impact", "audience_count", "preview")}
        ask = {"kind": "confirm", "confirm": shown, "skippable": False}
        pending = {"kind": "confirm", "confirm": confirm}
        content = intro + "\n" + interpretation
    run.pending = {**pending, "ask_message_id": message_id, "step_key": step_key}
    run.status = "awaiting_user"
    run.clarify_rounds += 1
    run.expires_at = _now() + timedelta(hours=settings.orch_pending_ttl_h)
    head = {"run_id": run.id, "agent": agent_ref(lead), "intro": intro}
    yield sse({"type": "ask", "message_id": message_id, **head, **ask})
    turn.path = "full"
    await _store(
        turn, lead, content, "awaiting_user", {"path": "full", "run_id": run.id, "ask": {**head, **ask, "state": "open"}},
        started, [],
    )
    yield sse({"type": "done", "message_id": message_id, "status": "awaiting_user", "agent": lead.slug, "path": "full"})


async def pause_for_confirm(
    turn: "Turn",
    run: TurnRun,
    lead: ResolvedAgent,
    started: float,
    signal: dict[str, Any],
    *,
    step_key: str | None = None,
) -> AsyncIterator[str]:
    """Stops the run before a tool that acts outside the conversation (FR-014, research R6): the card shows the exact
    preview built from the arguments (FR-048). Confirming an action is not a clarify round (FR-016)."""
    from app.runtime.dify_turn import _store  # runtime imports the orchestrator

    settings = get_settings()
    message_id = turn.message_id
    confirm = {
        "tool": signal["tool"],
        "agent": signal.get("agent") or lead.slug,
        "args": signal.get("args") or {},
        "summary": signal.get("summary", ""),
        "impact": signal.get("impact", ""),
        "source": "tool",
        "preview": signal.get("preview") or {},
        "audience_count": signal.get("audience_count"),
    }
    shown = {key: confirm[key] for key in ("tool", "summary", "impact", "audience_count", "preview")}
    ask = {"kind": "confirm", "confirm": shown, "skippable": False}
    run.pending = {"kind": "confirm", "confirm": confirm, "ask_message_id": message_id, "step_key": step_key}
    run.status = "awaiting_user"
    run.expires_at = _now() + timedelta(hours=settings.orch_pending_ttl_h)
    head = {"run_id": run.id, "agent": agent_ref(lead), "intro": ASK_ACTION}
    yield sse({"type": "ask", "message_id": message_id, **head, **ask})
    turn.path = "full"
    content = f"{ASK_ACTION}\n{confirm['summary']}"
    meta = {"path": "full", "run_id": run.id, "ask": {**head, **ask, "state": "open"}}
    await _store(turn, lead, content, "awaiting_user", meta, started, [])
    yield sse({"type": "done", "message_id": message_id, "status": "awaiting_user", "agent": lead.slug, "path": "full"})


async def apply_decision(
    turn: "Turn", run: TurnRun, decision: str
) -> AsyncIterator[str]:
    """The user's answer to a tool confirmation (research R18, FR-050). "Đồng ý" runs the tool once, with the stored
    arguments, from the backend: the run row is locked, the decision recorded and `pending` cleared and committed
    BEFORE the tool runs, so a repeated or concurrent approval finds nothing to approve. Permissions are checked again
    and the tool context is rebuilt (the turn's handle may have expired long ago). Yields `tool` events; False is
    put in `outcome` when there was nothing left to decide."""
    from app.tools import actions, registry

    pending = run.pending or {}
    confirm = dict(pending.get("confirm") or {})
    if decision != "approve":
        await close_pending(turn.db, run, "running", "rejected")
        await turn.db.commit()
        return

    locked = await turn.db.scalar(
        select(TurnRun).where(TurnRun.id == run.id).with_for_update().execution_options(populate_existing=True)
    )
    if locked is None or locked.status != "awaiting_user" or (locked.pending or {}).get("kind") != "confirm":
        return  # already decided by another request
    await close_pending(turn.db, run, "running", "approved")
    entry: dict[str, Any] = {
        "tool": confirm.get("tool"),
        "args": confirm.get("args") or {},
        "summary": confirm.get("summary", ""),
        "decision": "approve",
        "result": None,
        "executed_at": None,
        "result_ref": None,
    }
    run.confirmations = [*(run.confirmations or []), entry]
    await turn.db.commit()

    name = str(confirm.get("tool") or "")
    room = turn.room if turn.room is not None and turn.room.id == run.class_id else None
    if room is None and run.class_id:
        from app.classes.models import ClassRoom

        room = await turn.db.get(ClassRoom, run.class_id)
    queue: asyncio.Queue[Any] = asyncio.Queue()
    context = registry.ToolContext(
        user_id=run.user_id,
        role=turn.role,
        class_id=run.class_id,
        grade=room.grade if room else None,
        conversation_id=run.conversation_id,
        agent_slug=str(confirm.get("agent") or run.lead_agent or ""),
        allowed_tools=frozenset({name}),
        log_calls=True,
        message_id=turn.message_id,
        source="chat",
        dataset_id=room.dify_dataset_id if room else None,
        excerpt=run.request_text,
        events=queue,
        mode="synthesis",
        run_id=run.id,
    )
    result: dict[str, Any]
    result_ref: str | None = None
    executed_at: str | None = None
    denied = registry.deny_reason(name, context)
    if denied is None and name in actions.TEACHER_TOOLS and not await actions.is_class_teacher(
        run.user_id, run.class_id
    ):
        denied = registry.NOT_CLASS_TEACHER
    if denied:
        # Rights changed while the question waited: nothing runs.
        result = {"done": False, "reason": "permission", "detail": denied}
    else:
        registry._emit(context, name, "start")
        started = time.perf_counter()
        try:
            args = registry.TOOLS[name].args.model_validate(entry["args"])
            data = await registry.IMPLEMENTATIONS[name](context, args)
        except Exception as error:  # a failed action is reported, never retried silently
            log.warning("confirmed tool %s failed: %s", name, error)
            message = str(error) if isinstance(error, (registry.impl.ToolFailure,)) else type(error).__name__
            result = {"done": False, "reason": "failed", "detail": message[:300]}
            registry._emit(context, name, "error")
            await registry._log_call(
                context, name, entry["args"], json.dumps(result, ensure_ascii=False), is_error=True,
                latency_ms=int((time.perf_counter() - started) * 1000),
            )
        else:
            result = {"done": True, **{k: v for k, v in data.items() if k in ("summary", "link")}}
            result_ref = data.get("result_ref") or data.get("target")
            executed_at = _now().isoformat()
            registry._emit(context, name, "done")
            await registry._log_call(
                context, name, entry["args"], json.dumps(data, ensure_ascii=False, default=str),
                latency_ms=int((time.perf_counter() - started) * 1000),
            )
    # A new dict: the JSON column only notices a new value, not a change inside the stored one.
    done = {**entry, "result": result, "result_ref": result_ref, "executed_at": executed_at}
    run.confirmations = [*run.confirmations[:-1], done]
    await turn.db.commit()
    while not queue.empty():
        yield sse(queue.get_nowait())


# --- Resume ---------------------------------------------------------------------------------------------------------


async def resume(
    turn: "Turn",
    client: DifyClient,
    agents: list[ResolvedAgent],
    run: TurnRun,
    text: str,
    reply: "ReplyIn | None",
    user_message: ChatMessage,
    started: float,
    outcome: Resumed,
) -> AsyncIterator[str]:
    """A message arrived while `run` waits (research R7). An answer through the card always continues the run (FR-009,
    FR-011); a message typed in the chat box continues it only if the planner reads it as the answer, otherwise the
    run is cancelled and `outcome.new_request` tells the caller to handle the message as a new request (FR-012).
    Steps already done are kept."""
    from app.runtime.dify_turn import _store, pick_agent  # runtime imports the orchestrator

    settings = get_settings()
    message_id = turn.message_id
    by_slug = {agent.slug: agent for agent in agents}
    pending = run.pending or {}
    through_card = reply is not None and reply.run_id == run.id
    turn.path = "full"

    async def give_up() -> AsyncIterator[str]:
        await close_pending(turn.db, run, "cancelled", "cancelled")
        await turn.db.commit()
        outcome.new_request = True
        yield notice_event(message_id, "pending_cancelled", PENDING_CANCELLED)

    if through_card:
        user_message.meta = {
            **(user_message.meta or {}),
            "reply_to": {"run_id": run.id, "ask_message_id": pending.get("ask_message_id")},
        }

    if pending.get("kind") == "confirm":
        if not through_card or reply.decision is None:
            # Typing something else while a confirmation waits is a no, without asking a model (R7).
            async for event in give_up():
                yield event
            return
        if (pending.get("confirm") or {}).get("source") == "tool":
            # An action: run it (once) or not, then finish the run; the synthesis says what happened (FR-018).
            async with aclosing(apply_decision(turn, run, reply.decision)) as decided:
                async for event in decided:
                    yield event
            if run.status != "running":
                outcome.new_request = True  # decided already, by an earlier request
                return
            rows = await _rows(turn.db, run)
            if rows:
                yield _plan_event(message_id, run, rows, by_slug, resumed=True)
            async with aclosing(_execute(turn, client, agents, run, rows, started, user_message)) as stream:
                async for event in stream:
                    yield event
            return
        if reply.decision == "reject":
            await close_pending(turn.db, run, "cancelled", "rejected")
            lead = by_slug.get(run.lead_agent or "") or pick_agent(agents, "")
            yield sse({"type": "text_delta", "message_id": message_id, "generation": 0, "text_offset": 0,
                       "delta": INTERPRETATION_REJECTED})
            await _store(turn, lead, INTERPRETATION_REJECTED, "ok", {"path": "full", "run_id": run.id}, started, [])
            yield sse({"type": "done", "message_id": message_id, "status": "ok", "agent": lead.slug, "path": "full"})
            return
        summary = (pending.get("confirm") or {}).get("summary", "")
        await close_pending(turn.db, run, "running", "approved")
        run.resume_answers = [*run.resume_answers, {"question": "Cách hiểu yêu cầu", "answer": f"{summary} (đã xác nhận)"}]
        await turn.db.commit()
        rows = await _rows(turn.db, run)
        yield _plan_event(message_id, run, rows, by_slug, resumed=True)
        async with aclosing(_execute(turn, client, agents, run, rows, started, user_message)) as stream:
            async for event in stream:
                yield event
        return

    # Clarifying questions.
    questions = pending.get("questions") or []
    answers: dict[str, str] = {}
    if through_card:
        ids = {q["id"] for q in questions}
        for qid, value in reply.answers.items():
            if qid in ids and value.strip():
                answers[qid] = rules.redact(value.strip())[0]
    skipped = through_card and (reply.skip_all or not answers)
    existing = await _rows(turn.db, run)
    done_rows = [row for row in existing if row.status == "done"]
    can_ask = run.interactive and run.clarify_rounds < settings.orch_max_clarify_rounds
    plan = await _plan(
        turn,
        client,
        agents,
        run.request_text,
        requested_agent="",
        history=await _history(turn, user_message),
        resume={
            "goal": run.goal,
            "questions": [{"question": q["question"], "answer": answers.get(q["id"], "")} for q in questions],
            "skipped": skipped,
            "done_steps": [{"key": r.key, "agent": r.agent_slug, "title": r.title} for r in done_rows],
            "new_message": "" if through_card else text,
        },
        interactive=run.interactive,
        can_ask=can_ask,
    )
    if not through_card and (plan is None or not plan.answers_pending):
        async for event in give_up():
            yield event
        return
    if plan is None:
        # The planner failed on an answer given through the card: go on with the plan it made before, checked
        # against the agents available now.
        plan = planning.validate_plan(
            run.plan,
            agents,
            interactive=run.interactive,
            can_ask=False,
            limits=planning.Limits.from_settings(settings),
            fallback_goal=run.goal,
        )
        if plan is None:
            async for event in give_up():
                yield event
            return

    if through_card:
        answered = [{"question": q["question"], "answer": answers[q["id"]]} for q in questions if q["id"] in answers]
        unanswered = [SKIPPED_QUESTION.format(question=q["question"]) for q in questions if q["id"] not in answers]
    else:
        answered = [{"question": " / ".join(q["question"] for q in questions), "answer": text}]
        unanswered = []
    await close_pending(turn.db, run, "running", "skipped" if skipped else "answered", answers if through_card else None)
    run.resume_answers = [*run.resume_answers, *answered]
    run.assumptions = _merge(run.assumptions, [*unanswered, *plan.assumptions])
    run.goal = plan.goal or run.goal
    run.lead_agent = plan.lead
    run.plan = {**plan.as_dict(), "handled": (run.plan or {}).get("handled", [])}

    # The steps not done yet are replaced by the new plan's; done steps stay as they are (FR-011).
    done_keys = {row.key for row in done_rows}
    await turn.db.execute(delete(RunStep).where(RunStep.run_id == run.id, RunStep.status != "done"))
    await turn.db.flush()
    new_rows = _new_rows(run, [step for step in plan.steps if step["key"] not in done_keys], by_slug)
    turn.db.add_all(new_rows)
    await turn.db.commit()
    rows = await _rows(turn.db, run)
    yield _plan_event(message_id, run, rows, by_slug, resumed=True)

    if plan.missing or plan.confirm_interpretation:
        # Only with more than one clarify round allowed per turn.
        async with aclosing(
            pause_for_clarify(
                turn, run, by_slug[plan.lead], started, questions=plan.missing,
                interpretation=plan.confirm_interpretation,
            )
        ) as paused:
            async for event in paused:
                yield event
        return

    async with aclosing(_execute(turn, client, agents, run, rows, started, user_message)) as stream:
        async for event in stream:
            yield event


# --- Steps and synthesis --------------------------------------------------------------------------------------------


async def _execute(
    turn: "Turn",
    client: DifyClient,
    agents: list[ResolvedAgent],
    run: TurnRun,
    rows: list[RunStep],
    started: float,
    user_message: ChatMessage,
) -> AsyncIterator[str]:
    """Runs the steps not done yet, then the synthesis, and closes the run (done or error). When the client goes away
    the running steps are cancelled, every Dify task of the run is stopped and the run is `cancelled` (FR-040)."""
    task_ids: set[str] = set()
    finished = False
    try:
        async with aclosing(
            _steps_and_synthesis(turn, client, agents, run, rows, started, user_message, task_ids)
        ) as stream:
            async for event in stream:
                yield event
        finished = True
    finally:
        if not finished:
            await _stop_all(client, task_ids, turn.user.id)
            run.status = "cancelled"
            try:
                await turn.db.commit()
            except Exception as error:  # the session may be unusable while the request is torn down
                log.warning("could not mark run %s cancelled: %s", run.id, error)


async def _steps_and_synthesis(
    turn: "Turn",
    client: DifyClient,
    agents: list[ResolvedAgent],
    run: TurnRun,
    rows: list[RunStep],
    started: float,
    user_message: ChatMessage,
    task_ids: set[str],
) -> AsyncIterator[str]:
    from app.runtime.dify_turn import (  # runtime imports the orchestrator
        RunnerResult,
        _finish,
        _store,
        _stream_runner,
        agent_event,
        tool_context,
    )

    message_id = turn.message_id
    by_slug = {agent.slug: agent for agent in agents}
    lead = by_slug.get(run.lead_agent or "")
    assert lead is not None, "the plan's lead comes from the roster"
    text = run.request_text

    async with aclosing(
        run_plan(
            turn,
            client,
            agents,
            rows,
            goal=run.goal,
            request=text,
            started=started,
            task_ids=task_ids,
            run=run,
            # A replan (request_help) shows the new steps in the panel (contracts/chat-sse.md `plan`).
            plan_event=lambda: _plan_event(message_id, run, rows, by_slug, resumed=False),
        )
    ) as steps:
        async for event in steps:
            yield event
    await turn.db.commit()

    # What the agents asked for while working (research R5, R6): an action to confirm, an interpretation to check.
    settings = get_settings()
    kinds = ("confirm_tool", "request_confirmation", "ask_user")
    while (found := _next_signal(run, rows, kinds)) is not None:
        key, row, signal = found
        _mark_handled(run, key)
        if signal["type"] == "confirm_tool":
            if run.interactive:
                async with aclosing(pause_for_confirm(turn, run, lead, started, signal, step_key=row.key)) as paused:
                    async for event in paused:
                        yield event
                return
            # Nobody to confirm (certification, eval): always a no (FR-041).
            run.confirmations = [*(run.confirmations or []), _not_done(signal, "no_person")]
        elif signal["type"] == "ask_user":
            questions = _signal_questions(signal, settings.orch_max_questions)
            if run.interactive and run.clarify_rounds < settings.orch_max_clarify_rounds and questions:
                async with aclosing(
                    pause_for_clarify(turn, run, lead, started, questions=questions, step_key=row.key)
                ) as paused:
                    async for event in paused:
                        yield event
                return
            # No question left this turn: decide and say so (FR-007).
            run.assumptions = _merge(run.assumptions, [SKIPPED_QUESTION.format(question=q["question"]) for q in questions])
        elif run.interactive and run.clarify_rounds < settings.orch_max_clarify_rounds:
            async with aclosing(
                pause_for_clarify(turn, run, lead, started, interpretation=signal["summary"], step_key=row.key)
            ) as paused:
                async for event in paused:
                    yield event
            return
        else:
            run.assumptions = _merge(run.assumptions, [signal["summary"]])
    await turn.db.commit()

    if rows and not any(row.status == "done" for row in rows):
        # Nothing to build on: a friendly error, never a half answer.
        yield sse({"type": "error", "message_id": message_id, "message": ALL_STEPS_FAILED})
        run.status = "error"
        run.reply_message_id = message_id
        meta = {"path": "full", "run_id": run.id, "error": "all steps failed", "process": process_of(rows, lead, started)}
        await _store(turn, lead, ALL_STEPS_FAILED, "error", meta, started, [])
        yield sse({"type": "done", "message_id": message_id, "status": "error", "agent": lead.slug, "path": "full"})
        return

    # Synthesis: the lead writes the one answer the user reads, on the main conversation (research R8).
    yield step_event(message_id, "synthesis", "running", title="Tổng hợp kết quả", agent=agent_ref(lead))
    yield agent_event(message_id, lead, "plan")
    query = build_synthesis_query(text, run.resume_answers)
    context = tool_context(turn, lead, text, mode="synthesis")
    for row in rows:
        for citation in row.citations or []:
            if citation not in context.citations:
                context.citations.append(citation)
    notes = [
        {"title": row.title, "agent": _ref(row.agent_slug, by_slug)["name"], "status": row.status, "note": row.note}
        for row in rows
    ]
    system_prompt = build_synthesis_prompt(
        build_system_prompt(lead, turn.room, turn.role, agents),
        notes,
        assumptions=run.assumptions,
        confirmations=run.confirmations,
    )
    result = RunnerResult()
    async with aclosing(
        _stream_runner(turn, client, lead, context, system_prompt, query, result, purpose="synthesis", span="synthesis")
    ) as stream:
        async for event in stream:
            yield event
    contributors = contributors_of(rows, lead.slug, by_slug)
    meta = {
        "route_reason": "plan",
        "run_id": run.id,
        "contributors": contributors,
        "process": process_of(rows, lead, started),
        **({"assumptions": run.assumptions} if run.assumptions else {}),
    }
    async with aclosing(
        _finish(
            turn, client, lead, query, result, context, started, user_message, meta,
            done_extra={"contributors": contributors},
        )
    ) as finish:
        async for event in finish:
            yield event
    run.status = "error" if turn.final_status == "error" and not result.text else "done"
    run.reply_message_id = message_id
    await turn.db.commit()
