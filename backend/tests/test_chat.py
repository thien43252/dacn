"""Chat endpoints around a turn: conversations, access, consent, rosters and the tool guard. The turn itself runs on
the fake Dify (tests/dify_fake.py); test_runtime_dify.py covers the stream in detail."""

import json

from app.audit.models import GuardEvent
from app.chat.models import ToolCallLog
from tests.dify_fake import deltas_sse, rows, triage_body
from tests.helpers import chat, class_with_student, reply_text


async def test_conversation_history_and_messages_endpoint(as_user, dify) -> None:
    _, student, _, room = await class_with_student(as_user)
    dify.runner = [deltas_sse("Trả lời một"), deltas_sse("Trả lời hai")]
    first = await chat(student, "Câu một", class_id=room["id"])
    conversation_id = next(event for event in first if event["type"] == "conversation")["conversation_id"]
    second = await chat(student, "Câu hai", class_id=room["id"], conversation_id=conversation_id)
    assert reply_text(second) == "Trả lời hai"
    # Dify keeps the agent's memory: the second turn only sends the new message and the Dify conversation id.
    runner = dify.calls("/chat-messages")
    assert [body["query"] for body in runner] == ["Câu một", "Câu hai"]
    assert runner[1]["conversation_id"] == "dify-conv-1"

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


async def test_consent_not_needed_when_class_does_not_require_it(as_user) -> None:
    _, student, _, room = await class_with_student(as_user, consent=False, require_consent=False)
    events = await chat(student, "Xin chào", class_id=room["id"])
    assert "text_delta" in {event["type"] for event in events}


async def test_outsider_cannot_chat_in_class(as_user, dify) -> None:
    _, _, _, room = await class_with_student(as_user)
    outsider = await as_user("student")
    response = await outsider.post("/api/chat/stream", json={"message": "x", "class_id": room["id"]})
    assert response.status_code == 404
    assert dify.requests == []


async def test_tool_guard_denies_tool_not_in_manifest_and_audits_it(as_user, dify, sessionmaker) -> None:
    _, student, _, room = await class_with_student(as_user)
    # tro-ly-lop only has class_doc_search; Dify's agent asking for progress_summary must be refused by the handler.
    dify.triage = triage_body(agent="tro-ly-lop")
    dify.tool_calls = [("progress_summary", {})]
    dify.runner = [deltas_sse("Mình không xem được thông tin đó.")]
    events = await chat(student, "Bạn Nam học thế nào?", class_id=room["id"])
    assert ("progress_summary", "denied") in [(e["name"], e["status"]) for e in events if e["type"] == "tool"]
    [log] = await rows(sessionmaker, ToolCallLog)
    assert log.denied_reason == "Agent này không được cấp công cụ đó."
    [event] = await rows(sessionmaker, GuardEvent)
    assert (event.stage, event.category, event.agent_slug) == ("tool", "tool_denied", "tro-ly-lop")


async def test_agents_endpoint_filters_by_role_and_triage_only_sees_allowed_agents(as_user, dify) -> None:
    teacher, student, parent, room = await class_with_student(as_user)
    hub = (await teacher.get("/api/hub/agents")).json()
    for slug in ("tao-de", "gia-su-toan"):
        agent = next(agent for agent in hub if agent["slug"] == slug)
        await teacher.post(f"/api/classes/{room['id']}/agents", json={"agent_id": agent["id"]})
    teacher_slugs = {a["slug"] for a in (await teacher.get("/api/chat/agents", params={"class_id": room["id"]})).json()}
    student_slugs = {a["slug"] for a in (await student.get("/api/chat/agents", params={"class_id": room["id"]})).json()}
    assert teacher_slugs == {"tro-ly-lop", "tao-de"}
    assert student_slugs == {"tro-ly-lop", "gia-su-toan"}
    # A student mentioning a teacher-only agent: triage never gets it in the roster, and if it answered with it
    # anyway the backend falls back to the class assistant.
    dify.triage = triage_body(agent="tao-de", route_reason="mention: tao-de")
    events = await chat(student, "@tao-de cho em xem đề", class_id=room["id"])
    [triage] = dify.calls("/workflows/run")
    assert {a["slug"] for a in json.loads(triage["inputs"]["roster"])} == student_slugs
    assert next(event for event in events if event["type"] == "agent")["agent"] == "tro-ly-lop"
