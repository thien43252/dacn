CLASS = {"name": "Toán 8A1", "subject": "toan", "grade": 8, "description": "Lớp học thêm buổi tối"}


async def create_class(teacher, **overrides) -> dict:
    response = await teacher.post("/api/classes", json={**CLASS, **overrides})
    assert response.status_code == 201, response.text
    return response.json()


async def test_teacher_creates_class_and_sees_join_code(as_user) -> None:
    teacher = await as_user("teacher", "Cô Hà")
    room = await create_class(teacher)
    assert room["my_role"] == "teacher"
    assert room["teacher_name"] == "Cô Hà"
    assert len(room["join_code"]) == 6
    assert room["student_count"] == 0
    listed = (await teacher.get("/api/classes")).json()
    assert [item["id"] for item in listed] == [room["id"]]


async def test_only_teachers_create_classes(as_user) -> None:
    student = await as_user("student")
    assert (await student.post("/api/classes", json=CLASS)).status_code == 403


async def test_student_joins_by_code_without_seeing_code(as_user) -> None:
    teacher = await as_user("teacher")
    student = await as_user("student")
    room = await create_class(teacher)
    code = room["join_code"]
    joined = await student.post("/api/classes/join", json={"code": f" {code[:3].lower()}-{code[3:]} "})
    assert joined.status_code == 200, joined.text
    assert joined.json()["my_role"] == "student"
    assert joined.json()["join_code"] is None
    # Joining twice is harmless.
    await student.post("/api/classes/join", json={"code": code})
    assert (await teacher.get(f"/api/classes/{room['id']}")).json()["student_count"] == 1


async def test_wrong_code_and_parent_join_are_rejected(as_user) -> None:
    teacher = await as_user("teacher")
    parent = await as_user("parent")
    student = await as_user("student")
    room = await create_class(teacher)
    assert (await student.post("/api/classes/join", json={"code": "ZZZZZZ"})).status_code == 404
    assert (await parent.post("/api/classes/join", json={"code": room["join_code"]})).status_code == 403


async def test_outsider_gets_404_not_403(as_user) -> None:
    teacher = await as_user("teacher")
    other_teacher = await as_user("teacher")
    room = await create_class(teacher)
    assert (await other_teacher.get(f"/api/classes/{room['id']}")).status_code == 404
    assert (await other_teacher.get(f"/api/classes/{room['id']}/members")).status_code == 404


async def test_student_cannot_manage_class(as_user) -> None:
    teacher = await as_user("teacher")
    student = await as_user("student")
    room = await create_class(teacher)
    await student.post("/api/classes/join", json={"code": room["join_code"]})
    assert (await student.get(f"/api/classes/{room['id']}/members")).status_code == 403
    assert (await student.patch(f"/api/classes/{room['id']}", json={"name": "Hack"})).status_code == 403
    policy = await student.put(f"/api/classes/{room['id']}/policy", json={"no_direct_answers": False})
    assert policy.status_code == 403


async def test_rotating_code_invalidates_old_one(as_user) -> None:
    teacher = await as_user("teacher")
    student = await as_user("student")
    room = await create_class(teacher)
    rotated = (await teacher.post(f"/api/classes/{room['id']}/join-code")).json()
    assert rotated["join_code"] != room["join_code"]
    assert (await student.post("/api/classes/join", json={"code": room["join_code"]})).status_code == 404
    assert (await student.post("/api/classes/join", json={"code": rotated["join_code"]})).status_code == 200


async def test_teacher_adds_student_by_email_and_removes(as_user) -> None:
    teacher = await as_user("teacher")
    student = await as_user("student", "Minh Anh")
    room = await create_class(teacher)
    members = await teacher.post(f"/api/classes/{room['id']}/members", json={"email": student.user["email"].upper()})
    assert members.status_code == 201
    assert {m["name"] for m in members.json() if m["role"] == "student"} == {"Minh Anh"}
    missing = await teacher.post(f"/api/classes/{room['id']}/members", json={"email": "nobody@example.com"})
    assert missing.status_code == 404
    deleted = await teacher.delete(f"/api/classes/{room['id']}/members/{student.user['id']}")
    assert deleted.status_code == 204
    assert (await teacher.get(f"/api/classes/{room['id']}")).json()["student_count"] == 0


async def test_parent_links_with_child_code_and_sees_classes(as_user) -> None:
    teacher = await as_user("teacher")
    student = await as_user("student", "Minh Anh")
    parent = await as_user("parent", "Bố Bình")
    room = await create_class(teacher)
    await student.post("/api/classes/join", json={"code": room["join_code"]})

    code = (await student.get("/api/me/link-code")).json()["code"]
    assert (await parent.post("/api/parent/children", json={"code": "WRONG1"})).status_code == 404
    children = (await parent.post("/api/parent/children", json={"code": code.lower()})).json()
    assert [child["name"] for child in children] == ["Minh Anh"]
    assert [klass["name"] for klass in children[0]["classes"]] == ["Toán 8A1"]
    assert children[0]["consent"]["allow_agents"] is False

    # The parent reaches the class through the child, read-only.
    detail = await parent.get(f"/api/classes/{room['id']}")
    assert detail.json()["my_role"] == "parent"
    assert detail.json()["children"] == [student.user["id"]]
    assert detail.json()["join_code"] is None
    assert (await parent.get(f"/api/classes/{room['id']}/members")).status_code == 403

    linked = (await student.get("/api/me/link-code")).json()["parents"]
    assert [p["name"] for p in linked] == ["Bố Bình"]


async def test_consent_gates_agent_use_per_class_setting(as_user) -> None:
    teacher = await as_user("teacher")
    student = await as_user("student")
    parent = await as_user("parent")
    room = await create_class(teacher)
    await student.post("/api/classes/join", json={"code": room["join_code"]})

    def can_use(members: list[dict]) -> bool:
        return next(m for m in members if m["role"] == "student")["can_use_agents"]

    assert can_use((await teacher.get(f"/api/classes/{room['id']}/members")).json()) is False

    code = (await student.get("/api/me/link-code")).json()["code"]
    await parent.post("/api/parent/children", json={"code": code})
    consent = await parent.put(f"/api/parent/children/{student.user['id']}/consent", json={"allow_agents": True})
    assert consent.json()["allow_agents"] is True
    assert can_use((await teacher.get(f"/api/classes/{room['id']}/members")).json()) is True

    await parent.put(f"/api/parent/children/{student.user['id']}/consent", json={"allow_agents": False})
    assert can_use((await teacher.get(f"/api/classes/{room['id']}/members")).json()) is False

    await teacher.patch(f"/api/classes/{room['id']}", json={"require_parent_consent": False})
    assert can_use((await teacher.get(f"/api/classes/{room['id']}/members")).json()) is True


async def test_parent_cannot_consent_for_unlinked_child(as_user) -> None:
    student = await as_user("student")
    parent = await as_user("parent")
    response = await parent.put(f"/api/parent/children/{student.user['id']}/consent", json={"allow_agents": True})
    assert response.status_code == 404


async def test_teacher_links_parent_by_email(as_user) -> None:
    teacher = await as_user("teacher")
    student = await as_user("student")
    parent = await as_user("parent", "Mẹ Lan")
    room = await create_class(teacher)
    await student.post("/api/classes/join", json={"code": room["join_code"]})
    members = await teacher.post(
        f"/api/classes/{room['id']}/parents",
        json={"parent_email": parent.user["email"], "student_id": student.user["id"]},
    )
    assert members.status_code == 200
    row = next(m for m in members.json() if m["role"] == "student")
    assert [p["name"] for p in row["parents"]] == ["Mẹ Lan"]
    # A student outside the class cannot be targeted.
    outsider = await as_user("student")
    response = await teacher.post(
        f"/api/classes/{room['id']}/parents",
        json={"parent_email": parent.user["email"], "student_id": outsider.user["id"]},
    )
    assert response.status_code == 404


async def test_policy_roundtrip_with_defaults(as_user) -> None:
    teacher = await as_user("teacher")
    room = await create_class(teacher)
    policy = (await teacher.get(f"/api/classes/{room['id']}/policy")).json()
    assert policy["no_direct_answers"] is True
    updated = {**policy, "blocked_topics": ["game"], "notes_for_agents": "Xưng cô, gọi các em."}
    assert (await teacher.put(f"/api/classes/{room['id']}/policy", json=updated)).json() == updated
    assert (await teacher.get(f"/api/classes/{room['id']}/policy")).json() == updated
