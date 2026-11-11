"""Runs the steps of a plan (specs/002-multi-agent-orchestration research R4).

Each step is one eduagent-runner call on a fresh Dify conversation (`conversation_id=""`), with the step agent's own
system prompt, tools and permissions plus the STEP_MODE block (FR-020, FR-021). The stream is read to the end as the
step's working note and never shown to the user (FR-022); the step's `tool` events still reach the progress panel.
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from app import tracing
from app.agents.service import ResolvedAgent
from app.guard import dify_rules
from app.orchestrator.models import RunStep
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


def apply_outcome(step: RunStep, outcome: StepOutcome, tool_events: list[dict[str, str]]) -> None:
    """Writes a finished step's outcome on its row."""
    step.status = outcome.status
    step.note = outcome.note
    step.error = outcome.error
    step.citations = outcome.citations
    step.signals = outcome.signals
    step.tools = tool_events
    step.finished_at = datetime.now(UTC)
