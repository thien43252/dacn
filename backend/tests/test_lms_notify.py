from datetime import UTC, datetime

from sqlalchemy import select

from app.lms.models import Notification
from app.lms.notify import notify


async def test_notify_deduplicates_pending_and_committed_rows(as_user, sessionmaker) -> None:
    student = await as_user("student")
    async with sessionmaker() as db:
        args = {
            "user_ids": [student.user["id"]],
            "kind": "due_soon",
            "title": "Bài tập sắp đến hạn",
            "link": "/student/todo",
            "dedupe_key": "due_soon:assignment",
        }
        assert await notify(db, **args) == 1
        assert await notify(db, **args) == 0
        await db.commit()
    async with sessionmaker() as db:
        assert await notify(db, **args) == 0
        await db.commit()
        rows = list(await db.scalars(select(Notification)))
        assert len(rows) == 1
        assert rows[0].dedupe_key == f"due_soon:assignment:{student.user['id']}"
    response = await student.get("/api/notifications")
    assert response.status_code == 200, response.text
    assert response.json()["unread_count"] == 1
    assert response.json()["items"][0]["title"] == args["title"]


async def test_read_selected_and_all_notifications_are_scoped_to_user(as_user, sessionmaker, monkeypatch) -> None:
    student = await as_user("student")
    other = await as_user("student")
    stamp = datetime(2026, 11, 16, 8, tzinfo=UTC)
    monkeypatch.setattr("app.lms.now", lambda: stamp)
    async with sessionmaker() as db:
        for key in ("first", "second"):
            assert (
                await notify(
                    db,
                    [student.user["id"], other.user["id"]],
                    "assigned",
                    "Có bài tập mới",
                    dedupe_key=key,
                )
                == 2
            )
        await db.commit()
    response = await student.get("/api/notifications")
    assert response.status_code == 200, response.text
    mine = response.json()
    theirs = (await other.get("/api/notifications")).json()
    assert mine["unread_count"] == theirs["unread_count"] == 2
    my_ids = {item["id"] for item in mine["items"]}
    other_ids = {item["id"] for item in theirs["items"]}
    assert len(my_ids) == len(other_ids) == 2
    assert my_ids.isdisjoint(other_ids)
    selected = mine["items"][0]["id"]
    response = await student.post("/api/notifications/read", json={"ids": [selected, *other_ids]})
    assert response.status_code == 200, response.text
    assert response.json()["unread_count"] == 1
    assert {item["id"] for item in response.json()["items"] if item["read_at"]} == {selected}
    read_item = next(item for item in response.json()["items"] if item["id"] == selected)
    assert datetime.fromisoformat(read_item["read_at"]).replace(tzinfo=UTC) == stamp
    response = await student.get("/api/notifications", params={"unread": 1})
    assert response.status_code == 200, response.text
    assert response.json()["unread_count"] == 1
    assert {item["id"] for item in response.json()["items"]} == my_ids - {selected}
    response = await student.post("/api/notifications/read", json={})
    assert response.status_code == 200, response.text
    assert response.json()["unread_count"] == 0
    assert {item["id"] for item in response.json()["items"]} == my_ids
    assert all(item["read_at"] for item in response.json()["items"])
    assert (await student.get("/api/notifications?unread=1")).json() == {"items": [], "unread_count": 0}
    response = await other.get("/api/notifications")
    assert response.status_code == 200, response.text
    assert response.json()["unread_count"] == 2
    assert {item["id"] for item in response.json()["items"]} == other_ids
    assert all(item["read_at"] is None for item in response.json()["items"])
