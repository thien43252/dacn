"""The platform's MCP server. Agents reach every tool through it, in-process via `mcp.Client(server)`.

Each tool takes a `ctx` handle that the platform's tool guard registers just before the call; it carries the
caller's identity and class, so the model never supplies (or sees) who it is acting for. Run standalone with
`uv run python -m app.tools.server` to inspect the tools with any MCP client over stdio.
"""

import json
from typing import Literal

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from app.tools import impl
from app.tools.context import resolve

server = MCPServer(
    name="eduagent-tools",
    instructions="Công cụ đã kiểm chứng của EduAgent Hub. Tham số ctx do nền tảng cấp, không do mô hình điền.",
)


async def _run(ctx: str, fn, args) -> str:
    context = resolve(ctx)
    try:
        return json.dumps(await fn(context, args), ensure_ascii=False)
    except impl.ToolFailure as failure:
        # ToolError (unlike other exceptions) keeps its message in the error result the model reads.
        raise ToolError(str(failure)) from failure


@server.tool(description="Tìm các đoạn liên quan trong tài liệu giáo viên đã tải lên lớp.")
async def class_doc_search(ctx: str, query: str, top_k: int = 4) -> str:
    return await _run(ctx, impl.class_doc_search, impl.DocSearchArgs(query=query, top_k=top_k))


@server.tool(description="Soạn câu hỏi trắc nghiệm hoặc tự luận theo chủ đề, bám tài liệu lớp.")
async def quiz_generator(
    ctx: str,
    topic: str,
    num_questions: int = 5,
    question_type: Literal["mcq", "essay", "mixed"] = "mcq",
    level: Literal["nhan_biet", "thong_hieu", "van_dung", "van_dung_cao", "hon_hop"] = "hon_hop",
    with_answers: bool = False,
) -> str:
    args = impl.QuizArgs(
        topic=topic, num_questions=num_questions, question_type=question_type, level=level, with_answers=with_answers
    )
    return await _run(ctx, impl.quiz_generator, args)


@server.tool(description="Chấm hoặc nhận xét bài văn theo rubric.")
async def rubric_grader(ctx: str, essay: str, rubric: str = "", assignment: str = "") -> str:
    return await _run(ctx, impl.rubric_grader, impl.RubricArgs(essay=essay, rubric=rubric, assignment=assignment))


@server.tool(description="Giải, rút gọn hoặc kiểm tra kết quả toán bằng tính toán ký hiệu (sympy).")
async def math_check(
    ctx: str,
    operation: Literal["solve", "check_answer", "simplify", "equivalent"],
    expression: str,
    answer: str = "",
    variable: str = "x",
) -> str:
    args = impl.MathArgs(operation=operation, expression=expression, answer=answer, variable=variable)
    return await _run(ctx, impl.math_check, args)


@server.tool(description="Tổng hợp tình hình học tập của con hoặc học sinh trong lớp, không trích nguyên văn tin nhắn.")
async def progress_summary(ctx: str, student_name: str = "", days: int = 7) -> str:
    return await _run(ctx, impl.progress_summary, impl.ProgressArgs(student_name=student_name, days=days))


if __name__ == "__main__":
    server.run()
