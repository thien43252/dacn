"""Per-conversation event bus and the SSE endpoint that replays and follows a conversation.

The bus is in memory (one backend process, research R2). A client that reconnects passes `after=<seq>` and gets every
stored message it may see since then, so nothing is lost when the connection drops; live events follow. Stored
messages carry `seq`, and the client drops anything at or below the highest `seq` it has, so a replay never duplicates.
"""

import asyncio
import json
from collections import defaultdict
from collections.abc import AsyncIterator
from typing import Any

from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse

from app.auth.deps import CurrentUser, DbSession
from app.chat import visibility
from app.chat.models import ChatMessage
from app.db import session_factory

router = APIRouter(prefix="/chat", tags=["chat"])
PING_SECONDS = 20.0


class _Listener:
    def __init__(self, user_id: str) -> None:
        self.user_id = user_id
        self.queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=1000)


_listeners: dict[str, set[_Listener]] = defaultdict(set)


def publish(conversation_id: str, event: dict[str, Any], visible_to: list[str] | None = None) -> None:
    """Sends an event to everyone following the conversation (or only to `visible_to`)."""
    for listener in list(_listeners.get(conversation_id, ())):
        if visible_to is not None and listener.user_id not in visible_to:
            continue
        try:
            listener.queue.put_nowait(event)
        except asyncio.QueueFull:  # a stuck client misses live events; it replays from the DB on reconnect
            pass


def listener_count(conversation_id: str) -> int:
    return len(_listeners.get(conversation_id, ()))


def sse(event: dict[str, Any]) -> str:
    return f"data: {json.dumps(event, ensure_ascii=False, default=str)}\n\n"


async def _follow(conversation_id: str, user_id: str, after: int) -> AsyncIterator[str]:
    from app.chat.serialize import message_out

    listener = _Listener(user_id)
    _listeners[conversation_id].add(listener)
    try:
        async with session_factory()() as db:
            conversation, member = await visibility.viewable(db, await _user(db, user_id), conversation_id)
            rows = await db.scalars(
                visibility.visible_messages(conversation, member)
                .where(ChatMessage.seq > after)
                .order_by(ChatMessage.seq)
            )
            for message in visibility.filter_visible(list(rows), member, user_id):
                out = await message_out(db, message, user_id)
                yield sse({"type": "message", "seq": message.seq, "message": out})
        yield sse({"type": "ready"})
        while True:
            try:
                event = await asyncio.wait_for(listener.queue.get(), timeout=PING_SECONDS)
            except TimeoutError:
                yield sse({"type": "ping"})
                continue
            yield sse(event)
    finally:
        _listeners[conversation_id].discard(listener)
        if not _listeners[conversation_id]:
            _listeners.pop(conversation_id, None)


async def _user(db, user_id: str):
    from app.auth.models import User

    return await db.get(User, user_id)


@router.get("/conversations/{conversation_id}/events")
async def events(conversation_id: str, user: CurrentUser, db: DbSession, after: int = Query(default=0, ge=0)):
    # Access is checked before streaming so outsiders get a plain 404.
    await visibility.viewable(db, user, conversation_id)
    return StreamingResponse(
        _follow(conversation_id, user.id, after),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


async def stored_events(db, conversation_id: str, user_id: str, after: int = 0) -> list[dict[str, Any]]:
    """The replay part of the stream, for tests and for clients that poll."""
    from app.chat.serialize import message_out

    conversation, member = await visibility.viewable(db, await _user(db, user_id), conversation_id)
    rows = await db.scalars(
        visibility.visible_messages(conversation, member).where(ChatMessage.seq > after).order_by(ChatMessage.seq)
    )
    return [
        {"type": "message", "seq": m.seq, "message": await message_out(db, m, user_id)}
        for m in visibility.filter_visible(list(rows), member, user_id)
    ]
