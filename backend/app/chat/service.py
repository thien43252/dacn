"""Writing messages: every stored message gets the next `seq` of its conversation and is published to followers."""

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import set_committed_value
from sqlalchemy.orm.util import identity_key

from app.chat import events
from app.chat.models import ChatMessage, Conversation, ConversationMember


async def next_seq(db: AsyncSession, conversation_id: str) -> int:
    """Atomically bumps the conversation's counter (the row lock serialises concurrent writers on Postgres)."""
    value = await db.scalar(
        update(Conversation)
        .where(Conversation.id == conversation_id)
        .values(last_seq=Conversation.last_seq + 1, updated_at=datetime.now(UTC))
        .returning(Conversation.last_seq)
    )
    if value is None:  # pragma: no cover - the conversation was deleted mid-turn
        raise LookupError(conversation_id)
    cached = db.identity_map.get(identity_key(Conversation, conversation_id))
    if cached is not None:
        set_committed_value(cached, "last_seq", int(value))
    return int(value)


async def add_message(db: AsyncSession, conversation_id: str, **fields: Any) -> ChatMessage:
    """Adds a message with the next seq. The caller commits, then calls `announce`."""
    seq = await next_seq(db, conversation_id)
    message = ChatMessage(conversation_id=conversation_id, seq=seq, **fields)
    db.add(message)
    await db.flush()
    return message


async def announce(db: AsyncSession, message: ChatMessage, kind: str = "message") -> None:
    """Publishes a stored message (or an update to it) to everyone following the conversation."""
    from app.chat.serialize import message_out

    out = await message_out(db, message)
    events.publish(
        message.conversation_id, {"type": kind, "seq": message.seq, "message": out}, visible_to=message.visible_to
    )


async def add_member(
    db: AsyncSession,
    conversation: Conversation,
    *,
    user_id: str | None = None,
    agent_slug: str | None = None,
    is_admin: bool = False,
    can_see_history: bool = False,
) -> ConversationMember:
    query = select(ConversationMember).where(ConversationMember.conversation_id == conversation.id)
    query = (
        query.where(ConversationMember.user_id == user_id)
        if user_id
        else query.where(ConversationMember.agent_slug == agent_slug)
    )
    member = await db.scalar(query)
    if member is None:
        member = ConversationMember(
            conversation_id=conversation.id,
            user_id=user_id,
            agent_slug=agent_slug,
            is_admin=is_admin,
            joined_seq=conversation.last_seq,
            can_see_history=can_see_history,
            last_read_seq=conversation.last_seq,
        )
        db.add(member)
    else:
        member.left_at = None
        member.joined_seq = conversation.last_seq if not can_see_history else member.joined_seq
        member.can_see_history = member.can_see_history or can_see_history
        member.is_admin = member.is_admin or is_admin
    await db.flush()
    return member
