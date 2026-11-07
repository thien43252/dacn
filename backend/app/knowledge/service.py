"""Class documents: the platform keeps the file, the document row and its status; the class's Dify knowledge base
does the parsing, chunking, embedding and search (app/knowledge/dify_datasets.py, research R7).
"""

import asyncio
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.classes.models import ClassRoom
from app.config import get_settings
from app.db import session_factory
from app.knowledge import dify_datasets
from app.knowledge.dify_datasets import DifyDatasetError, Segment
from app.knowledge.models import Document

ALLOWED_TYPES = {
    "application/pdf": ".pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
    "text/plain": ".txt",
    "text/markdown": ".md",
}
MAX_BYTES = 15 * 1024 * 1024


@dataclass
class SearchHit:
    document_id: str
    title: str
    location: str
    content: str
    score: float


def detect_type(filename: str, declared: str | None) -> str | None:
    suffix = Path(filename).suffix.lower()
    for content_type, extension in ALLOWED_TYPES.items():
        if suffix == extension:
            return content_type
    return declared if declared in ALLOWED_TYPES else None


def storage_root() -> Path:
    root = Path(get_settings().upload_dir)
    if not root.is_absolute():
        root = Path(__file__).resolve().parents[2] / root
    root.mkdir(parents=True, exist_ok=True)
    return root


def location(position: int) -> str:
    return f"đoạn {position}" if position else ""


async def process_document(document_id: str) -> None:
    """Background job: sends the stored file to the class's knowledge base, creating it on the class's first document.
    Reprocessing deletes the old Dify document first. Indexing then runs in Dify; `refresh_status` follows it."""
    async with session_factory()() as db:
        document = await db.get(Document, document_id)
        room = await db.get(ClassRoom, document.class_id) if document else None
        if document is None or room is None:
            return
        client = dify_datasets.make_datasets()
        try:
            if not room.dify_dataset_id:
                room.dify_dataset_id = await client.create_dataset(room.id)
                await db.commit()
            if document.dify_document_id:
                await client.delete_document(room.dify_dataset_id, document.dify_document_id)
                document.dify_document_id = document.dify_batch = None
            data = await asyncio.to_thread(Path(document.storage_path).read_bytes)
            document.dify_document_id, document.dify_batch = await client.upload_document(
                room.dify_dataset_id, document.filename, data, document.content_type
            )
            document.status, document.error, document.chunk_count = "processing", None, 0
        except (DifyDatasetError, OSError) as error:
            document.status = "failed"
            document.error = str(error)[:500]
        finally:
            await client.http.aclose()
        await db.commit()


async def refresh_status(db: AsyncSession, room: ClassRoom, documents: list[Document]) -> None:
    """Asks Dify how indexing is going for documents still processing (FR-021). Dify unreachable: unchanged."""
    pending = [d for d in documents if d.status == "processing" and d.dify_batch and room.dify_dataset_id]
    if not pending:
        return
    client = dify_datasets.make_datasets()
    try:
        for document in pending:
            try:
                status = await client.indexing_status(room.dify_dataset_id, document.dify_batch)
            except DifyDatasetError:
                continue
            if status.status == "completed":
                document.status, document.chunk_count, document.error = "ready", status.segments, None
            elif status.status == "error":
                document.status = "failed"
                document.error = (status.error or "Dify không xử lý được tài liệu.")[:500]
    finally:
        await client.http.aclose()
    await db.commit()


async def delete_from_dify(room: ClassRoom, document: Document) -> None:
    """Raises DifyDatasetError if Dify still has the document; the caller then keeps the row."""
    if not (room.dify_dataset_id and document.dify_document_id):
        return
    client = dify_datasets.make_datasets()
    try:
        await client.delete_document(room.dify_dataset_id, document.dify_document_id)
    finally:
        await client.http.aclose()


async def segments(room: ClassRoom, document: Document) -> list[Segment]:
    """Dify's chunks of one document for the teacher's preview; none until it is indexed."""
    if not (room.dify_dataset_id and document.dify_document_id):
        return []
    client = dify_datasets.make_datasets()
    try:
        return await client.segments(room.dify_dataset_id, document.dify_document_id)
    finally:
        await client.http.aclose()


async def search(db: AsyncSession, dataset_id: str | None, query: str, top_k: int = 4) -> list[SearchHit]:
    """Searches one class's knowledge base. The dataset id comes from the tool handle, never from the model."""
    if not dataset_id:
        return []
    client = dify_datasets.make_datasets()
    try:
        records = await client.retrieve(dataset_id, query, top_k)
    finally:
        await client.http.aclose()
    ids = {record.dify_document_id for record in records}
    documents = {
        d.dify_document_id: d for d in await db.scalars(select(Document).where(Document.dify_document_id.in_(ids)))
    }
    hits = []
    for record in records:
        document = documents.get(record.dify_document_id)
        hits.append(
            SearchHit(
                document_id=document.id if document else record.dify_document_id,
                title=document.title if document else record.document_name,
                location=location(record.position),
                content=record.content,
                score=record.score,
            )
        )
    return hits
