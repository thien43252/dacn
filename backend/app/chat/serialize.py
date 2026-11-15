"""JSON shapes of conversations and messages (contracts/rest-api.md)."""

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.manifest import AgentManifest
from app.agents.models import Agent
from app.agents.service import latest_version
from app.auth.models import User
from app.chat.models import ChatMessage, Conversation, ConversationMember
from app.classes.models import ClassMember, ClassRoom, ParentLink

HIDDEN_TEXT = "Nội dung đã được ẩn"
SUBJECT_NAMES = {
    "toan": "Toán",
    "van": "Văn",
    "anh": "Tiếng Anh",
    "ly": "Lý",
    "hoa": "Hóa",
    "sinh": "Sinh",
    "su": "Sử",
    "dia": "Địa",
    "tin": "Tin",
    "gdcd": "GDCD",
    "chung": "chung",
}


async def agent_card(db: AsyncSession, slug: str | None) -> dict[str, Any] | None:
    if not slug:
        return None
    agent = await db.scalar(select(Agent).where(Agent.slug == slug))
    if agent is None:
        return {"slug": slug, "name": slug, "avatar": "owl"}
    version = await latest_version(db, agent.id)
    manifest = AgentManifest.model_validate(version.manifest if version else agent.draft_manifest)
    return {"slug": slug, "name": manifest.name, "avatar": manifest.avatar}


async def role_label(db: AsyncSession, user: User, class_id: str | None) -> str:
    """ "GV Toán", "Phụ huynh của An", "Học sinh"... in the context of a class."""
    if user.role == "teacher":
        subject = None
        if class_id:
            subject = await db.scalar(
                select(ClassMember.subject).where(ClassMember.class_id == class_id, ClassMember.user_id == user.id)
            )
            if subject is None:
                room = await db.get(ClassRoom, class_id)
                if room and room.owner_id == user.id:
                    return "GV chủ nhiệm"
        return f"GV {SUBJECT_NAMES.get(subject, subject)}" if subject else "Giáo viên"
    if user.role == "parent":
        children = list(
            await db.scalars(
                select(User.name)
                .join(ParentLink, ParentLink.student_id == User.id)
                .where(ParentLink.parent_id == user.id)
            )
        )
        return f"Phụ huynh của {children[0].split()[-1]}" if children else "Phụ huynh"
    if user.role == "student":
        return "Học sinh"
    return "Quản trị"


async def sender_of(db: AsyncSession, message: ChatMessage, class_id: str | None) -> dict[str, Any]:
    if message.role == "user" and message.sender_user_id:
        user = await db.get(User, message.sender_user_id)
        if user is not None:
            return {
                "kind": "user",
                "id": user.id,
                "name": user.name,
                "role_label": await role_label(db, user, class_id),
                "avatar": None,
            }
    if message.role == "assistant" and message.agent_slug:
        card = await agent_card(db, message.agent_slug) or {}
        return {
            "kind": "agent",
            "id": message.agent_slug,
            "name": card.get("name"),
            "role_label": "Agent",
            "avatar": card.get("avatar"),
        }
    return {"kind": "system", "id": None, "name": "EduAgent Hub", "role_label": "", "avatar": None}


async def message_out(db: AsyncSession, message: ChatMessage, viewer_id: str | None = None) -> dict[str, Any]:
    from app.orchestration import serialize as orch

    conversation = await db.get(Conversation, message.conversation_id)
    class_id = conversation.class_id if conversation else None
    hidden = message.status == "hidden"
    return {
        "id": message.id,
        "seq": message.seq,
        "role": message.role,
        "content": HIDDEN_TEXT if hidden else message.content,
        "agent_slug": message.agent_slug,
        "status": message.status,
        "created_at": message.created_at,
        "meta": message.meta or {},
        "sender": await sender_of(db, message, class_id),
        "handoff_id": message.handoff_id,
        "reply_to_agent": message.reply_to_agent,
        "handoffs": await orch.handoff_tree(db, message) if message.role == "assistant" else [],
        "person_request": await orch.person_request_out(db, message.person_request_id, viewer_id)
        if message.person_request_id
        else None,
        "approval_card": await orch.approval_card_out(db, message.approval_card_id)
        if message.approval_card_id
        else None,
        "visible_to": message.visible_to,
    }


async def conversation_out(db: AsyncSession, conversation: Conversation, user_id: str) -> dict[str, Any]:
    from app.orchestration import serialize as orch

    await db.refresh(conversation)
    member = await db.scalar(
        select(ConversationMember).where(
            ConversationMember.conversation_id == conversation.id, ConversationMember.user_id == user_id
        )
    )
    last_read = member.last_read_seq if member else conversation.last_seq
    last = await db.scalar(
        select(ChatMessage)
        .where(ChatMessage.conversation_id == conversation.id, ChatMessage.handoff_id.is_(None))
        .order_by(ChatMessage.seq.desc())
        .limit(1)
    )
    last_message = None
    if last is not None:
        sender = await sender_of(db, last, conversation.class_id)
        last_message = {
            "seq": last.seq,
            "sender": sender.get("name"),
            "text": (HIDDEN_TEXT if last.status == "hidden" else last.content)[:140],
            "at": last.created_at,
        }
    unread = await db.scalar(
        select(func.count()).where(
            ChatMessage.conversation_id == conversation.id,
            ChatMessage.seq > last_read,
            ChatMessage.sender_user_id.is_distinct_from(user_id),
        )
    )
    out: dict[str, Any] = {
        "id": conversation.id,
        "kind": conversation.kind,
        "class_id": conversation.class_id,
        "title": conversation.title,
        "updated_at": conversation.updated_at,
        "last_message": last_message,
        "unread": int(unread or 0),
        "waiting_for": await orch.waiting_for(db, conversation.id),
        "agent": None,
        "members_preview": [],
        "default_agent": conversation.default_agent_slug,
    }
    if conversation.kind == "direct":
        out["agent"] = await agent_card(db, conversation.direct_agent_slug) or {
            "slug": None,
            "name": "Trợ lý tự chọn agent",
            "avatar": "owl",
        }
    elif conversation.kind == "group":
        members = list(
            await db.scalars(
                select(ConversationMember).where(
                    ConversationMember.conversation_id == conversation.id, ConversationMember.left_at.is_(None)
                )
            )
        )
        preview = []
        for item in members[:6]:
            if item.user_id:
                person = await db.get(User, item.user_id)
                if person:
                    preview.append(
                        {
                            "kind": "user",
                            "id": person.id,
                            "name": person.name,
                            "role_label": await role_label(db, person, conversation.class_id),
                        }
                    )
            else:
                card = await agent_card(db, item.agent_slug) or {}
                preview.append(
                    {
                        "kind": "agent",
                        "id": item.agent_slug,
                        "name": card.get("name"),
                        "role_label": "Agent",
                        "avatar": card.get("avatar"),
                    }
                )
        out["members_preview"] = preview
        out["member_count"] = len(members)
    return out
