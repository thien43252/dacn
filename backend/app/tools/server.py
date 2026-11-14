"""The platform's MCP server. Dify's agent reaches every tool through it over streamable HTTP at /mcp
(app/tools/mcp_http.py).

Each tool takes a `ctx` handle registered by the platform (app/tools/context.py); it carries the caller's identity,
class and the agent's granted tools, so the model never supplies (or sees) who it is acting for. Every call goes
through `registry.run_tool`, which checks the handle and the tool guard before running the tool. Run standalone with
`uv run python -m app.tools.server` to inspect the tools with any MCP client over stdio.
"""

from typing import Annotated, Any

from mcp.server.mcpserver import MCPServer
from pydantic import BaseModel, WithJsonSchema

from app.tools import actions, impl, registry

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
    full = args.model_json_schema()
    definitions = full.get("$defs", {})

    def inline(node: Any) -> Any:
        # Nested models (assign_practice's questions) refer to $defs, which a single property schema would lose.
        if isinstance(node, dict):
            if "$ref" in node:
                return inline(definitions[node["$ref"].rsplit("/", 1)[-1]])
            # Drops the "title" annotation (a string), never a property that happens to be named "title".
            return {key: inline(value) for key, value in node.items() if not (key == "title" and isinstance(value, str))}
        if isinstance(node, list):
            return [inline(item) for item in node]
        return node

    return Annotated[Any, WithJsonSchema(inline(full["properties"][name]))]


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


# ---------- Feature 002: signal tools (a step of the full path only) ----------

HelpAgent = param(impl.RequestHelpArgs, "agent")
HelpTask = param(impl.RequestHelpArgs, "task")
UserQuestions = param(impl.AskUserArgs, "questions")
ConfirmSummary = param(impl.RequestConfirmationArgs, "summary")


@server.tool(description="Nhờ một agent khác làm việc ngoài chuyên môn của bạn; ghi nhận rồi kết thúc phần việc.")
async def request_help(ctx: str, task: HelpTask, agent: HelpAgent = "") -> str:
    return await registry.run_tool(ctx, "request_help", {"agent": agent, "task": task})


@server.tool(description="Hỏi người dùng thông tin chỉ họ mới biết (1–3 câu); ghi nhận rồi kết thúc phần việc.")
async def ask_user(ctx: str, questions: UserQuestions) -> str:
    return await registry.run_tool(ctx, "ask_user", {"questions": questions})


@server.tool(description="Xin người dùng xác nhận cách hiểu yêu cầu trước khi làm tiếp; ghi nhận rồi kết thúc phần việc.")
async def request_confirmation(ctx: str, summary: ConfirmSummary) -> str:
    return await registry.run_tool(ctx, "request_confirmation", {"summary": summary})


# ---------- Feature 002: teacher actions, run only after the teacher confirms (R18) ----------

DocTitle = param(actions.SaveDocumentArgs, "title")
DocContent = param(actions.SaveDocumentArgs, "content")
Notes = param(actions.AgentNotesArgs, "notes")
NotesMode = param(actions.AgentNotesArgs, "mode")
AgentSlug = param(actions.InstallAgentArgs, "agent")
NoticeTitle = param(actions.AnnouncementArgs, "title")
NoticeBody = param(actions.AnnouncementArgs, "body")
Audience = param(actions.AnnouncementArgs, "audience")
PracticeTitle = param(actions.PracticeArgs, "title")
Instructions = param(actions.PracticeArgs, "instructions")
PracticeQuestions = param(actions.PracticeArgs, "questions")
AnswerKey = param(actions.PracticeArgs, "answer_key")
DueAt = param(actions.PracticeArgs, "due_at")


@server.tool(description="Lưu nội dung Markdown thành tài liệu lớp. Giáo viên sẽ được hỏi xác nhận trước.")
async def save_class_document(ctx: str, title: DocTitle, content: DocContent) -> str:
    return await registry.run_tool(ctx, "save_class_document", {"title": title, "content": content})


@server.tool(description="Thay hoặc thêm ghi chú cho mọi agent của lớp. Giáo viên sẽ được hỏi xác nhận trước.")
async def set_agent_notes(ctx: str, notes: Notes, mode: NotesMode = "append") -> str:
    return await registry.run_tool(ctx, "set_agent_notes", {"notes": notes, "mode": mode})


@server.tool(description="Cài một agent từ Hub vào lớp. Giáo viên sẽ được hỏi xác nhận trước.")
async def install_agent(ctx: str, agent: AgentSlug) -> str:
    return await registry.run_tool(ctx, "install_agent", {"agent": agent})


@server.tool(description="Đăng thông báo tới học sinh, phụ huynh hoặc cả hai. Giáo viên sẽ được hỏi xác nhận trước.")
async def post_class_announcement(ctx: str, title: NoticeTitle, body: NoticeBody, audience: Audience = "students") -> str:
    return await registry.run_tool(ctx, "post_class_announcement", {"title": title, "body": body, "audience": audience})


@server.tool(description="Giao bài luyện cho học sinh của lớp. Giáo viên sẽ được hỏi xác nhận trước.")
async def assign_practice(
    ctx: str,
    title: PracticeTitle,
    questions: PracticeQuestions,
    instructions: Instructions = "",
    answer_key: AnswerKey = None,
    due_at: DueAt = None,
) -> str:
    arguments = {
        "title": title,
        "instructions": instructions,
        "questions": questions,
        "answer_key": answer_key,
        "due_at": due_at,
    }
    return await registry.run_tool(ctx, "assign_practice", arguments)


if __name__ == "__main__":
    server.run()
