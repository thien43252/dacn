"""Asking a person (OpenBot's ask_person; FR-024 to FR-031).

ask_person is offered to every run. The default route is the person in the conversation (no approval needed: nothing
leaves the conversation). The deployment-supplied routes here are a class's teachers (by subject), the homeroom
teacher and a student's own linked parents. Sending to anyone else is a "send" action and goes through approvals
before it leaves. Answers land in the origin conversation and wake the run that asked.
"""

import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from pydantic import ValidationError
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.models import User
from app.chat.models import ChatMessage, Conversation, ConversationMember
from app.chat.serialize import SUBJECT_NAMES, role_label
from app.classes.models import ClassMember, ClassRoom, ParentLink
from app.config import get_settings
from app.guard import rules
from app.orchestration import approvals, runs
from app.orchestration.models import PersonRequest

ANSWERABLE_KINDS = {"approval", "question", "choice", "install_agent"}


@dataclass
class Recipient:
    user: User
    label: str
    subject: str | None = None
    homeroom: bool = False


class RequestError(Exception):
    def __init__(self, status: int, detail: str) -> None:
        super().__init__(detail)
        self.status = status
        self.detail = detail


async def allowed_recipients(db: AsyncSession, user: User, role: str, room: ClassRoom | None) -> list[Recipient]:
    """Who this user may send a question to (FR-025). A student: the class's teachers, the homeroom teacher and their
    own linked parents. A teacher or parent: members of the same class."""
    found: dict[str, Recipient] = {}

    async def add(person: User | None, **extra) -> None:
        if person is None or person.id == user.id or not person.is_active or person.id in found:
            return
        found[person.id] = Recipient(person, await role_label(db, person, room.id if room else None), **extra)

    if room is not None:
        owner = await db.get(User, room.owner_id)
        await add(owner, homeroom=True)
        teachers = await db.execute(
            select(User, ClassMember.subject)
            .join(ClassMember, ClassMember.user_id == User.id)
            .where(ClassMember.class_id == room.id, ClassMember.role == "teacher")
        )
        for teacher, subject in teachers:
            await add(teacher, subject=subject)
        if room.owner_id in found and found[room.owner_id].subject is None:
            found[room.owner_id].subject = room.subject
    if role == "student":
        parents = await db.scalars(
            select(User).join(ParentLink, ParentLink.parent_id == User.id).where(ParentLink.student_id == user.id)
        )
        for parent in parents:
            await add(parent)
    elif room is not None:
        students = list(
            await db.scalars(
                select(User)
                .join(ClassMember, ClassMember.user_id == User.id)
                .where(ClassMember.class_id == room.id, ClassMember.role == "student")
            )
        )
        for student in students:
            await add(student)
        if students:
            parents = await db.scalars(
                select(User)
                .join(ParentLink, ParentLink.parent_id == User.id)
                .where(ParentLink.student_id.in_([s.id for s in students]))
            )
            for parent in parents:
                await add(parent)
    elif role == "parent":
        children = await db.scalars(
            select(User).join(ParentLink, ParentLink.student_id == User.id).where(ParentLink.parent_id == user.id)
        )
        for child in children:
            await add(child)
    return list(found.values())


def resolve(recipients: list[Recipient], recipient: str, subject: str) -> list[Recipient]:
    """Candidates for the requested recipient; the first is suggested, the others offered on the approval card."""
    recipient = recipient.strip().lower()
    if recipient == "teacher":
        matching = [r for r in recipients if r.user.role == "teacher" and subject and r.subject == subject.lower()]
        return matching or [r for r in recipients if r.homeroom]
    if recipient == "homeroom":
        return [r for r in recipients if r.homeroom]
    if recipient == "parent":
        return [r for r in recipients if r.user.role == "parent"]
    return [r for r in recipients if r.user.id == recipient]


async def moderate(ctx, text: str) -> tuple[str, bool]:
    """Redacts personal data and checks the content before it is shown to someone (FR-031). Returns (text, ok)."""
    from app.guard import classifier

    redacted, _ = rules.redact(text)
    verdict = rules.screen_output(redacted, ctx.user_text or "")
    if verdict.blocks:
        return redacted, False
    if ctx.guard_mode == "full":
        verdict, _usage = await classifier.review_output(ctx.chat_model, redacted, ctx.user_text or "", ctx.role, False)
        if verdict.blocks:
            return redacted, False
    return redacted, True


async def card_visibility(db: AsyncSession, conversation: Conversation, requester_id: str, recipient_id: str):
    """Who sees the question card in the origin conversation."""
    if conversation.kind != "group":
        return [requester_id]
    member = await db.scalar(
        select(ConversationMember).where(
            ConversationMember.conversation_id == conversation.id,
            ConversationMember.user_id == recipient_id,
            ConversationMember.left_at.is_(None),
        )
    )
    return None if member is not None else [requester_id]


async def open_request(db: AsyncSession, request: PersonRequest) -> ChatMessage:
    """draft -> open: the question becomes visible to the recipient (inbox) and as a card in the conversation."""
    from app.chat.service import add_message

    conversation = await db.get(Conversation, request.conversation_id)
    request.status = "open"
    request.expires_at = datetime.now(UTC) + timedelta(hours=get_settings().person_request_hours)
    visible = await card_visibility(db, conversation, request.requester_id, request.recipient_id)
    if request.recipient_id == request.requester_id:
        visible = None if conversation.kind != "group" else [request.requester_id]
    request.private_to_recipient = visible is not None and request.recipient_id not in visible
    message = await add_message(
        db,
        request.conversation_id,
        role="system",
        content=request.body,
        person_request_id=request.id,
        run_id=request.run_id,
        visible_to=visible,
    )
    await db.flush()
    return message


async def request_person(ctx, agent, call) -> str:
    from app.tools.registry import AskPersonArgs

    try:
        args = AskPersonArgs.model_validate(call.arguments)
    except ValidationError:
        return json.dumps(
            {"status": "refused", "reason": "Câu hỏi thiếu nội dung hoặc người nhận."}, ensure_ascii=False
        )
    kind = args.kind if args.kind in ("approval", "question", "choice") else "question"
    body, ok = await moderate(ctx, args.question)
    if not ok:
        return json.dumps(
            {"status": "refused", "reason": "Nội dung câu hỏi chưa phù hợp để gửi đi; hãy viết lại lịch sự, đúng mực."},
            ensure_ascii=False,
        )
    run = await runs.ensure_run(ctx, agent)
    options = [option.strip()[:60] for option in args.options if option.strip()]
    if kind == "approval" and not options:
        options = ["Đồng ý", "Sửa", "Từ chối"]
    db = ctx.db
    base = {
        "run_id": run.id,
        "tool_call_id": call.id,
        "conversation_id": ctx.conversation.id,
        "class_id": ctx.room.id if ctx.room else None,
        "requester_id": ctx.user.id,
        "agent_slug": agent.slug,
        "kind": kind,
        "body": body,
        "options": options,
        "expires_at": datetime.now(UTC) + timedelta(hours=get_settings().person_request_hours),
    }

    if args.recipient.strip().lower() == "self":
        if ctx.source in ("sandbox", "certify"):
            return json.dumps(
                {
                    "status": "no_person",
                    "note": "Không có người thật trong chế độ này; hãy tự giả định hợp lý và nêu rõ giả định.",
                },
                ensure_ascii=False,
            )
        request = PersonRequest(recipient_id=ctx.user.id, status="draft", **base)
        db.add(request)
        await db.flush()
        await open_request(db, request)
        ctx.after_commit.append(("request", request.id))
        ctx.waits.append({"type": "person", "id": request.id})
        return json.dumps(
            {
                "status": "asked",
                "note": "Câu hỏi đã hiện cho người dùng; dừng lại chờ họ trả lời, đừng tự trả lời thay.",
            },
            ensure_ascii=False,
        )

    candidates = resolve(await allowed_recipients(db, ctx.user, ctx.role, ctx.room), args.recipient, args.subject)
    if not candidates or ctx.source in ("sandbox", "certify"):
        db.add(PersonRequest(recipient_id=ctx.user.id, status="undeliverable", **base))
        await db.flush()
        return json.dumps(
            {"status": "undeliverable", "note": "Không có người nhận phù hợp; hãy nói rõ với người dùng."},
            ensure_ascii=False,
        )
    chosen = candidates[0]
    request = PersonRequest(recipient_id=chosen.user.id, status="draft", **base)
    db.add(request)
    await db.flush()
    action = approvals.Action("send", agent.slug, "ask_person", chosen.user.id)
    decision = (
        approvals.Decision("deny")
        if ctx.source in ("sandbox", "certify")
        else await approvals.decide_for(
            db,
            action,
            user_id=ctx.user.id,
            role=ctx.role,
            class_id=ctx.room.id if ctx.room else None,
            conversation_id=ctx.conversation.id,
        )
    )
    if decision.effect == "deny":
        request.status = "cancelled"
        await db.flush()
        return json.dumps(
            {"status": "denied", "note": "Việc gửi câu hỏi bị chặn bởi quy tắc duyệt."}, ensure_ascii=False
        )
    if decision.effect == "allow":
        await open_request(db, request)
        ctx.after_commit.append(("request", request.id))
        ctx.waits.append({"type": "person", "id": request.id})
        return json.dumps(
            {
                "status": "sent",
                "recipient": chosen.label,
                "note": "Đã gửi; hãy báo người dùng là đang chờ người đó trả lời.",
            },
            ensure_ascii=False,
        )
    subject_name = SUBJECT_NAMES.get(chosen.subject or "", chosen.subject or "")
    label = chosen.label if not subject_name or "GV" in chosen.label else f"{chosen.label} ({subject_name})"
    card = await approvals.open_card(
        db,
        run_id=run.id,
        tool_call_id=call.id,
        conversation_id=ctx.conversation.id,
        user_id=ctx.user.id,
        action=action,
        arguments={"request_id": request.id},
        summary=f"Gửi câu hỏi cho {chosen.user.name} ({label})",
        preview={
            "body": body,
            "options": options,
            "targets": [{"id": c.user.id, "name": c.user.name, "role_label": c.label} for c in candidates],
        },
        choices=decision.choices,
    )
    ctx.after_commit.append(("card", card.id))
    ctx.waits.append({"type": "approval", "id": card.id})
    return json.dumps(
        {
            "status": "waiting_approval",
            "recipient": chosen.user.name,
            "note": "Người dùng cần duyệt trước khi câu hỏi được gửi; hãy báo ngắn cho họ và dừng lại.",
        },
        ensure_ascii=False,
    )


async def after_card(db: AsyncSession, card, recipient_id: str | None = None) -> PersonRequest | None:
    """Follow-up of an answered ask_person card: open the question (exactly once) or cancel it."""
    request = await db.get(PersonRequest, (card.arguments or {}).get("request_id"))
    if request is None or request.status != "draft":
        return request
    if card.status == "allowed":
        if recipient_id and recipient_id in [t["id"] for t in card.preview.get("targets", [])]:
            request.recipient_id = recipient_id
        await open_request(db, request)
        if request.run_id:
            await runs.add_pending(db, request.run_id, {"type": "person", "id": request.id})
    else:
        request.status = "cancelled"
    card.executed_at = datetime.now(UTC)
    await db.flush()
    return request


async def answer(db: AsyncSession, request_id: str, user: User, choice: str | None, text: str | None):
    """Records a person's answer exactly once and writes it into the origin conversation (FR-029)."""
    from app.chat.service import add_message

    request = await db.get(PersonRequest, request_id)
    if request is None or request.recipient_id != user.id:
        raise RequestError(404, "Không tìm thấy câu hỏi.")
    if request.status != "open":
        raise RequestError(409, "Câu hỏi đã được trả lời hoặc không còn mở.")
    expires = request.expires_at if request.expires_at.tzinfo else request.expires_at.replace(tzinfo=UTC)
    if expires < datetime.now(UTC):
        request.status = "expired"
        await runs.try_mark_resumable(db, request.run_id)
        await db.flush()
        raise RequestError(409, "Câu hỏi đã hết hạn.")
    parts = [part.strip() for part in (choice or "", text or "") if part and part.strip()]
    if not parts:
        raise RequestError(422, "Hãy chọn một lựa chọn hoặc viết câu trả lời.")
    reply = ": ".join(parts)[:2000]
    screened = rules.screen_input(reply)
    if screened.action == "redact" and screened.text:
        reply = screened.text
    hidden = screened.blocks or rules.screen_output(reply, request.body).blocks
    result = await db.execute(
        update(PersonRequest)
        .where(PersonRequest.id == request.id, PersonRequest.status == "open")
        .values(
            status="answered", answer=reply, answer_hidden=hidden, answered_by=user.id, answered_at=datetime.now(UTC)
        )
    )
    if result.rowcount != 1:
        raise RequestError(409, "Câu hỏi đã được trả lời.")
    await db.refresh(request)
    conversation = await db.get(Conversation, request.conversation_id)
    visible = await card_visibility(db, conversation, request.requester_id, request.recipient_id)
    if request.recipient_id == request.requester_id:
        visible = None if conversation.kind != "group" else [request.requester_id]
    message = await add_message(
        db,
        request.conversation_id,
        role="user",
        content=reply,
        sender_user_id=user.id,
        person_request_id=request.id,
        status="hidden" if hidden else "ok",
        visible_to=visible,
        meta={"answer_to": request.id},
    )
    if request.kind == "install_agent" and not hidden and reply.lower().startswith("đồng ý"):
        await install_from_request(db, request, user)
    await runs.try_mark_resumable(db, request.run_id)
    await db.flush()
    return request, message


async def install_from_request(db: AsyncSession, request: PersonRequest, teacher: User) -> None:
    from app.agents.models import Installation

    payload = request.payload or {}
    if not payload.get("agent_id") or not request.class_id:
        return
    exists = await db.scalar(
        select(Installation).where(
            Installation.agent_id == payload["agent_id"],
            Installation.class_id == request.class_id,
            Installation.scope == "class",
        )
    )
    if exists is None:
        db.add(
            Installation(
                agent_id=payload["agent_id"],
                agent_version_id=payload["version_id"],
                scope="class",
                class_id=request.class_id,
                installed_by=teacher.id,
            )
        )
        await db.flush()


async def cancel(db: AsyncSession, request_id: str, user: User) -> PersonRequest:
    request = await db.get(PersonRequest, request_id)
    if request is None or request.requester_id != user.id:
        raise RequestError(404, "Không tìm thấy câu hỏi.")
    if request.status not in ("open", "draft"):
        raise RequestError(409, "Câu hỏi không còn mở.")
    request.status = "cancelled"
    await runs.try_mark_resumable(db, request.run_id)
    await db.flush()
    return request


async def expire_due(db: AsyncSession) -> list[PersonRequest]:
    now = datetime.now(UTC)
    rows = list(
        await db.scalars(select(PersonRequest).where(PersonRequest.status == "open", PersonRequest.expires_at < now))
    )
    for request in rows:
        request.status = "expired"
        await runs.try_mark_resumable(db, request.run_id)
    await db.flush()
    return rows


async def undeliver_for_member_loss(db: AsyncSession, user_id: str) -> None:
    """A recipient who left the class (or lost a parent link) can no longer answer open questions."""
    rows = list(
        await db.scalars(
            select(PersonRequest).where(PersonRequest.recipient_id == user_id, PersonRequest.status == "open")
        )
    )
    for request in rows:
        request.status = "undeliverable"
        await runs.try_mark_resumable(db, request.run_id)
    await db.flush()
