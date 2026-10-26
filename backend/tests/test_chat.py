from sqlalchemy import select

from app.chat.models import ChatMessage, ToolCallLog, UsageRecord
from app.llm.base import ToolCall
from app.llm.fake import Scripted
from tests.helpers import chat, class_with_student, reply_text


async def test_chat_streams_events_in_contract_order(as_user, fake_llm) -> None:
    teacher, student, _, room = await class_with_student(as_user)
    fake_llm.script("Chào em, mình là trợ lý lớp.")
    events = await chat(student, "Xin chào", class_id=room["id"])
    types = [event["type"] for event in events]
    assert types[0] == "operation" and types[1] == "conversation" and types[2] == "agent" and types[-1] == "done"
    assert events[2]["agent"] == "tro-ly-lop" and events[2]["reason"] == "fallback"
    assert reply_text(events) == "Chào em, mình là trợ lý lớp."
    # Offsets are cumulative UTF-16 positions, as chatStream.ts expects.
    deltas = [event for event in events if event["type"] == "text_delta"]
    assert deltas[0]["text_offset"] == 0
    assert all(event["message_id"] == events[0]["operation_id"] for event in deltas)


async def test_conversation_history_and_messages_endpoint(as_user, fake_llm) -> None:
    _, student, _, room = await class_with_student(as_user)
    first = await chat(student, "Câu một", class_id=room["id"])
    conversation_id = next(event for event in first if event["type"] == "conversation")["conversation_id"]
    fake_llm.script("Trả lời hai")
    await chat(student, "Câu hai", class_id=room["id"], conversation_id=conversation_id)
    # The second turn received the first exchange as history.
    sent = fake_llm.calls[-1]["messages"]
    assert [m.content for m in sent if m.role == "user"] == ["Câu một", "Câu hai"]

    listed = (await student.get("/api/chat/conversations", params={"class_id": room["id"]})).json()
    assert [c["id"] for c in listed] == [conversation_id]
    messages = (await student.get(f"/api/chat/conversations/{conversation_id}/messages")).json()
    assert [m["role"] for m in messages] == ["user", "assistant", "user", "assistant"]
    assert messages[-1]["content"] == "Trả lời hai"


async def test_other_users_cannot_read_or_continue_a_conversation(as_user) -> None:
    teacher, student, _, room = await class_with_student(as_user)
    events = await chat(student, "Bí mật", class_id=room["id"])
    conversation_id = next(event for event in events if event["type"] == "conversation")["conversation_id"]
    assert (await teacher.get(f"/api/chat/conversations/{conversation_id}/messages")).status_code == 404
    response = await teacher.post(
        "/api/chat/stream", json={"message": "x", "class_id": room["id"], "conversation_id": conversation_id}
    )
    assert response.status_code == 404


async def test_student_without_consent_gets_notice_and_nothing_is_stored(as_user, fake_llm, sessionmaker) -> None:
    _, student, _, room = await class_with_student(as_user, consent=False)
    events = await chat(student, "Giải giúp em bài này", class_id=room["id"])
    assert [event["type"] for event in events] == ["operation", "notice", "done"]
    assert events[1]["kind"] == "consent_required"
    assert fake_llm.calls == []
    async with sessionmaker() as db:
        assert (await db.scalars(select(ChatMessage))).all() == []


async def test_consent_not_needed_when_class_does_not_require_it(as_user) -> None:
    _, student, _, room = await class_with_student(as_user, consent=False, require_consent=False)
    events = await chat(student, "Xin chào", class_id=room["id"])
    assert "text_delta" in {event["type"] for event in events}


async def test_outsider_cannot_chat_in_class(as_user) -> None:
    _, _, _, room = await class_with_student(as_user)
    outsider = await as_user("student")
    response = await outsider.post("/api/chat/stream", json={"message": "x", "class_id": room["id"]})
    assert response.status_code == 404


async def test_agent_tool_loop_runs_math_check_and_logs_it(as_user, fake_llm, sessionmaker) -> None:
    teacher, student, _, room = await class_with_student(as_user)
    # Install the platform math tutor in the class (week 6 endpoint).
    hub = (await teacher.get("/api/hub/agents")).json()
    math = next(agent for agent in hub if agent["slug"] == "gia-su-toan")
    installed = await teacher.post(f"/api/classes/{room['id']}/agents", json={"agent_id": math["id"]})
    assert installed.status_code == 201, installed.text

    fake_llm.script(
        Scripted(
            text="Để mình kiểm tra nhé.",
            tool_calls=[
                ToolCall(
                    id="c1",
                    name="math_check",
                    arguments={"operation": "check_answer", "expression": "3x+7=2x-5", "answer": "x=-12"},
                )
            ],
        ),
        "Chính xác! Em làm đúng rồi.",
    )
    events = await chat(student, "@gia-su-toan em ra x = -12 đúng không ạ", class_id=room["id"])
    agent_event = next(event for event in events if event["type"] == "agent")
    assert agent_event["agent"] == "gia-su-toan" and agent_event["reason"] == "mention"
    assert [(e["name"], e["status"]) for e in events if e["type"] == "tool"] == [
        ("math_check", "start"),
        ("math_check", "done"),
    ]
    assert reply_text(events).endswith("Chính xác! Em làm đúng rồi.")
    # The model saw the real sympy verdict as the tool result.
    tool_message = fake_llm.calls[-1]["messages"][-1]
    assert tool_message.role == "tool" and '"is_correct": true' in tool_message.content
    async with sessionmaker() as db:
        log = (await db.scalars(select(ToolCallLog))).one()
        assert log.tool == "math_check" and not log.is_error and log.denied_reason is None
        purposes = {row.purpose for row in await db.scalars(select(UsageRecord))}
        assert purposes == {"agent"}


async def test_tool_guard_denies_tool_not_in_manifest(as_user, fake_llm, sessionmaker) -> None:
    _, student, _, room = await class_with_student(as_user)
    # tro-ly-lop only has class_doc_search; a model asking for progress_summary must be refused.
    fake_llm.script(
        Scripted(tool_calls=[ToolCall(id="c1", name="progress_summary", arguments={})]),
        "Mình không xem được thông tin đó.",
    )
    events = await chat(student, "Bạn Nam học thế nào?", class_id=room["id"])
    assert ("progress_summary", "denied") in [(e["name"], e["status"]) for e in events if e["type"] == "tool"]
    async with sessionmaker() as db:
        log = (await db.scalars(select(ToolCallLog))).one()
        assert log.denied_reason == "Agent này không được cấp công cụ đó."


async def test_agents_endpoint_filters_by_role(as_user) -> None:
    teacher, student, parent, room = await class_with_student(as_user)
    hub = (await teacher.get("/api/hub/agents")).json()
    for slug in ("tao-de", "gia-su-toan"):
        agent = next(agent for agent in hub if agent["slug"] == slug)
        await teacher.post(f"/api/classes/{room['id']}/agents", json={"agent_id": agent["id"]})
    teacher_slugs = {a["slug"] for a in (await teacher.get("/api/chat/agents", params={"class_id": room["id"]})).json()}
    student_slugs = {a["slug"] for a in (await student.get("/api/chat/agents", params={"class_id": room["id"]})).json()}
    assert teacher_slugs == {"tro-ly-lop", "tao-de"}
    assert student_slugs == {"tro-ly-lop", "gia-su-toan"}
    # A student mentioning a teacher-only agent falls back instead of reaching it.
    events = await chat(student, "@tao-de cho em xem đề", class_id=room["id"])
    assert next(event for event in events if event["type"] == "agent")["agent"] == "tro-ly-lop"
