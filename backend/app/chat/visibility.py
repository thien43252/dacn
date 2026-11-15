"""Who may see a conversation and which of its messages (FR-039, FR-047, FR-050).

Every conversation is a private space: only its members see it. Outsiders, including the class owner, get a 404 so a
conversation's existence does not leak.
"""

from fastapi import HTTPException, status
from sqlalchemy import Select, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.models import User
from app.chat.models import ChatMessage, Conversation, ConversationMember


def not_found() -> HTTPException:
    return HTTPException(status.HTTP_404_NOT_FOUND, "Không tìm thấy cuộc trò chuyện.")


async def membership(db: AsyncSession, conversation: Conversation, user_id: str) -> ConversationMember | None:
    member = await db.scalar(
        select(ConversationMember).where(
            ConversationMember.conversation_id == conversation.id, ConversationMember.user_id == user_id
        )
    )
    if member is None and conversation.kind != "group" and conversation.user_id == user_id:
        # Direct chats and sandboxes created before members existed: the creator is the only person.
        member = ConversationMember(conversation_id=conversation.id, user_id=user_id, can_see_history=True)
    return member


async def viewable(db: AsyncSession, user: User, conversation_id: str) -> tuple[Conversation, ConversationMember]:
    conversation = await db.get(Conversation, conversation_id)
    if conversation is None:
        raise not_found()
    member = await membership(db, conversation, user.id)
    if member is None or member.left_at is not None:
        raise not_found()
    return conversation, member


def can_see(message: ChatMessage, member: ConversationMember, user_id: str) -> bool:
    if not member.can_see_history and message.seq <= member.joined_seq:
        return False
    if member.left_at is not None and message.created_at and message.created_at > member.left_at:
        return False
    return message.visible_to is None or user_id in message.visible_to


def visible_messages(conversation: Conversation, member: ConversationMember) -> Select:
    query = select(ChatMessage).where(ChatMessage.conversation_id == conversation.id)
    if not member.can_see_history:
        query = query.where(ChatMessage.seq > member.joined_seq)
    return query


def filter_visible(messages: list[ChatMessage], member: ConversationMember, user_id: str) -> list[ChatMessage]:
    return [message for message in messages if can_see(message, member, user_id)]


async def member_user_ids(db: AsyncSession, conversation: Conversation) -> list[str]:
    rows = await db.scalars(
        select(ConversationMember.user_id).where(
            ConversationMember.conversation_id == conversation.id,
            ConversationMember.user_id.is_not(None),
            ConversationMember.left_at.is_(None),
        )
    )
    ids = [row for row in rows if row]
    if not ids and conversation.kind != "group":
        ids = [conversation.user_id]
    return ids


def is_member_condition(user_id: str):
    """SQL condition: the conversation has this user as a current member (used by list endpoints)."""
    return or_(
        Conversation.id.in_(
            select(ConversationMember.conversation_id).where(
                ConversationMember.user_id == user_id, ConversationMember.left_at.is_(None)
            )
        ),
        (Conversation.kind != "group") & (Conversation.user_id == user_id),
    )
