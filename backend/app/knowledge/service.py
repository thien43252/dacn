"""Class documents: parse, chunk, embed, and search (pgvector cosine distance on Postgres)."""

import asyncio
import io
import math
import re
import time
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db import session_factory
from app.knowledge.models import Document, DocumentChunk
from app.llm.base import Embedder, LLMError, Usage
from app.llm.registry import get_embedder

ALLOWED_TYPES = {
    "application/pdf": ".pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
    "text/plain": ".txt",
    "text/markdown": ".md",
}
MAX_BYTES = 15 * 1024 * 1024
CHUNK_CHARS = 1200
CHUNK_OVERLAP = 200
EMBED_BATCH = 64


@dataclass
class Section:
    text: str
    location: str


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


def extract_sections(data: bytes, content_type: str) -> list[Section]:
    """Plain text per page (PDF), per heading block (DOCX) or whole file (TXT/MD)."""
    if content_type == "application/pdf":
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(data))
        return [Section(page.extract_text() or "", f"trang {index}") for index, page in enumerate(reader.pages, 1)]
    if content_type.endswith("wordprocessingml.document"):
        import docx

        document = docx.Document(io.BytesIO(data))
        sections: list[Section] = []
        heading, buffer = "đầu tài liệu", []
        for paragraph in document.paragraphs:
            text = paragraph.text.strip()
            if not text:
                continue
            if paragraph.style is not None and paragraph.style.name.lower().startswith(("heading", "title")):
                if buffer:
                    sections.append(Section("\n".join(buffer), heading))
                heading, buffer = text[:70], [text]
            else:
                buffer.append(text)
        for table in document.tables:
            for row in table.rows:
                buffer.append(" | ".join(cell.text.strip() for cell in row.cells))
        if buffer:
            sections.append(Section("\n".join(buffer), heading))
        return sections
    text = data.decode("utf-8", errors="replace")
    if content_type == "text/markdown":
        # One section per heading, so citations can name the part of the lesson.
        sections, heading, buffer = [], "", []
        for line in text.splitlines():
            if line.lstrip().startswith("#"):
                if "\n".join(buffer).strip():
                    sections.append(Section("\n".join(buffer), heading))
                heading, buffer = line.lstrip("# ").strip()[:70], [line.lstrip("# ").strip()]
            else:
                buffer.append(line)
        if "\n".join(buffer).strip():
            sections.append(Section("\n".join(buffer), heading))
        return sections
    return [Section(text, "")]


def chunk_sections(sections: list[Section], size: int = CHUNK_CHARS, overlap: int = CHUNK_OVERLAP) -> list[Section]:
    """Splits on paragraph and sentence boundaries into ~size-character chunks with overlap."""
    chunks: list[Section] = []
    for section in sections:
        text = re.sub(r"[ \t]+", " ", section.text).strip()
        if not text:
            continue
        pieces = re.split(r"(?<=[.!?…])\s+|\n{2,}", text)
        current = ""
        for piece in pieces:
            piece = piece.strip()
            if not piece:
                continue
            while len(piece) > size:
                head, piece = piece[:size], piece[size - overlap :]
                if current:
                    chunks.append(Section(current, section.location))
                    current = ""
                chunks.append(Section(head, section.location))
            if len(current) + len(piece) + 1 > size and current:
                chunks.append(Section(current, section.location))
                current = current[-overlap:] + " " + piece
            else:
                current = f"{current} {piece}".strip()
        if current:
            chunks.append(Section(current, section.location))
    return chunks


def storage_root() -> Path:
    root = Path(get_settings().upload_dir)
    if not root.is_absolute():
        root = Path(__file__).resolve().parents[2] / root
    root.mkdir(parents=True, exist_ok=True)
    return root


async def embed_all(embedder: Embedder, texts: list[str]) -> list[list[float]]:
    vectors: list[list[float]] = []
    for start in range(0, len(texts), EMBED_BATCH):
        vectors.extend(await embedder.embed(texts[start : start + EMBED_BATCH]))
    return vectors


async def process_document(document_id: str) -> None:
    """Background job: parse, chunk and embed one uploaded document. Uses its own session."""
    async with session_factory()() as db:
        document = await db.get(Document, document_id)
        if document is None:
            return
        started = time.perf_counter()
        try:
            data = await asyncio.to_thread(Path(document.storage_path).read_bytes)
            # Parsing large PDFs is CPU-bound; keep it off the event loop.
            sections = await asyncio.to_thread(extract_sections, data, document.content_type)
            chunks = chunk_sections(sections)
            if not chunks:
                raise ValueError("Không đọc được chữ trong tài liệu (có thể là ảnh scan).")
            embedder = get_embedder()
            vectors = await embed_all(embedder, [chunk.text for chunk in chunks])
            await db.execute(delete(DocumentChunk).where(DocumentChunk.document_id == document.id))
            for position, (chunk, vector) in enumerate(zip(chunks, vectors, strict=True)):
                db.add(
                    DocumentChunk(
                        document_id=document.id,
                        class_id=document.class_id,
                        position=position,
                        content=chunk.text,
                        location=chunk.location,
                        embedding=vector,
                    )
                )
            document.status = "ready"
            document.chunk_count = len(chunks)
            document.error = None
            document.meta = {
                **(document.meta or {}),
                "embedding_model": f"{embedder.provider}:{embedder.model}",
                "processing_ms": int((time.perf_counter() - started) * 1000),
            }
        except (ValueError, LLMError, OSError) as error:
            document.status = "failed"
            document.error = str(error)[:500]
        except Exception as error:  # parser libraries raise many types on malformed files
            document.status = "failed"
            document.error = f"Không xử lý được tệp: {type(error).__name__}"
        await db.commit()


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=False))
    norm = math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b))
    return dot / norm if norm else 0.0


async def search(db: AsyncSession, class_id: str, query: str, top_k: int = 4) -> tuple[list[SearchHit], Usage]:
    embedder = get_embedder()
    [vector] = await embedder.embed([query])
    usage = Usage(provider=embedder.provider, model=embedder.model, input_tokens=max(1, len(query) // 4))
    if db.bind.dialect.name == "postgresql":
        distance = DocumentChunk.embedding.cosine_distance(vector)  # type: ignore[attr-defined]
        rows = await db.execute(
            select(DocumentChunk, Document.title, distance.label("distance"))
            .join(Document, Document.id == DocumentChunk.document_id)
            .where(DocumentChunk.class_id == class_id, Document.status == "ready")
            .order_by(distance)
            .limit(top_k)
        )
        hits = [
            SearchHit(chunk.document_id, title, chunk.location, chunk.content, round(1 - float(dist), 4))
            for chunk, title, dist in rows
        ]
    else:
        rows = await db.execute(
            select(DocumentChunk, Document.title)
            .join(Document, Document.id == DocumentChunk.document_id)
            .where(DocumentChunk.class_id == class_id, Document.status == "ready")
        )
        scored = [
            SearchHit(
                chunk.document_id, title, chunk.location, chunk.content, round(_cosine(vector, chunk.embedding), 4)
            )
            for chunk, title in rows
            if chunk.embedding
        ]
        hits = sorted(scored, key=lambda hit: hit.score, reverse=True)[:top_k]
    return hits, usage
