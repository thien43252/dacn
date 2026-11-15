"""What an agent remembers of a conversation (FR-045, FR-054, research R7).

Only messages the person who called the agent may see, without hidden content. The agent's own replies are
`assistant`; everyone else's words (other agents' verbatim handoff answers, other people in a group, people answering a
question) come as `user` turns prefixed with the speaker's name, so an agent never mistakes another's words for its own.
Consecutive `user` turns are merged so providers that want alternating roles accept the history.
"""

from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.models import User
from app.chat import visibility
from app.chat.models import ChatMessage, Conversation
from app.chat.serialize import agent_card
from app.llm.base import Message

HISTORY_MESSAGES = 12


async def build_history(
    db: AsyncSession,
    conversation: Conversation,
    viewer_id: str,
    agent_slug: str | None,
    *,
    before_seq: int | None = None,
    limit: int = HISTORY_MESSAGES,
) -> tuple[list[Message], str | None]:
    """(history, previous agent). `agent_slug` None: the auto-routing assistant (pre-feature direct chats)."""
    member = await visibility.membership(db, conversation, viewer_id)
    if member is None:
        return [], None
    query = visibility.visible_messages(conversation, member).where(
        ChatMessage.status == "ok", ChatMessage.role.in_(("user", "assistant"))
    )
    if before_seq is not None:
        query = query.where(ChatMessage.seq < before_seq)
    rows = list(await db.scalars(query.order_by(ChatMessage.seq.desc()).limit(limit)))
    rows = visibility.filter_visible(list(reversed(rows)), member, viewer_id)
    previous_agent = next(
        (m.agent_slug for m in reversed(rows) if m.role == "assistant" and m.agent_slug and not m.handoff_id), None
    )
    names: dict[str, str] = {}
    history: list[Message] = []
    for message in rows:
        own = (
            message.role == "assistant"
            and not message.handoff_id
            and (agent_slug is None or message.agent_slug == agent_slug)
        )
        if own:
            history.append(Message(role="assistant", content=message.content))
            continue
        if message.role == "user" and message.sender_user_id == viewer_id and not message.person_request_id:
            text = message.content
        else:
            key = message.sender_user_id or message.agent_slug or ""
            if key not in names:
                if message.sender_user_id:
                    person = await db.get(User, message.sender_user_id)
                    names[key] = person.name if person else "Người dùng"
                else:
                    card = await agent_card(db, message.agent_slug)
                    names[key] = card["name"] if card else (message.agent_slug or "Agent")
            text = f"[{names[key]}]: {message.content}"
        if history and history[-1].role == "user":
            history[-1] = Message(role="user", content=history[-1].content + "\n\n" + text)
        else:
            history.append(Message(role="user", content=text))
    # The history ends before the new user message, so a trailing user turn is merged into it by the caller.
    return history, previous_agent
