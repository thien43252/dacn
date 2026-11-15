"""SC-008: personal data is scoped to students and their linked guardians."""

import pytest

from app.classes.models import ParentLink
from app.lms.models import LmsFile, QuizAttempt, Submission, SubmissionVersion
from tests.helpers import class_with_student
from tests.test_lms_gradebook import STAMP, add_item


@pytest.fixture
async def access_case(as_user, sessionmaker, monkeypatch, tmp_path):
    teacher, a, pa, room = await class_with_student(as_user)
    b = await as_user("student", "Học sinh B")
    pb = await as_user("parent")
    await b.post("/api/classes/join", json={"code": room["join_code"]})
    async with sessionmaker() as db:
        db.add(ParentLink(parent_id=pb.user["id"], student_id=b.user["id"]))
        assignment = await add_item(db, room["id"])
        quiz = await add_item(db, room["id"], kind="quiz", position=1)
        submission = Submission(
            class_id=room["id"], assignment_id=assignment.id, student_id=b.user["id"], latest_version=1
        )
        attempt = QuizAttempt(
            class_id=room["id"], quiz_id=quiz.id, student_id=b.user["id"], attempt_no=1, started_at=STAMP
        )
        db.add_all([submission, attempt])
        await db.flush()
        path = tmp_path / "private.txt"
        path.write_text("B's private work", encoding="utf-8")
        file = LmsFile(
            class_id=room["id"],
            owner_id=b.user["id"],
            purpose="submission",
            filename="private.txt",
            content_type="text/plain",
            size_bytes=16,
            storage_path=str(path),
        )
        db.add(file)
        await db.flush()
        db.add(
            SubmissionVersion(
                submission_id=submission.id, version_no=1, text="B's answer", file_ids=[file.id], submitted_at=STAMP
            )
        )
        await db.commit()
    monkeypatch.setattr("app.lms.now", lambda: STAMP)
    return dict(
        teacher=teacher,
        a=a,
        pa=pa,
        b=b,
        pb=pb,
        room=room,
        assignment=assignment.id,
        quiz=quiz.id,
        submission=submission.id,
        attempt=attempt.id,
        file=file.id,
    )


@pytest.mark.parametrize(
    "endpoint",
    [
        "attempts/{attempt}",
        "submissions/{submission}",
        "assignments/{assignment}?student_id={bid}",
        "quizzes/{quiz}?student_id={bid}",
        "my-grades?student_id={bid}",
        "files/{file}",
        "assignments/{assignment}/submissions",
        "quizzes/{quiz}/results",
        "gradebook",
        "gradebook.csv",
        "todo",
    ],
)
async def test_cross_student_reads_denied(access_case, endpoint):
    c = access_case
    suffix = endpoint.format(**c, bid=c["b"].user["id"])
    path = f"/api/classes/{c['room']['id']}/{suffix}"
    if endpoint == "todo":
        path = f"/api/todo?student_id={c['b'].user['id']}"
    for reader in (c["a"], c["pa"]):
        response = await reader.get(path)
        assert response.status_code in {403, 404}, (endpoint, reader.user["role"], response.text)


@pytest.mark.parametrize(
    "method,endpoint,body",
    [
        ("post", "assignments/{assignment}/submissions", {"text": "Bài làm"}),
        ("patch", "assignments/{assignment}", {"prompt": "Đề bài"}),
        ("put", "assignments/{assignment}/extensions/{bid}", {"due_at": STAMP.isoformat()}),
        ("delete", "assignments/{assignment}/extensions/{bid}", None),
        ("put", "submissions/{submission}/grade", {"raw_score": 8}),
        ("post", "assignments/{assignment}/return", {}),
        ("patch", "quizzes/{quiz}", {"weight": 2}),
        ("post", "quizzes/{quiz}/attempts", None),
        ("put", "attempts/{attempt}/answers", {"question_id": "question", "value": "2"}),
        ("post", "attempts/{attempt}/submit", None),
        ("put", "attempts/{attempt}/scores/question", {"points": 1}),
        ("post", "quizzes/{quiz}/questions", {"kind": "short", "prompt": "Câu hỏi", "answer_key": ["2"]}),
        ("patch", "questions/question", {"points": 1}),
        ("delete", "questions/question", None),
        ("put", "quizzes/{quiz}/questions/order", {"ids": []}),
        ("post", "questions/question/regrade", None),
        ("post", "quizzes/{quiz}/copy", {"target_lesson_id": "lesson"}),
        ("patch", "gradebook/columns/{assignment}", {"weight": 2}),
    ],
)
async def test_parent_writes_denied(access_case, method, endpoint, body):
    c = access_case
    path = f"/api/classes/{c['room']['id']}/" + endpoint.format(**c, bid=c["b"].user["id"])
    response = await c["pa"].request(method, path, **({"json": body} if body is not None else {}))
    assert response.status_code == 403, response.text


async def test_parent_upload_denied(access_case):
    c = access_case
    response = await c["pa"].post(
        f"/api/classes/{c['room']['id']}/files",
        data={"purpose": "submission"},
        files={"file": ("answer.txt", b"answer", "text/plain")},
    )
    assert response.status_code == 403


async def test_own_child_read_and_nonmember_parent(access_case, as_user):
    c = access_case
    base = f"/api/classes/{c['room']['id']}"
    for suffix in [
        f"submissions/{c['submission']}",
        f"attempts/{c['attempt']}",
        f"files/{c['file']}",
        f"assignments/{c['assignment']}?student_id={c['b'].user['id']}",
        f"quizzes/{c['quiz']}?student_id={c['b'].user['id']}",
        f"my-grades?student_id={c['b'].user['id']}",
    ]:
        response = await c["pb"].get(f"{base}/{suffix}")
        assert response.status_code == 200, response.text
    _, outside, guardian, _ = await class_with_student(as_user)
    for suffix in [
        "lessons",
        f"assignments/{c['assignment']}",
        f"quizzes/{c['quiz']}",
        "my-grades",
        f"submissions/{c['submission']}",
        f"attempts/{c['attempt']}",
        f"files/{c['file']}",
    ]:
        response = await guardian.get(f"{base}/{suffix}?student_id={outside.user['id']}")
        assert response.status_code == 404, response.text
