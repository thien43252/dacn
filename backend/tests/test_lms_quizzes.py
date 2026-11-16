from datetime import UTC, datetime, timedelta
from itertools import product

import pytest
from sqlalchemy import select

from app.classes.models import ClassRoom
from app.lms import jobs
from app.lms.models import GradeAudit, Lesson, LessonItem, Quiz, QuizAttempt, QuizQuestion
from tests.helpers import CLASS, class_with_student

TIME = datetime(2026, 11, 16, 8, tzinfo=UTC)
BASE = "/api/classes"
SECRET_KEYS = {"answer_key", "explanation", "rubric", "correct"}


async def make_quiz(sessionmaker, room, teacher, **config):
    """Avoid the lessons API, which is implemented in parallel."""
    async with sessionmaker() as db:
        lesson = Lesson(class_id=room["id"], title="Buổi học", status="published", created_by=teacher.user["id"])
        db.add(lesson)
        await db.flush()
        item = LessonItem(lesson_id=lesson.id, class_id=room["id"], kind="quiz", title="Kiểm tra")
        db.add(item)
        await db.flush()
        db.add(Quiz(item_id=item.id, class_id=room["id"], **config))
        await db.commit()
        return item.id, lesson.id


async def add_question(teacher, root, qid, kind="single", **changes):
    body = {
        "kind": kind,
        "prompt": "Chọn kết quả phù hợp",
        "points": 2,
        "options": [{"id": "a", "text": "Một"}, {"id": "b", "text": "Hai"}],
        "answer_key": "a",
        "explanation": "Lời giải mẫu",
    }
    if kind not in {"single", "multi"}:
        body["options"] = []
    body["answer_key"] = {"single": "a", "multi": ["a"], "true_false": True, "short": ["Hà Nội"], "essay": None}[kind]
    if kind == "essay":
        body["rubric"] = {
            "criteria": [{"name": "Ý chính", "max_points": 2, "description": "Đủ ý"}],
            "model_answer": "Mẫu",
        }
    response = await teacher.post(f"{root}/quizzes/{qid}/questions", json={**body, **changes})
    assert response.status_code == 201, response.text
    return response.json()


def keys_in(value):
    if isinstance(value, dict):
        return set(value).union(*(keys_in(v) for v in value.values()))
    if isinstance(value, list):
        return set().union(*(keys_in(v) for v in value))
    return set()


def safe(response, status=200):
    assert response.status_code == status, response.text
    assert not keys_in(response.json()) & SECRET_KEYS, response.text
    return response.json()


async def test_attempt_snapshot_resume_autosave_and_timeout(as_user, sessionmaker, monkeypatch):
    monkeypatch.setattr("app.lms.now", lambda: TIME)
    teacher, student, _, room = await class_with_student(as_user, consent=False)
    root = f"{BASE}/{room['id']}"
    qid, _ = await make_quiz(sessionmaker, room, teacher, duration_minutes=5, close_at=TIME + timedelta(minutes=10))
    question = await add_question(teacher, root, qid)
    attempt = safe(await student.post(f"{root}/quizzes/{qid}/attempts"))
    assert datetime.fromisoformat(attempt["deadline_at"]) == TIME + timedelta(minutes=5)
    assert datetime.fromisoformat(attempt["server_now"]) == TIME
    assert safe(await student.post(f"{root}/quizzes/{qid}/attempts"))["id"] == attempt["id"]
    path = f"{root}/attempts/{attempt['id']}"
    answer = {"question_id": question["id"], "value": question["answer_key"]}
    safe(await student.put(f"{path}/answers", json=answer))
    assert safe(await student.get(path))["answers"][question["id"]] == question["answer_key"]
    await teacher.patch(f"{root}/questions/{question['id']}", json={"prompt": "Đề mới", "points": 4})
    assert safe(await student.get(path))["questions"] == attempt["questions"]
    monkeypatch.setattr("app.lms.now", lambda: TIME + timedelta(minutes=5))
    safe(await student.put(f"{path}/answers", json=answer))  # The exact deadline is still accepted.
    monkeypatch.setattr("app.lms.now", lambda: TIME + timedelta(minutes=5, seconds=1))
    response = await student.put(f"{path}/answers", json=answer)
    assert response.status_code == 409 and response.json()["detail"] == "attempt_closed"
    result = (await student.get(path)).json()
    assert (result["status"], result["submit_reason"], result["score"]) == ("graded", "timeout", 2)
    assert (await student.post(f"{root}/quizzes/{qid}/attempts")).status_code == 409


async def test_lazy_read_and_jobs_finalize_with_binding_deadline(as_user, sessionmaker, monkeypatch):
    monkeypatch.setattr("app.lms.now", lambda: TIME)
    teacher, student, _, room = await class_with_student(as_user, consent=False)
    root = f"{BASE}/{room['id']}"
    paths = []
    for config in ({"duration_minutes": 1}, {"duration_minutes": 5, "close_at": TIME + timedelta(minutes=1)}):
        qid, _ = await make_quiz(sessionmaker, room, teacher, **config)
        await add_question(teacher, root, qid)
        attempt = safe(await student.post(f"{root}/quizzes/{qid}/attempts"))
        assert datetime.fromisoformat(attempt["deadline_at"]) == TIME + timedelta(minutes=1)
        paths.append(f"{root}/attempts/{attempt['id']}")
    monkeypatch.setattr("app.lms.now", lambda: TIME + timedelta(minutes=2))
    assert (await student.get(paths[0])).json()["submit_reason"] == "timeout"
    async with sessionmaker() as db:
        await jobs.run_due(db)
        await jobs.run_due(db)
    assert (await student.get(paths[1])).json()["submit_reason"] == "closed"


@pytest.mark.parametrize("config", [{"open_at": TIME + timedelta(seconds=1)}, {"close_at": TIME}, {}])
async def test_start_rejects_unavailable_or_empty_quiz(as_user, sessionmaker, monkeypatch, config):
    monkeypatch.setattr("app.lms.now", lambda: TIME)
    teacher, student, _, room = await class_with_student(as_user, consent=False)
    root = f"{BASE}/{room['id']}"
    qid, _ = await make_quiz(sessionmaker, room, teacher, **config)
    from app.lms.quizzes import quiz_ready

    async with sessionmaker() as db:
        assert not await quiz_ready(db, qid)
    if config:
        await add_question(teacher, root, qid)
    assert (await student.post(f"{root}/quizzes/{qid}/attempts")).status_code == 409


@pytest.mark.parametrize("show_score,show_answers", list(product(("on_submit", "after_close", "never"), repeat=2)))
async def test_student_parent_secrecy_all_modes_and_kinds(as_user, sessionmaker, monkeypatch, show_score, show_answers):
    monkeypatch.setattr("app.lms.now", lambda: TIME)
    teacher, student, parent, room = await class_with_student(as_user)
    root = f"{BASE}/{room['id']}"
    qid, _ = await make_quiz(
        sessionmaker,
        room,
        teacher,
        show_score=show_score,
        show_answers=show_answers,
        close_at=TIME + timedelta(hours=1),
    )
    questions = [
        await add_question(teacher, root, qid, kind) for kind in ("single", "multi", "true_false", "short", "essay")
    ]
    for actor in (student, parent):
        safe(await actor.get(f"{root}/quizzes/{qid}"))
    attempt = safe(await student.post(f"{root}/quizzes/{qid}/attempts"))
    path = f"{root}/attempts/{attempt['id']}"
    for question in questions:
        value = question["answer_key"]
        if question["kind"] == "short":
            value = value[0]
        if question["kind"] == "essay":
            value = "Bài làm của em"
        safe(await student.put(f"{path}/answers", json={"question_id": question["id"], "value": value}))
        for actor in (student, parent):
            safe(await actor.get(path))
    assert (await parent.post(f"{root}/quizzes/{qid}/attempts")).status_code == 403
    assert (await teacher.post(f"{root}/quizzes/{qid}/attempts")).status_code == 403
    for actor in (parent, teacher):
        assert (
            await actor.put(f"{path}/answers", json={"question_id": questions[0]["id"], "value": "a"})
        ).status_code == 403
        assert (await actor.post(f"{path}/submit")).status_code == 403
    submitted = await student.post(f"{path}/submit")
    assert submitted.status_code == 200, submitted.text
    assert ("correct" in keys_in(submitted.json())) == (show_answers == "on_submit")
    assert not keys_in(submitted.json()) & {"answer_key", "rubric"}
    if show_score == "on_submit":
        assert {entry["points"] for entry in submitted.json()["item_scores"].values()} == {2}
    for stage in ("before_close", "after_close"):
        if stage == "after_close":
            monkeypatch.setattr("app.lms.now", lambda: TIME + timedelta(hours=1))
        for actor in (student, parent):
            safe(await actor.get(f"{root}/quizzes/{qid}"))
            response = await actor.get(path)
            assert response.status_code == 200, response.text
            result = response.json()
            reveal = show_answers == "on_submit" or (show_answers == "after_close" and stage == "after_close")
            assert ("correct" in keys_in(result)) == reveal
            assert ("explanation" in keys_in(result)) == reveal
            assert not keys_in(result) & {"answer_key", "rubric"}
            visible_score = show_score == "on_submit" or (show_score == "after_close" and stage == "after_close")
            assert ("item_scores" in result) == visible_score


async def test_essay_grading_regrade_results_and_copy(as_user, sessionmaker, monkeypatch):
    monkeypatch.setattr("app.lms.now", lambda: TIME)
    teacher, student, _, room = await class_with_student(as_user, consent=False)
    root = f"{BASE}/{room['id']}"
    qid, _ = await make_quiz(sessionmaker, room, teacher, max_attempts=0)
    single = await add_question(teacher, root, qid)
    essay = await add_question(teacher, root, qid, "essay")
    paths = []
    for _ in range(2):
        attempt = safe(await student.post(f"{root}/quizzes/{qid}/attempts"))
        path = f"{root}/attempts/{attempt['id']}"
        paths.append(path)
        await student.put(f"{path}/answers", json={"question_id": single["id"], "value": single["answer_key"]})
        result = (await student.post(f"{path}/submit")).json()
        assert result["status"] == "submitted" and result["score"] is None
        assert (await teacher.put(f"{path}/scores/{essay['id']}", json={"points": 3})).status_code == 422
        graded = await teacher.put(f"{path}/scores/{essay['id']}", json={"points": 1, "feedback": "Đúng một phần"})
        assert graded.status_code == 200, graded.text
        assert (graded.json()["status"], graded.json()["score"]) == ("graded", 3)
    edit = await teacher.patch(f"{root}/questions/{single['id']}", json={"answer_key": single["options"][1]["id"]})
    assert edit.json()["affects_submitted"] == 2
    assert edit.json()["options"] == single["options"]
    regrade = await teacher.post(f"{root}/questions/{single['id']}/regrade")
    assert regrade.json() == {"updated": 2}
    for path in paths:
        assert (await teacher.get(path)).json()["score"] == 1
    results = (await teacher.get(f"{root}/quizzes/{qid}/results")).json()
    assert results["stats"]["attempted_students"] == 1
    assert results["stats"]["average"] == 2.5
    assert sum(results["stats"]["distribution"].values()) == 1
    assert next(q for q in results["stats"]["per_question"] if q["question_id"] == single["id"])["correct_rate"] == 0
    async with sessionmaker() as db:
        audits = list(await db.scalars(select(GradeAudit)))
        assert [a.action for a in audits].count("grade") == 2
        assert [a.action for a in audits].count("regrade") == 2
        assert all(a.before is not None and a.after is not None for a in audits)
    target_room = (await teacher.post("/api/classes", json=CLASS)).json()
    _, lesson_id = await make_quiz(sessionmaker, target_room, teacher)
    copied = await teacher.post(f"{root}/quizzes/{qid}/copy", json={"target_lesson_id": lesson_id})
    assert copied.status_code == 201, copied.text
    copy_data = copied.json()
    assert copy_data["item_id"] != qid
    assert {q["id"] for q in copy_data["questions"]}.isdisjoint({single["id"], essay["id"]})
    assert (await teacher.get(f"{root}/quizzes/{qid}")).json()["questions"][0]["id"] == single["id"]
    outsider = await as_user("teacher")
    other_room = (await outsider.post("/api/classes", json=CLASS)).json()
    _, other_lesson = await make_quiz(sessionmaker, other_room, outsider)
    assert (
        await teacher.post(f"{root}/quizzes/{qid}/copy", json={"target_lesson_id": other_lesson})
    ).status_code == 404
    deleted = await teacher.delete(f"{root}/questions/{single['id']}")
    assert deleted.json()["affects_submitted"] == 2


async def test_access_validation_visibility_and_question_order(as_user, sessionmaker, monkeypatch):
    monkeypatch.setattr("app.lms.now", lambda: TIME)
    teacher, student, parent, room = await class_with_student(as_user)
    root = f"{BASE}/{room['id']}"
    qid, _ = await make_quiz(sessionmaker, room, teacher)
    first = await add_question(teacher, root, qid)
    second = await add_question(teacher, root, qid, "true_false")
    assert first["options"][0]["id"] != "a"
    for changes in ({"points": 0}, {"answer_key": "unknown"}, {"kind": "true_false", "answer_key": "true"}):
        assert (await teacher.patch(f"{root}/questions/{first['id']}", json=changes)).status_code == 422
    assert (await teacher.patch(f"{root}/quizzes/{qid}", json={"max_attempts": -1})).status_code == 422
    assert (
        await teacher.patch(
            f"{root}/quizzes/{qid}",
            json={"close_at": TIME.isoformat(), "open_at": (TIME + timedelta(hours=1)).isoformat()},
        )
    ).status_code == 422
    order = await teacher.put(f"{root}/quizzes/{qid}/questions/order", json={"ids": [second["id"], first["id"]]})
    assert order.status_code == 200, order.text
    assert [q["id"] for q in (await teacher.get(f"{root}/quizzes/{qid}")).json()["questions"]] == [
        second["id"],
        first["id"],
    ]
    attempt = safe(await student.post(f"{root}/quizzes/{qid}/attempts"))
    other = await as_user("student")
    await other.post("/api/classes/join", json={"code": room["join_code"]})
    other_parent = await as_user("parent")
    code = (await other.get("/api/me/link-code")).json()["code"]
    await other_parent.post("/api/parent/children", json={"code": code})
    for actor in (other, other_parent):
        assert (await actor.get(f"{root}/attempts/{attempt['id']}")).status_code == 404
    for actor in (student, parent):
        assert (await actor.get(f"{root}/quizzes/{qid}/results")).status_code == 403
        assert (await actor.patch(f"{root}/quizzes/{qid}", json={"max_attempts": 0})).status_code == 403
    async with sessionmaker() as db:
        item = await db.get(LessonItem, qid)
        item.visible = False
        await db.commit()
    assert (await student.get(f"{root}/quizzes/{qid}")).status_code == 404
    assert (await student.post(f"{root}/quizzes/{qid}/attempts")).status_code == 409
    async with sessionmaker() as db:
        klass = await db.get(ClassRoom, room["id"])
        klass.archived = True
        await db.commit()
    for actor in (teacher, parent):
        assert (await actor.post(f"{root}/quizzes/{qid}/attempts")).status_code == 403
        assert (
            await actor.put(
                f"{root}/attempts/{attempt['id']}/answers", json={"question_id": first["id"], "value": None}
            )
        ).status_code == 403


async def test_after_close_without_close_and_stable_shuffled_ids(as_user, sessionmaker, monkeypatch):
    monkeypatch.setattr("app.lms.now", lambda: TIME)
    teacher, student, _, room = await class_with_student(as_user, consent=False)
    root = f"{BASE}/{room['id']}"
    qid, _ = await make_quiz(
        sessionmaker, room, teacher, shuffle_questions=True, shuffle_options=True, show_score="after_close"
    )
    questions = [await add_question(teacher, root, qid) for _ in range(3)]
    attempt = safe(await student.post(f"{root}/quizzes/{qid}/attempts"))
    assert attempt["deadline_at"] is None
    assert {q["question_id"] for q in attempt["questions"]} == {q["id"] for q in questions}
    for question in attempt["questions"]:
        original = next(q for q in questions if q["id"] == question["question_id"])
        assert {o["id"] for o in question["options"]} == {o["id"] for o in original["options"]}
    result = (await student.post(f"{root}/attempts/{attempt['id']}/submit")).json()
    assert "correct" in keys_in(result) and "score" in result
    async with sessionmaker() as db:
        row = await db.get(QuizAttempt, attempt["id"])
        assert not keys_in(row.snapshot) & SECRET_KEYS
        assert len(list(await db.scalars(select(QuizQuestion).where(QuizQuestion.quiz_id == qid)))) == 3


async def test_changed_kind_and_deleted_questions_keep_original_paper(as_user, sessionmaker, monkeypatch):
    monkeypatch.setattr("app.lms.now", lambda: TIME)
    teacher, student, _, room = await class_with_student(as_user, consent=False)
    root = f"{BASE}/{room['id']}"
    qid, _ = await make_quiz(sessionmaker, room, teacher)
    multi = await add_question(teacher, root, qid, "multi")
    single = await add_question(teacher, root, qid)
    attempt = safe(await student.post(f"{root}/quizzes/{qid}/attempts"))
    path = f"{root}/attempts/{attempt['id']}"
    for question in (multi, single):
        safe(
            await student.put(f"{path}/answers", json={"question_id": question["id"], "value": question["answer_key"]})
        )
    changed = await teacher.patch(
        f"{root}/questions/{multi['id']}", json={"kind": "true_false", "options": [], "answer_key": True}
    )
    assert changed.status_code == 200, changed.text
    assert (await teacher.delete(f"{root}/questions/{single['id']}")).status_code == 200
    assert safe(await student.get(path))["questions"] == attempt["questions"]
    submitted = await student.post(f"{path}/submit")
    assert submitted.status_code == 200, submitted.text
    assert submitted.json()["score"] == 0
    assert (await teacher.post(f"{root}/questions/{multi['id']}/regrade")).json() == {"updated": 1}


async def test_essay_attempt_notifies_teacher_then_student(as_user, sessionmaker, monkeypatch):
    """FR-025 for quizzes: an attempt waiting for essay grading tells the teachers (once per quiz and day), and the
    student hears once every essay is graded, unless the quiz never shows scores."""
    monkeypatch.setattr("app.lms.now", lambda: TIME)
    teacher, student, _, room = await class_with_student(as_user, consent=False)
    root = f"{BASE}/{room['id']}"
    qid, _ = await make_quiz(sessionmaker, room, teacher, max_attempts=0)
    essay = await add_question(teacher, root, qid, "essay")
    paths = []
    for _ in range(2):
        attempt = safe(await student.post(f"{root}/quizzes/{qid}/attempts"))
        paths.append(f"{root}/attempts/{attempt['id']}")
        assert (await student.post(f"{paths[-1]}/submit")).json()["status"] == "submitted"
    inbox = (await teacher.get("/api/notifications")).json()
    to_grade = [n for n in inbox["items"] if n["kind"] == "to_grade"]
    assert len(to_grade) == 1 and to_grade[0]["link"].endswith(f"/quizzes/{qid}")
    assert not [n for n in (await student.get("/api/notifications")).json()["items"] if n["kind"] == "returned"]

    await teacher.put(f"{paths[0]}/scores/{essay['id']}", json={"points": 1})
    await teacher.put(f"{paths[0]}/scores/{essay['id']}", json={"points": 2})
    returned = [n for n in (await student.get("/api/notifications")).json()["items"] if n["kind"] == "returned"]
    assert len(returned) == 1 and returned[0]["link"] == f"/student/classes/{room['id']}/quizzes/{qid}"

    async with sessionmaker() as db:
        (await db.get(Quiz, qid)).show_score = "never"
        await db.commit()
    await teacher.put(f"{paths[1]}/scores/{essay['id']}", json={"points": 1})
    returned = [n for n in (await student.get("/api/notifications")).json()["items"] if n["kind"] == "returned"]
    assert len(returned) == 1
