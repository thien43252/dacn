"""The platform's MCP server. Agents reach every tool through it: the LangGraph engine in-process via
`mcp.Client(server)`, Dify over streamable HTTP at /mcp (app/tools/http.py).

Each tool takes a `ctx` handle registered by the platform (app/tools/context.py); it carries the caller's identity,
class and the agent's granted tools, so the model never supplies (or sees) who it is acting for. Every call goes
through `registry.run_tool`, which checks the handle and the tool guard before running the tool. Run standalone with
`uv run python -m app.tools.server` to inspect the tools with any MCP client over stdio.
"""

from typing import Literal

from mcp.server.mcpserver import MCPServer

from app.tools import registry

server = MCPServer(
    name="eduagent-tools",
    instructions="Công cụ đã kiểm chứng của EduAgent Hub. Tham số ctx do nền tảng cấp, không do mô hình điền.",
)


@server.tool(description="Tìm các đoạn liên quan trong tài liệu giáo viên đã tải lên lớp.")
async def class_doc_search(ctx: str, query: str, top_k: int = 4) -> str:
    return await registry.run_tool(ctx, "class_doc_search", {"query": query, "top_k": top_k})


@server.tool(description="Soạn câu hỏi trắc nghiệm hoặc tự luận theo chủ đề, bám tài liệu lớp.")
async def quiz_generator(
    ctx: str,
    topic: str,
    num_questions: int = 5,
    question_type: Literal["mcq", "essay", "mixed"] = "mcq",
    level: Literal["nhan_biet", "thong_hieu", "van_dung", "van_dung_cao", "hon_hop"] = "hon_hop",
    with_answers: bool = False,
) -> str:
    arguments = {
        "topic": topic,
        "num_questions": num_questions,
        "question_type": question_type,
        "level": level,
        "with_answers": with_answers,
    }
    return await registry.run_tool(ctx, "quiz_generator", arguments)


@server.tool(description="Chấm hoặc nhận xét bài văn theo rubric.")
async def rubric_grader(ctx: str, essay: str, rubric: str = "", assignment: str = "") -> str:
    return await registry.run_tool(ctx, "rubric_grader", {"essay": essay, "rubric": rubric, "assignment": assignment})


@server.tool(description="Giải, rút gọn hoặc kiểm tra kết quả toán bằng tính toán ký hiệu (sympy).")
async def math_check(
    ctx: str,
    operation: Literal["solve", "check_answer", "simplify", "equivalent"],
    expression: str,
    answer: str = "",
    variable: str = "x",
) -> str:
    arguments = {"operation": operation, "expression": expression, "answer": answer, "variable": variable}
    return await registry.run_tool(ctx, "math_check", arguments)


@server.tool(description="Tổng hợp tình hình học tập của con hoặc học sinh trong lớp, không trích nguyên văn tin nhắn.")
async def progress_summary(ctx: str, student_name: str = "", days: int = 7) -> str:
    return await registry.run_tool(ctx, "progress_summary", {"student_name": student_name, "days": days})


if __name__ == "__main__":
    server.run()
