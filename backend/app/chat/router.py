"""Chat: the Messenger-style conversation list, direct chats, group turns and the SSE turn stream.

Turn stream event types match web/src/api-client/chatStream.ts:
operation -> conversation -> agent -> (text_delta | tool | handoff)* -> done, or notice/error in place of a reply.
Messages that arrive later (handoff answers, conclusions, other people in a group) come through the per-conversation
event stream in app/chat/events.py.
"""

import asyncio
import json
import time
import uuid
from collections import defaultdict
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import delete, select

from app import tracing
from app.agents.service import ResolvedAgent, available_agents
from app.auth.deps import CurrentUser, DbSession
from app.auth.models import Role, User
from app.chat import service as chat_service
from app.chat import visibility
from app.chat.direct import open_direct
from app.chat.history import build_history
from app.chat.models import ChatMessage, Conversation, ConversationMember, UsageRecord
from app.chat.serialize import conversation_out, message_out
from app.classes import service as classes
from app.classes.models import ClassRoom
from app.config import get_settings
from app.db import session_factory
from app.guard import rules
from app.llm.base import Message, Usage
from app.llm.registry import cost_usd, get_chat_model
from app.runtime.graph import GRAPH, INPUT_BLOCKED, RunContext
from app.runtime.router import route_group

router = APIRouter(prefix="/chat", tags=["chat"])
HISTORY_MESSAGES = 12
# Turns in one group run one at a time, in arrival order.
_group_locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)


class ChatIn(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    class_id: str | None = None
    conversation_id: str | None = None
    # Explicit agent choice from the UI for a new direct chat; an @mention in the message works too.
    agent: str | None = None


class DirectIn(BaseModel):
    class_id: str | None = None
    agent: str | None = None


class ReadIn(BaseModel):
    seq: int = Field(ge=0)


class AgentOut(BaseModel):
    slug: str
    name: str
    description: str
    avatar: str
    source: str
    certification_status: str
    starter_prompts: list[str]


def sse(event: dict[str, Any]) -> str:
    return f"data: {json.dumps(event, ensure_ascii=False, default=str)}\n\n"


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


@router.get("/conversations")
async def list_conversations(
    user: CurrentUser,
    db: DbSession,
    class_id: str | None = Query(default=None),
    all: bool = Query(default=False),
    q: str = Query(default="", max_length=80),
) -> list[dict[str, Any]]:
    """Direct chats and groups the user is in, newest first (FR-049). `all=true` lists every class and the personal
    space; otherwise `class_id` (or the personal space when absent)."""
    query = select(Conversation).where(
        visibility.is_member_condition(user.id),
        Conversation.kind.in_(("direct", "group")),
        Conversation.archived_at.is_(None),
    )
    if not all:
        query = (
            query.where(Conversation.class_id == class_id) if class_id else query.where(Conversation.class_id.is_(None))
        )
    if q.strip():
        query = query.where(Conversation.title.ilike(f"%{q.strip()}%"))
    rows = list(await db.scalars(query.order_by(Conversation.updated_at.desc()).limit(100)))
    return [await conversation_out(db, conversation, user.id) for conversation in rows]


@router.post("/direct")
async def open_direct_chat(payload: DirectIn, user: CurrentUser, db: DbSession) -> dict[str, Any]:
    room, role = await chat_context(db, user, payload.class_id)
    if payload.agent:
        usable = {agent.slug for agent in await available_agents(db, user, room, role)}
        if payload.agent not in usable:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Agent không dùng được ở đây.")
    conversation = await open_direct(db, user, room, payload.agent)
    await db.commit()
    return await conversation_out(db, conversation, user.id)


def _same_direct_sessions(user: User, conversation: Conversation):
    """Every direct chat (open or closed) this user had with the same agent in the same class or personal space."""
    return select(Conversation).where(
        Conversation.kind == "direct",
        Conversation.user_id == user.id,
        Conversation.class_id.is_(None)
        if conversation.class_id is None
        else Conversation.class_id == conversation.class_id,
        Conversation.direct_agent_slug.is_(None)
        if conversation.direct_agent_slug is None
        else Conversation.direct_agent_slug == conversation.direct_agent_slug,
    )


@router.post("/direct/{conversation_id}/restart")
async def restart_direct(conversation_id: str, user: CurrentUser, db: DbSession) -> dict[str, Any]:
    conversation, _ = await visibility.viewable(db, user, conversation_id)
    if conversation.kind != "direct":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Chỉ bắt đầu lại được chat riêng.")
    # Close every open session with this agent (older auto-routed chats may have several) so one stays open.
    now = datetime.now(UTC)
    for other in await db.scalars(_same_direct_sessions(user, conversation).where(Conversation.archived_at.is_(None))):
        other.archived_at = now
    room = await db.get(ClassRoom, conversation.class_id) if conversation.class_id else None
    await db.flush()
    fresh = await open_direct(db, user, room, conversation.direct_agent_slug)
    await db.commit()
    return await conversation_out(db, fresh, user.id)


@router.get("/direct/{conversation_id}/sessions")
async def direct_sessions(conversation_id: str, user: CurrentUser, db: DbSession) -> list[dict[str, Any]]:
    """Past and current sessions with the agent of this direct chat, newest first (the history drawer)."""
    conversation, _ = await visibility.viewable(db, user, conversation_id)
    if conversation.kind != "direct":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Chỉ chat riêng mới có lịch sử phiên.")
    rows = list(
        await db.scalars(_same_direct_sessions(user, conversation).order_by(Conversation.updated_at.desc()).limit(50))
    )
    out = []
    for row in rows:
        item = await conversation_out(db, row, user.id)
        item["archived"] = row.archived_at is not None
        out.append(item)
    return out


@router.post("/direct/{conversation_id}/resume")
async def resume_direct(conversation_id: str, user: CurrentUser, db: DbSession) -> dict[str, Any]:
    """Make a past session the open one again; the session open before it moves to history."""
    conversation, _ = await visibility.viewable(db, user, conversation_id)
    if conversation.kind != "direct":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Chỉ mở lại được chat riêng.")
    now = datetime.now(UTC)
    for other in await db.scalars(
        _same_direct_sessions(user, conversation).where(
            Conversation.archived_at.is_(None), Conversation.id != conversation.id
        )
    ):
        other.archived_at = now
    conversation.archived_at = None
    await db.commit()
    return await conversation_out(db, conversation, user.id)


@router.get("/conversations/{conversation_id}")
async def get_conversation(conversation_id: str, user: CurrentUser, db: DbSession) -> dict[str, Any]:
    conversation, _ = await visibility.viewable(db, user, conversation_id)
    return await conversation_out(db, conversation, user.id)


@router.get("/conversations/{conversation_id}/messages")
async def list_messages(
    conversation_id: str,
    user: CurrentUser,
    db: DbSession,
    before: int | None = Query(default=None),
    limit: int = Query(default=200, ge=1, le=500),
) -> list[dict[str, Any]]:
    conversation, member = await visibility.viewable(db, user, conversation_id)
    query = visibility.visible_messages(conversation, member)
    if before is not None:
        query = query.where(ChatMessage.seq < before)
    rows = list(await db.scalars(query.order_by(ChatMessage.seq.desc()).limit(limit)))
    rows = visibility.filter_visible(list(reversed(rows)), member, user.id)
    return [await message_out(db, message, user.id) for message in rows]


@router.post("/conversations/{conversation_id}/read", status_code=status.HTTP_204_NO_CONTENT)
async def mark_read(conversation_id: str, payload: ReadIn, user: CurrentUser, db: DbSession) -> None:
    conversation, member = await visibility.viewable(db, user, conversation_id)
    if member.id is None:  # legacy direct chat without a member row
        member = await chat_service.add_member(db, conversation, user_id=user.id, is_admin=True, can_see_history=True)
    member.last_read_seq = max(member.last_read_seq, min(payload.seq, conversation.last_seq))
    await db.commit()


@router.delete("/conversations/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_conversation(conversation_id: str, user: CurrentUser, db: DbSession) -> None:
    conversation, _ = await visibility.viewable(db, user, conversation_id)
    if conversation.kind == "group":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Hãy rời nhóm thay vì xoá nhóm.")
    await db.execute(delete(Conversation).where(Conversation.id == conversation.id))
    await db.commit()


@router.post("/stream")
async def stream(payload: ChatIn, user: CurrentUser, db: DbSession) -> StreamingResponse:
    # Access is checked on the request session before streaming starts, so failures are plain HTTP errors.
    room, role = await chat_context(db, user, payload.class_id)
    if payload.conversation_id:
        conversation, _ = await visibility.viewable(db, user, payload.conversation_id)
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

        # Consent gate (FR-005): without a guardian's consent no agent sees the student's message. Outside a group the
        # message is not stored either; in a group the student still talks with the people there (edge case: consent
        # withdrawn), only no agent answers.
        # The account's role, not the one a teacher previews in the sandbox ("as_role": "student").
        consented = user.role != Role.STUDENT or await classes.student_may_use_agents(db, user.id, room)
        existing = await db.get(Conversation, payload.conversation_id) if payload.conversation_id else None
        if not consented and not (existing is not None and existing.kind == "group"):
            text = (
                "Lớp này cần phụ huynh đồng ý trước khi em dùng agent. Hãy đưa mã liên kết trong mục "
                "“Lớp của tôi” cho bố mẹ và nhờ bố mẹ bật đồng ý nhé."
                if room is not None
                else "Em cần phụ huynh đồng ý trước khi dùng agent. Hãy đưa mã liên kết cho bố mẹ và nhờ bố mẹ bật "
                "đồng ý trong mục “Đồng ý & quyền riêng tư” nhé."
            )
            yield sse(
                {
                    "type": "notice",
                    "message_id": message_id,
                    "kind": "consent_required",
                    "text": text,
                }
            )
            yield sse({"type": "done", "message_id": message_id, "status": "consent_required"})
            return

        if payload.conversation_id:
            conversation = await db.get(Conversation, payload.conversation_id)
        elif kind == "sandbox":
            conversation = Conversation(
                user_id=user.id, class_id=class_id, title=payload.message.strip()[:80], kind="sandbox"
            )
            db.add(conversation)
            await db.flush()
        elif payload.agent:
            conversation = await open_direct(db, user, room, payload.agent)
        else:
            # A new auto-routed chat, as before the feature (the orchestrator picks an agent per message).
            conversation = Conversation(
                user_id=user.id, class_id=class_id, title=payload.message.strip()[:80], kind="direct"
            )
            db.add(conversation)
            await db.flush()
            await chat_service.add_member(db, conversation, user_id=user.id, is_admin=True, can_see_history=True)
        assert conversation is not None
        yield sse({"type": "conversation", "conversation_id": conversation.id})

        if conversation.kind == "group":
            async with _group_locks[conversation.id]:
                async for chunk in _group_turn(
                    db, user, role, room, conversation, payload, message_id, agents_allowed=consented
                ):
                    yield chunk
            return

        requested = conversation.direct_agent_slug or payload.agent
        history, previous_agent = await build_history(db, conversation, user.id, conversation.direct_agent_slug)
        user_message = await chat_service.add_message(
            db, conversation.id, role="user", content=payload.message, sender_user_id=user.id
        )
        # Committed before the agent runs: tools use their own sessions, and the question survives a crashed turn.
        await db.commit()

        agents = agents_override or await available_agents(db, user, room, role)
        if not agents:
            yield sse({"type": "error", "message_id": message_id, "message": "Chưa có agent nào khả dụng."})
            yield sse({"type": "done", "message_id": message_id, "status": "error"})
            await db.commit()
            return
        async for chunk in _agent_turn(
            db,
            user,
            role,
            room,
            conversation,
            agents,
            payload.message,
            user_message,
            message_id,
            requested=requested,
            previous_agent=previous_agent,
            history=history,
            kind=kind,
        ):
            yield chunk


async def _agent_turn(
    db,
    user: User,
    role: str,
    room: ClassRoom | None,
    conversation: Conversation,
    agents: list[ResolvedAgent],
    text: str,
    user_message: ChatMessage,
    message_id: str,
    *,
    requested: str | None,
    previous_agent: str | None,
    history: list[Message],
    kind: str,
) -> AsyncIterator[str]:
    from app.orchestration import runs
    from app.runtime.run import announce_after_commit

    settings = get_settings()
    ctx = RunContext(
        db=db,
        user=user,
        role=role,
        room=room,
        conversation=conversation,
        agents=agents,
        chat_model=get_chat_model(),
        message_id=message_id,
        source=kind,
        guard_mode=settings.guard_mode,
        router_mode=settings.router_mode,
        conversation_kind=conversation.kind,
        user_text=text,
    )
    started = time.perf_counter()
    final: dict[str, Any] = {}
    with tracing.start_trace(
        kind,
        user_id=user.id,
        session_id=conversation.id,
        tags=[kind, role],
        metadata={"class_id": room.id if room else None, "message_id": message_id, "guard_mode": settings.guard_mode},
        input=text,
    ) as trace:
        ctx.trace = trace
        try:
            async for mode, chunk in GRAPH.astream(
                {
                    "ctx": ctx,
                    "text": text,
                    "requested_agent": requested,
                    "previous_agent": previous_agent,
                    "history": history,
                },
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
        if trace is not None:
            trace.update(
                output=reply,
                level={"blocked": "WARNING", "error": "ERROR"}.get(reply_status),
                status_message=final.get("error") or final.get("blocked_stage"),
                metadata={"status": reply_status, "agent": agent.slug if agent else None},
            )
    # A safety reply in a group is only for the person who wrote (FR-053).
    support_only = conversation.kind == "group" and (
        (reply_status == "blocked" and not agent) or bool(final.get("support"))
    )
    assistant = await chat_service.add_message(
        db,
        conversation.id,
        id=message_id,
        role="assistant",
        content=reply,
        agent_slug=agent.slug if agent else None,
        agent_version_id=agent.version_id if agent else None,
        status=reply_status,
        run_id=ctx.run.id if ctx.run else None,
        visible_to=[user.id] if support_only else None,
        meta={
            "route_reason": final.get("route_reason"),
            "tools": final.get("tool_events", []),
            "guard": [{"stage": e.stage, "verdict": e.verdict, "category": e.category} for e in ctx.events],
            "latency_ms": int((time.perf_counter() - started) * 1000),
        },
    )
    if reply_status == "blocked":
        user_message.status = "blocked"
    # Personal data the input guard redacted is not stored either.
    if final.get("text") and final["text"] != text:
        user_message.content = final["text"]
    if ctx.run is not None:
        if ctx.waits:
            await runs.save_waiting(ctx, ctx.transcript, ctx.waits)
        else:
            ctx.run.status = "done"
    conversation.updated_at = datetime.now(UTC)
    record_usage(db, user.id, room.id if room else None, conversation.id, ctx.usage)
    await db.commit()
    if reply_status == "error" and not final.get("reply"):
        yield sse({"type": "error", "message_id": message_id, "message": reply})
    yield sse(
        {
            "type": "done",
            "message_id": message_id,
            "status": reply_status,
            "agent": agent.slug if agent else None,
            "seq": assistant.seq,
            "waiting": bool(ctx.waits),
        }
    )
    # The sender already has the turn; other members and other tabs get it from the conversation stream.
    try:
        await chat_service.announce(db, user_message, "message_update")
        await chat_service.announce(db, assistant)
        await announce_after_commit(ctx)
    except Exception:  # best effort: clients replay from the database
        pass


async def group_agents(db, conversation: Conversation, user: User, room: ClassRoom | None, role: str):
    members = set(
        await db.scalars(
            select(ConversationMember.agent_slug).where(
                ConversationMember.conversation_id == conversation.id,
                ConversationMember.agent_slug.is_not(None),
                ConversationMember.left_at.is_(None),
            )
        )
    )
    return [agent for agent in await available_agents(db, user, room, role) if agent.slug in members]


async def _group_turn(
    db,
    user: User,
    role: str,
    room: ClassRoom | None,
    conversation: Conversation,
    payload: ChatIn,
    message_id: str,
    *,
    agents_allowed: bool = True,
) -> AsyncIterator[str]:
    """A message in a group: stored and shown to every member; an agent answers only when routed to (FR-043)."""
    from app.audit.models import GuardEvent

    text = payload.message
    verdict = rules.screen_input(text)
    if verdict.action != "allow":
        excerpt, _ = rules.redact(text)
        db.add(
            GuardEvent(
                source="chat",
                class_id=room.id if room else None,
                user_id=user.id,
                role=role,
                conversation_id=conversation.id,
                message_id=message_id,
                stage="input",
                verdict=verdict.action,
                category=verdict.category,
                detector=verdict.detector,
                severity=verdict.severity,
                reason=verdict.reason[:300],
                excerpt=excerpt[:300],
                private_space=True,
            )
        )
    if verdict.blocks:
        notice = rules.SELF_HARM_REPLY if verdict.category == "self_harm" else INPUT_BLOCKED
        safety = await chat_service.add_message(
            db, conversation.id, role="assistant", content=notice, status="blocked", visible_to=[user.id]
        )
        await db.commit()
        await chat_service.announce(db, safety)
        yield sse({"type": "notice", "message_id": message_id, "kind": "guard_blocked", "text": notice})
        yield sse({"type": "done", "message_id": message_id, "status": "blocked"})
        return
    if verdict.action == "redact" and verdict.text:
        text = verdict.text
    history, previous_agent = await build_history(db, conversation, user.id, None)
    user_message = await chat_service.add_message(
        db, conversation.id, role="user", content=text, sender_user_id=user.id
    )
    await db.commit()
    await chat_service.announce(db, user_message)

    if not agents_allowed:
        if verdict.action == "support":
            # Without consent no agent answers, but a wellbeing signal still gets the support line, privately.
            support = await chat_service.add_message(
                db, conversation.id, role="assistant", content=rules.SELF_HARM_REPLY, visible_to=[user.id]
            )
            await db.commit()
            await chat_service.announce(db, support)
        yield sse({"type": "done", "message_id": message_id, "status": "ok", "agent": None, "seq": user_message.seq})
        return
    agents = await group_agents(db, conversation, user, room, role)
    chosen = await route_group(
        text,
        agents,
        people=await _member_names(db, conversation),
        default=conversation.default_agent_slug,
        role=role,
        model=get_chat_model(),
        mode=get_settings().router_mode,
    )
    if chosen is None and verdict.action == "support" and agents:
        # A wellbeing signal always gets the supportive reply, shown only to the writer (FR-053).
        chosen = next((a for a in agents if a.slug == conversation.default_agent_slug), agents[0])
    if chosen is None:
        yield sse({"type": "done", "message_id": message_id, "status": "ok", "agent": None, "seq": user_message.seq})
        return
    history, _ = await build_history(db, conversation, user.id, chosen.slug, before_seq=user_message.seq)
    async for chunk in _agent_turn(
        db,
        user,
        role,
        room,
        conversation,
        agents,
        text,
        user_message,
        message_id,
        requested=chosen.slug,
        previous_agent=previous_agent,
        history=history,
        kind="chat",
    ):
        yield chunk


async def _member_names(db, conversation: Conversation) -> list[str]:
    rows = await db.scalars(
        select(User.name)
        .join(ConversationMember, ConversationMember.user_id == User.id)
        .where(ConversationMember.conversation_id == conversation.id, ConversationMember.left_at.is_(None))
    )
    return list(rows)
