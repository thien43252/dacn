"""Activity: what agents ran, handed over, asked people and were refused (FR-055 to FR-057, OpenBot's Activity page).

Three views, three privacy levels:
- a teacher's class log: only groups the teacher is a member of;
- an agent owner's activity page: metadata only (no conversation text of other people);
- a user's own activity: their own conversations, with content.
"""

from typing import Any

from sqlalchemy import or_, select

from app.audit.models import GuardEvent
from app.chat.models import ToolCallLog
from app.orchestration.handoffs import client_status
from app.orchestration.models import ApprovalCard, Handoff, PersonRequest


def _handoff_row(handoff: Handoff, with_content: bool) -> dict[str, Any]:
    row = {
        "type": "handoff",
        "id": handoff.id,
        "at": handoff.created_at,
        "conversation_id": handoff.conversation_id if with_content else None,
        "from_agent": handoff.from_agent,
        "to_agent": handoff.to_agent,
        "depth": handoff.depth,
        "status": client_status(handoff),
        "attempts": handoff.attempts,
        # Which grant or cap stopped it (every refusal carries its rule).
        "reason": handoff.refusal_reason,
    }
    if with_content:
        row["task"] = handoff.task
    return row


def _request_row(request: PersonRequest, with_content: bool) -> dict[str, Any]:
    row = {
        "type": "person_request",
        "id": request.id,
        "at": request.created_at,
        "conversation_id": request.conversation_id if with_content else None,
        "agent": request.agent_slug,
        "kind": request.kind,
        "status": request.status,
        "answered_at": request.answered_at,
    }
    if with_content:
        row["body"] = request.body
    return row


def _card_row(card: ApprovalCard, with_content: bool = True) -> dict[str, Any]:
    return {
        "type": "approval",
        "id": card.id,
        "at": card.created_at,
        "conversation_id": card.conversation_id if with_content else None,
        "agent": card.agent_slug,
        "tool": card.tool,
        "action_kind": card.action_kind,
        "status": card.status,
        "answer": card.answer,
        "decided_by": "card",
    }


def _decision_row(event: GuardEvent, with_content: bool = True) -> dict[str, Any]:
    """An approval decided by a rule (or because no person could answer), without a card (FR-056)."""
    return {
        "type": "approval",
        "id": event.id,
        "at": event.created_at,
        "conversation_id": event.conversation_id if with_content else None,
        "agent": event.agent_slug,
        "status": "denied" if event.verdict == "block" else "allowed",
        "decided_by": "rule",
        "reason": event.reason,
    }


def _sorted(rows: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    return sorted(rows, key=lambda row: row["at"] or 0, reverse=True)[:limit]


async def scope_activity(db, conversation_ids, limit: int = 100, *, with_content: bool = True) -> list[dict[str, Any]]:
    """Handoffs, questions and approvals in the given conversations (a subquery of ids), with content unless an
    operator looks (admins see what was allowed, refused and failed, never private text: FR-057)."""
    handoffs = await db.scalars(select(Handoff).where(Handoff.conversation_id.in_(conversation_ids)).limit(limit))
    requests = await db.scalars(
        select(PersonRequest).where(PersonRequest.conversation_id.in_(conversation_ids)).limit(limit)
    )
    cards = await db.scalars(
        select(ApprovalCard).where(ApprovalCard.conversation_id.in_(conversation_ids)).limit(limit)
    )
    decisions = await db.scalars(
        select(GuardEvent)
        .where(GuardEvent.stage == "approval", GuardEvent.conversation_id.in_(conversation_ids))
        .limit(limit)
    )
    return _sorted(
        [_handoff_row(h, with_content) for h in handoffs]
        + [_request_row(r, with_content) for r in requests]
        + [_card_row(c, with_content) for c in cards]
        + [_decision_row(e, with_content) for e in decisions],
        limit,
    )


async def agent_activity(db, slug: str, limit: int = 200) -> list[dict[str, Any]]:
    """For the agent's owner: what it ran and handed over, without anyone's conversation text."""
    handoffs = await db.scalars(
        select(Handoff).where(or_(Handoff.from_agent == slug, Handoff.to_agent == slug)).limit(limit)
    )
    tools = await db.scalars(
        select(ToolCallLog).where(ToolCallLog.agent_slug == slug).order_by(ToolCallLog.created_at.desc()).limit(limit)
    )
    requests = await db.scalars(select(PersonRequest).where(PersonRequest.agent_slug == slug).limit(limit))
    rows = [_handoff_row(h, False) for h in handoffs] + [_request_row(r, False) for r in requests]
    rows += [
        {
            "type": "tool",
            "id": call.id,
            "at": call.created_at,
            "tool": call.tool,
            "status": "denied" if call.denied_reason else ("error" if call.is_error else "done"),
            "reason": call.denied_reason,
            "latency_ms": call.latency_ms,
        }
        for call in tools
    ]
    return _sorted(rows, limit)
