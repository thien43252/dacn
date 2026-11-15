"""The runtime side of platform tools: what is offered, how calls are handled and how actions are held for approval."""

import json
import re
from typing import Any

from app.agents.service import ResolvedAgent
from app.llm.base import ToolCall
from app.orchestration import approvals, handoffs, people

PRIVATE_NOTICE = "Mình sẽ trả lời riêng cho bạn trong chat riêng."
MENTION = re.compile(r"(?<![\w@])@([a-z0-9]+(?:-[a-z0-9]+)*)")


async def offers(ctx, agent: ResolvedAgent) -> dict[str, dict[str, Any] | None]:
    """message_agent only with a valid target (granted nobody → offered nothing), ask_person always (except on the
    safety-support path), reply_privately in groups."""
    # FR-053: on the safety-support path nothing is handed to another agent and nobody else is asked.
    targets = [] if ctx.support else await handoffs.handoff_targets(ctx, agent)
    return {
        "message_agent": {"agent": {"enum": [target.slug for target in targets]}} if targets else None,
        "ask_person": None if ctx.support else {},
        "reply_privately": {} if ctx.conversation_kind == "group" and ctx.depth == 0 else None,
    }


async def handle(ctx, agent: ResolvedAgent, call: ToolCall, offered: dict[str, Any]) -> str:
    if offered.get(call.name) is None:
        if call.name == "message_agent":
            # Not offered (no grants, disabled, depth): a forced call still gets the same refusal and is logged.
            reason = (
                "disabled"
                if ctx.support
                else await handoffs.refusal_reason(ctx, agent, str(call.arguments.get("agent", ""))) or "not_granted"
            )
            handoffs._log_refusal(ctx, agent, str(call.arguments.get("agent", "")), reason)
            return json.dumps({"status": "refused", "reason": handoffs._refusal_text(reason)}, ensure_ascii=False)
        return json.dumps({"status": "refused", "reason": "Công cụ này không dùng được ở đây."}, ensure_ascii=False)
    if call.name == "message_agent":
        return await handoffs.request_handoff(ctx, agent, call)
    if call.name == "ask_person":
        return await people.request_person(ctx, agent, call)
    if call.name == "reply_privately":
        return await reply_privately(ctx, agent)
    return json.dumps({"status": "refused", "reason": "Công cụ không xác định."}, ensure_ascii=False)


async def gate_action(ctx, agent: ResolvedAgent, call: ToolCall):
    """Holds an action-tool call for approval (FR-032). None: run it now."""
    from app.tools import registry as tools

    tool = tools.TOOLS.get(call.name)
    if tool is None or tool.action_kind == "none":
        return None
    action = approvals.Action(tool.action_kind, agent.slug, tool.name, None)
    if ctx.source in ("sandbox", "certify"):
        approvals.log_decision(ctx, action, approvals.Decision("deny", reason="no person in this mode"))
        return tools.ToolOutcome(approvals.result_text_denied(), denied="không có người duyệt trong chế độ này")
    decision = await approvals.decide_for(
        ctx.db,
        action,
        user_id=ctx.user.id,
        role=ctx.role,
        class_id=ctx.room.id if ctx.room else None,
        conversation_id=ctx.conversation.id,
    )
    approvals.log_decision(ctx, action, decision)
    if decision.effect == "allow":
        return None
    if decision.effect == "deny":
        rule = f" ({decision.rule_id})" if decision.rule_id else ""
        return tools.ToolOutcome(approvals.result_text_denied(), denied=f"bị chặn bởi quy tắc duyệt{rule}")
    from app.orchestration import runs

    run = await runs.ensure_run(ctx, agent)
    card = await approvals.open_card(
        ctx.db,
        run_id=run.id,
        tool_call_id=call.id,
        conversation_id=ctx.conversation.id,
        user_id=ctx.user.id,
        action=action,
        arguments=call.arguments,
        summary=f"{agent.manifest.name} muốn dùng “{tool.title}”",
        preview={"arguments": call.arguments},
        choices=decision.choices,
    )
    ctx.after_commit.append(("card", card.id))
    ctx.waits.append({"type": "approval", "id": card.id})
    return tools.ToolOutcome(
        json.dumps(
            {"status": "waiting_approval", "note": "Hành động đang chờ người dùng duyệt; đừng làm lại."},
            ensure_ascii=False,
        )
    )


async def execute_card_action(db, card) -> None:
    """Runs an approved action exactly once, with the arguments shown on the card (FR-036)."""
    from app.orchestration.models import AgentRun
    from app.tools import registry as tools

    if card.tool == "ask_person" or card.status != "allowed" or card.executed_at is not None:
        return
    run = await db.get(AgentRun, card.run_id) if card.run_id else None
    context = tools.ToolContext(
        user_id=card.user_id,
        role=run.role if run else "student",
        class_id=run.class_id if run else None,
        grade=None,
        conversation_id=card.conversation_id,
        agent_slug=card.agent_slug,
        allowed_tools=frozenset({card.tool}),
    )
    from datetime import UTC, datetime

    card.executed_at = datetime.now(UTC)
    await db.flush()
    outcome = await tools.execute(ToolCall(id=card.tool_call_id, name=card.tool, arguments=card.arguments), context)
    card.preview = {**(card.preview or {}), "result": outcome.content[:4000]}
    await db.flush()


async def mentions_to_handoffs(ctx, agent: ResolvedAgent, text: str, targets: list[ResolvedAgent]) -> None:
    """In a group, an agent naming a peer as @slug hands off under the same grants, caps and audit (FR-044)."""
    if ctx.support:
        return
    allowed = {target.slug for target in targets}
    for slug in dict.fromkeys(MENTION.findall(text)):
        if slug not in allowed:
            continue
        call = ToolCall(
            id=f"mention-{slug}",
            name="message_agent",
            arguments={
                "agent": slug,
                "task": text[:1000],
                "bounds": "Trả lời ngắn, chỉ phần được nhắc tới, trong nhóm chat.",
                "good_answer": "Đúng phần việc được nhắc tới, dễ hiểu với người hỏi.",
            },
        )
        await handoffs.request_handoff(ctx, agent, call)


async def reply_privately(ctx, agent: ResolvedAgent) -> str:
    """Moves a question about one person's own data from the group to their direct chat with this agent (FR-046)."""
    from app.chat.direct import open_direct
    from app.chat.service import add_message
    from app.orchestration.models import AgentRun

    direct = await open_direct(ctx.db, ctx.user, ctx.room, agent.slug)
    question = ctx.user_text or ""
    message = await add_message(
        ctx.db,
        direct.id,
        role="user",
        content=question,
        sender_user_id=ctx.user.id,
        meta={"forwarded_from": ctx.conversation.id},
    )
    ctx.db.add(
        AgentRun(
            conversation_id=direct.id,
            user_id=ctx.user.id,
            role=ctx.role,
            class_id=ctx.room.id if ctx.room else None,
            agent_slug=agent.slug,
            agent_version_id=agent.version_id,
            depth=0,
            chain=[],
            trigger_message_id=message.id,
            transcript=[],
            pending={"fresh": True, "items": []},
            status="resumable",
            source=ctx.source,
            user_text=question,
        )
    )
    await ctx.db.flush()
    ctx.private_reply = True
    ctx.after_commit.append(("message", message.id))
    return json.dumps({"status": "moved", "note": "Câu hỏi đã được chuyển sang chat riêng."}, ensure_ascii=False)
