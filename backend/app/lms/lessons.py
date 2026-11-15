"""Lessons, content items and scheduled publication (feature 004, user story 1)."""

import asyncio
import re
import shutil
from datetime import date, datetime
from pathlib import Path
from typing import Literal
from urllib.parse import parse_qs, urlsplit

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app import lms
from app.auth.deps import CurrentUser, DbSession
from app.auth.models import User
from app.classes import service as classes
from app.classes.models import ClassMember
from app.knowledge import service as knowledge
from app.knowledge.models import Document, DocumentChunk
from app.lms import access, aware, files, jobs, schemas
from app.lms.models import (
    Assignment,
    AssignmentExtension,
    ContentView,
    Lesson,
    LessonItem,
    LmsFile,
    Quiz,
    QuizAttempt,
    QuizQuestion,
    Submission,
)
from app.lms.notify import notify
from app.lms.schemas import FileOut

router = APIRouter(tags=["lms"])


class LessonCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str = ""
    lesson_date: date | None = None
    publish_at: datetime | None = None


class LessonPatch(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    lesson_date: date | None = None
    publish_at: datetime | None = None
    status: Literal["draft", "published", "archived"] | None = None

    @field_validator("title", "description", "status")
    @classmethod
    def not_null(cls, value):
        if value is None:
            raise ValueError("Trường này không được để trống.")
        return value


class ItemCreate(BaseModel):
    kind: Literal["file", "video", "link", "text", "assignment", "quiz"]
    title: str = Field(min_length=1, max_length=200)
    body: str = ""
    url: str | None = Field(default=None, max_length=1000)
    file_id: str | None = None


class ItemPatch(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    body: str | None = None
    url: str | None = Field(default=None, max_length=1000)
    file_id: str | None = None
    visible: bool | None = None
    agent_readable: bool | None = None

    @field_validator("title", "body", "visible", "agent_readable")
    @classmethod
    def not_null(cls, value):
        if value is None:
            raise ValueError("Trường này không được để trống.")
        return value


class ItemOut(BaseModel):
    id: str
    lesson_id: str
    class_id: str
    kind: str
    title: str
    position: int
    body: str
    url: str | None
    embed_url: str | None
    file_id: str | None
    file: FileOut | None
    document_id: str | None
    agent_readable: bool
    visible: bool
    viewed: bool = False
    quiz_id: str | None = None
    assignment_id: str | None = None


class LessonOut(BaseModel):
    id: str
    class_id: str
    title: str
    description: str
    lesson_date: date | None
    position: int
    status: str
    publish_at: datetime | None
    locked: bool
    items: list[ItemOut]


class OrderIn(BaseModel):
    ids: list[str]


class ViewOut(BaseModel):
    student_id: str
    name: str
    viewed: bool
    first_viewed_at: datetime | None


def lesson_open(lesson: Lesson) -> bool:
    """Students and parents see the lesson's content: published and its publish time reached (research R15)."""
    if lesson.status != "published":
        return False
    publish_at = aware(lesson.publish_at)
    return publish_at is None or publish_at <= lms.now()


async def item_visible(db: AsyncSession, item: LessonItem) -> bool:
    """Whether students and parents of the class may see this item."""
    if not item.visible:
        return False
    lesson = await db.get(Lesson, item.lesson_id)
    return lesson is not None and lesson_open(lesson)


def embed_for(url: str) -> tuple[str, str | None]:
    """Return a supported video embed, direct video, or ordinary link (research R4)."""
    try:
        parts = urlsplit(url)
    except ValueError:
        return "link", None
    if parts.scheme not in {"http", "https"}:
        return "link", None
    host = (parts.hostname or "").lower().removeprefix("www.")
    video_id = None
    if host == "youtu.be":
        video_id = parts.path.strip("/")
    elif host in {"youtube.com", "m.youtube.com", "youtube-nocookie.com"}:
        if parts.path == "/watch":
            video_id = parse_qs(parts.query).get("v", [None])[0]
        elif parts.path.startswith("/embed/"):
            video_id = parts.path.removeprefix("/embed/").rstrip("/")
    if video_id and re.fullmatch(r"[A-Za-z0-9_-]+", video_id):
        return "youtube", f"https://www.youtube-nocookie.com/embed/{video_id}"
    if host == "vimeo.com" and re.fullmatch(r"/[0-9]+/?", parts.path):
        return "vimeo", f"https://player.vimeo.com/video/{parts.path.strip('/')}"
    if parts.path.lower().endswith((".mp4", ".webm")):
        return "video", None
    return "link", None


async def _lesson(db: AsyncSession, cid: str, lid: str, role: str = "teacher") -> Lesson:
    row = await db.get(Lesson, lid)
    if row is None or row.class_id != cid or (role != "teacher" and row.status != "published"):
        raise classes.not_found()
    return row


async def _item(db: AsyncSession, cid: str, iid: str) -> LessonItem:
    row = await db.get(LessonItem, iid)
    if row is None or row.class_id != cid:
        raise classes.not_found()
    return row


async def _item_out(db: AsyncSession, row: LessonItem, student_id: str | None = None) -> ItemOut:
    file = await db.get(LmsFile, row.file_id) if row.file_id else None
    viewed = False
    if student_id:
        viewed = bool(
            await db.scalar(
                select(ContentView.id).where(ContentView.item_id == row.id, ContentView.student_id == student_id)
            )
        )
    return ItemOut(
        **{
            key: getattr(row, key)
            for key in (
                "id",
                "lesson_id",
                "class_id",
                "kind",
                "title",
                "position",
                "body",
                "url",
                "embed_url",
                "file_id",
                "document_id",
                "visible",
            )
        },
        file=files._out(file) if file else None,
        agent_readable=row.document_id is not None,
        viewed=viewed,
        quiz_id=row.id if row.kind == "quiz" else None,
        assignment_id=row.id if row.kind == "assignment" else None,
    )


async def _lesson_out(db: AsyncSession, row: Lesson, role: str, student_id: str | None = None) -> LessonOut:
    locked = role != "teacher" and not lesson_open(row)
    items = []
    if not locked:
        rows = await db.scalars(select(LessonItem).where(LessonItem.lesson_id == row.id).order_by(LessonItem.position))
        for item in rows:
            if role == "teacher" or await item_visible(db, item):
                items.append(await _item_out(db, item, student_id))
    return LessonOut(
        **{
            key: getattr(row, key)
            for key in ("id", "class_id", "title", "description", "lesson_date", "position", "status", "publish_at")
        },
        locked=locked,
        items=items,
    )


async def _validate_item(db: AsyncSession, row: LessonItem) -> None:
    if row.kind == "video" and bool(row.url) == bool(row.file_id):
        raise HTTPException(422, "Video cần đúng một đường dẫn hoặc tệp.")
    if row.kind == "file" and not row.file_id:
        raise HTTPException(422, "Tài liệu cần có tệp.")
    if row.kind == "link" and not row.url:
        raise HTTPException(422, "Liên kết cần có đường dẫn.")
    if row.file_id:
        file = await db.get(LmsFile, row.file_id)
        if file is None or file.class_id != row.class_id or file.purpose != "content":
            raise HTTPException(422, "Tệp nội dung không hợp lệ trong lớp này.")
    row.embed_url = None
    if row.kind == "video" and row.url:
        kind, row.embed_url = embed_for(row.url)
        if kind == "link":
            raise HTTPException(422, "Link video không được hỗ trợ, hãy dùng YouTube, Vimeo hoặc tệp .mp4/.webm.")


async def _agent_file(db: AsyncSession, item: LessonItem) -> LmsFile:
    file = await db.get(LmsFile, item.file_id) if item.file_id else None
    if file is None or files.extension_of(file.filename) not in files.AGENT_READABLE:
        raise HTTPException(422, "Chỉ tài liệu PDF, DOCX, TXT hoặc MD mới cho agent đọc được.")
    return file


async def set_agent_readable(db: AsyncSession, item: LessonItem, on: bool, user: User) -> str | None:
    """Maintain the independently deletable knowledge copy; caller commits and queues processing."""
    if not on:
        if item.document_id:
            document = await db.get(Document, item.document_id)
            item.document_id = None
            if document:
                await db.execute(delete(DocumentChunk).where(DocumentChunk.document_id == document.id))
                await db.delete(document)
                await asyncio.to_thread(Path(document.storage_path).unlink, missing_ok=True)
        return None
    file = await _agent_file(db, item)
    if item.document_id:
        return None
    document = Document(
        class_id=item.class_id,
        uploaded_by=user.id,
        title=item.title,
        filename=file.filename,
        content_type=knowledge.detect_type(file.filename, file.content_type),
        size_bytes=file.size_bytes,
        storage_path="",
        meta={"lesson_item_id": item.id},
    )
    db.add(document)
    await db.flush()
    root = await asyncio.to_thread(knowledge.storage_root)
    target = root / item.class_id / f"{document.id}{files.extension_of(file.filename)}"
    await asyncio.to_thread(target.parent.mkdir, parents=True, exist_ok=True)
    await asyncio.to_thread(shutil.copyfile, file.storage_path, target)
    document.storage_path = str(target)
    item.document_id = document.id
    return document.id


async def _notify_published(db: AsyncSession, row: Lesson) -> None:
    students = await access.student_ids(db, row.class_id)
    await notify(
        db,
        students,
        "lesson_published",
        f"Buổi học mới: {row.title}",
        link=f"/student/classes/{row.class_id}/lessons/{row.id}",
        class_id=row.class_id,
        dedupe_key=f"lesson_published:{row.id}",
    )
    # FR-025: each assignment or quiz of the lesson is "given" when students can first see it.
    work = await db.scalars(
        select(LessonItem).where(
            LessonItem.lesson_id == row.id, LessonItem.kind.in_(("assignment", "quiz")), LessonItem.visible.is_(True)
        )
    )
    for item in work:
        page = "assignments" if item.kind == "assignment" else "quizzes"
        await notify(
            db,
            students,
            "assigned",
            f"Bài mới: {item.title}",
            link=f"/student/classes/{row.class_id}/{page}/{item.id}",
            class_id=row.class_id,
            dedupe_key=f"assigned:{item.id}",
        )


async def _require_quizzes_ready(db: AsyncSession, row: Lesson) -> None:
    """A lesson cannot be published with an empty quiz in it (spec edge case "Quiz không có câu hỏi nào")."""
    from app.lms.quizzes import quiz_ready

    quizzes = await db.scalars(
        select(LessonItem.id).where(
            LessonItem.lesson_id == row.id, LessonItem.kind == "quiz", LessonItem.visible.is_(True)
        )
    )
    for quiz_id in quizzes:
        if not await quiz_ready(db, quiz_id):
            raise HTTPException(422, "Không thể công bố: có quiz chưa có câu hỏi nào.")


@jobs.step
async def publish_due_lessons(db: AsyncSession) -> None:
    rows = await db.scalars(select(Lesson).where(Lesson.status == "published", Lesson.publish_at <= lms.now()))
    for row in rows:
        await _notify_published(db, row)
    await db.commit()


async def _order(db: AsyncSession, rows: list, body: OrderIn) -> None:
    by_id = {row.id: row for row in rows}
    if len(body.ids) != len(by_id) or set(body.ids) != set(by_id):
        raise HTTPException(422, "Danh sách phải chứa đầy đủ mỗi mục đúng một lần.")
    for position, row_id in enumerate(body.ids):
        by_id[row_id].position = position
    await db.commit()


@router.put("/classes/{cid}/lessons/order", status_code=204)
async def order_lessons(cid: str, body: OrderIn, user: CurrentUser, db: DbSession) -> None:
    await access.load_lms_class(db, cid, user, {"teacher"}, write=True)
    rows = list(await db.scalars(select(Lesson).where(Lesson.class_id == cid)))
    await _order(db, rows, body)


@router.get("/classes/{cid}/lessons", response_model=list[LessonOut])
async def list_lessons(cid: str, user: CurrentUser, db: DbSession, student_id: str | None = None):
    room, role = await access.load_lms_class(db, cid, user)
    sid = await access.resolve_student(db, room, user, role, student_id) if role != "teacher" else None
    query = select(Lesson).where(Lesson.class_id == cid).order_by(Lesson.position)
    if role != "teacher":
        query = query.where(Lesson.status == "published")
    return [await _lesson_out(db, row, role, sid) for row in await db.scalars(query)]


@router.post("/classes/{cid}/lessons", response_model=LessonOut, status_code=201)
async def create_lesson(cid: str, body: LessonCreate, user: CurrentUser, db: DbSession):
    await access.load_lms_class(db, cid, user, {"teacher"}, write=True)
    position = await db.scalar(select(func.max(Lesson.position)).where(Lesson.class_id == cid))
    row = Lesson(
        **body.model_dump(), class_id=cid, created_by=user.id, position=(position + 1 if position is not None else 0)
    )
    row.title = schemas.clean("Tiêu đề", row.title)
    row.description = schemas.clean("Mô tả", row.description)
    db.add(row)
    await db.commit()
    return await _lesson_out(db, row, "teacher")


@router.get("/classes/{cid}/lessons/{lid}", response_model=LessonOut)
async def get_lesson(cid: str, lid: str, user: CurrentUser, db: DbSession, student_id: str | None = None):
    room, role = await access.load_lms_class(db, cid, user)
    row = await _lesson(db, cid, lid, role)
    sid = await access.resolve_student(db, room, user, role, student_id) if role != "teacher" else None
    return await _lesson_out(db, row, role, sid)


@router.patch("/classes/{cid}/lessons/{lid}", response_model=LessonOut)
async def patch_lesson(cid: str, lid: str, body: LessonPatch, user: CurrentUser, db: DbSession):
    await access.load_lms_class(db, cid, user, {"teacher"}, write=True)
    row = await _lesson(db, cid, lid)
    for key, value in body.model_dump(exclude_unset=True).items():
        setattr(row, key, schemas.clean(key, value) if key in {"title", "description"} else value)
    if body.model_dump(exclude_unset=True).get("status") == "published":
        await _require_quizzes_ready(db, row)
    if lesson_open(row):
        await _notify_published(db, row)
    await db.commit()
    return await _lesson_out(db, row, "teacher")


async def _check_deletable(db: AsyncSession, ids: list[str]) -> None:
    attempt = await db.scalar(select(QuizAttempt.id).where(QuizAttempt.quiz_id.in_(ids)).limit(1))
    submission = await db.scalar(select(Submission.id).where(Submission.assignment_id.in_(ids)).limit(1))
    if attempt or submission:
        raise HTTPException(409, "Buổi học đã có bài nộp, hãy lưu trữ thay vì xóa.")


async def _delete_item(db: AsyncSession, row: LessonItem, user: User) -> None:
    await set_agent_readable(db, row, False, user)
    # Explicit deletes also support SQLite test sessions without foreign-key cascades enabled.
    for model, column in (
        (ContentView, ContentView.item_id),
        (QuizQuestion, QuizQuestion.quiz_id),
        (Quiz, Quiz.item_id),
        (AssignmentExtension, AssignmentExtension.assignment_id),
        (Assignment, Assignment.item_id),
    ):
        await db.execute(delete(model).where(column == row.id))
    await db.delete(row)


@router.delete("/classes/{cid}/lessons/{lid}", status_code=204)
async def delete_lesson(cid: str, lid: str, user: CurrentUser, db: DbSession) -> None:
    await access.load_lms_class(db, cid, user, {"teacher"}, write=True)
    row = await _lesson(db, cid, lid)
    items = list(await db.scalars(select(LessonItem).where(LessonItem.lesson_id == lid)))
    await _check_deletable(db, [item.id for item in items])
    for item in items:
        await _delete_item(db, item, user)
    # Flush the items first: deleting the lesson in the same flush lets Postgres cascade them away before the ORM's
    # own DELETE, which then matches no row.
    await db.flush()
    await db.delete(row)
    await db.commit()


@router.post("/classes/{cid}/lessons/{lid}/items", response_model=ItemOut, status_code=201)
async def create_item(cid: str, lid: str, body: ItemCreate, user: CurrentUser, db: DbSession):
    await access.load_lms_class(db, cid, user, {"teacher"}, write=True)
    await _lesson(db, cid, lid)
    position = await db.scalar(select(func.max(LessonItem.position)).where(LessonItem.lesson_id == lid))
    row = LessonItem(
        **body.model_dump(), class_id=cid, lesson_id=lid, position=(position + 1 if position is not None else 0)
    )
    row.title = schemas.clean("Tiêu đề", row.title)
    row.body = schemas.clean("Nội dung", row.body)
    await _validate_item(db, row)
    db.add(row)
    await db.flush()
    if row.kind in {"quiz", "assignment"}:
        model = Quiz if row.kind == "quiz" else Assignment
        db.add(model(item_id=row.id, class_id=cid))
    await db.commit()
    return await _item_out(db, row)


@router.patch("/classes/{cid}/items/{iid}", response_model=ItemOut)
async def patch_item(
    cid: str, iid: str, body: ItemPatch, user: CurrentUser, db: DbSession, background: BackgroundTasks
):
    await access.load_lms_class(db, cid, user, {"teacher"}, write=True)
    row = await _item(db, cid, iid)
    values = body.model_dump(exclude_unset=True)
    readable = values.pop("agent_readable", row.document_id is not None)
    replacing_file = "file_id" in values and values["file_id"] != row.file_id and row.document_id is not None
    # Validate the merged state before an autoflush can write an invalid foreign key.
    with db.no_autoflush:
        for key, value in values.items():
            setattr(row, key, schemas.clean(key, value) if key in {"title", "body"} else value)
        await _validate_item(db, row)
        if readable:
            await _agent_file(db, row)
    if replacing_file:
        await set_agent_readable(db, row, False, user)
    document_id = await set_agent_readable(db, row, readable, user)
    await db.commit()
    if document_id:
        background.add_task(knowledge.process_document, document_id)
    return await _item_out(db, row)


@router.delete("/classes/{cid}/items/{iid}", status_code=204)
async def delete_item(cid: str, iid: str, user: CurrentUser, db: DbSession) -> None:
    await access.load_lms_class(db, cid, user, {"teacher"}, write=True)
    row = await _item(db, cid, iid)
    await _check_deletable(db, [row.id])
    await _delete_item(db, row, user)
    await db.commit()


@router.put("/classes/{cid}/lessons/{lid}/items/order", status_code=204)
async def order_items(cid: str, lid: str, body: OrderIn, user: CurrentUser, db: DbSession) -> None:
    await access.load_lms_class(db, cid, user, {"teacher"}, write=True)
    await _lesson(db, cid, lid)
    rows = list(await db.scalars(select(LessonItem).where(LessonItem.lesson_id == lid)))
    await _order(db, rows, body)


@router.post("/classes/{cid}/items/{iid}/view", status_code=204)
async def view_item(cid: str, iid: str, user: CurrentUser, db: DbSession) -> None:
    await access.load_lms_class(db, cid, user, {"student"}, write=True)
    row = await _item(db, cid, iid)
    if not await item_visible(db, row):
        raise classes.not_found()
    # Native upsert keeps simultaneous requests idempotent on both supported databases.
    if db.bind.dialect.name == "postgresql":
        from sqlalchemy.dialects.postgresql import insert
    else:
        from sqlalchemy.dialects.sqlite import insert
    stamp = lms.now()
    statement = insert(ContentView).values(
        class_id=cid, item_id=iid, student_id=user.id, first_viewed_at=stamp, last_viewed_at=stamp
    )
    await db.execute(
        statement.on_conflict_do_update(
            index_elements=[ContentView.item_id, ContentView.student_id], set_={"last_viewed_at": stamp}
        )
    )
    await db.commit()


@router.get("/classes/{cid}/items/{iid}/views", response_model=list[ViewOut])
async def item_views(cid: str, iid: str, user: CurrentUser, db: DbSession):
    await access.load_lms_class(db, cid, user, {"teacher"})
    await _item(db, cid, iid)
    rows = await db.execute(
        select(User.id, User.name, ContentView.first_viewed_at)
        .join(ClassMember, ClassMember.user_id == User.id)
        .outerjoin(ContentView, (ContentView.student_id == User.id) & (ContentView.item_id == iid))
        .where(ClassMember.class_id == cid, ClassMember.role == "student")
        .order_by(User.name, User.id)
    )
    return [
        ViewOut(student_id=sid, name=name, viewed=stamp is not None, first_viewed_at=stamp) for sid, name, stamp in rows
    ]
