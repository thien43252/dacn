"""Shared LMS schemas and helpers. Each router module keeps its own request/response models next to its routes so
parallel work on different areas does not collide on this file."""

from datetime import datetime

from fastapi import HTTPException, status
from pydantic import BaseModel

from app.guard import rules


class FileOut(BaseModel):
    id: str
    filename: str
    content_type: str
    size_bytes: int
    purpose: str
    created_at: datetime | None = None


class NotificationOut(BaseModel):
    id: str
    kind: str
    class_id: str | None
    title: str
    link: str
    read_at: datetime | None
    created_at: datetime | None


class Screened(BaseModel):
    text: str
    redacted: bool = False


def screen_text(field: str, text: str | None) -> Screened:
    """Research R14: user-entered LMS text goes through the same rule layer as chat. A block is a 422 naming the
    field; personal data is redacted and the caller is told so it can show a notice."""
    if not text:
        return Screened(text=text or "")
    verdict = rules.screen_input(text)
    if verdict.blocks:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, f"Nội dung “{field}” vi phạm quy tắc an toàn của nền tảng."
        )
    if verdict.action == "redact" and verdict.text is not None:
        return Screened(text=verdict.text, redacted=True)
    return Screened(text=text)


def clean(field: str, text: str | None) -> str:
    """`screen_text` when the caller only needs the stored text."""
    return screen_text(field, text).text
