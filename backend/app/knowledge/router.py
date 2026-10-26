import asyncio
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, UploadFile, status
from pydantic import BaseModel
from sqlalchemy import select

from app.auth.deps import CurrentUser, DbSession
from app.classes import service as classes
from app.knowledge import service
from app.knowledge.models import Document, DocumentChunk

router = APIRouter(tags=["documents"])


class DocumentOut(BaseModel):
    id: str
    title: str
    filename: str
    content_type: str
    size_bytes: int
    status: str
    error: str | None
    chunk_count: int
    created_at: datetime


class ChunkOut(BaseModel):
    position: int
    location: str
    content: str


def _out(document: Document) -> DocumentOut:
    return DocumentOut(
        id=document.id,
        title=document.title,
        filename=document.filename,
        content_type=document.content_type,
        size_bytes=document.size_bytes,
        status=document.status,
        error=document.error,
        chunk_count=document.chunk_count,
        created_at=document.created_at,
    )


@router.get("/classes/{class_id}/documents", response_model=list[DocumentOut])
async def list_documents(class_id: str, user: CurrentUser, db: DbSession) -> list[DocumentOut]:
    # Students see the list so they know what the agents can read; only teachers upload or delete.
    room, _ = await classes.load_class(db, class_id, user, {"teacher", "student"})
    rows = await db.scalars(select(Document).where(Document.class_id == room.id).order_by(Document.created_at.desc()))
    return [_out(document) for document in rows]


@router.post("/classes/{class_id}/documents", response_model=DocumentOut, status_code=status.HTTP_201_CREATED)
async def upload_document(
    class_id: str,
    user: CurrentUser,
    db: DbSession,
    background: BackgroundTasks,
    file: UploadFile = File(...),
    title: str = Form(default=""),
) -> DocumentOut:
    room, _ = await classes.load_class(db, class_id, user, {"teacher"})
    filename = Path(file.filename or "tai-lieu").name
    content_type = service.detect_type(filename, file.content_type)
    if content_type is None:
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "Chỉ nhận tệp PDF, DOCX, TXT hoặc MD.")
    data = await file.read(service.MAX_BYTES + 1)
    if len(data) > service.MAX_BYTES:
        raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, "Tệp vượt quá 15 MB.")
    if not data:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Tệp rỗng.")
    document = Document(
        class_id=room.id,
        uploaded_by=user.id,
        title=(title.strip() or Path(filename).stem)[:200],
        filename=filename[:255],
        content_type=content_type,
        size_bytes=len(data),
        storage_path="",
    )
    db.add(document)
    await db.flush()
    # Stored under a generated name: the client-supplied filename never becomes a path.
    target = service.storage_root() / room.id / f"{document.id}{service.ALLOWED_TYPES[content_type]}"
    target.parent.mkdir(parents=True, exist_ok=True)
    await asyncio.to_thread(target.write_bytes, data)
    document.storage_path = str(target)
    await db.commit()
    await db.refresh(document)
    background.add_task(service.process_document, document.id)
    return _out(document)


async def _document(db, class_id: str, document_id: str) -> Document:
    document = await db.get(Document, document_id)
    if document is None or document.class_id != class_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Không tìm thấy tài liệu.")
    return document


@router.get("/classes/{class_id}/documents/{document_id}/chunks", response_model=list[ChunkOut])
async def list_chunks(class_id: str, document_id: str, user: CurrentUser, db: DbSession) -> list[ChunkOut]:
    room, _ = await classes.load_class(db, class_id, user, {"teacher"})
    document = await _document(db, room.id, document_id)
    rows = await db.scalars(
        select(DocumentChunk)
        .where(DocumentChunk.document_id == document.id)
        .order_by(DocumentChunk.position)
        .limit(200)
    )
    return [ChunkOut(position=c.position, location=c.location, content=c.content) for c in rows]


@router.post("/classes/{class_id}/documents/{document_id}/reprocess", response_model=DocumentOut)
async def reprocess(
    class_id: str, document_id: str, user: CurrentUser, db: DbSession, background: BackgroundTasks
) -> DocumentOut:
    room, _ = await classes.load_class(db, class_id, user, {"teacher"})
    document = await _document(db, room.id, document_id)
    document.status, document.error = "processing", None
    await db.commit()
    background.add_task(service.process_document, document.id)
    return _out(document)


@router.delete("/classes/{class_id}/documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(class_id: str, document_id: str, user: CurrentUser, db: DbSession) -> None:
    room, _ = await classes.load_class(db, class_id, user, {"teacher"})
    document = await _document(db, room.id, document_id)
    path = Path(document.storage_path)
    await db.delete(document)
    await db.commit()
    await asyncio.to_thread(path.unlink, missing_ok=True)
