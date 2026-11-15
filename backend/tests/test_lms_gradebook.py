import csv
import io
import time
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.auth.models import User
from app.classes.models import ClassMember
from app.lms import jobs
from app.lms.models import (
    Assignment,
    AssignmentExtension,
    Lesson,
    LessonItem,
    Notification,
    Quiz,
    QuizAttempt,
    QuizQuestion,
    Submission,
)
from tests.helpers import CLASS, class_with_student

STAMP = datetime(2026, 11, 16, 12, tzinfo=UTC)


async def add_item(db, cid, kind="assignment", position=0, status="published", **config):
    lesson = Lesson(class_id=cid, title=f"Buổi {position}", position=position, status=status)
    db.add(lesson)
    await db.flush()
    item = LessonItem(class_id=cid, lesson_id=lesson.id, kind=kind, title=f"Bài {position}", position=position)
    db.add(item)
    await db.flush()
    db.add((Assignment if kind == "assignment" else Quiz)(item_id=item.id, class_id=cid, **config))
    if kind == "quiz":
        await db.flush()
        db.add(QuizQuestion(quiz_id=item.id, class_id=cid, kind="short", prompt="Một cộng một?", points=20))
    await db.flush()
    return item


async def test_gradebook_states_average_csv_weights(as_user, sessionmaker, monkeypatch):
    teacher, student, _, room = await class_with_student(as_user)
    monkeypatch.setattr("app.lms.now", lambda: STAMP)
    cid, sid = room["id"], student.user["id"]
    async with sessionmaker() as db:
        user = await db.get(User, sid)
        user.name = "Nguyễn Thị Ánh"
        member = await db.scalar(select(ClassMember).where(ClassMember.user_id == sid))
        member.joined_at = STAMP - timedelta(days=2)
        configs = [
            dict(due_at=STAMP - timedelta(days=1)),
            dict(due_at=STAMP - timedelta(days=3)),
            dict(due_at=STAMP + timedelta(days=1)),
            {},
            dict(max_points=20, weight=2),
            dict(counts_in_grade=False),
        ]
        items = [await add_item(db, cid, position=n, **config) for n, config in enumerate(configs)]
        for index, state, raw, final in [(3, "submitted", None, None), (4, "graded", 18, 16), (5, "returned", 1, 1)]:
            db.add(
                Submission(
                    class_id=cid,
                    assignment_id=items[index].id,
                    student_id=sid,
                    status=state,
                    raw_score=raw,
                    final_score=final,
                )
            )
        for n, state, score in [(6, "in_progress", None), (7, "submitted", None), (8, "graded", 10)]:
            item = await add_item(db, cid, kind="quiz", position=n, status="archived" if n == 8 else "published")
            items.append(item)
            db.add(
                QuizAttempt(
                    class_id=cid,
                    quiz_id=item.id,
                    student_id=sid,
                    status=state,
                    attempt_no=1,
                    started_at=STAMP,
                    score=score,
                    max_score=20,
                )
            )
        await add_item(db, cid, position=9, status="draft")
        await db.commit()
    base = f"/api/classes/{cid}"
    response = await teacher.get(f"{base}/gradebook")
    assert response.status_code == 200, response.text
    book = response.json()
    assert len(book["columns"]) == 9
    row = book["rows"][0]
    assert [c["state"] for c in row["cells"]] == [
        "missing",
        "not_assigned",
        "open",
        "pending",
        "graded",
        "returned",
        "in_progress",
        "pending",
        "graded",
    ]
    assert row["cells"][4]["final"] == 16
    assert row["average"] == 5.25
    assert book["columns"][-1]["archived"] and book["columns"][-1]["max_points"] == 20
    for suffix in ("gradebook", "gradebook.csv"):
        assert (await student.get(f"{base}/{suffix}")).status_code == 403
    exported = await teacher.get(f"{base}/gradebook.csv")
    assert exported.content.startswith(b"\xef\xbb\xbf")
    rows = list(csv.reader(io.StringIO(exported.content.decode("utf-8-sig"))))
    assert rows[0][0] == "Học sinh" and rows[0][-1] == "Điểm TB"
    assert rows[1][0] == "Nguyễn Thị Ánh"
    assert "so-diem-toan-8a1.csv" in exported.headers["content-disposition"]
    path = f"{base}/gradebook/columns/{items[4].id}"
    assert (await teacher.patch(path, json={"weight": -1})).status_code == 422
    assert (await teacher.patch(path, json={"weight": 3})).status_code == 200
    assert (await teacher.get(f"{base}/gradebook")).json()["rows"][0]["average"] == 5.8
    assert (await teacher.patch(path, json={"counts_in_grade": False})).status_code == 200
    assert (await teacher.get(f"{base}/gradebook")).json()["rows"][0]["average"] == 2.5


async def test_quiz_policies_personal_visibility(as_user, sessionmaker, monkeypatch):
    teacher, student, parent, room = await class_with_student(as_user)
    monkeypatch.setattr("app.lms.now", lambda: STAMP)
    cid, sid = room["id"], student.user["id"]
    async with sessionmaker() as db:
        for n, policy in enumerate(["best", "last", "average"]):
            item = await add_item(db, cid, kind="quiz", position=n, scoring_policy=policy)
            for attempt_no, score in enumerate([16, 8], 1):
                db.add(
                    QuizAttempt(
                        class_id=cid,
                        quiz_id=item.id,
                        student_id=sid,
                        status="graded",
                        attempt_no=attempt_no,
                        started_at=STAMP,
                        score=score,
                        max_score=20,
                    )
                )
        for n, mode, close in [
            (3, "never", STAMP - timedelta(hours=1)),
            (4, "after_close", STAMP + timedelta(hours=1)),
            (5, "after_close", STAMP - timedelta(hours=1)),
        ]:
            item = await add_item(db, cid, kind="quiz", position=n, show_score=mode, close_at=close)
            db.add(
                QuizAttempt(
                    class_id=cid,
                    quiz_id=item.id,
                    student_id=sid,
                    status="graded",
                    attempt_no=1,
                    started_at=STAMP,
                    score=10,
                    max_score=20,
                )
            )
        for n, status in [(6, "graded"), (7, "returned")]:
            item = await add_item(db, cid, position=n)
            db.add(
                Submission(
                    class_id=cid, assignment_id=item.id, student_id=sid, status=status, raw_score=9, final_score=8
                )
            )
        await db.commit()
    base = f"/api/classes/{cid}"
    book = (await teacher.get(f"{base}/gradebook")).json()
    assert [c["final"] for c in book["rows"][0]["cells"][:3]] == [16, 8, 12]
    for reader in (student, parent):
        response = await reader.get(f"{base}/my-grades?student_id={sid}")
        assert response.status_code == 200, response.text
        grades = response.json()
        assert [c["title"] for c in grades["columns"]] == ["Bài 0", "Bài 1", "Bài 2", "Bài 5", "Bài 7"]
        assert grades["cells"][-1]["final"] == 8


async def test_todo_extensions_and_reminder_dedupe(as_user, sessionmaker, monkeypatch):
    teacher, student, parent, room = await class_with_student(as_user)
    monkeypatch.setattr("app.lms.now", lambda: STAMP)
    second = (await teacher.post("/api/classes", json=CLASS)).json()
    await student.post("/api/classes/join", json={"code": second["join_code"]})
    sid = student.user["id"]
    async with sessionmaker() as db:
        later = await add_item(db, room["id"], due_at=STAMP + timedelta(hours=23))
        earlier = await add_item(db, second["id"], kind="quiz", close_at=STAMP + timedelta(hours=1))
        submitted = await add_item(db, room["id"], position=1, due_at=STAMP + timedelta(hours=2))
        db.add(Submission(class_id=room["id"], assignment_id=submitted.id, student_id=sid))
        await add_item(db, room["id"], position=2, due_at=STAMP - timedelta(hours=1), allow_late=False)
        extended = await add_item(db, room["id"], position=3, due_at=STAMP - timedelta(hours=1), allow_late=False)
        db.add(AssignmentExtension(assignment_id=extended.id, student_id=sid, due_at=STAMP + timedelta(hours=30)))
        no_due = await add_item(db, room["id"], position=4)
        await add_item(db, room["id"], position=5, status="draft", due_at=STAMP + timedelta(hours=1))
        completed = await add_item(db, room["id"], kind="quiz", position=6, close_at=STAMP + timedelta(hours=1))
        db.add(
            QuizAttempt(
                class_id=room["id"],
                quiz_id=completed.id,
                student_id=sid,
                status="submitted",
                attempt_no=1,
                started_at=STAMP,
            )
        )
        await db.commit()
    for reader in (student, parent):
        response = await reader.get(f"/api/todo?student_id={sid}")
        assert response.status_code == 200, response.text
        assert [r["item_id"] for r in response.json()] == [earlier.id, later.id, extended.id, no_due.id]
    async with sessionmaker() as db:
        await jobs.run_due(db)
        await jobs.run_due(db)
        notices = list(await db.scalars(select(Notification).where(Notification.kind == "due_soon")))
        assert len(notices) == 2
        assert {r.dedupe_key for r in notices} == {f"due_soon:{i}:{sid}" for i in [earlier.id, later.id]}


async def test_gradebook_40_by_20_under_three_seconds(as_user, sessionmaker):
    teacher, student, _, room = await class_with_student(as_user)
    async with sessionmaker() as db:
        students = [student.user["id"]]
        for n in range(39):
            user = User(email=f"perf{n}@example.com", name=f"Học sinh {n}", role="student", password_hash="unused")
            db.add(user)
            await db.flush()
            students.append(user.id)
            db.add(ClassMember(class_id=room["id"], user_id=user.id, role="student"))
        for n in range(20):
            item = await add_item(db, room["id"], position=n)
            db.add_all(
                [
                    Submission(
                        class_id=room["id"],
                        assignment_id=item.id,
                        student_id=sid,
                        status="graded",
                        raw_score=8,
                        final_score=8,
                    )
                    for sid in students
                ]
            )
        await db.commit()
    started = time.perf_counter()
    response = await teacher.get(f"/api/classes/{room['id']}/gradebook")
    elapsed = time.perf_counter() - started
    assert response.status_code == 200, response.text
    assert len(response.json()["rows"]) == 40 and len(response.json()["columns"]) == 20
    assert all(r["average"] == 8 for r in response.json()["rows"])
    assert elapsed < 3, elapsed


async def test_todo_quiz_windows_and_reminder_boundaries(as_user, sessionmaker, monkeypatch):
    teacher, student, _, room = await class_with_student(as_user)
    other = await as_user("student")
    await other.post("/api/classes/join", json={"code": room["join_code"]})
    monkeypatch.setattr("app.lms.now", lambda: STAMP)
    cid, sid = room["id"], student.user["id"]
    async with sessionmaker() as db:
        edge = await add_item(db, cid, due_at=STAMP + timedelta(hours=24))
        await add_item(db, cid, position=1, due_at=STAMP + timedelta(hours=24, seconds=1))
        await add_item(db, cid, position=2, due_at=STAMP - timedelta(seconds=1), allow_late=False)
        hidden = await add_item(db, cid, position=3, due_at=STAMP + timedelta(hours=1))
        hidden.visible = False
        future = await add_item(
            db, cid, kind="quiz", position=4, open_at=STAMP + timedelta(hours=1), close_at=STAMP + timedelta(hours=2)
        )
        active = await add_item(db, cid, kind="quiz", position=5, close_at=STAMP + timedelta(hours=3))
        closed = await add_item(db, cid, kind="quiz", position=6, close_at=STAMP)
        db.add(Submission(class_id=cid, assignment_id=edge.id, student_id=other.user["id"]))
        db.add(
            QuizAttempt(
                class_id=cid, quiz_id=active.id, student_id=sid, attempt_no=1, started_at=STAMP, status="in_progress"
            )
        )
        await db.commit()
    todo = (await student.get("/api/todo")).json()
    assert future.id not in {r["item_id"] for r in todo}
    assert closed.id not in {r["item_id"] for r in todo}
    assert hidden.id not in {r["item_id"] for r in todo}
    assert next(r["state"] for r in todo if r["item_id"] == active.id) == "in_progress"
    async with sessionmaker() as db:
        await jobs.run_due(db)
        notices = list(await db.scalars(select(Notification).where(Notification.kind == "due_soon")))
        edge_notices = [n for n in notices if n.dedupe_key.startswith(f"due_soon:{edge.id}:")]
        assert [n.user_id for n in edge_notices] == [sid]
        assert {n.user_id for n in notices if n.dedupe_key.startswith(f"due_soon:{future.id}:")} == {
            sid,
            other.user["id"],
        }
        assert all(n.dedupe_key.split(":")[1] in {edge.id, future.id, active.id, closed.id} for n in notices)


async def test_grade_audit_lists_changes_for_teachers_only(as_user, sessionmaker) -> None:
    from app.lms.models import GradeAudit
    from tests.helpers import class_with_student

    teacher, student, _, room = await class_with_student(as_user)
    async with sessionmaker() as db:
        db.add(
            GradeAudit(
                class_id=room["id"],
                actor_id=teacher.user["id"],
                action="grade",
                target_type="submission",
                target_id="sub-1",
                student_id=student.user["id"],
                after={"raw_score": 8},
            )
        )
        await db.commit()
    rows = (await teacher.get(f"/api/classes/{room['id']}/grade-audit", params={"target_id": "sub-1"})).json()
    assert [(r["action"], r["student_name"] is not None) for r in rows] == [("grade", True)]
    assert (await teacher.get(f"/api/classes/{room['id']}/grade-audit", params={"target_id": "x"})).json() == []
    assert (await student.get(f"/api/classes/{room['id']}/grade-audit")).status_code == 403


async def test_csv_uses_vietnamese_state_labels() -> None:
    from app.lms.gradebook import STATE_LABELS

    assert STATE_LABELS["pending"] == "Chờ chấm" and STATE_LABELS["missing"] == "Chưa nộp"
