"""The LangGraph engine: one chat turn run by the in-process graph in app/runtime/graph.py.

Kept selectable through `runtime_engine` until the Dify comparison is done (FR-025), then deleted.
"""

import time
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import select

from app import tracing
from app.agents.service import ResolvedAgent, available_agents
from app.auth.models import User
from app.chat.models import ChatMessage, Conversation
from app.chat.router import HISTORY_MESSAGES, record_usage, sse
from app.classes import service as classes
from app.classes.models import ClassRoom
from app.config import get_settings
from app.db import session_factory
from app.llm.base import Message
from app.llm.registry import get_chat_model
from app.runtime.graph import GRAPH, RunContext

if TYPE_CHECKING:
    from app.chat.router import ChatIn


async def run_langgraph_turn(
    user_id: str,
    class_id: str | None,
    role: str,
    payload: "ChatIn",
    *,
    agents_override: list[ResolvedAgent] | None = None,
    kind: str = "chat",
) -> AsyncIterator[str]:
    """One chat turn through the in-process LangGraph graph (runtime_engine "langgraph")."""
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
        previous_agent = next((m.agent_slug for m in previous if m.role == "assistant" and m.agent_slug), None)
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
        )
        started = time.perf_counter()
        final: dict[str, Any] = {}
        with tracing.start_trace(
            kind,
            user_id=user.id,
            session_id=conversation.id,
            tags=[kind, role],
            metadata={"class_id": class_id, "message_id": message_id, "guard_mode": settings.guard_mode},
            input=payload.message,
        ) as trace:
            ctx.trace = trace
            try:
                async for mode, chunk in GRAPH.astream(
                    {
                        "ctx": ctx,
                        "text": payload.message,
                        "requested_agent": payload.agent,
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
                    "engine": "langgraph",
                    "route_reason": final.get("route_reason"),
                    "tools": final.get("tool_events", []),
                    "guard": [{"stage": e.stage, "verdict": e.verdict, "category": e.category} for e in ctx.events],
                    "latency_ms": int((time.perf_counter() - started) * 1000),
                },
            )
        )
        if reply_status == "blocked":
            user_message.status = "blocked"
        # Personal data the input guard redacted is not stored either.
        if final.get("text") and final["text"] != payload.message:
            user_message.content = final["text"]
        conversation.updated_at = datetime.now(UTC)
        record_usage(db, user.id, class_id, conversation.id, ctx.usage)
        await db.commit()
        if reply_status == "error" and not final.get("reply"):
            yield sse({"type": "error", "message_id": message_id, "message": reply})
        yield sse(
            {"type": "done", "message_id": message_id, "status": reply_status, "agent": agent.slug if agent else None}
        )
