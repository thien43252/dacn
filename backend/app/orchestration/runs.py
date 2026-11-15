"""Saving, resolving and resuming runs that wait on handoffs, people or approvals (research R3).

A run that calls message_agent / ask_person (or reaches an action held for approval) gets an immediate tool result
("queued", "waiting") and finishes its turn normally; its transcript and the ids it waits on are then saved with
status "waiting". When every pending item is terminal the run becomes "resumable"; the worker claims it, appends one
platform message with the results and runs the agent again (FR-017). The asking agent therefore writes its conclusion
exactly once per wave of handoffs.
"""

import json
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.service import ResolvedAgent, available_agents
from app.auth.models import User
from app.chat.models import Conversation
from app.classes.models import ClassRoom
from app.llm.base import Message, ToolCall
from app.orchestration.models import AgentRun, ApprovalCard, Handoff, PersonRequest

TERMINAL = {
    "handoff": {"answered", "failed", "refused"},
    "person": {"answered", "expired", "cancelled", "undeliverable"},
    "approval": {"allowed", "denied", "expired"},
}
NOTE_HEADER = "[Thông báo của nền tảng, không phải lời người dùng] Các việc bạn đang chờ đã có kết quả:"


def dump_messages(messages: list[Message]) -> list[dict[str, Any]]:
    out = []
    for message in messages:
        out.append(
            {
                "role": message.role,
                "content": message.content,
                "tool_calls": [{"id": c.id, "name": c.name, "arguments": c.arguments} for c in message.tool_calls],
                "tool_call_id": message.tool_call_id,
                "is_error": message.is_error,
            }
        )
    return out


def load_messages(data: list[dict[str, Any]]) -> list[Message]:
    return [
        Message(
            role=item["role"],
            content=item.get("content", ""),
            tool_calls=[
                ToolCall(id=c["id"], name=c["name"], arguments=c.get("arguments", {}))
                for c in item.get("tool_calls", [])
            ],
            tool_call_id=item.get("tool_call_id"),
            is_error=item.get("is_error", False),
        )
        for item in data
    ]


async def ensure_run(ctx, agent: ResolvedAgent) -> AgentRun:
    """The run row for this agent's turn, created the first time a meta tool needs it."""
    if ctx.run is not None:
        return ctx.run
    run = AgentRun(
        conversation_id=ctx.conversation.id,
        user_id=ctx.user.id,
        role=ctx.role,
        class_id=ctx.room.id if ctx.room else None,
        agent_slug=agent.slug,
        agent_version_id=agent.version_id,
        depth=ctx.depth,
        chain=list(ctx.chain),
        root_run_id=ctx.root_run_id,
        message_id=ctx.message_id,
        transcript=[],
        pending={},
        status="running",
        source=ctx.source,
        user_text=ctx.user_text or "",
    )
    ctx.db.add(run)
    await ctx.db.flush()
    ctx.run = run
    return run


async def item_status(db: AsyncSession, item: dict[str, Any]) -> str | None:
    model = {"handoff": Handoff, "person": PersonRequest, "approval": ApprovalCard}[item["type"]]
    row = await db.get(model, item["id"])
    return row.status if row else None


async def is_resolved(db: AsyncSession, run: AgentRun) -> bool:
    for item in (run.pending or {}).get("items", []):
        if await item_status(db, item) not in TERMINAL[item["type"]]:
            return False
    return True


async def save_waiting(ctx, transcript: list[Message], waits: list[dict[str, Any]]) -> AgentRun:
    run = ctx.run
    assert run is not None
    run.transcript = dump_messages(transcript)
    existing = (run.pending or {}).get("items", [])
    run.pending = {"items": [*existing, *waits]}
    run.status = "waiting"
    await ctx.db.flush()
    if await is_resolved(ctx.db, run):
        run.status = "resumable"
        await ctx.db.flush()
    return run


async def add_pending(db: AsyncSession, run_id: str, item: dict[str, Any]) -> None:
    run = await db.get(AgentRun, run_id, with_for_update=True)
    if run is None:
        return
    items = (run.pending or {}).get("items", [])
    run.pending = {"items": [*items, item]}
    await db.flush()


async def try_mark_resumable(db: AsyncSession, run_id: str | None) -> bool:
    """Called after any pending item changes; safe to call twice (conditional update)."""
    if not run_id:
        return False
    run = await db.get(AgentRun, run_id)
    if run is None or run.status != "waiting":
        return False
    await db.refresh(run)
    if not await is_resolved(db, run):
        return False
    result = await db.execute(
        update(AgentRun).where(AgentRun.id == run_id, AgentRun.status == "waiting").values(status="resumable")
    )
    await db.flush()
    return result.rowcount == 1


async def resolution_note(db: AsyncSession, run: AgentRun) -> str:
    """One platform message listing what the run waited for, in the order it asked."""
    from app.orchestration import approvals

    lines = [NOTE_HEADER]
    for item in (run.pending or {}).get("items", []):
        if item.get("noted"):
            continue
        if item["type"] == "handoff":
            handoff = await db.get(Handoff, item["id"])
            if handoff is None:
                continue
            if handoff.status == "answered" and handoff.answer_visible is not False:
                result = {"status": "answered", "agent": handoff.to_agent, "answer": handoff.answer}
            elif handoff.status == "answered":
                result = {
                    "status": "hidden",
                    "agent": handoff.to_agent,
                    "note": "Câu trả lời đã bị ẩn theo chính sách lớp.",
                }
            elif handoff.status == "refused":
                result = {"status": "refused", "agent": handoff.to_agent}
            else:
                result = {"status": "no_answer", "agent": handoff.to_agent}
        elif item["type"] == "person":
            request = await db.get(PersonRequest, item["id"])
            if request is None:
                continue
            if request.status == "answered":
                by = await db.get(User, request.answered_by) if request.answered_by else None
                result = {
                    "status": "answered",
                    "by": by.name if by else "",
                    "answer": "Câu trả lời đã bị ẩn." if request.answer_hidden else request.answer,
                }
            else:
                result = {"status": request.status}
        else:
            card = await db.get(ApprovalCard, item["id"])
            if card is None:
                continue
            if card.tool == "ask_person" and card.status == "allowed":
                continue  # the question itself is listed as its own item
            result = {"status": card.status, "tool": card.tool, "note": approvals.result_text(card)}
            if card.preview.get("result"):
                result["result"] = card.preview["result"]
        lines.append(json.dumps(result, ensure_ascii=False))
    lines.append(
        "Hãy viết phần kết luận cho người dùng: dẫn tới các câu trả lời trên (không chép lại nguyên văn), nói rõ phần "
        "nào chưa làm được hoặc chưa kiểm chứng được, và ghi tên các agent đã đóng góp."
    )
    return "\n".join(lines)


async def mark_noted(db: AsyncSession, run: AgentRun) -> None:
    items = [{**item, "noted": True} for item in (run.pending or {}).get("items", [])]
    run.pending = {"items": items}
    await db.flush()


async def build_context(db: AsyncSession, run: AgentRun, agent_slug: str | None = None, **overrides: Any):
    """A RunContext rebuilt as the origin user (FR-010): their role, class policy and available agents."""
    from app.config import get_settings
    from app.llm.registry import get_chat_model
    from app.runtime.graph import RunContext

    user = await db.get(User, run.user_id)
    room = await db.get(ClassRoom, run.class_id) if run.class_id else None
    conversation = await db.get(Conversation, run.conversation_id)
    if user is None or conversation is None:
        return None, None
    agents = await available_agents(db, user, room, run.role)
    slug = agent_slug or run.agent_slug
    agent = next((candidate for candidate in agents if candidate.slug == slug), None)
    settings = get_settings()
    fields = {
        "db": db,
        "user": user,
        "role": run.role,
        "room": room,
        "conversation": conversation,
        "agents": agents,
        "chat_model": get_chat_model(),
        "message_id": run.message_id or "",
        "source": run.source,
        "guard_mode": settings.guard_mode,
        "router_mode": settings.router_mode,
        "conversation_kind": conversation.kind,
        "depth": run.depth,
        "chain": list(run.chain or []),
        "root_run_id": run.root_run_id or run.id,
        "run": run,
        "stream": False,
        "user_text": run.user_text,
    }
    fields.update(overrides)
    return RunContext(**fields), agent


async def resumable_ids(db: AsyncSession, limit: int = 20) -> list[str]:
    return list(
        await db.scalars(
            select(AgentRun.id).where(AgentRun.status == "resumable").order_by(AgentRun.updated_at).limit(limit)
        )
    )
