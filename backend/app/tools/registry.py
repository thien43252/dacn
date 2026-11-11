"""Tool registry and tool guard.

The registry is the only list of tools an agent can be given. Before every call the guard checks that the tool is
registered, listed in the agent's manifest, allowed for the caller's role and has the class context it needs; then it
validates the arguments. Dify's agent reaches the tools through the platform's MCP server (app/tools/server.py),
whose handler is `run_tool`.
"""

import asyncio
import json
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Literal

from mcp.server.mcpserver.exceptions import ToolError
from pydantic import BaseModel, ValidationError

from app.audit.models import GuardEvent
from app.chat.models import ToolCallLog
from app.db import session_factory
from app.guard.rules import redact
from app.llm.base import Usage
from app.tools import context as handles
from app.tools import impl

log = logging.getLogger("eduagent.tools")


@dataclass(frozen=True)
class PlatformTool:
    name: str
    title: str
    description: str
    args: type[BaseModel]
    roles: frozenset[str]
    needs_class: bool = False
    # Feature 002 (contracts/mcp-tools.md). The platform never runs a tool that requires confirmation until the user
    # approves that exact call; `confirm_template` describes its effect from the arguments (never written by a model).
    requires_confirmation: bool = False
    # Signal tools (request_help, ask_user, request_confirmation) only record a signal for the orchestrator; any agent
    # may call them, in a step of the full path only.
    signal: bool = False
    confirm_template: str = ""
    # Builds the confirmation preview (FR-048): (context, args) -> {title?, body?, items?, before?, after?, ...}.
    preview: Callable[..., Any] | None = None
    # Content other people will read: also reviewed by eduagent-review before confirmation is asked (FR-049).
    share_review: bool = False


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
    # Tool calls arrive over HTTP from Dify: the handler then logs each call (tool_calls, guard_events) and queues
    # `tool` SSE events for the turn. Off for handles that should leave no trace.
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
    # Feature 002: which part of a full-path turn this runner call is. Signal tools work only in `step` mode.
    step_key: str | None = None
    mode: Literal["fast", "step", "synthesis"] = "fast"
    # Signals recorded by signal tools and by tools waiting for confirmation, read by the orchestrator afterwards.
    signals: list[dict[str, Any]] = field(default_factory=list)
    # False in a step created by request_help: a helper cannot ask for help in turn (FR-024).
    may_request_help: bool = False

    def record(self, purpose: str, usage: Usage) -> None:
        self.usage.append((purpose, usage))


def _llm_schema(args: type[BaseModel]) -> dict[str, Any]:
    schema = args.model_json_schema()
    schema.pop("title", None)
    for prop in schema.get("properties", {}).values():
        prop.pop("title", None)
    return schema


STEP_ONLY = "Công cụ này chỉ dùng trong phần việc của quá trình nhiều bước."


def deny_reason(name: str, context: ToolContext) -> str | None:
    """Authorization checks 2–5 of contracts/mcp-tools.md (with 2a/2b of feature 002); None when the call may run."""
    tool = TOOLS.get(name)
    if tool is None:
        return "Công cụ không có trong danh mục của nền tảng."
    if tool.signal:
        # 2a: signal tools belong to a step of the full path; 2b: they need no manifest entry.
        if context.mode != "step":
            return STEP_ONLY
    elif name not in context.allowed_tools:
        return "Agent này không được cấp công cụ đó."
    if context.role not in tool.roles:
        return "Vai trò của người dùng không được dùng công cụ này."
    if tool.needs_class and not context.class_id:
        return "Công cụ này chỉ dùng trong một lớp học."
    return None


IMPLEMENTATIONS = {
    "class_doc_search": impl.class_doc_search,
    "quiz_generator": impl.quiz_generator,
    "rubric_grader": impl.rubric_grader,
    "math_check": impl.math_check,
    "progress_summary": impl.progress_summary,
}


CITATION_EXCERPT = 300


def add_citations(context: ToolContext, data: dict[str, Any]) -> None:
    """Keeps what class_doc_search returned so the turn can show its sources (contracts/chat-sse.md `citations`)."""
    seen = {(item["document_id"], item["location"]) for item in context.citations}
    for result in data.get("results", []):
        key = (str(result.get("document_id", "")), str(result.get("location", "")))
        if key in seen:
            continue
        seen.add(key)
        context.citations.append(
            {
                "document_id": key[0],
                "title": str(result.get("title", "")),
                "location": key[1],
                "excerpt": str(result.get("content", ""))[:CITATION_EXCERPT],
            }
        )


def _emit(context: ToolContext, name: str, status: str) -> None:
    if context.events is not None:
        context.events.put_nowait(
            {
                "type": "tool",
                "message_id": context.message_id,
                "name": name,
                "status": status,
                # null on the fast path and in the synthesis; the client files the tool under that step otherwise.
                "step_key": context.step_key,
            }
        )


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
    """The MCP handler behind every tool (contracts/mcp-tools.md).

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
        data = await IMPLEMENTATIONS[name](context, args)
        if name == "class_doc_search":
            add_citations(context, data)
        text = json.dumps(data, ensure_ascii=False)
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
