"""Working notes shown on demand in the progress panel (specs/002-multi-agent-orchestration research R9).

A note is reviewed lazily, the first time someone opens it, and the outcome is stored on the step. A note that has not
passed review is never shown (FR-030): a failed review answers `hidden` without storing, so the next opening retries.
"""

import logging
import time
from dataclasses import dataclass, field
from typing import Any

from app import tracing
from app.audit.models import GuardEvent
from app.chat.models import ChatMessage, Conversation
from app.chat.router import record_usage
from app.classes.models import ClassRoom
from app.guard import dify_rules, rules
from app.orchestrator.models import RunStep, TurnRun
from app.runtime.dify_client import DifyClient, DifyError

log = logging.getLogger("eduagent.orchestrator")

HIDDEN_TEXT = "Nội dung này đã được ẩn"


@dataclass
class NoteView:
    key: str
    title: str
    agent: str
    status: str
    # visible · hidden · unavailable
    visibility: str
    note: str | None = None
    citations: list[dict[str, Any]] = field(default_factory=list)
    reason_text: str | None = None


def _view(step: RunStep, visibility: str) -> NoteView:
    shown = visibility == "visible"
    return NoteView(
        key=step.key,
        title=step.title,
        agent=step.agent_slug,
        status=step.status,
        visibility=visibility,
        note=step.note if shown else None,
        citations=list(step.citations or []) if shown else [],
        reason_text=HIDDEN_TEXT if visibility == "hidden" else None,
    )


def _guard_event(
    db, conversation: Conversation, message: ChatMessage, step: RunStep, role: str, category: str, detector: str,
    reason: str,
) -> None:
    excerpt, _ = rules.redact(step.note)
    db.add(
        GuardEvent(
            source="chat",
            class_id=conversation.class_id,
            user_id=conversation.user_id,
            role=role,
            conversation_id=conversation.id,
            message_id=message.id,
            agent_slug=step.agent_slug,
            stage="step_note",
            verdict="block",
            category=category,
            detector=detector,
            severity="medium",
            reason=reason[:300],
            excerpt=excerpt[:300],
        )
    )


async def review_note(
    db,
    client: DifyClient,
    conversation: Conversation,
    message: ChatMessage,
    run: TurnRun,
    step: RunStep,
    role: str,
) -> NoteView:
    """The note of `step` as the conversation's owner (`role`) may see it, reviewed once (research R9):

    1. a step that did not finish has nothing to show (`unavailable`);
    2. a blocked final answer hides every note of its run;
    3. a stored review is returned as is;
    4. otherwise the runner's keyword moderation, then eduagent-review with the viewer's role and the class policy
       (teachers skip the review, as their answers do). Hidden notes leave a guard event naming the step's agent
       (FR-043)."""
    if step.status != "done" or not step.note.strip():
        return _view(step, "unavailable")
    if message.status == "blocked":
        return _view(step, "hidden")
    if step.note_review in ("visible", "hidden"):
        return _view(step, step.note_review)

    if dify_rules.contains_blocked_keyword(step.note) or dify_rules.contains_blocked_keyword(step.title):
        _guard_event(db, conversation, message, step, role, "moderation", "keyword", "Ghi chú chứa từ khóa bị chặn")
        step.note_review = "hidden"
        await db.commit()
        return _view(step, "hidden")
    if role == "teacher" or not client.settings.dify_review_key:
        step.note_review = "visible"
        await db.commit()
        return _view(step, "visible")

    room = await db.get(ClassRoom, conversation.class_id) if conversation.class_id else None
    no_answers = bool((room.policy or {}).get("no_direct_answers", True)) if room else False
    started = time.perf_counter()
    try:
        with tracing.node(None, "note_review"):
            result = await client.run_review(
                {
                    "question": run.request_text[:4000],
                    "reply": step.note[:12000],
                    "role": role,
                    "no_direct_answers": "true" if no_answers and role == "student" else "false",
                },
                user=conversation.user_id,
            )
    except DifyError as error:
        log.warning("note review failed, note hidden this time: %s", error)
        return _view(step, "hidden")
    if result.usage:
        usage = [("note_review", result.usage, int((time.perf_counter() - started) * 1000))]
        record_usage(db, conversation.user_id, conversation.class_id, conversation.id, usage, path="full")
    if result.verdict == "block":
        _guard_event(db, conversation, message, step, role, result.category, "dify_review", result.reason)
        step.note_review = "hidden"
    else:
        step.note_review = "visible"
    await db.commit()
    return _view(step, step.note_review)
