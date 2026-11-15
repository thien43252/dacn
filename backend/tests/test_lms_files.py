import pytest
from sqlalchemy import func, select

from app.config import get_settings
from app.lms.models import Lesson, LessonItem, LmsFile
from tests.helpers import class_with_student

PDF = b"%PDF-1.4\nSmall lesson document for download tests.\n%%EOF"


@pytest.fixture(autouse=True)
def upload_dir(monkeypatch, tmp_path):
    monkeypatch.setattr(get_settings(), "upload_dir", str(tmp_path))
    return tmp_path


async def test_teacher_uploads_pdf_and_downloads_range(as_user) -> None:
    teacher, _, _, room = await class_with_student(as_user, consent=False)
    response = await teacher.post(
        f"/api/classes/{room['id']}/files",
        data={"purpose": "content"},
        files={"file": ("lesson.pdf", PDF, "application/pdf")},
    )
    assert response.status_code == 201, response.text
    uploaded = response.json()
    assert uploaded["purpose"] == "content"
    assert uploaded["filename"] == "lesson.pdf"
    assert uploaded["content_type"] == "application/pdf"
    assert uploaded["size_bytes"] == len(PDF)
    url = f"/api/classes/{room['id']}/files/{uploaded['id']}"
    response = await teacher.get(url, headers={"Range": "bytes=0-9"})
    assert response.status_code == 206, response.text
    assert response.content == PDF[:10]
    assert response.headers["content-range"] == f"bytes 0-9/{len(PDF)}"


async def test_unsupported_extension_is_rejected(as_user, upload_dir, sessionmaker) -> None:
    teacher, _, _, room = await class_with_student(as_user, consent=False)
    response = await teacher.post(
        f"/api/classes/{room['id']}/files",
        data={"purpose": "content"},
        files={"file": ("program.exe", b"MZ executable", "application/octet-stream")},
    )
    assert response.status_code == 415, response.text
    assert not any(path.is_file() for path in upload_dir.rglob("*"))
    async with sessionmaker() as db:
        assert await db.scalar(select(func.count()).select_from(LmsFile)) == 0


async def test_oversized_upload_leaves_no_file(as_user, monkeypatch, upload_dir, sessionmaker) -> None:
    teacher, _, _, room = await class_with_student(as_user, consent=False)
    monkeypatch.setattr("app.lms.files.limit_bytes", lambda content_type: 1024 * 1024)
    response = await teacher.post(
        f"/api/classes/{room['id']}/files",
        data={"purpose": "content"},
        files={"file": ("large.pdf", b"x" * (1024 * 1024 + 1), "application/pdf")},
    )
    assert response.status_code == 413, response.text
    assert not any(path.is_file() for path in upload_dir.rglob("*"))
    async with sessionmaker() as db:
        assert await db.scalar(select(func.count()).select_from(LmsFile)) == 0


async def test_content_requires_visible_item_and_class_membership(as_user, sessionmaker) -> None:
    teacher, student, _, room = await class_with_student(as_user, consent=False)
    _, outsider, _, _ = await class_with_student(as_user, consent=False)
    response = await teacher.post(
        f"/api/classes/{room['id']}/files",
        data={"purpose": "content"},
        files={"file": ("lesson.pdf", PDF, "application/pdf")},
    )
    assert response.status_code == 201, response.text
    file_id = response.json()["id"]
    url = f"/api/classes/{room['id']}/files/{file_id}"
    assert (await student.get(url)).status_code == 404
    assert (await outsider.get(url)).status_code == 404
    async with sessionmaker() as db:
        lesson = Lesson(class_id=room["id"], title="Buổi học", status="published", created_by=teacher.user["id"])
        db.add(lesson)
        await db.flush()
        db.add(LessonItem(lesson_id=lesson.id, class_id=room["id"], kind="file", title="Tài liệu", file_id=file_id))
        await db.commit()
    response = await student.get(url)
    assert response.status_code == 200, response.text
    assert response.content == PDF
    assert (await outsider.get(url)).status_code == 404


async def test_student_submission_is_private_and_teacher_can_download(as_user) -> None:
    teacher, student, _, room = await class_with_student(as_user, consent=False)
    peer = await as_user("student")
    joined = await peer.post("/api/classes/join", json={"code": room["join_code"]})
    assert joined.status_code == 200, joined.text
    upload_url = f"/api/classes/{room['id']}/files"
    response = await student.post(
        upload_url, data={"purpose": "content"}, files={"file": ("lesson.pdf", PDF, "application/pdf")}
    )
    assert response.status_code == 403, response.text
    response = await student.post(
        upload_url, data={"purpose": "submission"}, files={"file": ("answer.pdf", PDF, "application/pdf")}
    )
    assert response.status_code == 201, response.text
    assert response.json()["purpose"] == "submission"
    url = f"{upload_url}/{response.json()['id']}"
    response = await student.get(url)
    assert response.status_code == 200, response.text
    assert response.content == PDF
    assert (await peer.get(url)).status_code == 404
    response = await teacher.get(url)
    assert response.status_code == 200, response.text
    assert response.content == PDF
