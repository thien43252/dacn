"""Group chats (US4): membership rules, privacy, routing with a "nobody" choice, separate handoff messages and
private replies."""

from app.llm.fake import Scripted
from app.orchestration.runs import NOTE_HEADER
from tests.helpers import CLASS, agent_of, chat, class_with_student, conversation_messages, install, tool_call


async def family(as_user):
    """A class with a homeroom teacher, a maths teacher, two students and their two parents."""
    teacher, student, parent, room = await class_with_student(as_user)
    other = await as_user("student")
    await other.post("/api/classes/join", json={"code": room["join_code"]})
    other_parent = await as_user("parent")
    code = (await other.get("/api/me/link-code")).json()["code"]
    await other_parent.post("/api/parent/children", json={"code": code})
    await other_parent.put(f"/api/parent/children/{other.user['id']}/consent", json={"allow_agents": True})
    return teacher, student, parent, other, other_parent, room


async def make_group(client, room, members, agents=("tro-ly-lop",), **extra):
    response = await client.post(
        "/api/chat/groups",
        json={"class_id": room["id"], "title": "Ôn thi HK1", "members": members, "agents": list(agents), **extra},
    )
    return response


async def test_student_member_rules_and_privacy(as_user) -> None:
    teacher, student, parent, other, other_parent, room = await family(as_user)
    candidates = (await student.get("/api/chat/groups/candidates", params={"class_id": room["id"]})).json()
    ids = {person["id"] for person in candidates["people"]}
    assert {teacher.user["id"], parent.user["id"], other.user["id"]} <= ids
    assert other_parent.user["id"] not in ids  # FR-039

    bad = await make_group(student, room, [other_parent.user["id"]])
    assert bad.status_code == 422
    group = (await make_group(student, room, [other.user["id"], parent.user["id"]])).json()
    assert group["kind"] == "group" and group["default_agent"] == "tro-ly-lop"

    # Fully private: the homeroom teacher (not a member) cannot see it at all (FR-040).
    assert (await teacher.get(f"/api/chat/conversations/{group['id']}/messages")).status_code == 404
    assert (await teacher.get(f"/api/chat/conversations/{group['id']}/events")).status_code == 404
    listed = (await teacher.get("/api/chat/conversations", params={"all": True})).json()
    assert group["id"] not in {c["id"] for c in listed}
    assert group["id"] in {c["id"] for c in (await other.get("/api/chat/conversations", params={"all": True})).json()}


async def test_teacher_can_turn_off_member_groups(as_user) -> None:
    teacher, student, _, room = await class_with_student(as_user)
    policy = (await teacher.get(f"/api/classes/{room['id']}/policy")).json()
    await teacher.put(f"/api/classes/{room['id']}/policy", json={**policy, "members_can_create_groups": False})
    assert (await make_group(student, room, [])).status_code == 403
    assert (await make_group(teacher, room, [student.user["id"]])).status_code == 201


async def test_messages_reach_members_and_history_rules(as_user, fake_llm) -> None:
    teacher, student, parent, other, _, room = await family(as_user)
    group = (await make_group(teacher, room, [student.user["id"]])).json()
    events = await chat(
        student, "Chào cả nhà, mai mình họp lúc mấy giờ nhỉ @Teacher", class_id=room["id"], conversation_id=group["id"]
    )
    assert events[-1]["agent"] is None  # a message for a person: no agent speaks
    assert fake_llm.main_calls == []
    seen = await conversation_messages(teacher, group["id"])
    assert [m["sender"]["id"] for m in seen] == [student.user["id"]]
    assert seen[0]["sender"]["role_label"] == "Học sinh"

    # A new member does not see history unless allowed; a removed member sees nothing more.
    await teacher.post(f"/api/chat/groups/{group['id']}/members", json={"users": [other.user["id"]]})
    assert await conversation_messages(other, group["id"]) == []
    await teacher.post(
        f"/api/chat/groups/{group['id']}/members", json={"users": [parent.user["id"]], "can_see_history": True}
    )
    assert len(await conversation_messages(parent, group["id"])) == 1
    members = (await teacher.get(f"/api/chat/groups/{group['id']}/members")).json()
    other_row = next(m for m in members if m.get("user_id") == other.user["id"])
    assert (await teacher.delete(f"/api/chat/groups/{group['id']}/members/{other_row['id']}")).status_code == 204
    assert (await other.get(f"/api/chat/conversations/{group['id']}/messages")).status_code == 404


async def test_mention_routes_and_handoff_is_its_own_message(as_user, fake_llm, drain) -> None:
    teacher, student, _, room = await class_with_student(as_user)
    await install(teacher, room, "gia-su-toan")
    group = (await make_group(teacher, room, [student.user["id"]], agents=("tro-ly-lop", "gia-su-toan"))).json()

    def respond(messages, system, tools, tier):
        if tier != "main":
            return None
        agent, last = agent_of(system), messages[-1]
        if agent == "tro-ly-lop":
            if last.role == "user" and last.content.startswith(NOTE_HEADER):
                return Scripted(text="Tóm lại: làm theo gợi ý của Gia sư Toán nhé.")
            if last.role == "tool":
                return Scripted(text="Mình nhờ Gia sư Toán.")
            return tool_call(
                "message_agent", agent="gia-su-toan", task="Giải thích bước 2", bounds="ngắn", good_answer="dễ hiểu"
            )
        if agent == "gia-su-toan":
            return Scripted(text="Bước 2: chuyển vế rồi chia hai vế cho 2.")
        return None

    fake_llm.respond_with(respond)
    events = await chat(
        student, "@tro-ly-lop nhờ Gia sư Toán giải thích bước 2", class_id=room["id"], conversation_id=group["id"]
    )
    assert events[-1]["agent"] == "tro-ly-lop"
    await drain()
    seen = await conversation_messages(teacher, group["id"])
    kinds = [(m["sender"]["kind"], m["agent_slug"], m["reply_to_agent"]) for m in seen]
    assert kinds == [
        ("user", None, None),
        ("agent", "tro-ly-lop", None),
        ("agent", "gia-su-toan", "tro-ly-lop"),
        ("agent", "tro-ly-lop", None),
    ]
    assert await drain() == 0 and len(await conversation_messages(teacher, group["id"])) == 4


async def test_personal_data_moves_to_a_private_chat(as_user, fake_llm, drain) -> None:
    teacher, student, parent, other, _, room = await family(as_user)
    group = (await make_group(teacher, room, [student.user["id"], other.user["id"]])).json()

    def respond(messages, system, tools, tier):
        if tier != "main" or agent_of(system) != "tro-ly-lop":
            return None
        names = {tool.name for tool in tools or []}
        if "reply_privately" in names and "điểm" in messages[-1].content:
            assert "progress_summary" not in names  # never offered in a group (FR-046)
            return tool_call("reply_privately", reason="điểm riêng")
        if messages[-1].role == "tool":
            return Scripted(text="(nội dung này bị thay)")
        return Scripted(text="Điểm bài kiểm tra của em: 8.")

    fake_llm.respond_with(respond)
    await chat(
        student, "@tro-ly-lop em được mấy điểm bài kiểm tra Toán?", class_id=room["id"], conversation_id=group["id"]
    )
    seen_by_other = await conversation_messages(other, group["id"])
    assert seen_by_other[-1]["content"] == "Mình sẽ trả lời riêng cho bạn trong chat riêng."
    await drain()
    private = [
        c
        for c in (await student.get("/api/chat/conversations", params={"all": True})).json()
        if c["kind"] == "direct" and c["agent"]["slug"] == "tro-ly-lop"
    ]
    [direct] = private
    messages = await conversation_messages(student, direct["id"])
    assert messages[-1]["content"] == "Điểm bài kiểm tra của em: 8."
    assert all("8." not in m["content"] for m in await conversation_messages(other, group["id"]))


async def test_safety_reply_in_a_group_is_only_for_the_writer(as_user, fake_llm) -> None:
    teacher, student, _, other, _, room = await family(as_user)
    group = (await make_group(teacher, room, [student.user["id"], other.user["id"]])).json()
    await chat(student, "Mình mệt mỏi lắm, không muốn sống nữa.", class_id=room["id"], conversation_id=group["id"])
    mine = await conversation_messages(student, group["id"])
    theirs = await conversation_messages(other, group["id"])
    replies_mine = [m for m in mine if m["role"] == "assistant"]
    assert replies_mine and replies_mine[-1]["visible_to"] == [student.user["id"]]
    assert not any(m["role"] == "assistant" for m in theirs)


async def test_outsiders_cannot_join_or_post(as_user) -> None:
    teacher, student, _, room = await class_with_student(as_user)
    group = (await make_group(teacher, room, [student.user["id"]])).json()
    stranger = await as_user("student")
    other_room = (await teacher.post("/api/classes", json=CLASS)).json()
    await stranger.post("/api/classes/join", json={"code": other_room["join_code"]})
    response = await stranger.post(
        "/api/chat/stream", json={"message": "x", "class_id": room["id"], "conversation_id": group["id"]}
    )
    assert response.status_code == 404
    assert (await student.post(f"/api/chat/groups/{group['id']}/members", json={"users": []})).status_code == 403
