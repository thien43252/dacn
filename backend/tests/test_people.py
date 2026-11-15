"""Asking people (US3): recipients the platform allows, the approval card before anything leaves, the inbox, answers
exactly once, and answers landing in the origin conversation even from a handoff two levels down."""

from sqlalchemy import select

from app.llm.fake import Scripted
from app.orchestration.models import PersonRequest
from app.orchestration.runs import NOTE_HEADER
from tests.helpers import (
    agent_of,
    chat,
    class_with_student,
    conversation_id_of,
    conversation_messages,
    install,
    tool_call,
)


def script_ask(fake_llm, *, agent="tro-ly-lop", recipient="teacher", subject="toan", question=None):
    question = question or "Em An xin cô cho nộp bài Toán muộn 2 ngày vì em bị ốm. Cô có đồng ý không?"

    def respond(messages, system, tools, tier):
        if tier != "main" or agent_of(system) != agent:
            return None
        last = messages[-1]
        if last.role == "user" and last.content.startswith(NOTE_HEADER):
            return Scripted(text="Cô đã trả lời, mình báo lại cho em nhé.")
        if last.role == "tool":
            return Scripted(text="Mình đã soạn câu hỏi gửi cô, em duyệt giúp nhé.")
        return tool_call("ask_person", recipient=recipient, subject=subject, question=question, kind="approval")

    fake_llm.respond_with(respond)


def card_of(messages):
    return next(m["approval_card"] for m in messages if m.get("approval_card"))


async def test_student_request_goes_through_card_then_inbox_then_back(as_user, fake_llm, drain) -> None:
    teacher, student, _, room = await class_with_student(as_user)
    script_ask(fake_llm)
    events = await chat(
        student, "Em xin cô cho nộp bài Toán muộn 2 ngày vì em ốm", class_id=room["id"], agent="tro-ly-lop"
    )
    conversation_id = conversation_id_of(events)
    assert events[-1]["waiting"] is True

    card = card_of(await conversation_messages(student, conversation_id))
    # A student's always-ask action offers only "once" and "deny" (FR-035 default mode).
    assert [choice["id"] for choice in card["choices"]] == ["once", "deny"]
    assert card["preview"]["targets"][0]["id"] == teacher.user["id"]
    # Nothing reached the teacher before the student allowed it.
    assert (await teacher.get("/api/inbox")).json() == []

    allowed = await student.post(f"/api/approvals/{card['id']}/answer", json={"choice": "once"})
    assert allowed.status_code == 200 and allowed.json()["status"] == "allowed"
    again = await student.post(f"/api/approvals/{card['id']}/answer", json={"choice": "once"})
    assert again.status_code == 409

    inbox = (await teacher.get("/api/inbox")).json()
    assert len(inbox) == 1 and inbox[0]["can_answer"] and inbox[0]["requester"]["name"] == student.user["name"]
    assert (await teacher.get("/api/inbox/count")).json() == {"open": 1}
    assert (await teacher.get("/api/auth/me")).json()["inbox_open"] == 1
    status = (await student.get(f"/api/chat/conversations/{conversation_id}")).json()
    assert status["waiting_for"] == [teacher.user["name"]]

    request_id = inbox[0]["id"]
    answered = await teacher.post(
        f"/api/person-requests/{request_id}/answer", json={"choice": "Sửa", "text": "cho nộp muộn 1 ngày"}
    )
    assert answered.status_code == 200 and answered.json()["status"] == "answered"
    twice = await teacher.post(f"/api/person-requests/{request_id}/answer", json={"choice": "Đồng ý"})
    assert twice.status_code == 409

    await drain()
    messages = await conversation_messages(student, conversation_id)
    reply = next(m for m in messages if m["role"] == "user" and m["sender"]["id"] == teacher.user["id"])
    assert reply["content"] == "Sửa: cho nộp muộn 1 ngày"
    assert messages[-1]["agent_slug"] == "tro-ly-lop" and "báo lại" in messages[-1]["content"]
    resumed = [c for c in fake_llm.main_calls if c["messages"][-1].content.startswith(NOTE_HEADER)]
    assert "cho nộp muộn 1 ngày" in resumed[0]["messages"][-1].content


async def test_denied_card_sends_nothing(as_user, fake_llm, drain, sessionmaker) -> None:
    teacher, student, _, room = await class_with_student(as_user)
    script_ask(fake_llm)
    events = await chat(student, "Em xin nghỉ", class_id=room["id"], agent="tro-ly-lop")
    card = card_of(await conversation_messages(student, conversation_id_of(events)))
    assert (await student.post(f"/api/approvals/{card['id']}/answer", json={"choice": "deny"})).status_code == 200
    assert (await teacher.get("/api/inbox")).json() == []
    async with sessionmaker() as db:
        assert (await db.scalar(select(PersonRequest))).status == "cancelled"
    await drain()
    resumed = [c for c in fake_llm.main_calls if c["messages"][-1].content.startswith(NOTE_HEADER)]
    assert resumed and '"denied"' in resumed[0]["messages"][-1].content


async def test_only_allowed_recipients(as_user, fake_llm, sessionmaker) -> None:
    teacher, student, parent, room = await class_with_student(as_user)
    other_parent = await as_user("parent")
    script_ask(fake_llm, recipient=other_parent.user["id"], subject="")
    events = await chat(student, "Hỏi phụ huynh bạn khác", class_id=room["id"], agent="tro-ly-lop")
    assert events[-1]["waiting"] is False
    tool_result = next(m.content for m in fake_llm.main_calls[-1]["messages"] if m.role == "tool")
    assert "undeliverable" in tool_result

    # The student's own parent is fine.
    fake_llm.responders.clear()
    script_ask(fake_llm, recipient="parent", subject="")
    events = await chat(student, "Xin bố mẹ cho đi tham quan", class_id=room["id"], agent="tro-ly-lop")
    card = card_of(await conversation_messages(student, conversation_id_of(events)))
    assert card["preview"]["targets"][0]["id"] == parent.user["id"]


async def test_asking_the_user_themselves_needs_no_card(as_user, fake_llm, drain) -> None:
    _, student, _, room = await class_with_student(as_user)
    script_ask(fake_llm, recipient="self", subject="", question="Em muốn ôn chương nào: 1 hay 2?")
    events = await chat(student, "Làm đề ôn tập cho em", class_id=room["id"], agent="tro-ly-lop")
    messages = await conversation_messages(student, conversation_id_of(events))
    assert not any(m.get("approval_card") for m in messages)
    request = next(m["person_request"] for m in messages if m.get("person_request"))
    assert request["can_answer"] and request["recipient"]["id"] == student.user["id"]
    response = await student.post(f"/api/person-requests/{request['id']}/answer", json={"choice": "Chương 2"})
    assert response.status_code == 200
    await drain()
    assert (await conversation_messages(student, conversation_id_of(events)))[-1]["agent_slug"] == "tro-ly-lop"


async def test_question_from_a_handoff_lands_in_the_origin_conversation(as_user, fake_llm, drain) -> None:
    teacher, student, _, room = await class_with_student(as_user)
    await install(teacher, room, "gia-su-toan")

    def respond(messages, system, tools, tier):
        if tier != "main":
            return None
        agent, last = agent_of(system), messages[-1]
        resumed = last.role == "user" and last.content.startswith(NOTE_HEADER)
        if agent == "tro-ly-lop":
            if resumed:
                return Scripted(text="Trợ lý lớp: đã có ý kiến của cô.")
            if last.role == "tool":
                return Scripted(text="Mình hỏi Gia sư Toán.")
            return tool_call(
                "message_agent", agent="gia-su-toan", task="Kiểm tra bài 3", bounds="ngắn", good_answer="đúng"
            )
        if agent == "gia-su-toan":
            if resumed:
                return Scripted(text="Gia sư: cô xác nhận cách làm đúng.")
            if last.role == "tool":
                return Scripted(text="Đang chờ cô.")
            return tool_call("ask_person", recipient="teacher", subject="toan", question="Cô xem giúp bài 3 của em An?")
        return None

    fake_llm.respond_with(respond)
    events = await chat(student, "Bài 3 em làm đúng không?", class_id=room["id"], agent="tro-ly-lop")
    conversation_id = conversation_id_of(events)
    await drain()  # the handoff runs; the tutor asks the teacher from depth 1
    card = card_of(await conversation_messages(student, conversation_id))
    await student.post(f"/api/approvals/{card['id']}/answer", json={"choice": "once"})
    [item] = (await teacher.get("/api/inbox")).json()
    assert item["conversation_id"] == conversation_id  # the origin conversation (SC-004)
    await teacher.post(f"/api/person-requests/{item['id']}/answer", json={"text": "Đúng rồi"})
    await drain()
    messages = await conversation_messages(student, conversation_id)
    assert [m["content"] for m in messages if m["handoff_id"]] == ["Gia sư: cô xác nhận cách làm đúng."]
    assert messages[-1]["content"] == "Trợ lý lớp: đã có ý kiến của cô."


async def test_answers_are_screened_for_personal_data(as_user, fake_llm, drain) -> None:
    teacher, student, _, room = await class_with_student(as_user)
    script_ask(fake_llm)
    events = await chat(student, "Xin nghỉ", class_id=room["id"], agent="tro-ly-lop")
    card = card_of(await conversation_messages(student, conversation_id_of(events)))
    await student.post(f"/api/approvals/{card['id']}/answer", json={"choice": "once"})
    [item] = (await teacher.get("/api/inbox")).json()
    await teacher.post(f"/api/person-requests/{item['id']}/answer", json={"text": "Gọi cô số 0912345678 nhé"})
    messages = await conversation_messages(student, conversation_id_of(events))
    reply = next(m for m in messages if m["role"] == "user" and m["sender"]["id"] == teacher.user["id"])
    assert "0912345678" not in reply["content"]


async def test_cancel_and_outsiders(as_user, fake_llm) -> None:
    teacher, student, _, room = await class_with_student(as_user)
    script_ask(fake_llm)
    events = await chat(student, "Xin nghỉ", class_id=room["id"], agent="tro-ly-lop")
    card = card_of(await conversation_messages(student, conversation_id_of(events)))
    await student.post(f"/api/approvals/{card['id']}/answer", json={"choice": "once"})
    [item] = (await teacher.get("/api/inbox")).json()
    stranger = await as_user("teacher")
    assert (await stranger.post(f"/api/person-requests/{item['id']}/answer", json={"text": "x"})).status_code == 404
    assert (await teacher.post(f"/api/person-requests/{item['id']}/cancel")).status_code == 404
    assert (await student.post(f"/api/person-requests/{item['id']}/cancel")).status_code == 200
    assert (await teacher.post(f"/api/person-requests/{item['id']}/answer", json={"text": "x"})).status_code == 409
