from sqlalchemy import update

from app.agents.models import AgentVersion
from tests.helpers import chat, class_with_student, parse_sse, reply_text

MANIFEST = {
    "slug": "on-thi-hoa-9",
    "name": "Ôn thi Hoá 9",
    "description": "Ôn tập Hoá học lớp 9 theo từng chương, gợi ý cách nhớ công thức.",
    "avatar": "frog",
    "subjects": ["hoa"],
    "grades": [9],
    "target_roles": ["student"],
    "capabilities": ["ôn tập hoá học lớp 9"],
    "tools": ["class_doc_search"],
    "knowledge": "class_documents",
    "system_prompt": "Bạn giúp học sinh lớp 9 ôn tập Hoá học. Giải thích ngắn gọn và đặt câu hỏi kiểm tra.",
}


async def test_hub_lists_certified_platform_agents_filtered_by_role(as_user) -> None:
    teacher = await as_user("teacher")
    student = await as_user("student")
    teacher_view = {agent["slug"] for agent in (await teacher.get("/api/hub/agents")).json()}
    assert {"tro-ly-lop", "gia-su-toan", "tao-de", "tro-ly-phu-huynh"} <= teacher_view
    student_view = {agent["slug"] for agent in (await student.get("/api/hub/agents")).json()}
    assert "tao-de" not in student_view and "gia-su-toan" in student_view
    math_only = (await teacher.get("/api/hub/agents", params={"subject": "toan"})).json()
    assert "luyen-tieng-anh" not in {agent["slug"] for agent in math_only}


async def test_teacher_builds_versions_and_installs_own_agent(as_user, sessionmaker) -> None:
    teacher, student, _, room = await class_with_student(as_user)
    created = await teacher.post("/api/agents", json={"manifest": MANIFEST})
    assert created.status_code == 201, created.text
    agent = created.json()
    assert agent["version"] == 0 and agent["is_mine"] and agent["visibility"] == "private"

    # No version yet: cannot install.
    assert (await teacher.post(f"/api/classes/{room['id']}/agents", json={"agent_id": agent["id"]})).status_code == 400
    versioned = (await teacher.post(f"/api/agents/{agent['id']}/versions")).json()
    assert versioned["version"] == 1 and versioned["certification_status"] == "uncertified"
    assert (await teacher.post(f"/api/agents/{agent['id']}/versions")).status_code == 409

    installed = await teacher.post(f"/api/classes/{room['id']}/agents", json={"agent_id": agent["id"]})
    assert installed.status_code == 201
    teacher_agents = {
        a["slug"] for a in (await teacher.get("/api/chat/agents", params={"class_id": room["id"]})).json()
    }
    student_agents = {
        a["slug"] for a in (await student.get("/api/chat/agents", params={"class_id": room["id"]})).json()
    }
    # Uncertified: the class lists it, but students cannot reach it yet.
    assert "on-thi-hoa-9" not in student_agents and "on-thi-hoa-9" not in teacher_agents  # targets students only

    async with sessionmaker() as db:
        await db.execute(
            update(AgentVersion)
            .where(AgentVersion.id == versioned["version_id"])
            .values(certification_status="certified")
        )
        await db.commit()
    student_agents = {
        a["slug"] for a in (await student.get("/api/chat/agents", params={"class_id": room["id"]})).json()
    }
    assert "on-thi-hoa-9" in student_agents


async def test_manifest_validation_messages(as_user) -> None:
    teacher = await as_user("teacher")
    bad_tool = await teacher.post("/api/agents", json={"manifest": {**MANIFEST, "tools": ["shell"]}})
    assert bad_tool.status_code == 422 and "shell" in bad_tool.json()["detail"]
    bad_slug = await teacher.post("/api/agents", json={"manifest": {**MANIFEST, "slug": "Ôn Thi"}})
    assert bad_slug.status_code == 422 and "slug" in bad_slug.json()["detail"]
    taken = await teacher.post("/api/agents", json={"manifest": {**MANIFEST, "slug": "gia-su-toan"}})
    assert taken.status_code == 409


async def test_students_cannot_build_and_others_cannot_edit(as_user) -> None:
    teacher = await as_user("teacher")
    other = await as_user("teacher")
    student = await as_user("student")
    assert (await student.post("/api/agents", json={"manifest": MANIFEST})).status_code == 403
    agent = (await teacher.post("/api/agents", json={"manifest": MANIFEST})).json()
    assert (await other.put(f"/api/agents/{agent['id']}", json={"manifest": MANIFEST})).status_code == 404
    assert (await other.get(f"/api/hub/agents/{agent['id']}")).status_code == 404


async def test_fork_platform_agent(as_user) -> None:
    teacher = await as_user("teacher")
    hub = (await teacher.get("/api/hub/agents")).json()
    math = next(agent for agent in hub if agent["slug"] == "gia-su-toan")
    fork = (await teacher.post(f"/api/agents/{math['id']}/fork")).json()
    assert fork["slug"] == "gia-su-toan-ban-sao" and fork["forked_from_id"] == math["id"]
    assert fork["draft_manifest"]["system_prompt"] == fork["manifest"]["system_prompt"]
    second = (await teacher.post(f"/api/agents/{math['id']}/fork")).json()
    assert second["slug"] == "gia-su-toan-ban-sao-2"


async def test_personal_install_respects_role_and_class_policy(as_user) -> None:
    teacher, student, _, room = await class_with_student(as_user)
    hub = (await student.get("/api/hub/agents")).json()
    english = next(agent for agent in hub if agent["slug"] == "luyen-tieng-anh")
    assert (await student.post("/api/me/agents", json={"agent_id": english["id"]})).status_code == 201
    in_class = {a["slug"] for a in (await student.get("/api/chat/agents", params={"class_id": room["id"]})).json()}
    assert "luyen-tieng-anh" in in_class
    policy = (await teacher.get(f"/api/classes/{room['id']}/policy")).json()
    await teacher.put(f"/api/classes/{room['id']}/policy", json={**policy, "allow_personal_agents": False})
    in_class = {a["slug"] for a in (await student.get("/api/chat/agents", params={"class_id": room["id"]})).json()}
    assert "luyen-tieng-anh" not in in_class
    # Outside the class the personal agent still works.
    personal = {a["slug"] for a in (await student.get("/api/chat/agents")).json()}
    assert "luyen-tieng-anh" in personal

    teacher_hub = (await teacher.get("/api/hub/agents")).json()
    quiz = next(agent for agent in teacher_hub if agent["slug"] == "tao-de")
    assert (await student.post("/api/me/agents", json={"agent_id": quiz["id"]})).status_code in (400, 404)


async def test_class_agent_toggle_and_uninstall(as_user) -> None:
    teacher, student, _, room = await class_with_student(as_user)
    hub = (await teacher.get("/api/hub/agents")).json()
    math = next(agent for agent in hub if agent["slug"] == "gia-su-toan")
    installation = (await teacher.post(f"/api/classes/{room['id']}/agents", json={"agent_id": math["id"]})).json()
    await teacher.patch(f"/api/classes/{room['id']}/agents/{installation['id']}", json={"enabled": False})
    assert "gia-su-toan" not in {
        a["slug"] for a in (await student.get("/api/chat/agents", params={"class_id": room["id"]})).json()
    }
    assert (await teacher.delete(f"/api/classes/{room['id']}/agents/{installation['id']}")).status_code == 204
    assert (await teacher.get(f"/api/classes/{room['id']}/agents")).json() == []
    fallback = next(agent for agent in hub if agent["slug"] == "tro-ly-lop")
    assert (
        await teacher.post(f"/api/classes/{room['id']}/agents", json={"agent_id": fallback["id"]})
    ).status_code == 400


async def test_sandbox_runs_draft_without_class_and_hides_from_history(as_user, fake_llm) -> None:
    teacher = await as_user("teacher")
    agent = (await teacher.post("/api/agents", json={"manifest": MANIFEST})).json()
    fake_llm.script("Chào em, cùng ôn Hoá 9 nhé!")
    response = await teacher.post(f"/api/agents/{agent['id']}/try", json={"message": "Xin chào", "as_role": "student"})
    events = parse_sse(response.text)
    assert next(event for event in events if event["type"] == "agent")["agent"] == "on-thi-hoa-9"
    assert reply_text(events) == "Chào em, cùng ôn Hoá 9 nhé!"
    assert "Ôn thi Hoá 9" in fake_llm.main_calls[-1]["system"]
    assert (await teacher.get("/api/chat/conversations")).json() == []
    # A normal personal chat still goes to the fallback.
    events = await chat(teacher, "Xin chào")
    assert next(event for event in events if event["type"] == "agent")["agent"] == "tro-ly-lop"
