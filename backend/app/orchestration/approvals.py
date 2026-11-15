"""Approvals, the OpenBot way (FR-032 to FR-038, research R8).

Decision order, first answer wins:
1. kinds that always ask (send, share, post, delete, settings, money), whatever the user's own switch says;
2. rules (user, class, admin, conversation allowances): deny before allow, the strictest match wins, no matching policy
   permits nothing, a broken rule refuses. Only an answer given on a card can open an always-ask kind;
3. the user's "extra vigilant" switch, which asks before every change.

`decide()` is pure so the whole truth table is testable without a model.
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.orchestration.models import (
    ALWAYS_ASK,
    ApprovalCard,
    ApprovalKindMode,
    ApprovalRule,
    UserSettings,
)

CHOICES_BY_MODE = {
    "members_choose": ["once", "conversation", "always", "deny"],
    "ask_every_time": ["once", "deny"],
    "do_it_yourself": ["did_it", "dont"],
}
DEFAULT_MODE = {"student": "ask_every_time"}
CHOICE_LABELS = {
    "once": "Cho phép lần này",
    "conversation": "Cho phép trong hội thoại này",
    "always": "Luôn cho phép ở đây",
    "deny": "Từ chối",
    "did_it": "Tôi đã tự làm",
    "dont": "Đừng làm",
}
VALID_EFFECTS = {"allow", "deny", "ask"}


@dataclass
class Decision:
    effect: str  # allow | deny | ask
    choices: list[str] = field(default_factory=list)
    reason: str = ""


@dataclass
class Action:
    kind: str
    agent_slug: str
    tool: str
    target: str | None = None


def _matches(rule: ApprovalRule, action: Action) -> bool:
    return (
        rule.action_kind == action.kind
        and (rule.agent_slug is None or rule.agent_slug == action.agent_slug)
        and (rule.tool is None or rule.tool == action.tool)
        and (rule.target is None or rule.target == action.target)
    )


def decide(action: Action, rules: list[ApprovalRule], mode: str, extra_vigilant: bool) -> Decision:
    """`rules` are the rules in scope for this user, class, conversation and the admin."""
    if action.kind == "none":
        return Decision("allow", reason="not an action")
    matching = [rule for rule in rules if _matches(rule, action)]
    if any(rule.effect not in VALID_EFFECTS for rule in matching):
        return Decision("deny", reason="broken rule")
    if any(rule.effect == "deny" for rule in matching):
        return Decision("deny", reason="deny rule")
    asks = any(rule.effect == "ask" for rule in matching)
    choices = CHOICES_BY_MODE.get(mode, CHOICES_BY_MODE["members_choose"])
    if action.kind in ALWAYS_ASK:
        if mode == "do_it_yourself":
            return Decision("ask", CHOICES_BY_MODE["do_it_yourself"], "members do it themselves")
        # Typed, class and admin rules can only tighten an always-ask kind; only a card answer opens it.
        opened = any(rule.effect == "allow" and rule.source == "card" for rule in matching)
        if opened and not asks:
            return Decision("allow", reason="allowed on a card")
        return Decision("ask", choices, "always asks")
    if asks:
        return Decision("ask", choices, "ask rule")
    if extra_vigilant:
        return Decision("ask", choices, "extra vigilant")
    return Decision("allow", reason="ordinary change")


async def rules_in_scope(
    db: AsyncSession, user_id: str, class_id: str | None, conversation_id: str | None
) -> list[ApprovalRule]:
    scopes = [
        (ApprovalRule.scope == "user") & (ApprovalRule.scope_id == user_id),
        ApprovalRule.scope == "admin",
    ]
    if class_id:
        scopes.append((ApprovalRule.scope == "class") & (ApprovalRule.scope_id == class_id))
    if conversation_id:
        scopes.append((ApprovalRule.scope == "conversation") & (ApprovalRule.scope_id == conversation_id))
    return list(await db.scalars(select(ApprovalRule).where(or_(*scopes))))


async def mode_for(db: AsyncSession, kind: str, role: str) -> str:
    row = await db.get(ApprovalKindMode, (kind, role))
    return row.mode if row else DEFAULT_MODE.get(role, "members_choose")


async def extra_vigilant(db: AsyncSession, user_id: str) -> bool:
    row = await db.get(UserSettings, user_id)
    return bool(row and row.extra_vigilant)


async def decide_for(
    db: AsyncSession,
    action: Action,
    *,
    user_id: str,
    role: str,
    class_id: str | None,
    conversation_id: str | None,
) -> Decision:
    rules = await rules_in_scope(db, user_id, class_id, conversation_id)
    return decide(action, rules, await mode_for(db, action.kind, role), await extra_vigilant(db, user_id))


async def open_card(
    db: AsyncSession,
    *,
    run_id: str | None,
    tool_call_id: str,
    conversation_id: str,
    user_id: str,
    action: Action,
    arguments: dict[str, Any],
    summary: str,
    preview: dict[str, Any],
    choices: list[str],
) -> ApprovalCard:
    """Writes the card into the origin conversation for the origin user (FR-037) and returns it (not committed)."""
    from app.chat.service import add_message

    card = ApprovalCard(
        run_id=run_id,
        tool_call_id=tool_call_id,
        conversation_id=conversation_id,
        user_id=user_id,
        agent_slug=action.agent_slug,
        tool=action.tool,
        arguments=arguments,
        action_kind=action.kind,
        target=action.target,
        summary=summary[:300],
        preview=preview,
        choices=choices,
        expires_at=datetime.now(UTC) + timedelta(hours=get_settings().approval_card_hours),
    )
    db.add(card)
    await db.flush()
    await add_message(
        db,
        conversation_id,
        role="system",
        content=summary,
        approval_card_id=card.id,
        run_id=run_id,
        visible_to=[user_id],
    )
    return card


class CardError(Exception):
    def __init__(self, status: int, detail: str) -> None:
        super().__init__(detail)
        self.status = status
        self.detail = detail


async def answer_card(db: AsyncSession, card_id: str, user_id: str, choice: str) -> ApprovalCard:
    """Records the answer exactly once (conditional update). The caller then runs the follow-up and commits."""
    card = await db.get(ApprovalCard, card_id)
    if card is None or card.user_id != user_id:
        raise CardError(404, "Không tìm thấy yêu cầu duyệt.")
    if card.status != "open":
        raise CardError(409, "Yêu cầu duyệt này đã được trả lời hoặc đã hết hạn.")
    if card.expires_at.replace(tzinfo=card.expires_at.tzinfo or UTC) < datetime.now(UTC):
        card.status = "expired"
        await db.flush()
        raise CardError(409, "Yêu cầu duyệt đã hết hạn.")
    if choice not in card.choices:
        raise CardError(422, "Lựa chọn không có trên thẻ duyệt này.")
    allowed = choice in ("once", "conversation", "always")
    result = await db.execute(
        update(ApprovalCard)
        .where(ApprovalCard.id == card.id, ApprovalCard.status == "open")
        .values(status="allowed" if allowed else "denied", answer=choice)
    )
    if result.rowcount != 1:
        raise CardError(409, "Yêu cầu duyệt này đã được trả lời.")
    await db.refresh(card)
    if choice == "conversation":
        db.add(
            ApprovalRule(
                scope="conversation",
                scope_id=card.conversation_id,
                action_kind=card.action_kind,
                agent_slug=card.agent_slug,
                tool=card.tool,
                target=card.target,
                effect="allow",
                source="card",
                created_by=user_id,
            )
        )
    elif choice == "always":
        db.add(
            ApprovalRule(
                scope="user",
                scope_id=user_id,
                action_kind=card.action_kind,
                agent_slug=card.agent_slug,
                tool=card.tool,
                target=card.target,
                effect="allow",
                source="card",
                created_by=user_id,
            )
        )
    await db.flush()
    return card


def result_text_denied() -> str:
    return '{"status": "denied", "note": "Hành động bị từ chối; việc này chưa được thực hiện."}'


def result_text(card: ApprovalCard) -> str:
    if card.status == "allowed":
        return "Người dùng đã cho phép."
    if card.answer == "did_it":
        return "Người dùng cho biết họ đã tự làm việc này; bạn không làm."
    if card.status == "expired":
        return "Yêu cầu duyệt đã hết hạn; việc này chưa được thực hiện."
    return "Người dùng đã từ chối; việc này chưa được thực hiện."
