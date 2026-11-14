"""Chat over Server-Sent Events. Event types match web/src/api-client/chatStream.ts:

operation -> conversation -> agent -> (text_delta | tool)* -> done, or notice/error in place of a reply.
"""

import json
from collections.abc import AsyncIterator
from datetime import datetime
from typing import Annotated, Any, Literal

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
from app.llm.base import Usage
from app.llm.registry import cost_usd
from app.runtime import engine

router = APIRouter(prefix="/chat", tags=["chat"])


class ReplyIn(BaseModel):
    """An answer to the question card of a paused run (specs/002-multi-agent-orchestration/contracts/chat-sse.md).

    `message` of the request still carries the same answer as text: it is stored and goes through redaction and
    triage like every message (FR-037)."""

    run_id: str = Field(max_length=36)
    # clarify: {question id: answer}; unanswered questions are left out.
    answers: dict[str, Annotated[str, Field(max_length=500)]] = Field(default_factory=dict)
    # "Cứ làm luôn": go on with assumptions.
    skip_all: bool = False
    # confirm: the user's decision.
    decision: Literal["approve", "reject"] | None = None


class ChatIn(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    class_id: str | None = None
    conversation_id: str | None = None
    # Explicit agent choice from the UI; an @mention in the message works too.
    agent: str | None = None
    reply: ReplyIn | None = None


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


class StepNoteOut(BaseModel):
    key: str
    title: str
    agent: str
    status: str
    # visible · hidden · unavailable
    visibility: str
    note: str | None
    citations: list[dict[str, Any]]
    reason_text: str | None = None


@router.get("/messages/{message_id}/steps/{step_key}/note", response_model=StepNoteOut)
async def step_note(message_id: str, step_key: str, user: CurrentUser, db: DbSession) -> StepNoteOut:
    """One working note of a full-path answer, reviewed the first time it is opened (contracts/chat-sse.md, R9).
    Only the conversation's owner sees it; anyone else gets 404."""
    from app.orchestrator.models import RunStep, TurnRun  # the orchestrator imports this module
    from app.orchestrator.notes import review_note
    from app.runtime.dify_turn import make_client

    missing = HTTPException(status.HTTP_404_NOT_FOUND, "Không tìm thấy phần việc.")
    message = await db.get(ChatMessage, message_id)
    if message is None:
        raise missing
    conversation = await db.get(Conversation, message.conversation_id)
    run_id = (message.meta or {}).get("run_id")
    if conversation is None or conversation.user_id != user.id or not run_id:
        raise missing
    run = await db.get(TurnRun, run_id)
    step = await db.scalar(select(RunStep).where(RunStep.run_id == run_id, RunStep.key == step_key))
    if run is None or step is None or run.conversation_id != conversation.id:
        raise missing
    client = make_client()
    try:
        view = await review_note(db, client, conversation, message, run, step, user.role)
    finally:
        await client.http.aclose()
    return StepNoteOut(**view.__dict__)


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


def record_usage(
    db,
    user_id: str,
    class_id: str | None,
    conversation_id: str,
    usage: list[tuple[str, Usage, int]],
    path: str | None = None,
):
    """One usage_ledger row per model call. `path` is fast | full for chat turns (feature 002); purposes added by
    the full path: planner, step, synthesis, note_review."""
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
                cost_usd=item.cost_usd
                if item.cost_usd is not None
                else cost_usd(item.model, item.input_tokens, item.output_tokens),
                latency_ms=latency,
                path=path,
            )
        )


def run_turn(
    user_id: str,
    class_id: str | None,
    role: str,
    payload: ChatIn,
    *,
    agents_override: list[ResolvedAgent] | None = None,
    kind: str = "chat",
    force_path: str | None = None,
) -> AsyncIterator[str]:
    """One chat turn on the configured engine. The builder's sandbox passes `agents_override` (the draft) and
    kind="sandbox". `force_path` is internal (eval only, research R14) and never comes from a request."""
    return engine.run_turn(
        user_id, class_id, role, payload, agents_override=agents_override, kind=kind, force_path=force_path
    )
