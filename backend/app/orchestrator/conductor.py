"""The full path of a chat turn (specs/002-multi-agent-orchestration research R1, R8, R10).

    step(analyze) ─▶ planner ─▶ plan ─▶ step(sN running/done…)* ─▶ step(synthesis) ─▶ agent(lead) ─▶ text ─▶ done
         └── no usable plan ─▶ step(analyze, skipped), the caller answers on the fast path (FR-006)

The backend keeps the state (turn_runs, run_steps) and the limits; every model call still runs on Dify. The
synthesis streams through the fast path's own code (`_stream_runner`, `_finish`), so review, sources, follow-up
questions and storage behave the same (FR-030).
"""

import asyncio
import logging
import time
from collections.abc import AsyncIterator, Awaitable
from contextlib import aclosing
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import select, update

from app import tracing
from app.agents.service import ResolvedAgent
from app.chat.models import ChatMessage
from app.chat.router import sse
from app.config import get_settings
from app.orchestrator import planner as planning
from app.orchestrator.models import OPEN_STATUSES, RunStep, TurnRun
from app.orchestrator.prompts import build_synthesis_prompt, build_synthesis_query
from app.orchestrator.steps import StepOutcome, apply_outcome, run_step
from app.runtime.dify_client import DifyClient
from app.runtime.prompts import build_system_prompt

if TYPE_CHECKING:
    from app.runtime.dify_turn import Turn

log = logging.getLogger("eduagent.orchestrator")

ALL_STEPS_FAILED = "Các agent chưa làm được yêu cầu này. Em thử lại sau ít phút hoặc hỏi ngắn gọn hơn nhé."


class FullPath:
    """Outcome of `run_full` for the caller: `fell_back` means nothing was answered and the fast path should."""

    def __init__(self) -> None:
        self.fell_back = False
        self.run_id: str | None = None


def agent_ref(agent: ResolvedAgent) -> dict[str, str]:
    return {"slug": agent.slug, "name": agent.manifest.name, "avatar": agent.manifest.avatar}


def step_event(message_id: str, key: str, status: str, **extra: Any) -> str:
    return sse({"type": "step", "message_id": message_id, "key": key, "status": status, **extra})


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


async def _pump(task: "asyncio.Task[Any]", queue: "asyncio.Queue[Any]") -> AsyncIterator[dict[str, Any]]:
    """Yields what the task's tools put on `queue` while the task runs, then whatever is left."""
    getter: asyncio.Task[Any] | None = None
    try:
        while not task.done():
            getter = asyncio.ensure_future(queue.get())
            await asyncio.wait({task, getter}, return_when=asyncio.FIRST_COMPLETED)
            if getter.done():
                yield getter.result()
            else:
                getter.cancel()
            getter = None
        while not queue.empty():
            yield queue.get_nowait()
    finally:
        if getter is not None and not getter.done():
            getter.cancel()


async def _drive(
    work: Awaitable[Any], queue: "asyncio.Queue[Any]", tool_events: dict[str, list[dict[str, str]]]
) -> AsyncIterator[Any]:
    """Runs `work` in its own task and streams its tool events as SSE; the task's result comes last (as a tuple).
    Closing the generator cancels the task (FR-040)."""
    task = asyncio.ensure_future(work)
    try:
        async for item in _pump(task, queue):
            if isinstance(item, dict) and item.get("type") == "tool":
                tool_events.setdefault(item.get("step_key") or "", []).append(
                    {"name": item["name"], "status": item["status"]}
                )
                yield sse(item)
        yield ("result", task.result())
    finally:
        if not task.done():
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass


async def _close_stale_runs(turn: "Turn") -> None:
    """A run left open by a crashed turn would block the one-open-run-per-conversation index."""
    await turn.db.execute(
        update(TurnRun)
        .where(TurnRun.conversation_id == turn.conversation.id, TurnRun.status.in_(OPEN_STATUSES))
        .values(status="cancelled", pending=None, expires_at=None)
    )


async def run_full(
    turn: "Turn",
    client: DifyClient,
    agents: list[ResolvedAgent],
    text: str,
    requested_agent: str,
    user_message: ChatMessage,
    started: float,
    outcome: FullPath,
) -> AsyncIterator[str]:
    """One full-path turn, run straight through. Yields SSE events; sets `outcome.fell_back` when the planner gave
    nothing usable, in which case it has emitted only `step(analyze)` events and stored nothing."""
    from app.runtime.dify_turn import (  # runtime imports the orchestrator
        RunnerResult,
        _finish,
        _store,
        _stream_runner,
        agent_event,
        tool_context,
    )

    settings = get_settings()
    message_id = turn.message_id
    by_slug = {agent.slug: agent for agent in agents}
    interactive = turn.kind == "chat"

    # SC-006: the panel gets its first update as soon as triage is done, before the planner runs.
    yield step_event(message_id, "analyze", "running", title="Phân tích yêu cầu")
    planner_started = time.perf_counter()
    with tracing.node(turn.trace, "plan", as_type="chain", input=text) as span:
        plan, usage = await planning.plan_request(
            client,
            user_id=turn.user.id,
            query=text,
            role=turn.role,
            agents=agents,
            requested_agent=requested_agent,
            history=await _history(turn, user_message),
            interactive=interactive,
            # Pausing for questions comes with clarifying questions (User Story 1); until then, assume.
            can_ask=False,
            limits=planning.Limits.from_settings(settings),
        )
        if span is not None:
            span.update(output=plan.as_dict() if plan else None)
    if usage:
        turn.usage.append(("planner", usage, int((time.perf_counter() - planner_started) * 1000)))
    if plan is None:
        outcome.fell_back = True
        yield step_event(message_id, "analyze", "skipped")
        return

    turn.path = "full"
    lead = by_slug[plan.lead]
    await _close_stale_runs(turn)
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
        assumptions=list(plan.assumptions),
        interactive=interactive,
    )
    turn.db.add(run)
    await turn.db.flush()
    outcome.run_id = run.id
    rows: list[RunStep] = []
    for item in plan.steps:
        agent = by_slug[item["agent"]]
        row = RunStep(
            run_id=run.id,
            key=item["key"],
            agent_slug=agent.slug,
            agent_version_id=agent.version_id,
            title=item["title"],
            task=item["task"],
            depends_on=list(item["depends_on"]),
            origin="plan",
            status="pending",
        )
        rows.append(row)
        turn.db.add(row)
    await turn.db.commit()

    yield step_event(message_id, "analyze", "done", duration_ms=int((time.perf_counter() - planner_started) * 1000))
    yield sse(
        {
            "type": "plan",
            "message_id": message_id,
            "run_id": run.id,
            "goal": plan.goal,
            "lead": agent_ref(lead),
            "steps": [
                {
                    "key": row.key,
                    "title": row.title,
                    "agent": agent_ref(by_slug[row.agent_slug]),
                    "depends_on": row.depends_on,
                    "status": row.status,
                }
                for row in rows
            ],
            "resumed": False,
        }
    )

    # Steps one after another, in plan order (already dependency-ordered); parallel layers come with User Story 2.
    queue: asyncio.Queue[Any] = asyncio.Queue()
    task_ids: set[str] = set()
    tool_events: dict[str, list[dict[str, str]]] = {}
    deadline = started + settings.orch_deadline_s
    by_key = {row.key: row for row in rows}
    for row in rows:
        agent = by_slug[row.agent_slug]
        if time.perf_counter() >= deadline:
            row.status = "skipped"
            row.finished_at = datetime.now(UTC)
            yield step_event(message_id, row.key, "skipped", title=row.title, agent=agent_ref(agent))
            continue
        row.status = "running"
        row.started_at = datetime.now(UTC)
        yield step_event(message_id, row.key, "running", title=row.title, agent=agent_ref(agent))
        dependency_notes = [
            (by_key[key].title, by_key[key].note if by_key[key].status == "done" else "") for key in row.depends_on
        ]
        work = run_step(
            turn,
            client,
            agent,
            agents,
            row,
            goal=plan.goal,
            request=text,
            dependency_notes=dependency_notes,
            events=queue,
            task_ids=task_ids,
            timeout_s=min(settings.orch_step_timeout_s, max(1.0, deadline - time.perf_counter())),
        )
        result: StepOutcome | None = None
        async with aclosing(_drive(work, queue, tool_events)) as stream:
            async for item in stream:
                if isinstance(item, tuple):
                    result = item[1]
                else:
                    yield item
        assert result is not None
        apply_outcome(row, result, tool_events.get(row.key, []))
        yield step_event(
            message_id, row.key, row.status, title=row.title, agent=agent_ref(agent), duration_ms=result.duration_ms
        )
    await turn.db.commit()

    if not any(row.status == "done" for row in rows):
        # Nothing to build on: a friendly error, never a half answer.
        yield sse({"type": "error", "message_id": message_id, "message": ALL_STEPS_FAILED})
        run.status = "error"
        run.reply_message_id = message_id
        meta = {"path": "full", "run_id": run.id, "error": "all steps failed"}
        await _store(turn, lead, ALL_STEPS_FAILED, "error", meta, started, [])
        yield sse({"type": "done", "message_id": message_id, "status": "error", "agent": lead.slug, "path": "full"})
        return

    # Synthesis: the lead writes the one answer the user reads, on the main conversation (research R8).
    yield step_event(message_id, "synthesis", "running", title="Tổng hợp kết quả", agent=agent_ref(lead))
    yield agent_event(message_id, lead, "plan")
    context = tool_context(turn, lead, text, mode="synthesis")
    for row in rows:
        for citation in row.citations or []:
            if citation not in context.citations:
                context.citations.append(citation)
    notes = [
        {"title": row.title, "agent": by_slug[row.agent_slug].manifest.name, "status": row.status, "note": row.note}
        for row in rows
    ]
    system_prompt = build_synthesis_prompt(
        build_system_prompt(lead, turn.room, turn.role, agents),
        notes,
        assumptions=run.assumptions,
        confirmations=run.confirmations,
    )
    query = build_synthesis_query(text, run.resume_answers)
    result = RunnerResult()
    async with aclosing(
        _stream_runner(turn, client, lead, context, system_prompt, query, result, purpose="synthesis", span="synthesis")
    ) as stream:
        async for event in stream:
            yield event
    meta = {
        "route_reason": "plan",
        "run_id": run.id,
        **({"assumptions": run.assumptions} if run.assumptions else {}),
    }
    async with aclosing(_finish(turn, client, lead, text, result, context, started, user_message, meta)) as finish:
        async for event in finish:
            yield event
    run.status = "error" if turn.final_status == "error" and not result.text else "done"
    run.reply_message_id = message_id
    await turn.db.commit()
