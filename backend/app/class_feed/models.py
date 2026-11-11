"""Class announcements and assigned practice sets (specs/002-multi-agent-orchestration/data-model.md, R18)."""

from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.auth.models import new_id
from app.db import Base

ANNOUNCEMENT_BODY_MAX = 2000
INSTRUCTIONS_MAX = 1000
MAX_QUESTIONS = 20


class ClassAnnouncement(Base):
    __tablename__ = "class_announcements"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    class_id: Mapped[str] = mapped_column(ForeignKey("classes.id", ondelete="CASCADE"), index=True)
    author_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    title: Mapped[str] = mapped_column(String(120))
    body: Mapped[str] = mapped_column(Text)
    # students · parents · all
    audience: Mapped[str] = mapped_column(String(16))
    # agent (through a confirmed tool) · ui
    source: Mapped[str] = mapped_column(String(16), default="ui")
    run_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)


class Assignment(Base):
    __tablename__ = "assignments"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    class_id: Mapped[str] = mapped_column(ForeignKey("classes.id", ondelete="CASCADE"), index=True)
    author_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    title: Mapped[str] = mapped_column(String(120))
    instructions: Mapped[str] = mapped_column(Text, default="")
    # [{question ≤ 500, options?: string[] ≤ 6}], 1–20 items
    questions: Mapped[list] = mapped_column(JSON, default=list)
    # [{index, answer, explanation?}]; teachers only
    answer_key: Mapped[list | None] = mapped_column(JSON, nullable=True)
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    source: Mapped[str] = mapped_column(String(16), default="ui")
    run_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
