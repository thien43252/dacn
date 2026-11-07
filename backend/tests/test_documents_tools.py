import json

import pytest
from mcp.server.mcpserver.exceptions import ToolError

from app.tools import context as handles
from app.tools import registry
from tests.helpers import class_with_student

LESSON = (
    "Chương 3. Phương trình bậc nhất một ẩn. Phương trình bậc nhất một ẩn có dạng ax + b = 0 với a khác 0. "
    "Để giải, ta chuyển vế và chia hai vế cho a.\n\n"
    "Quang hợp là quá trình cây xanh dùng ánh sáng mặt trời để tạo chất hữu cơ từ khí cacbonic và nước."
)


async def upload(client, class_id: str, name: str, data: bytes, content_type: str, title: str = ""):
    return await client.post(
        f"/api/classes/{class_id}/documents",
        files={"file": (name, data, content_type)},
        data={"title": title},
    )


async def test_teacher_uploads_a_document_students_see_it_and_teachers_preview_difys_chunks(as_user) -> None:
    teacher, student, _, room = await class_with_student(as_user)
    response = await upload(teacher, room["id"], "chuong3.txt", LESSON.encode(), "text/plain", "Bài giảng chương 3")
    assert response.status_code == 201, response.text
    document = response.json()
    assert document["title"] == "Bài giảng chương 3" and document["status"] == "processing"
    # Listing asks Dify how indexing went (the fake reports it completed).
    [listed] = (await student.get(f"/api/classes/{room['id']}/documents")).json()
    assert listed["status"] == "ready" and listed["chunk_count"] > 0
    chunks = (await teacher.get(f"/api/classes/{room['id']}/documents/{document['id']}/chunks")).json()
    assert [chunk["position"] for chunk in chunks] == [1, 2, 3]
    assert chunks[0]["location"] == "đoạn 1" and chunks[0]["content"].startswith("Chương 3")
    assert (await student.get(f"/api/classes/{room['id']}/documents/{document['id']}/chunks")).status_code == 403


async def test_chunk_preview_fails_softly_when_dify_is_down(as_user, knowledge) -> None:
    teacher, _, _, room = await class_with_student(as_user)
    document = (await upload(teacher, room["id"], "a.txt", LESSON.encode(), "text/plain")).json()
    knowledge.datasets.clear()  # Dify lost the knowledge base
    response = await teacher.get(f"/api/classes/{room['id']}/documents/{document['id']}/chunks")
    assert response.status_code == 502


async def test_unsupported_and_empty_files_are_rejected(as_user) -> None:
    teacher, _, _, room = await class_with_student(as_user)
    assert (await upload(teacher, room["id"], "virus.exe", b"MZ...", "application/octet-stream")).status_code == 415
    assert (await upload(teacher, room["id"], "empty.txt", b"", "text/plain")).status_code == 400


async def test_deleting_document_removes_it(as_user, knowledge) -> None:
    teacher, _, _, room = await class_with_student(as_user)
    doc = (await upload(teacher, room["id"], "a.txt", LESSON.encode(), "text/plain")).json()
    assert (await teacher.delete(f"/api/classes/{room['id']}/documents/{doc['id']}")).status_code == 204
    assert (await teacher.get(f"/api/classes/{room['id']}/documents")).json() == []
    assert knowledge.datasets == {"ds-1": []}


def _ctx(role: str = "student", tools=("math_check",), class_id: str | None = "c1") -> registry.ToolContext:
    return registry.ToolContext(
        user_id="u1",
        role=role,
        class_id=class_id,
        grade=8,
        conversation_id=None,
        agent_slug="t",
        allowed_tools=frozenset(tools),
    )


async def call(name: str, arguments: dict, context: registry.ToolContext) -> dict:
    """One call through the MCP handler, as Dify makes it; refusals and errors raise ToolError."""
    handle = handles.register(context)
    try:
        return json.loads(await registry.run_tool(handle, name, arguments))
    finally:
        handles.release(handle)


async def test_math_check_operations() -> None:
    async def run(**arguments):
        return await call("math_check", arguments, _ctx())

    solved = await run(operation="solve", expression="x^2 - 5x + 6 = 0")
    assert sorted(solved["solutions"]) == ["2", "3"]
    wrong = await run(operation="check_answer", expression="2x + 3 = 11", answer="x = 5")
    assert wrong["is_correct"] is False
    simplified = await run(operation="simplify", expression="(x^2 - 1)/(x - 1)")
    assert simplified["simplified"] == "x + 1"
    same = await run(operation="equivalent", expression="(x+1)^2", answer="x^2 + 2x + 1")
    assert same["equivalent"] is True


async def test_math_check_rejects_code_injection() -> None:
    for payload in ["__import__('os').system('dir')", "x.__class__", "open('a')", "lambda: 1"]:
        with pytest.raises(ToolError):
            await call("math_check", {"operation": "simplify", "expression": payload}, _ctx())


@pytest.mark.parametrize(
    ("name", "arguments", "context", "message"),
    [
        ("quiz_generator", {"topic": "phân số"}, _ctx("parent", ("quiz_generator",)), "Vai trò của người dùng"),
        ("class_doc_search", {"query": "abc"}, _ctx(tools=("class_doc_search",), class_id=None), "trong một lớp"),
        ("math_check", {"operation": "fly"}, _ctx(), "Tham số không hợp lệ"),
        ("shell", {}, _ctx(tools=("shell",)), "không có trong danh mục"),
        ("progress_summary", {}, _ctx(), "không được cấp"),
    ],
)
async def test_tool_guard_checks_role_class_and_arguments(name, arguments, context, message) -> None:
    with pytest.raises(ToolError, match=message):
        await call(name, arguments, context)


async def test_quiz_hides_answers_from_students(fake_llm) -> None:
    quiz = '{"questions":[{"type":"mcq","question":"2+2?","options":["A. 3","B. 4"],"answer":"B","explanation":"vì"}]}'
    fake_llm.script(quiz, quiz)
    as_student = _ctx("student", tools=("quiz_generator",), class_id=None)
    student = await call("quiz_generator", {"topic": "cộng", "with_answers": True}, as_student)
    teacher = await call(
        "quiz_generator", {"topic": "cộng", "with_answers": True}, _ctx("teacher", ("quiz_generator",))
    )
    assert "answer" not in student["questions"][0]
    assert teacher["questions"][0]["answer"] == "B"
    assert as_student.usage and as_student.usage[0][1].provider == "fake"


async def test_rubric_grader_gives_students_feedback_without_scores(fake_llm) -> None:
    graded = json.dumps(
        {
            "criteria": [
                {"name": "Bố cục", "score": 1.5, "max_score": 2, "evidence": "...", "suggestion": "Thêm kết bài"}
            ],
            "total": 1.5,
            "max_total": 2,
            "strengths": ["Mở bài hay"],
            "improvements": ["Thiếu kết bài"],
            "injection_detected": False,
        }
    )
    fake_llm.script(graded)
    essay = "Mùa thu đến rồi, lá vàng rơi đầy sân trường em."
    result = await call("rubric_grader", {"essay": essay}, _ctx("student", tools=("rubric_grader",)))
    assert "total" not in result and "score" not in result["criteria"][0]
    assert result["criteria"][0]["suggestion"] == "Thêm kết bài"


async def test_tools_endpoint_lists_registry(as_user) -> None:
    teacher = await as_user("teacher")
    tools = (await teacher.get("/api/tools")).json()
    assert {tool["name"] for tool in tools} == set(registry.TOOLS)
    math = next(tool for tool in tools if tool["name"] == "math_check")
    assert "ctx" not in math["parameters"]["properties"]
