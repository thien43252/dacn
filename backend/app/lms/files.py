"""Uploads and downloads for lesson content, assignment prompts and submissions (research R2).

Files are written in 1 MB chunks under `<upload_dir>/lms/<class_id>/<file_id><ext>`; the client filename is only a
display name. Downloads go through access checks and `FileResponse`, which answers `Range` requests (video seeking).
"""

import asyncio
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import CurrentUser, DbSession
from app.auth.models import User
from app.classes import service as classes
from app.classes.models import ClassRoom
from app.config import get_settings
from app.knowledge.service import storage_root
from app.lms import access
from app.lms.models import Assignment, LessonItem, LmsFile
from app.lms.schemas import FileOut

router = APIRouter(tags=["lms"])

CHUNK = 1024 * 1024
# extension -> content type
ALLOWED: dict[str, str] = {
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".txt": "text/plain",
    ".md": "text/markdown",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".mp4": "video/mp4",
    ".webm": "video/webm",
    ".mp3": "audio/mpeg",
    ".zip": "application/zip",
}
VIDEO_TYPES = {"video/mp4", "video/webm"}
# Formats the knowledge base can read, for "cho agent đọc" (research R3).
AGENT_READABLE = {".pdf", ".docx", ".txt", ".md"}


def extension_of(filename: str) -> str:
    return Path(filename).suffix.lower()


def lms_root() -> Path:
    return storage_root() / "lms"


def limit_bytes(content_type: str) -> int:
    settings = get_settings()
    mb = settings.lms_max_video_mb if content_type in VIDEO_TYPES else settings.lms_max_file_mb
    return mb * 1024 * 1024


def _out(row: LmsFile) -> FileOut:
    return FileOut(
        id=row.id,
        filename=row.filename,
        content_type=row.content_type,
        size_bytes=row.size_bytes,
        purpose=row.purpose,
        created_at=row.created_at,
    )


async def save_upload(db: AsyncSession, room: ClassRoom, owner: User, upload: UploadFile, purpose: str) -> LmsFile:
    filename = Path(upload.filename or "tep").name[:255]
    ext = extension_of(filename)
    content_type = ALLOWED.get(ext)
    if content_type is None:
        allowed = ", ".join(sorted({e.lstrip(".").upper() for e in ALLOWED}))
        raise HTTPException(
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, f"Định dạng tệp không được hỗ trợ. Nhận: {allowed}."
        )
    limit = limit_bytes(content_type)
    row = LmsFile(
        class_id=room.id,
        owner_id=owner.id,
        purpose=purpose,
        filename=filename,
        content_type=content_type,
        size_bytes=0,
    )
    db.add(row)
    await db.flush()
    target = lms_root() / room.id / f"{row.id}{ext}"
    target.parent.mkdir(parents=True, exist_ok=True)
    size = 0
    try:
        with target.open("wb") as handle:
            while chunk := await upload.read(CHUNK):
                size += len(chunk)
                if size > limit:
                    raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, f"Tệp vượt quá {limit // (1024 * 1024)} MB.")
                await asyncio.to_thread(handle.write, chunk)
        if size == 0:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Tệp rỗng.")
    except BaseException:
        target.unlink(missing_ok=True)
        raise
    row.size_bytes = size
    row.storage_path = str(target)
    return row


@router.post("/classes/{class_id}/files", response_model=FileOut, status_code=status.HTTP_201_CREATED)
async def upload_file(
    class_id: str,
    user: CurrentUser,
    db: DbSession,
    file: UploadFile = File(...),
    purpose: str = Form(default="content"),
) -> FileOut:
    room, role = await access.load_lms_class(db, class_id, user, {"teacher", "student"}, write=True)
    if purpose not in ("content", "prompt", "submission"):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Mục đích tệp không hợp lệ.")
    if (purpose == "submission") != (role == "student"):
        raise classes.forbidden()
    row = await save_upload(db, room, user, file, purpose)
    await db.commit()
    await db.refresh(row)
    return _out(row)


async def _visible_to_class(db: AsyncSession, row: LmsFile, role: str) -> bool:
    """Content and prompt files: teachers always; students and parents only when an item or assignment that shows
    them is visible (published lesson, visible item, open time reached)."""
    if role == "teacher":
        return True
    from app.lms.lessons import item_visible  # local import: lessons imports this module

    items = list(await db.scalars(select(LessonItem).where(LessonItem.file_id == row.id)))
    for item in items:
        if await item_visible(db, item):
            return True
    if row.purpose == "prompt":
        assignments = await db.scalars(select(Assignment).where(Assignment.class_id == row.class_id))
        for assignment in assignments:
            if row.id in (assignment.prompt_file_ids or []):
                item = await db.get(LessonItem, assignment.item_id)
                if item is not None and await item_visible(db, item):
                    return True
    return False


async def can_read(db: AsyncSession, room: ClassRoom, user: User, role: str, row: LmsFile) -> bool:
    if row.class_id != room.id:
        return False
    if row.purpose != "submission":
        return await _visible_to_class(db, row, role)
    if role == "teacher":
        return True
    if role == "student":
        return row.owner_id == user.id
    # Parents: only files their own child submitted.
    return row.owner_id in set(await classes.children_of(db, user.id))


@router.get("/classes/{class_id}/files/{file_id}")
async def download_file(class_id: str, file_id: str, user: CurrentUser, db: DbSession, download: int = 0):
    room, role = await access.load_lms_class(db, class_id, user)
    row = await db.get(LmsFile, file_id)
    if row is None or not await can_read(db, room, user, role, row):
        raise classes.not_found()
    if not await asyncio.to_thread(Path(row.storage_path).is_file):
        raise classes.not_found()
    return FileResponse(
        row.storage_path,
        media_type=row.content_type,
        filename=row.filename,
        content_disposition_type="attachment" if download else "inline",
    )
