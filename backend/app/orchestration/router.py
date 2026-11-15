"""Inbox, answers to questions, approval cards and approval settings (contracts/rest-api.md)."""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select

from app.auth.deps import CurrentUser, DbSession, require_roles
from app.auth.models import Role, User
from app.chat import service as chat_service
from app.chat.models import ChatMessage
from app.orchestration import approvals, meta, people, runs
from app.orchestration.models import (
    ACTION_KINDS,
    ALWAYS_ASK,
    KIND_MODES,
    ApprovalCard,
    ApprovalKindMode,
    ApprovalRule,
    PersonRequest,
    UserSettings,
)
from app.orchestration.serialize import approval_card_out, inbox_items, person_request_out

router = APIRouter(tags=["orchestration"])
Admin = Annotated[User, Depends(require_roles(Role.ADMIN))]


class AnswerIn(BaseModel):
    choice: str | None = Field(default=None, max_length=60)
    text: str | None = Field(default=None, max_length=2000)


class CardAnswerIn(BaseModel):
    choice: str
    # On an ask_person card with several possible recipients (two teachers of the subject).
    recipient_id: str | None = None


class ApprovalSettingsIn(BaseModel):
    extra_vigilant: bool


class ModeIn(BaseModel):
    action_kind: str
    role: str
    mode: str


class RuleIn(BaseModel):
    action_kind: str
    effect: str
    agent_slug: str | None = None
    tool: str | None = None


async def inbox_count(db, user_id: str) -> int:
    return int(
        await db.scalar(
            select(func.count()).where(
                PersonRequest.recipient_id == user_id,
                PersonRequest.status == "open",
                PersonRequest.recipient_id != PersonRequest.requester_id,
            )
        )
        or 0
    )


async def _announce_request(db, request: PersonRequest) -> None:
    rows = await db.scalars(select(ChatMessage).where(ChatMessage.person_request_id == request.id))
    for message in rows:
        await chat_service.announce(db, message, "message_update" if message.role == "system" else "message")


@router.get("/inbox")
async def inbox(
    user: CurrentUser,
    db: DbSession,
    status_filter: str = Query(default="open", alias="status"),
    class_id: str | None = Query(default=None),
) -> list[dict[str, Any]]:
    if status_filter not in ("open", "answered", "expired", "cancelled", "all"):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Trạng thái không hợp lệ.")
    return await inbox_items(db, user, status_filter, class_id)


@router.get("/inbox/count")
async def inbox_open(user: CurrentUser, db: DbSession) -> dict[str, int]:
    return {"open": await inbox_count(db, user.id)}


@router.get("/person-requests/{request_id}")
async def get_request(request_id: str, user: CurrentUser, db: DbSession) -> dict[str, Any]:
    request = await db.get(PersonRequest, request_id)
    if request is None or user.id not in (request.recipient_id, request.requester_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Không tìm thấy câu hỏi.")
    return await person_request_out(db, request.id, user.id)


@router.post("/person-requests/{request_id}/answer")
async def answer_request(request_id: str, payload: AnswerIn, user: CurrentUser, db: DbSession) -> dict[str, Any]:
    try:
        request, message = await people.answer(db, request_id, user, payload.choice, payload.text)
    except people.RequestError as error:
        await db.commit()  # an expiry noticed here is kept
        raise HTTPException(error.status, error.detail) from None
    await db.commit()
    await chat_service.announce(db, message)
    await _announce_request(db, request)
    return await person_request_out(db, request.id, user.id)


@router.post("/person-requests/{request_id}/cancel")
async def cancel_request(request_id: str, user: CurrentUser, db: DbSession) -> dict[str, Any]:
    try:
        request = await people.cancel(db, request_id, user)
    except people.RequestError as error:
        raise HTTPException(error.status, error.detail) from None
    await db.commit()
    await _announce_request(db, request)
    return await person_request_out(db, request.id, user.id)


@router.post("/approvals/{card_id}/answer")
async def answer_card(card_id: str, payload: CardAnswerIn, user: CurrentUser, db: DbSession) -> dict[str, Any]:
    try:
        card = await approvals.answer_card(db, card_id, user.id, payload.choice)
    except approvals.CardError as error:
        await db.commit()
        raise HTTPException(error.status, error.detail) from None
    request = None
    if card.tool == "ask_person":
        request = await people.after_card(db, card, payload.recipient_id)
    else:
        await meta.execute_card_action(db, card)
    await runs.try_mark_resumable(db, card.run_id)
    await db.commit()
    message = await db.scalar(select(ChatMessage).where(ChatMessage.approval_card_id == card.id))
    if message is not None:
        await chat_service.announce(db, message, "message_update")
    if request is not None and request.status == "open":
        await _announce_request(db, request)
    return await approval_card_out(db, card.id)


@router.get("/approvals/{card_id}")
async def get_card(card_id: str, user: CurrentUser, db: DbSession) -> dict[str, Any]:
    card = await db.get(ApprovalCard, card_id)
    if card is None or card.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Không tìm thấy yêu cầu duyệt.")
    return await approval_card_out(db, card.id)


def _rule_out(rule: ApprovalRule) -> dict[str, Any]:
    return {
        "id": rule.id,
        "scope": rule.scope,
        "scope_id": rule.scope_id,
        "action_kind": rule.action_kind,
        "agent_slug": rule.agent_slug,
        "tool": rule.tool,
        "target": rule.target,
        "effect": rule.effect,
        "source": rule.source,
        "created_at": rule.created_at,
    }


@router.get("/settings/approvals")
async def approval_settings(user: CurrentUser, db: DbSession) -> dict[str, Any]:
    settings = await db.get(UserSettings, user.id)
    rules = list(
        await db.scalars(
            select(ApprovalRule).where(
                ApprovalRule.created_by == user.id, ApprovalRule.scope.in_(("user", "conversation"))
            )
        )
    )
    return {
        "extra_vigilant": bool(settings and settings.extra_vigilant),
        "rules": [_rule_out(rule) for rule in rules if rule.scope == "user"],
        "conversation_allowances": [_rule_out(rule) for rule in rules if rule.scope == "conversation"],
    }


@router.patch("/settings/approvals")
async def update_approval_settings(payload: ApprovalSettingsIn, user: CurrentUser, db: DbSession) -> dict[str, Any]:
    settings = await db.get(UserSettings, user.id)
    if settings is None:
        settings = UserSettings(user_id=user.id)
        db.add(settings)
    settings.extra_vigilant = payload.extra_vigilant
    await db.commit()
    return await approval_settings(user, db)


@router.delete("/settings/approvals/rules/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_rule(rule_id: str, user: CurrentUser, db: DbSession) -> None:
    rule = await db.get(ApprovalRule, rule_id)
    if rule is None or rule.created_by != user.id or rule.scope not in ("user", "conversation"):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Không tìm thấy quy tắc.")
    await db.execute(delete(ApprovalRule).where(ApprovalRule.id == rule_id))
    await db.commit()


@router.get("/admin/approvals/modes")
async def list_modes(_: Admin, db: DbSession) -> list[dict[str, str]]:
    rows = {(row.action_kind, row.role): row.mode for row in await db.scalars(select(ApprovalKindMode))}
    return [
        {
            "action_kind": kind,
            "role": role,
            "mode": rows.get((kind, role), approvals.DEFAULT_MODE.get(role, "members_choose")),
        }
        for kind in sorted(ALWAYS_ASK)
        for role in ("student", "teacher", "parent")
    ]


@router.put("/admin/approvals/modes")
async def set_mode(payload: ModeIn, _: Admin, db: DbSession) -> list[dict[str, str]]:
    if (
        payload.action_kind not in ALWAYS_ASK
        or payload.mode not in KIND_MODES
        or payload.role not in ("student", "teacher", "parent")
    ):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Chế độ duyệt không hợp lệ.")
    row = await db.get(ApprovalKindMode, (payload.action_kind, payload.role))
    if row is None:
        db.add(ApprovalKindMode(action_kind=payload.action_kind, role=payload.role, mode=payload.mode))
    else:
        row.mode = payload.mode
    await db.commit()
    return await list_modes(_, db)


@router.get("/admin/approvals/rules")
async def admin_rules(_: Admin, db: DbSession) -> list[dict[str, Any]]:
    return [_rule_out(rule) for rule in await db.scalars(select(ApprovalRule).where(ApprovalRule.scope == "admin"))]


@router.post("/admin/approvals/rules", status_code=status.HTTP_201_CREATED)
async def add_admin_rule(payload: RuleIn, admin: Admin, db: DbSession) -> dict[str, Any]:
    if payload.action_kind not in ACTION_KINDS or payload.effect not in ("allow", "deny", "ask"):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Quy tắc không hợp lệ.")
    if payload.action_kind in ALWAYS_ASK and payload.effect == "allow":
        # FR-034: only an answer on the card itself opens an always-ask kind.
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "Loại hành động này luôn phải hỏi; quy tắc chỉ được chặn hoặc hỏi."
        )
    rule = ApprovalRule(
        scope="admin",
        action_kind=payload.action_kind,
        effect=payload.effect,
        agent_slug=payload.agent_slug,
        tool=payload.tool,
        source="admin",
        created_by=admin.id,
    )
    db.add(rule)
    await db.commit()
    return _rule_out(rule)


@router.delete("/admin/approvals/rules/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_admin_rule(rule_id: str, _: Admin, db: DbSession) -> None:
    await db.execute(delete(ApprovalRule).where(ApprovalRule.id == rule_id, ApprovalRule.scope == "admin"))
    await db.commit()


@router.get("/admin/approvals/activity")
async def admin_activity(
    _: Admin, db: DbSession, limit: int = Query(default=200, ge=1, le=500)
) -> list[dict[str, Any]]:
    """Platform-wide: what was handed over, asked, allowed, refused (with the rule or cap) and what failed, without
    conversation text (FR-057)."""
    from app.chat.models import Conversation
    from app.orchestration.activity import scope_activity

    return await scope_activity(db, select(Conversation.id), limit, with_content=False)


@router.get("/me/activity")
async def my_activity(
    user: CurrentUser, db: DbSession, conversation_id: str | None = Query(default=None)
) -> list[dict[str, Any]]:
    """A user's own activity: handoffs, questions and approvals in their own conversations (FR-057)."""
    from app.chat import visibility
    from app.chat.models import Conversation
    from app.orchestration.activity import scope_activity

    if conversation_id:
        await visibility.viewable(db, user, conversation_id)
        ids = select(Conversation.id).where(Conversation.id == conversation_id)
    else:
        ids = select(Conversation.id).where(visibility.is_member_condition(user.id))
    return await scope_activity(db, ids)
