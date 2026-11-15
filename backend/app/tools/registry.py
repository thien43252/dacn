"""Tool registry and tool guard.

The registry is the only list of tools an agent can be given. Before every call the guard checks that the tool is
registered, listed in the agent's manifest, allowed for the caller's role and has the class context it needs; then it
validates the arguments and calls the tool through the platform's MCP server.
"""

import json
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from mcp.client import Client
from pydantic import BaseModel, Field, ValidationError

from app.agents.manifest import AgentManifest
from app.classes.models import ClassRoom
from app.llm.base import ToolCall, ToolSpec, Usage
from app.tools import context as handles
from app.tools import impl

if TYPE_CHECKING:
    from app.agents.service import ResolvedAgent
    from app.runtime.graph import RunContext


@dataclass(frozen=True)
class PlatformTool:
    name: str
    title: str
    description: str
    args: type[BaseModel]
    roles: frozenset[str]
    needs_class: bool = False
    # Handled by the runtime itself (app/orchestration/meta.py), offered without being listed in the manifest.
    meta: bool = False
    # Input to approvals.decide(): none | change | send | share | post | delete | settings | money.
    action_kind: str = "none"
    # Reads one person's data (grades, progress): never offered in a group (FR-046).
    personal_data: bool = False
    # Only offered in group conversations (reply_privately).
    group_only: bool = False


class MessageAgentArgs(BaseModel):
    agent: str = Field(min_length=3, max_length=48, description="Mã agent được giao việc.")
    task: str = Field(min_length=1, max_length=1000, description="Việc cần agent đó làm.")
    bounds: str = Field(min_length=1, max_length=1000, description="Giới hạn: phạm vi, độ dài, điều không được làm.")
    good_answer: str = Field(min_length=1, max_length=1000, description="Thế nào là một câu trả lời tốt.")
    attachments: str = Field(default="", max_length=4000, description="Nội dung cần chuyển kèm (nếu có).")


class AskPersonArgs(BaseModel):
    recipient: str = Field(
        description="self (người đang trò chuyện) | teacher (kèm subject) | homeroom (chủ nhiệm) | parent | <user_id>"
    )
    subject: str = Field(default="", max_length=16, description="Mã môn khi hỏi giáo viên bộ môn, ví dụ toan.")
    question: str = Field(min_length=1, max_length=2000)
    kind: str = Field(default="question", description="approval | question | choice")
    options: list[str] = Field(default_factory=list, max_length=6)


class ReplyPrivatelyArgs(BaseModel):
    reason: str = Field(default="", max_length=300)


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
            personal_data=True,
        ),
        PlatformTool(
            "message_agent",
            "Giao việc cho agent khác",
            "Nhờ một agent khác trong danh sách được phép làm một phần việc. Câu trả lời của agent đó sẽ được ghi vào "
            "cuộc trò chuyện và bạn được gọi lại để viết kết luận khi mọi agent đã trả lời. Chỉ dùng khi phần việc "
            "nằm ngoài chuyên môn của bạn.",
            MessageAgentArgs,
            frozenset({"teacher", "student", "parent"}),
            meta=True,
        ),
        PlatformTool(
            "ask_person",
            "Hỏi một người",
            "Hỏi một người thật khi cần quyết định, sự cho phép hay thông tin mà bạn không được tự đoán: hỏi lại chính "
            "người đang trò chuyện (recipient=self), giáo viên bộ môn (teacher + subject), giáo viên chủ nhiệm "
            "(homeroom) hoặc phụ huynh (parent). Gửi cho người khác cần người dùng duyệt trước.",
            AskPersonArgs,
            frozenset({"teacher", "student", "parent"}),
            meta=True,
            action_kind="send",
        ),
        PlatformTool(
            "reply_privately",
            "Trả lời riêng",
            "Trong nhóm: chuyển câu hỏi về dữ liệu riêng của một người (điểm, tiến độ, lời xin phép) sang chat riêng "
            "giữa người đó và bạn. Không trả lời nội dung riêng trong nhóm.",
            ReplyPrivatelyArgs,
            frozenset({"teacher", "student", "parent"}),
            meta=True,
            group_only=True,
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
    conversation_kind: str = "direct"

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
            conversation_kind=ctx.conversation_kind,
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


def offerable(tool: PlatformTool, role: str, room: ClassRoom | None, conversation_kind: str) -> bool:
    if role not in tool.roles or (tool.needs_class and room is None):
        return False
    if tool.personal_data and conversation_kind == "group":
        return False
    return not (tool.group_only and conversation_kind != "group")


def specs_for(
    manifest: AgentManifest,
    role: str,
    room: ClassRoom | None,
    *,
    conversation_kind: str = "direct",
    meta_offers: dict[str, dict[str, Any] | None] | None = None,
) -> list[ToolSpec]:
    """Tools offered to the model: in the manifest, registered, allowed for this role, with context available.

    `meta_offers` maps a meta tool to schema overrides for its parameters (None: not offered). The runtime decides it:
    message_agent only with a valid target (its `agent` parameter becomes an enum of them), ask_person always,
    reply_privately in groups."""
    specs = []
    for name in manifest.tools:
        tool = TOOLS.get(name)
        if tool is None or tool.meta or not offerable(tool, role, room, conversation_kind):
            continue
        specs.append(ToolSpec(name=tool.name, description=tool.description, parameters=_llm_schema(tool.args)))
    for name, overrides in (meta_offers or {}).items():
        tool = TOOLS.get(name)
        if tool is None or overrides is None or not offerable(tool, role, room, conversation_kind):
            continue
        schema = _llm_schema(tool.args)
        for prop, extra in overrides.items():
            schema["properties"][prop] = {**schema["properties"].get(prop, {}), **extra}
        specs.append(ToolSpec(name=tool.name, description=tool.description, parameters=schema))
    return specs


def guard(call: ToolCall, context: ToolContext) -> str | None:
    tool = TOOLS.get(call.name)
    if tool is None:
        return "Công cụ không có trong danh mục của nền tảng."
    if tool.meta:
        return "Công cụ nền tảng này do runtime xử lý."
    if call.name not in context.allowed_tools:
        return "Agent này không được cấp công cụ đó."
    if tool.personal_data and context.conversation_kind == "group":
        return "Công cụ đọc dữ liệu riêng không dùng được trong nhóm."
    if context.role not in tool.roles:
        return "Vai trò của người dùng không được dùng công cụ này."
    if tool.needs_class and not context.class_id:
        return "Công cụ này chỉ dùng trong một lớp học."
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
