"""The platform's MCP server. Agents reach every tool through it: the LangGraph engine in-process via
`mcp.Client(server)`, Dify over streamable HTTP at /mcp (app/tools/mcp_http.py).

Each tool takes a `ctx` handle registered by the platform (app/tools/context.py); it carries the caller's identity,
class and the agent's granted tools, so the model never supplies (or sees) who it is acting for. Every call goes
through `registry.run_tool`, which checks the handle and the tool guard before running the tool. Run standalone with
`uv run python -m app.tools.server` to inspect the tools with any MCP client over stdio.
"""

from typing import Annotated, Any

from mcp.server.mcpserver import MCPServer
from pydantic import BaseModel, WithJsonSchema

from app.tools import impl, registry

server = MCPServer(
    name="eduagent-tools",
    instructions="Công cụ đã kiểm chứng của EduAgent Hub. Tham số ctx do nền tảng cấp, không do mô hình điền.",
)


def param(args: type[BaseModel], name: str) -> Any:
    """A parameter the model sees with the tool's own JSON schema, but that the SDK passes through unchecked.

    All validation then happens in `registry.run_tool`, so a call with a wrong type or value is logged in tool_calls
    and shown as a tool event like any other refused call (FR-014). Only a missing required argument is still
    rejected by the SDK before the handler runs.
    """
    schema = dict(args.model_json_schema()["properties"][name])
    schema.pop("title", None)
    return Annotated[Any, WithJsonSchema(schema)]


Query = param(impl.DocSearchArgs, "query")
TopK = param(impl.DocSearchArgs, "top_k")
Topic = param(impl.QuizArgs, "topic")
NumQuestions = param(impl.QuizArgs, "num_questions")
QuestionType = param(impl.QuizArgs, "question_type")
Level = param(impl.QuizArgs, "level")
WithAnswers = param(impl.QuizArgs, "with_answers")
Essay = param(impl.RubricArgs, "essay")
Rubric = param(impl.RubricArgs, "rubric")
Assignment = param(impl.RubricArgs, "assignment")
Operation = param(impl.MathArgs, "operation")
Expression = param(impl.MathArgs, "expression")
Answer = param(impl.MathArgs, "answer")
Variable = param(impl.MathArgs, "variable")
StudentName = param(impl.ProgressArgs, "student_name")
Days = param(impl.ProgressArgs, "days")


@server.tool(description="Tìm các đoạn liên quan trong tài liệu giáo viên đã tải lên lớp.")
async def class_doc_search(ctx: str, query: Query, top_k: TopK = 4) -> str:
    return await registry.run_tool(ctx, "class_doc_search", {"query": query, "top_k": top_k})


@server.tool(description="Soạn câu hỏi trắc nghiệm hoặc tự luận theo chủ đề, bám tài liệu lớp.")
async def quiz_generator(
    ctx: str,
    topic: Topic,
    num_questions: NumQuestions = 5,
    question_type: QuestionType = "mcq",
    level: Level = "hon_hop",
    with_answers: WithAnswers = False,
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
async def rubric_grader(ctx: str, essay: Essay, rubric: Rubric = "", assignment: Assignment = "") -> str:
    return await registry.run_tool(ctx, "rubric_grader", {"essay": essay, "rubric": rubric, "assignment": assignment})


@server.tool(description="Giải, rút gọn hoặc kiểm tra kết quả toán bằng tính toán ký hiệu (sympy).")
async def math_check(
    ctx: str,
    operation: Operation,
    expression: Expression,
    answer: Answer = "",
    variable: Variable = "x",
) -> str:
    arguments = {"operation": operation, "expression": expression, "answer": answer, "variable": variable}
    return await registry.run_tool(ctx, "math_check", arguments)


@server.tool(description="Tổng hợp tình hình học tập của con hoặc học sinh trong lớp, không trích nguyên văn tin nhắn.")
async def progress_summary(ctx: str, student_name: StudentName = "", days: Days = 7) -> str:
    return await registry.run_tool(ctx, "progress_summary", {"student_name": student_name, "days": days})


if __name__ == "__main__":
    server.run()
