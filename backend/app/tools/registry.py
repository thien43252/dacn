"""Tool registry and tool guard.

The registry is the only list of tools an agent can be given. Before every call the guard checks that the tool is
registered, listed in the agent's manifest, allowed for the caller's role and has the class context it needs; then it
validates the arguments and calls the tool through the platform's MCP server.
"""

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from mcp.client import Client
from mcp.server.mcpserver.exceptions import ToolError
from pydantic import BaseModel, ValidationError

from app.agents.manifest import AgentManifest
from app.audit.models import GuardEvent
from app.chat.models import ToolCallLog
from app.classes.models import ClassRoom
from app.db import session_factory
from app.guard.rules import redact
from app.llm.base import ToolCall, ToolSpec, Usage
from app.tools import context as handles
from app.tools import impl

if TYPE_CHECKING:
    from app.agents.service import ResolvedAgent
    from app.runtime.graph import RunContext

log = logging.getLogger("eduagent.tools")


@dataclass(frozen=True)
class PlatformTool:
    name: str
    title: str
    description: str
    args: type[BaseModel]
    roles: frozenset[str]
    needs_class: bool = False


TOOLS: dict[str, PlatformTool] = {
    tool.name: tool
    for tool in [
        PlatformTool(
            "class_doc_search",
            "Tìm trong tài liệu lớp",
            "Tìm các đoạn liên quan trong tài liệu giáo viên đã tải lên lớp. Dùng trước khi trả lời câu hỏi về bài học.",
            impl.DocSearchArgs,
            frozenset({"teacher", "student", "parent"}),
            needs_class=True,
        ),
        PlatformTool(
            "quiz_generator",
            "Tạo câu hỏi",
            "Soạn câu hỏi trắc nghiệm/tự luận theo chủ đề, bám tài liệu lớp. Đáp án chỉ trả về cho giáo viên.",
            impl.QuizArgs,
            frozenset({"teacher", "student"}),
        ),
        PlatformTool(
            "rubric_grader",
            "Chấm theo rubric",
            "Chấm hoặc nhận xét bài văn theo rubric. Học sinh chỉ nhận nhận xét, không nhận điểm.",
            impl.RubricArgs,
            frozenset({"teacher", "student"}),
        ),
        PlatformTool(
            "math_check",
            "Kiểm tra toán",
            "Giải phương trình, rút gọn biểu thức hoặc kiểm tra đáp án học sinh bằng tính toán ký hiệu chính xác.",
            impl.MathArgs,
            frozenset({"teacher", "student", "parent"}),
        ),
        PlatformTool(
            "progress_summary",
            "Tổng hợp tiến độ",
            "Tổng hợp tình hình học tập (số lượt hỏi, agent đã dùng, từ khoá thường gặp) của con hoặc học sinh trong lớp.",
            impl.ProgressArgs,
            frozenset({"teacher", "parent"}),
        ),
    ]
}


@dataclass
class ToolContext:
    user_id: str
    role: str
    class_id: str | None
    grade: int | None
    conversation_id: str | None
    agent_slug: str
    allowed_tools: frozenset[str]
    usage: list[tuple[str, Usage]] = field(default_factory=list)
    # Set by the Dify engine, whose tool calls arrive over HTTP: the handler then logs each call (tool_calls,
    # guard_events) and queues `tool` SSE events for the turn. The LangGraph engine logs and emits these itself.
    log_calls: bool = False
    message_id: str | None = None
    # chat | sandbox | certify, as in guard_events.source
    source: str = "chat"
    # The class's Dify knowledge base; None outside a class or before its first document.
    dataset_id: str | None = None
    # The user's message (already redacted) for guard_events.excerpt.
    excerpt: str = ""
    events: "asyncio.Queue[dict[str, Any]] | None" = None
    citations: list[dict[str, Any]] = field(default_factory=list)

    def record(self, purpose: str, usage: Usage) -> None:
        self.usage.append((purpose, usage))

    @classmethod
    def from_run(cls, ctx: "RunContext", agent: "ResolvedAgent") -> "ToolContext":
        return cls(
            user_id=ctx.user.id,
            role=ctx.role,
            class_id=ctx.room.id if ctx.room else None,
            grade=ctx.room.grade if ctx.room else None,
            conversation_id=ctx.conversation.id,
            agent_slug=agent.slug,
            allowed_tools=frozenset(agent.manifest.tools),
        )


@dataclass
class ToolOutcome:
    content: str
    is_error: bool = False
    # Why the tool guard refused the call; None when it ran.
    denied: str | None = None
    latency_ms: int = 0
    usage: list[Usage] = field(default_factory=list)


def _llm_schema(args: type[BaseModel]) -> dict[str, Any]:
    schema = args.model_json_schema()
    schema.pop("title", None)
    for prop in schema.get("properties", {}).values():
        prop.pop("title", None)
    return schema


def specs_for(manifest: AgentManifest, role: str, room: ClassRoom | None) -> list[ToolSpec]:
    """Tools offered to the model: in the manifest, registered, allowed for this role, with context available."""
    specs = []
    for name in manifest.tools:
        tool = TOOLS.get(name)
        if tool is None or role not in tool.roles or (tool.needs_class and room is None):
            continue
        specs.append(ToolSpec(name=tool.name, description=tool.description, parameters=_llm_schema(tool.args)))
    return specs


def deny_reason(name: str, context: ToolContext) -> str | None:
    """Authorization checks 2–5 of contracts/mcp-tools.md; None when the call may run."""
    tool = TOOLS.get(name)
    if tool is None:
        return "Công cụ không có trong danh mục của nền tảng."
    if name not in context.allowed_tools:
        return "Agent này không được cấp công cụ đó."
    if context.role not in tool.roles:
        return "Vai trò của người dùng không được dùng công cụ này."
    if tool.needs_class and not context.class_id:
        return "Công cụ này chỉ dùng trong một lớp học."
    return None


def guard(call: ToolCall, context: ToolContext) -> str | None:
    denied = deny_reason(call.name, context)
    if denied:
        return denied
    if call.invalid:
        return "Tham số công cụ không đầy đủ hoặc không đọc được."
    return None


def _result_text(result: Any) -> str:
    parts = []
    for item in getattr(result, "content", None) or []:
        text = getattr(item, "text", None)
        if text:
            parts.append(text)
    return "\n".join(parts)


async def execute(call: ToolCall, context: ToolContext) -> ToolOutcome:
    started = time.perf_counter()
    denied = guard(call, context)
    if denied:
        return ToolOutcome(json.dumps({"error": denied}, ensure_ascii=False), is_error=True, denied=denied)
    tool = TOOLS[call.name]
    try:
        args = tool.args.model_validate(call.arguments)
    except ValidationError as error:
        problems = "; ".join(f"{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in error.errors()[:5])
        return ToolOutcome(
            json.dumps({"error": f"Tham số không hợp lệ: {problems}"}, ensure_ascii=False), is_error=True
        )

    from app.tools.server import server

    handle = handles.register(context)
    try:
        async with Client(server) as client:
            result = await client.call_tool(call.name, {"ctx": handle, **args.model_dump()})
        text = _result_text(result)
        is_error = bool(getattr(result, "is_error", False) or getattr(result, "isError", False))
        if is_error:
            reason = text.split(": ", 1)[1] if text.startswith("Error executing tool") and ": " in text else text
            text = json.dumps({"error": reason or "Công cụ gặp lỗi."}, ensure_ascii=False)
    except Exception as error:  # transport or server failure must not crash the chat turn
        text, is_error = json.dumps({"error": f"Công cụ gặp lỗi: {type(error).__name__}"}, ensure_ascii=False), True
    finally:
        handles.release(handle)
    return ToolOutcome(
        text,
        is_error=is_error,
        latency_ms=int((time.perf_counter() - started) * 1000),
        usage=[usage for _, usage in context.usage],
    )


IMPLEMENTATIONS = {
    "class_doc_search": impl.class_doc_search,
    "quiz_generator": impl.quiz_generator,
    "rubric_grader": impl.rubric_grader,
    "math_check": impl.math_check,
    "progress_summary": impl.progress_summary,
}


def _emit(context: ToolContext, name: str, status: str) -> None:
    if context.events is not None:
        context.events.put_nowait({"type": "tool", "message_id": context.message_id, "name": name, "status": status})


async def _log_call(
    context: ToolContext,
    name: str,
    arguments: dict[str, Any],
    result: str,
    *,
    is_error: bool = False,
    denied: str | None = None,
    latency_ms: int = 0,
) -> None:
    """One tool_calls row per call, plus a guard event when the call was refused. Never fails the call."""
    if not context.log_calls or not context.conversation_id:
        return
    try:
        async with session_factory()() as db:
            db.add(
                ToolCallLog(
                    conversation_id=context.conversation_id,
                    message_id=context.message_id,
                    agent_slug=context.agent_slug,
                    tool=name,
                    arguments=arguments,
                    result=result[:20000],
                    is_error=is_error,
                    denied_reason=denied[:300] if denied else None,
                    latency_ms=latency_ms,
                )
            )
            if denied:
                excerpt, _ = redact(context.excerpt)
                db.add(
                    GuardEvent(
                        source=context.source,
                        class_id=context.class_id,
                        user_id=context.user_id,
                        role=context.role,
                        conversation_id=context.conversation_id,
                        message_id=context.message_id,
                        agent_slug=context.agent_slug,
                        stage="tool",
                        verdict="block",
                        category="tool_denied",
                        detector="policy",
                        severity="low",
                        reason=f"{name}: {denied}"[:300],
                        excerpt=excerpt[:300],
                    )
                )
            await db.commit()
    except Exception:
        log.exception("could not log tool call %s", name)


async def run_tool(handle: str, name: str, arguments: dict[str, Any]) -> str:
    """The MCP handler behind every tool, for both engines (contracts/mcp-tools.md).

    Checks, in order: live handle, registered tool, granted to the agent, allowed for the role, class context, valid
    arguments. `arguments` never contains `ctx`. Errors are raised as ToolError so the model reads the message.
    """
    context = handles.lookup(handle)
    if context is None:
        raise ToolError(handles.INVALID)
    _emit(context, name, "start")
    started = time.perf_counter()

    def elapsed() -> int:
        return int((time.perf_counter() - started) * 1000)

    denied = deny_reason(name, context)
    if denied:
        _emit(context, name, "denied")
        await _log_call(context, name, arguments, json.dumps({"error": denied}, ensure_ascii=False), denied=denied)
        raise ToolError(denied)
    try:
        args = TOOLS[name].args.model_validate(arguments)
    except ValidationError as error:
        problems = "; ".join(f"{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in error.errors()[:5])
        message = f"Tham số không hợp lệ: {problems}"
        _emit(context, name, "error")
        await _log_call(context, name, arguments, json.dumps({"error": message}, ensure_ascii=False), is_error=True)
        raise ToolError(message) from error
    try:
        text = json.dumps(await IMPLEMENTATIONS[name](context, args), ensure_ascii=False)
    except impl.ToolFailure as failure:
        message = str(failure)
    except Exception as error:  # a broken tool must not crash the agent loop
        log.exception("tool %s failed", name)
        message = f"Công cụ gặp lỗi: {type(error).__name__}"
    else:
        _emit(context, name, "done")
        await _log_call(context, name, arguments, text, latency_ms=elapsed())
        return text
    _emit(context, name, "error")
    await _log_call(
        context,
        name,
        arguments,
        json.dumps({"error": message}, ensure_ascii=False),
        is_error=True,
        latency_ms=elapsed(),
    )
    raise ToolError(message)
