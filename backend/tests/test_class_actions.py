"""Class announcements and assigned practice over REST (specs/002-multi-agent-orchestration/contracts/class-actions.md)."""

from app.class_feed.models import Assignment
from tests.helpers import class_with_student


async def post(teacher, class_id: str, audience: str, title: str) -> dict:
    response = await teacher.post(
        f"/api/classes/{class_id}/announcements",
        json={"title": title, "body": f"Nội dung cho {audience}, đủ dài.", "audience": audience},
    )
    assert response.status_code == 201, response.text
    return response.json()


async def test_each_reader_sees_what_is_meant_for_them(app, as_user) -> None:
    teacher, student, parent, room = await class_with_student(as_user)
    for audience in ("students", "parents", "all"):
        await post(teacher, room["id"], audience, f"Cho {audience}")
    url = f"/api/classes/{room['id']}/announcements"
    titles = lambda response: sorted(item["title"] for item in response.json())  # noqa: E731
    assert titles(await teacher.get(url)) == ["Cho all", "Cho parents", "Cho students"]
    assert titles(await student.get(url)) == ["Cho all", "Cho students"]
    assert titles(await parent.get(url)) == ["Cho all", "Cho parents"]
    [shared] = [item for item in (await teacher.get(url)).json() if item["title"] == "Cho all"]
    assert shared["audience"] == "all" and shared["source"] == "ui" and shared["author_name"]


async def test_only_the_class_teacher_posts_and_deletes(app, as_user) -> None:
    teacher, student, _, room = await class_with_student(as_user)
    url = f"/api/classes/{room['id']}/announcements"
    body = {"title": "Nghỉ học", "body": "Thứ Hai lớp nghỉ học.", "audience": "all"}
    assert (await student.post(url, json=body)).status_code == 403
    outsider = await as_user("teacher")
    assert (await outsider.get(url)).status_code == 404
    assert (await outsider.post(url, json=body)).status_code == 404
    posted = await post(teacher, room["id"], "all", "Nghỉ học")
    assert (await student.delete(f"{url}/{posted['id']}")).status_code == 403
    assert (await teacher.delete(f"{url}/{posted['id']}")).status_code == 204
    assert (await teacher.get(url)).json() == []


async def test_posted_announcements_get_the_keyword_check(app, as_user) -> None:
    from app.guard import dify_rules

    teacher, _, _, room = await class_with_student(as_user)
    response = await teacher.post(
        f"/api/classes/{room['id']}/announcements",
        json={"title": "Thông báo", "body": f"Có {dify_rules.keywords()[0]} ở đây.", "audience": "all"},
    )
    assert response.status_code == 422


async def test_only_teachers_see_answer_keys(app, as_user, sessionmaker) -> None:
    teacher, student, parent, room = await class_with_student(as_user)
    async with sessionmaker() as db:
        row = Assignment(
            class_id=room["id"],
            author_id=teacher.user["id"],
            title="Luyện Pytago",
            questions=[{"question": "Cạnh huyền của tam giác 6-8?", "options": ["10", "12"]}],
            answer_key=[{"index": 1, "answer": "10"}],
            source="agent",
        )
        db.add(row)
        await db.commit()
        assignment_id = row.id
    url = f"/api/classes/{room['id']}/assignments"
    assert (await teacher.get(url)).json()[0]["answer_key"] == [{"index": 1, "answer": "10"}]
    for reader in (student, parent):
        [item] = (await reader.get(url)).json()
        assert item["answer_key"] is None and item["questions"][0]["options"] == ["10", "12"]
        assert (await reader.get(f"{url}/{assignment_id}")).json()["answer_key"] is None
    assert (await teacher.get(f"{url}/{assignment_id}")).json()["answer_key"]
    assert (await student.delete(f"{url}/{assignment_id}")).status_code == 403
    assert (await teacher.delete(f"{url}/{assignment_id}")).status_code == 204
    assert (await teacher.get(f"{url}/{assignment_id}")).status_code == 404
