"""Runs the steps of a plan (specs/002-multi-agent-orchestration research R4).

Each step is one eduagent-runner call on a fresh Dify conversation (`conversation_id=""`), with the step agent's own
system prompt, tools and permissions plus the STEP_MODE block (FR-020, FR-021). The stream is read to the end as the
step's working note and never shown to the user (FR-022); the step's `tool` events still reach the progress panel.
"""

import asyncio
import logging
import re
import time
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from app import tracing
from app.agents.service import ResolvedAgent
from app.chat.router import sse
from app.guard import dify_rules
from app.orchestrator.models import RunStep, TurnRun
from app.orchestrator.prompts import NOTE_MAX, STEP_MODE, build_step_query
from app.runtime.dify_client import DifyClient, DifyError
from app.runtime.prompts import build_system_prompt
from app.tools import context as handles

if TYPE_CHECKING:
    from app.runtime.dify_turn import Turn

log = logging.getLogger("eduagent.orchestrator")

STEP_TIMEOUT = "Phần việc quá thời gian."
STEP_FAILED = "Phần việc gặp lỗi."


@dataclass
class StepOutcome:
    status: str  # done · error · blocked
    note: str = ""
    error: str | None = None
    citations: list[dict[str, Any]] = field(default_factory=list)
    tools: list[dict[str, str]] = field(default_factory=list)
    signals: list[dict[str, Any]] = field(default_factory=list)
    duration_ms: int = 0


async def run_step(
    turn: "Turn",
    client: DifyClient,
    agent: ResolvedAgent,
    agents: list[ResolvedAgent],
    step: RunStep,
    *,
    goal: str,
    request: str,
    dependency_notes: list[tuple[str, str]],
    events: "asyncio.Queue[Any] | None",
    task_ids: set[str],
    timeout_s: float,
) -> StepOutcome:
    """One step, start to finish. Never raises for a Dify failure or a timeout: those come back as `error`, and a
    note replaced by moderation as `blocked` with a guard event naming the step's agent (FR-026, FR-043).

    `task_ids` is shared by the run: the Dify task of a running step is in it, so a cancelled run can stop it."""
    from app.runtime.dify_turn import MAX_SYSTEM_PROMPT, tool_context  # runtime imports the orchestrator

    started = time.perf_counter()
    context = tool_context(
        turn,
        agent,
        request,
        mode="step",
        step_key=step.key,
        may_request_help=step.origin == "plan",
    )
    context.events = events
    handle = handles.register(context)
    system_prompt = build_system_prompt(agent, turn.room, turn.role, agents) + "\n\n" + STEP_MODE
    inputs = {"system_prompt": system_prompt[:MAX_SYSTEM_PROMPT], "ctx": handle, "safety_note": "false"}
    query = build_step_query(goal, {"task": step.task}, dependency_notes, request)
    note = ""
    replaced = False
    error = ""
    task_id = ""
    outcome = StepOutcome(status="error")

    async def read() -> None:
        nonlocal note, replaced, error, task_id
        async for event in client.stream_runner(query, inputs, "", turn.user.id):
            if event.kind == "start":
                task_id = event.task_id
                task_ids.add(task_id)
            elif event.kind == "delta":
                note += event.text
            elif event.kind == "replace":
                note, replaced = event.text, True
            elif event.kind == "end" and event.usage:
                turn.usage.append(("step", event.usage, int((time.perf_counter() - started) * 1000)))
            elif event.kind == "error":
                error = event.text

    try:
        with tracing.node(turn.trace, f"step:{step.key}", as_type="agent", input=query):
            async with asyncio.timeout(timeout_s):
                await read()
    except TimeoutError:
        error = STEP_TIMEOUT
        await _stop(client, task_id, turn.user.id)
    except DifyError as failure:
        error = str(failure) or STEP_FAILED
    except asyncio.CancelledError:
        await _stop(client, task_id, turn.user.id)
        raise
    finally:
        task_ids.discard(task_id)
        handles.release(handle)
        outcome.duration_ms = int((time.perf_counter() - started) * 1000)
        outcome.citations = list(context.citations)
        outcome.signals = list(context.signals)
        turn.usage.extend((purpose, item, 0) for purpose, item in context.usage)

    if replaced or (note and dify_rules.is_preset_input_block(note)):
        # The runner's moderation stood in for the note: the step did not produce usable work.
        reason = "Kiểm duyệt của Dify thay ghi chú của phần việc"
        turn.log("step", "block", "moderation", "dify_moderation", reason, note or request, agent.slug)
        outcome.status, outcome.note = "blocked", ""
    elif error and not note.strip():
        log.warning("step %s (%s) failed: %s", step.key, agent.slug, error)
        outcome.status, outcome.error = "error", error[:300]
    else:
        # Text that arrived before a mid-stream error is still a usable note.
        outcome.status, outcome.note = "done", note.strip()[:NOTE_MAX]
        if error:
            outcome.error = error[:300]
    return outcome


async def _stop(client: DifyClient, task_id: str, user_id: str) -> None:
    if not task_id:
        return
    try:
        await asyncio.wait_for(client.stop(task_id, user_id), timeout=5)
    except Exception as error:  # best effort
        log.warning("could not stop Dify task %s: %s", task_id, error)


def agent_ref(agent: ResolvedAgent) -> dict[str, str]:
    return {"slug": agent.slug, "name": agent.manifest.name, "avatar": agent.manifest.avatar}


def ref_of(slug: str, by_slug: dict[str, ResolvedAgent]) -> dict[str, str]:
    """An agent of the run that may no longer be available here (uninstalled while the run waited)."""
    agent = by_slug.get(slug)
    return agent_ref(agent) if agent else {"slug": slug, "name": slug, "avatar": ""}


def step_event(message_id: str, key: str, status: str, **extra: Any) -> str:
    return sse({"type": "step", "message_id": message_id, "key": key, "status": status, **extra})


def _layer(pending: list[RunStep], by_key: dict[str, RunStep]) -> list[RunStep]:
    """The pending steps whose dependencies have all finished, whatever their outcome (FR-026)."""
    ready = [
        row
        for row in pending
        if all(by_key[dep].status not in ("pending", "running") for dep in row.depends_on if dep in by_key)
    ]
    return ready or list(pending)  # the plan has no cycle; this only guards against a broken row


async def run_plan(
    turn: "Turn",
    client: DifyClient,
    agents: list[ResolvedAgent],
    rows: list[RunStep],
    *,
    goal: str,
    request: str,
    started: float,
    task_ids: set[str],
    run: TurnRun | None = None,
    plan_event: Callable[[], str] | None = None,
) -> AsyncIterator[str]:
    """Runs the pending steps as a DAG, layer by layer: the steps of one layer run at the same time, each with its own
    tool context (FR-019). A step whose dependency failed still runs, told that part has no result (FR-026). Past
    `orch_deadline_s` the remaining steps are skipped (FR-025).

    Yields `step` and `tool{step_key}` SSE events as they happen. Closing the generator (the client left) cancels the
    running steps, which stop their Dify tasks (FR-040)."""
    from app.config import get_settings

    settings = get_settings()
    message_id = turn.message_id
    by_slug = {agent.slug: agent for agent in agents}
    by_key = {row.key: row for row in rows}
    deadline = started + settings.orch_deadline_s
    pending = [row for row in rows if row.status == "pending"]

    def skip(row: RunStep) -> str:
        row.status = "skipped"
        row.finished_at = datetime.now(UTC)
        return step_event(message_id, row.key, "skipped", title=row.title, agent=ref_of(row.agent_slug, by_slug))

    while pending:
        layer = _layer(pending, by_key)
        pending = [row for row in pending if row not in layer]
        remaining = deadline - time.perf_counter()
        if remaining <= 0:
            for row in [*layer, *pending]:
                yield skip(row)
            return
        runnable: list[tuple[RunStep, ResolvedAgent]] = []
        for row in layer:
            agent = by_slug.get(row.agent_slug)
            if agent is None:
                yield skip(row)
            else:
                runnable.append((row, agent))
        if not runnable:
            continue

        queue: asyncio.Queue[Any] = asyncio.Queue()
        tool_events: dict[str, list[dict[str, str]]] = {}
        timeout_s = min(settings.orch_step_timeout_s, max(1.0, remaining))

        async def one(row: RunStep, agent: ResolvedAgent, queue: asyncio.Queue[Any], timeout_s: float) -> None:
            dependency_notes = [
                (by_key[key].title, by_key[key].note if by_key[key].status == "done" else "")
                for key in row.depends_on
                if key in by_key
            ]
            try:
                outcome = await run_step(
                    turn,
                    client,
                    agent,
                    agents,
                    row,
                    goal=goal,
                    request=request,
                    dependency_notes=dependency_notes,
                    events=queue,
                    task_ids=task_ids,
                    timeout_s=timeout_s,
                )
            except Exception as error:  # a bug in one step must not stall the others
                log.exception("step %s crashed", row.key)
                outcome = StepOutcome(status="error", error=str(error)[:300] or STEP_FAILED)
            # After the step's own tool events, so the panel gets them in order.
            await queue.put(("finished", row, agent, outcome))

        for row, _ in runnable:
            row.status = "running"
            row.started_at = datetime.now(UTC)
        # Started before the first yield: a client that leaves right after `running` still has them stopped.
        tasks = [asyncio.create_task(one(row, agent, queue, timeout_s)) for row, agent in runnable]
        try:
            for row, agent in runnable:
                yield step_event(message_id, row.key, "running", title=row.title, agent=agent_ref(agent))
            left = len(tasks)
            while left:
                item = await queue.get()
                if isinstance(item, tuple):
                    _, row, agent, outcome = item
                    apply_outcome(row, outcome, tool_events.get(row.key, []))
                    left -= 1
                    yield step_event(
                        message_id,
                        row.key,
                        row.status,
                        title=row.title,
                        agent=agent_ref(agent),
                        duration_ms=outcome.duration_ms,
                    )
                    if run is not None:
                        # request_help (research R5): a step for the agent that can do it, then this step again.
                        added = help_steps(run, rows, row, agents, settings)
                        if added:
                            for new in added:
                                turn.db.add(new)
                                rows.append(new)
                                by_key[new.key] = new
                            pending.extend(added)
                            if plan_event is not None:
                                yield plan_event()
                elif isinstance(item, dict) and item.get("type") == "tool":
                    tool_events.setdefault(item.get("step_key") or "", []).append(
                        {"name": item["name"], "status": item["status"]}
                    )
                    yield sse(item)
        finally:
            running = [task for task in tasks if not task.done()]
            for task in running:
                task.cancel()
            if running:
                await asyncio.gather(*running, return_exceptions=True)


def apply_outcome(step: RunStep, outcome: StepOutcome, tool_events: list[dict[str, str]]) -> None:
    """Writes a finished step's outcome on its row."""
    step.status = outcome.status
    step.note = outcome.note
    step.error = outcome.error
    step.citations = outcome.citations
    step.signals = outcome.signals
    step.tools = tool_events
    step.finished_at = datetime.now(UTC)


# --- request_help (User Story 5, research R5) ------------------------------------------------------------------------

OUT_OF_REACH = "Việc “{task}” nằm ngoài khả năng của các agent trong lớp."
RERUN_TASK = "{task}\n\nLàm lại phần này, dùng thêm kết quả của phần “{helper}” vừa được nhờ."
_WORD = re.compile(r"\w+", re.UNICODE)


def _words(text: str) -> set[str]:
    return {word for word in _WORD.findall(text.lower()) if len(word) > 2}


def pick_helper(task: str, slug: str, agents: list[ResolvedAgent], exclude: str) -> ResolvedAgent | None:
    """The agent named by the step if it is available here (FR-039), else the one whose name, description,
    capabilities and subjects share most words with the task; None when nothing matches."""
    by_slug = {agent.slug: agent for agent in agents}
    if slug in by_slug and slug != exclude:
        return by_slug[slug]
    wanted = _words(task)
    best, score = None, 0
    for agent in agents:
        if agent.slug == exclude:
            continue
        manifest = agent.manifest
        known = _words(" ".join([manifest.name, manifest.description, *manifest.capabilities, *manifest.subjects]))
        overlap = len(wanted & known)
        if overlap > score:
            best, score = agent, overlap
    return best


def help_steps(
    run: TurnRun, rows: list[RunStep], row: RunStep, agents: list[ResolvedAgent], settings
) -> list[RunStep]:
    """After a planned step asked for help: a helper step (`h<n>`, origin `help`) and the asking step again (origin
    `rerun`) with the helper's note, within ORCH_MAX_REPLANS, ORCH_MAX_STEPS and ORCH_MAX_AGENTS (FR-023 to FR-025).
    Only the step's first request counts; a helper cannot ask in turn (depth 1, FR-024)."""
    if row.origin != "plan" or row.status != "done":
        return []
    signal = next((item for item in row.signals or [] if item.get("type") == "request_help"), None)
    if signal is None:
        return []
    if run.replans >= settings.orch_max_replans or len(rows) + 2 > settings.orch_max_steps:
        return []
    helper = pick_helper(signal.get("task", ""), signal.get("agent", ""), agents, exclude=row.agent_slug)
    if helper is None:
        row.note = (row.note + "\n\n" + OUT_OF_REACH.format(task=signal.get("task", ""))).strip()[:NOTE_MAX]
        return []
    involved = {item.agent_slug for item in rows} | {run.lead_agent or ""}
    if helper.slug not in involved and len(involved - {""}) >= settings.orch_max_agents:
        return []
    number = 1 + sum(1 for item in rows if item.origin == "help")
    helper_key = f"h{number}"
    helper_title = f"Phần việc của {helper.manifest.name}"[:80]
    helper_row = RunStep(
        run_id=run.id,
        key=helper_key,
        agent_slug=helper.slug,
        agent_version_id=helper.version_id,
        title=helper_title,
        task=str(signal.get("task", ""))[:1000],
        depends_on=[],
        origin="help",
        requested_by=row.key,
        status="pending",
    )
    rerun_key = f"{row.key}r"[:16]
    rerun = RunStep(
        run_id=run.id,
        key=rerun_key,
        agent_slug=row.agent_slug,
        agent_version_id=row.agent_version_id,
        title=row.title,
        task=RERUN_TASK.format(task=row.task, helper=helper_title)[:2000],
        depends_on=[row.key, helper_key],
        origin="rerun",
        requested_by=row.key,
        status="pending",
    )
    # Steps still waiting for the asking step now wait for its rerun.
    for item in rows:
        if item.status == "pending" and row.key in item.depends_on:
            item.depends_on = [rerun_key if dep == row.key else dep for dep in item.depends_on]
    run.replans += 1
    run.plan_version += 1
    return [helper_row, rerun]
