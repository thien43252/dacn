import json

CLASS = {"name": "Toán 8A1", "subject": "toan", "grade": 8, "description": ""}


def parse_sse(body: str) -> list[dict]:
    events = []
    for block in body.split("\n\n"):
        data = "\n".join(line[5:].strip() for line in block.splitlines() if line.startswith("data:"))
        if data:
            events.append(json.loads(data))
    return events


def reply_text(events: list[dict]) -> str:
    return "".join(event["delta"] for event in events if event["type"] == "text_delta")


async def chat(client, message: str, **fields) -> list[dict]:
    response = await client.post("/api/chat/stream", json={"message": message, **fields})
    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("text/event-stream")
    return parse_sse(response.text)


async def class_with_student(as_user, *, consent: bool = True, require_consent: bool = True):
    teacher = await as_user("teacher")
    student = await as_user("student")
    room = (await teacher.post("/api/classes", json={**CLASS, "require_parent_consent": require_consent})).json()
    await student.post("/api/classes/join", json={"code": room["join_code"]})
    parent = None
    if consent:
        parent = await as_user("parent")
        code = (await student.get("/api/me/link-code")).json()["code"]
        await parent.post("/api/parent/children", json={"code": code})
        await parent.put(f"/api/parent/children/{student.user['id']}/consent", json={"allow_agents": True})
    return teacher, student, parent, room


def tool_call(name: str, call_id: str | None = None, **arguments):
    from app.llm.base import ToolCall
    from app.llm.fake import Scripted

    return Scripted(tool_calls=[ToolCall(id=call_id or f"call-{name}", name=name, arguments=arguments)])


def agent_of(system: str) -> str | None:
    """The agent slug a fake-model request was made for (from the system prompt's "(mã @slug)")."""
    import re

    match = re.search(r"\(mã @([a-z0-9-]+)\)", system)
    return match.group(1) if match else None


async def install(teacher, room, *slugs: str) -> None:
    hub = {a["slug"]: a for a in (await teacher.get("/api/hub/agents")).json()}
    for slug in slugs:
        response = await teacher.post(f"/api/classes/{room['id']}/agents", json={"agent_id": hub[slug]["id"]})
        assert response.status_code == 201, response.text


async def conversation_messages(client, conversation_id: str) -> list[dict]:
    response = await client.get(f"/api/chat/conversations/{conversation_id}/messages")
    assert response.status_code == 200, response.text
    return response.json()


def conversation_id_of(events: list[dict]) -> str:
    return next(event for event in events if event["type"] == "conversation")["conversation_id"]
