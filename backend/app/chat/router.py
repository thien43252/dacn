"""Chat over Server-Sent Events. Event types match web/src/api-client/chatStream.ts:

operation -> conversation -> agent -> (text_delta | tool)* -> done, or notice/error in place of a reply.
"""

import json
import time
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import delete, select

from app.agents.service import ResolvedAgent, available_agents
from app.auth.deps import CurrentUser, DbSession
from app.auth.models import Role, User
from app.chat.models import ChatMessage, Conversation, UsageRecord
from app.classes import service as classes
from app.classes.models import ClassRoom
from app.db import session_factory
from app.llm.base import Message, Usage
from app.llm.registry import cost_usd, get_chat_model
from app.runtime.graph import GRAPH, RunContext

router = APIRouter(prefix="/chat", tags=["chat"])
HISTORY_MESSAGES = 12


class ChatIn(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    class_id: str | None = None
    conversation_id: str | None = None
    # Explicit agent choice from the UI; an @mention in the message works too.
    agent: str | None = None


class AgentOut(BaseModel):
    slug: str
    name: str
    description: str
    avatar: str
    source: str
    certification_status: str
    starter_prompts: list[str]


class ConversationOut(BaseModel):
    id: str
    class_id: str | None
    title: str
    updated_at: datetime


class MessageOut(BaseModel):
    id: str
    role: str
    content: str
    agent_slug: str | None
    status: str
    created_at: datetime
    meta: dict[str, Any]


def sse(event: dict[str, Any]) -> str:
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"


async def chat_context(db, user: User, class_id: str | None) -> tuple[ClassRoom | None, str]:
    if user.role == Role.ADMIN:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Tài khoản quản trị không dùng chat của lớp.")
    if class_id:
        return await classes.load_class(db, class_id, user)
    return None, user.role


@router.get("/agents", response_model=list[AgentOut])
async def list_agents(user: CurrentUser, db: DbSession, class_id: str | None = Query(default=None)) -> list[AgentOut]:
    room, role = await chat_context(db, user, class_id)
    return [
        AgentOut(
            slug=agent.slug,
            name=agent.manifest.name,
            description=agent.manifest.description,
            avatar=agent.manifest.avatar,
            source=agent.source,
            certification_status=agent.certification_status,
            starter_prompts=agent.manifest.starter_prompts,
        )
        for agent in await available_agents(db, user, room, role)
    ]


@router.get("/conversations", response_model=list[ConversationOut])
async def list_conversations(
    user: CurrentUser, db: DbSession, class_id: str | None = Query(default=None)
) -> list[ConversationOut]:
    query = select(Conversation).where(Conversation.user_id == user.id, Conversation.kind == "chat")
    query = query.where(Conversation.class_id == class_id) if class_id else query.where(Conversation.class_id.is_(None))
    rows = await db.scalars(query.order_by(Conversation.updated_at.desc()).limit(50))
    return [ConversationOut(id=c.id, class_id=c.class_id, title=c.title, updated_at=c.updated_at) for c in rows]


async def own_conversation(db, user: User, conversation_id: str) -> Conversation:
    conversation = await db.get(Conversation, conversation_id)
    if conversation is None or conversation.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Không tìm thấy cuộc trò chuyện.")
    return conversation


@router.get("/conversations/{conversation_id}/messages", response_model=list[MessageOut])
async def list_messages(conversation_id: str, user: CurrentUser, db: DbSession) -> list[MessageOut]:
    conversation = await own_conversation(db, user, conversation_id)
    rows = await db.scalars(
        select(ChatMessage).where(ChatMessage.conversation_id == conversation.id).order_by(ChatMessage.created_at)
    )
    return [
        MessageOut(
            id=m.id,
            role=m.role,
            content=m.content,
            agent_slug=m.agent_slug,
            status=m.status,
            created_at=m.created_at,
            meta=m.meta or {},
        )
        for m in rows
    ]


@router.delete("/conversations/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_conversation(conversation_id: str, user: CurrentUser, db: DbSession) -> None:
    conversation = await own_conversation(db, user, conversation_id)
    await db.execute(delete(Conversation).where(Conversation.id == conversation.id))
    await db.commit()


@router.post("/stream")
async def stream(payload: ChatIn, user: CurrentUser, db: DbSession) -> StreamingResponse:
    # Access is checked on the request session before streaming starts, so failures are plain HTTP errors.
    room, role = await chat_context(db, user, payload.class_id)
    if payload.conversation_id:
        conversation = await own_conversation(db, user, payload.conversation_id)
        if conversation.class_id != (room.id if room else None):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Cuộc trò chuyện thuộc lớp khác.")
    return StreamingResponse(
        run_turn(user.id, room.id if room else None, role, payload),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def record_usage(db, user_id: str, class_id: str | None, conversation_id: str, usage: list[tuple[str, Usage, int]]):
    for purpose, item, latency in usage:
        db.add(
            UsageRecord(
                user_id=user_id,
                class_id=class_id,
                conversation_id=conversation_id,
                purpose=purpose,
                provider=item.provider,
                model=item.model,
                input_tokens=item.input_tokens,
                output_tokens=item.output_tokens,
                cost_usd=cost_usd(item.model, item.input_tokens, item.output_tokens),
                latency_ms=latency,
            )
        )


async def run_turn(
    user_id: str,
    class_id: str | None,
    role: str,
    payload: ChatIn,
    *,
    agents_override: list[ResolvedAgent] | None = None,
    kind: str = "chat",
) -> AsyncIterator[str]:
    """One chat turn. The builder's sandbox passes `agents_override` (the draft) and kind="sandbox"."""
    message_id = str(uuid.uuid4())
    yield sse({"type": "operation", "operation_id": message_id, "resume_supported": False})
    async with session_factory()() as db:
        user = await db.get(User, user_id)
        room = await db.get(ClassRoom, class_id) if class_id else None
        assert user is not None

        # Consent gate: without a guardian's consent no agent sees the student's message, and it is not stored.
        if role == "student" and room is not None and not await classes.student_can_use_agents(db, room, user.id):
            yield sse(
                {
                    "type": "notice",
                    "message_id": message_id,
                    "kind": "consent_required",
                    "text": "Lớp này cần phụ huynh đồng ý trước khi em dùng agent. Hãy đưa mã liên kết trong mục "
                    "“Lớp của tôi” cho bố mẹ và nhờ bố mẹ bật đồng ý nhé.",
                }
            )
            yield sse({"type": "done", "message_id": message_id, "status": "consent_required"})
            return

        if payload.conversation_id:
            conversation = await db.get(Conversation, payload.conversation_id)
        else:
            conversation = Conversation(
                user_id=user.id, class_id=class_id, title=payload.message.strip()[:80], kind=kind
            )
            db.add(conversation)
            await db.flush()
        assert conversation is not None
        yield sse({"type": "conversation", "conversation_id": conversation.id})

        previous = list(
            await db.scalars(
                select(ChatMessage)
                .where(ChatMessage.conversation_id == conversation.id, ChatMessage.status == "ok")
                .order_by(ChatMessage.created_at.desc())
                .limit(HISTORY_MESSAGES)
            )
        )
        history = [
            Message(role=m.role, content=m.content) for m in reversed(previous) if m.role in ("user", "assistant")
        ]
        user_message = ChatMessage(conversation_id=conversation.id, role="user", content=payload.message)
        db.add(user_message)
        # Committed before the agent runs: tools use their own sessions, and the question survives a crashed turn.
        await db.commit()

        agents = agents_override or await available_agents(db, user, room, role)
        if not agents:
            yield sse({"type": "error", "message_id": message_id, "message": "Chưa có agent nào khả dụng."})
            yield sse({"type": "done", "message_id": message_id, "status": "error"})
            await db.commit()
            return

        ctx = RunContext(
            db=db,
            user=user,
            role=role,
            room=room,
            conversation=conversation,
            agents=agents,
            chat_model=get_chat_model(),
            message_id=message_id,
        )
        started = time.perf_counter()
        final: dict[str, Any] = {}
        try:
            async for mode, chunk in GRAPH.astream(
                {"ctx": ctx, "text": payload.message, "requested_agent": payload.agent, "history": history},
                stream_mode=["custom", "values"],
            ):
                if mode == "custom":
                    yield sse(chunk)
                else:
                    final = chunk
        except Exception as error:  # a crashed turn still ends the stream cleanly for the UI
            final = {"reply": "", "status": "error", "error": type(error).__name__}

        agent = final.get("agent")
        reply_status = final.get("status", "error")
        reply = final.get("reply") or (
            "Đã có lỗi khi tạo câu trả lời. Vui lòng thử lại." if reply_status == "error" else ""
        )
        db.add(
            ChatMessage(
                id=message_id,
                conversation_id=conversation.id,
                role="assistant",
                content=reply,
                agent_slug=agent.slug if agent else None,
                agent_version_id=agent.version_id if agent else None,
                status=reply_status,
                meta={
                    "route_reason": final.get("route_reason"),
                    "tools": final.get("tool_events", []),
                    "latency_ms": int((time.perf_counter() - started) * 1000),
                },
            )
        )
        if reply_status == "blocked":
            user_message.status = "blocked"
        conversation.updated_at = datetime.now(UTC)
        record_usage(db, user.id, class_id, conversation.id, ctx.usage)
        await db.commit()
        if reply_status == "error" and not final.get("reply"):
            yield sse({"type": "error", "message_id": message_id, "message": reply})
        yield sse(
            {"type": "done", "message_id": message_id, "status": reply_status, "agent": agent.slug if agent else None}
        )
