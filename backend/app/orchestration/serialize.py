"""JSON shapes for handoff trees, question cards and approval cards (contracts/rest-api.md)."""

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.models import User
from app.chat.models import ChatMessage, Conversation
from app.chat.serialize import agent_card, role_label
from app.classes.models import ClassRoom
from app.orchestration import approvals, handoffs
from app.orchestration.models import AgentRun, ApprovalCard, PersonRequest


async def handoff_tree(db: AsyncSession, message: ChatMessage) -> list[dict[str, Any]]:
    """Handoffs made by the run whose visible reply is this message (bars in direct chats, nested by depth)."""
    if message.handoff_id:
        return []
    run_ids = list(await db.scalars(select(AgentRun.id).where(AgentRun.message_id == message.id)))
    return await handoffs.tree(db, run_ids)


async def person_request_out(db: AsyncSession, request_id: str | None, viewer_id: str | None = None):
    request = await db.get(PersonRequest, request_id) if request_id else None
    if request is None:
        return None
    requester = await db.get(User, request.requester_id)
    recipient = await db.get(User, request.recipient_id)
    room = await db.get(ClassRoom, request.class_id) if request.class_id else None
    answered_by = await db.get(User, request.answered_by) if request.answered_by else None
    return {
        "id": request.id,
        "kind": request.kind,
        "status": request.status,
        "conversation_id": request.conversation_id,
        "requester": {"id": requester.id, "name": requester.name, "class": room.name if room else None}
        if requester
        else None,
        "agent": await agent_card(db, request.agent_slug),
        "recipient": {
            "id": recipient.id,
            "name": recipient.name,
            "role_label": await role_label(db, recipient, request.class_id),
        }
        if recipient
        else None,
        "body": request.body,
        "options": request.options or [],
        "answer": None if request.answer_hidden else request.answer,
        "answer_hidden": request.answer_hidden,
        "answered_by": answered_by.name if answered_by else None,
        "expires_at": request.expires_at,
        "created_at": request.created_at,
        "can_answer": request.status == "open" and viewer_id == request.recipient_id,
        "can_cancel": request.status == "open" and viewer_id == request.requester_id,
    }


async def approval_card_out(db: AsyncSession, card_id: str | None) -> dict[str, Any] | None:
    card = await db.get(ApprovalCard, card_id) if card_id else None
    if card is None:
        return None
    return {
        "id": card.id,
        "status": card.status,
        "user_id": card.user_id,
        "agent": await agent_card(db, card.agent_slug),
        "tool": card.tool,
        "action_kind": card.action_kind,
        "summary": card.summary,
        "preview": {key: value for key, value in (card.preview or {}).items() if key != "result"},
        "choices": [{"id": choice, "label": approvals.CHOICE_LABELS.get(choice, choice)} for choice in card.choices],
        "answer": card.answer,
        "expires_at": card.expires_at,
    }


async def waiting_for(db: AsyncSession, conversation_id: str) -> list[str]:
    rows = await db.execute(
        select(User.name)
        .join(PersonRequest, PersonRequest.recipient_id == User.id)
        .where(
            PersonRequest.conversation_id == conversation_id,
            PersonRequest.status == "open",
            PersonRequest.recipient_id != PersonRequest.requester_id,
        )
    )
    return [name for (name,) in rows]


async def inbox_items(db: AsyncSession, user: User, status: str = "open", class_id: str | None = None):
    query = select(PersonRequest).where(
        PersonRequest.recipient_id == user.id, PersonRequest.recipient_id != PersonRequest.requester_id
    )
    if status != "all":
        query = query.where(PersonRequest.status == status)
    if class_id:
        query = query.where(PersonRequest.class_id == class_id)
    rows = list(await db.scalars(query.order_by(PersonRequest.created_at.desc()).limit(100)))
    return [await person_request_out(db, row.id, user.id) for row in rows]


async def conversation_of(db: AsyncSession, request: PersonRequest) -> Conversation | None:
    return await db.get(Conversation, request.conversation_id)
