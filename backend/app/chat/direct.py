"""Direct chats: one person and one agent, at most one open chat per person, agent and class (FR-048, FR-049)."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.models import User
from app.chat.models import Conversation
from app.chat.serialize import agent_card
from app.chat.service import add_member
from app.classes.models import ClassRoom


async def find_direct(db: AsyncSession, user: User, room: ClassRoom | None, agent_slug: str | None):
    query = select(Conversation).where(
        Conversation.kind == "direct",
        Conversation.user_id == user.id,
        Conversation.archived_at.is_(None),
    )
    query = query.where(Conversation.class_id == room.id) if room else query.where(Conversation.class_id.is_(None))
    query = (
        query.where(Conversation.direct_agent_slug == agent_slug)
        if agent_slug
        else query.where(Conversation.direct_agent_slug.is_(None))
    )
    return await db.scalar(query.order_by(Conversation.updated_at.desc()).limit(1))


async def open_direct(
    db: AsyncSession, user: User, room: ClassRoom | None, agent_slug: str | None, title: str | None = None
) -> Conversation:
    conversation = await find_direct(db, user, room, agent_slug)
    if conversation is not None:
        return conversation
    card = await agent_card(db, agent_slug) if agent_slug else None
    conversation = Conversation(
        user_id=user.id,
        class_id=room.id if room else None,
        kind="direct",
        direct_agent_slug=agent_slug,
        title=(title or (card["name"] if card else "Trợ lý"))[:200],
    )
    db.add(conversation)
    await db.flush()
    await add_member(db, conversation, user_id=user.id, is_admin=True, can_see_history=True)
    return conversation
