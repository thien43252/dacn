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
