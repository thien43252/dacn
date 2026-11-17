"""Finishing and resuming runs outside the user's own request (worker side).

`finish_run` ends any background run: an asked agent's answer becomes the verbatim handoff message; a resumed or
forwarded run's reply becomes a new message of that agent in the conversation. A run that waits again is saved.
"""

import logging
import time
import uuid
from typing import Any

from sqlalchemy import select, update

from app import tracing
from app.chat import service as chat_service
from app.chat.history import build_history
from app.chat.models import ChatMessage
from app.config import get_settings
from app.db import session_factory
from app.orchestration import handoffs, runs
from app.orchestration.models import AgentRun, ApprovalCard, Handoff, PersonRequest

log = logging.getLogger("eduagent.runs")
ERROR_TEXT = "Đã có lỗi khi tạo câu trả lời. Vui lòng thử lại."


def record_usage(ctx) -> None:
    from app.chat.router import record_usage as write_usage

    write_usage(ctx.db, ctx.user.id, ctx.room.id if ctx.room else None, ctx.conversation.id, ctx.usage)
    ctx.usage = []


async def announce_after_commit(ctx) -> None:
    """Publishes what the run created (handoff statuses, cards, questions) once it is committed."""
    db = ctx.db
    for kind, item_id in ctx.after_commit:
        try:
            if kind == "handoff":
                handoff = await db.get(Handoff, item_id)
                if handoff is not None:
                    handoffs.publish_status(handoff)
                continue
            column = {
                "card": ChatMessage.approval_card_id,
                "request": ChatMessage.person_request_id,
                "message": ChatMessage.id,
            }[kind]
            message = await db.scalar(select(ChatMessage).where(column == item_id).order_by(ChatMessage.seq).limit(1))
            if message is not None:
                await chat_service.announce(db, message)
        except Exception:  # announcing is best effort; clients replay from the database
            log.exception("could not announce %s %s", kind, item_id)
    ctx.after_commit = []


async def finish_run(ctx, agent, final: dict[str, Any]) -> None:
    db = ctx.db
    run: AgentRun | None = ctx.run
    status = final.get("status", "error")
    reply = final.get("reply") or ""
    record_usage(ctx)
    if run is None:
        await db.commit()
        return
    if run.handoff_id:
        handoff = await db.get(Handoff, run.handoff_id)
        if handoff is None:
            await db.commit()
            return
        if ctx.waits:
            await runs.save_waiting(ctx, ctx.transcript, ctx.waits)
            handoff.lease_until = None  # running, waiting on its own handoffs: not reclaimed by the lease sweep
            await db.commit()
            await announce_after_commit(ctx)
            return
        if status == "error":
            run.status = "failed"
            await handoffs.fail(db, handoff, final=handoff.attempts >= get_settings().handoff_max_attempts)
            return
        await handoffs.complete(ctx, handoff, reply or "(Không có nội dung.)", status == "ok", run)
        await announce_after_commit(ctx)
        return
    message = await chat_service.add_message(
        db,
        ctx.conversation.id,
        id=ctx.message_id,
        role="assistant",
        content=reply or (ERROR_TEXT if status == "error" else ""),
        agent_slug=agent.slug if agent else None,
        agent_version_id=agent.version_id if agent else None,
        status="ok" if status == "ok" else ("blocked" if status == "blocked" else "error"),
        run_id=run.id,
        meta={"resumed": True, "tools": final.get("tool_events", [])},
    )
    if ctx.waits:
        await runs.save_waiting(ctx, ctx.transcript, ctx.waits)
    else:
        run.status = "done" if status != "error" else "failed"
        run.transcript = runs.dump_messages(ctx.transcript)
    await db.commit()
    await chat_service.announce(db, message)
    await announce_after_commit(ctx)


async def claim_run(db, run_id: str) -> bool:
    result = await db.execute(
        update(AgentRun).where(AgentRun.id == run_id, AgentRun.status == "resumable").values(status="running")
    )
    await db.commit()
    return result.rowcount == 1


async def resume(run_id: str) -> None:
    """Worker entry: continues a resumable run (FR-017) or runs a forwarded question (reply_privately)."""
    from app.runtime.graph import GRAPH, RESUME_GRAPH

    async with session_factory()() as db:
        if not await claim_run(db, run_id):
            return
        run = await db.get(AgentRun, run_id)
        ctx, agent = await runs.build_context(db, run, message_id=str(uuid.uuid4()))
        if ctx is None:
            run.status = "failed"
            await db.commit()
            return
        if agent is None:
            # The agent was removed from the class while the run waited.
            if not run.handoff_id:
                message = await chat_service.add_message(
                    db,
                    run.conversation_id,
                    role="system",
                    content="Agent này không còn dùng được ở đây nên việc đang chờ đã dừng.",
                    run_id=run.id,
                )
                run.status = "failed"
                await db.commit()
                await chat_service.announce(db, message)
            else:
                run.status = "failed"
                handoff = await db.get(Handoff, run.handoff_id)
                if handoff is not None:
                    await handoffs.fail(db, handoff, final=True)
                await db.commit()
            return
        with tracing.start_trace(
            "resume-run",
            user_id=run.user_id,
            session_id=run.conversation_id,
            tags=[tag for tag in ("resume", run.role, run.source) if tag],
            metadata={"run_id": run.id, "agent": agent.slug, "class_id": run.class_id, "handoff_id": run.handoff_id},
            input=run.user_text,
            current=True,
        ) as trace:
            ctx.trace = trace
            started = time.perf_counter()
            try:
                if (run.pending or {}).get("fresh"):
                    run.pending = {"items": []}
                    run.message_id = ctx.message_id
                    trigger = await db.get(ChatMessage, run.trigger_message_id) if run.trigger_message_id else None
                    history, _previous = await build_history(
                        db, ctx.conversation, run.user_id, agent.slug, before_seq=trigger.seq if trigger else None
                    )
                    final = await GRAPH.ainvoke(
                        {"ctx": ctx, "text": run.user_text, "requested_agent": agent.slug, "history": history}
                    )
                else:
                    note = await runs.resolution_note(db, run)
                    await runs.mark_noted(db, run)
                    asked_by = None
                    if run.handoff_id:
                        handoff = await db.get(Handoff, run.handoff_id)
                        asker = next((a for a in ctx.agents if handoff and a.slug == handoff.from_agent), None)
                        asked_by = asker.manifest.name if asker else None
                    state = {
                        "ctx": ctx,
                        "agent": agent,
                        "text": note,
                        "transcript": runs.load_messages(run.transcript or []),
                        "review_text": run.user_text,
                    }
                    if asked_by:
                        state["asked_by"] = asked_by
                    final = await RESUME_GRAPH.ainvoke(state)
            except Exception:
                log.exception("resuming run %s failed", run_id)
                final = {"status": "error", "reply": ""}
            final.setdefault("latency_ms", int((time.perf_counter() - started) * 1000))
            if trace is not None:
                trace.update(
                    output=final.get("reply") or "",
                    level={"blocked": "WARNING", "error": "ERROR"}.get(final.get("status", "error")),
                    metadata={"status": final.get("status", "error"), "waiting": bool(ctx.waits)},
                )
            await finish_run(ctx, agent, final)


async def expire_cards(db) -> None:
    from datetime import UTC, datetime

    from app.orchestration import people

    now = datetime.now(UTC)
    cards = list(
        await db.scalars(select(ApprovalCard).where(ApprovalCard.status == "open", ApprovalCard.expires_at < now))
    )
    for card in cards:
        card.status = "expired"
        if card.tool == "ask_person":
            request = await db.get(PersonRequest, (card.arguments or {}).get("request_id"))
            if request is not None and request.status == "draft":
                request.status = "cancelled"
        await runs.try_mark_resumable(db, card.run_id)
    await people.expire_due(db)
    await db.flush()
