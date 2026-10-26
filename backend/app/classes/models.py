from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, false, func, true
from sqlalchemy.orm import Mapped, mapped_column

from app.auth.models import new_id
from app.db import Base, TimestampMixin

# Applied to every agent in the class (week 7 enforces them in the runtime and output guard).
DEFAULT_POLICY: dict = {
    "no_direct_answers": True,
    "allowed_subjects": [],
    "blocked_topics": [],
    "allow_personal_agents": True,
    "notes_for_agents": "",
}


class ClassRoom(TimestampMixin, Base):
    __tablename__ = "classes"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(120))
    subject: Mapped[str] = mapped_column(String(16))
    grade: Mapped[int] = mapped_column(Integer)
    description: Mapped[str] = mapped_column(Text, default="")
    join_code: Mapped[str] = mapped_column(String(12), unique=True, index=True)
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    # Children (under 16 under Vietnamese law) need a guardian's consent before agents process their messages.
    require_parent_consent: Mapped[bool] = mapped_column(Boolean, default=True, server_default=true())
    policy: Mapped[dict] = mapped_column(JSON, default=lambda: dict(DEFAULT_POLICY))
    archived: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())


class ClassMember(Base):
    """Students (and co-teachers) of a class. Parents are reached through `ParentLink`, not membership."""

    __tablename__ = "class_members"
    __table_args__ = (UniqueConstraint("class_id", "user_id", name="uq_class_members_class_user"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    class_id: Mapped[str] = mapped_column(ForeignKey("classes.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(String(16))  # "teacher" | "student"
    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ParentLink(Base):
    __tablename__ = "parent_links"
    __table_args__ = (UniqueConstraint("parent_id", "student_id", name="uq_parent_links_pair"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    parent_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    student_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    linked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class StudentLinkCode(Base):
    """A student's personal code; a parent who enters it becomes linked to that student."""

    __tablename__ = "student_link_codes"

    student_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    code: Mapped[str] = mapped_column(String(12), unique=True, index=True)


class Consent(TimestampMixin, Base):
    """A guardian's decision for one child. The latest row per (parent, student) is authoritative."""

    __tablename__ = "consents"
    __table_args__ = (UniqueConstraint("parent_id", "student_id", name="uq_consents_pair"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    parent_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    student_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    allow_agents: Mapped[bool] = mapped_column(Boolean, default=False)
    allow_progress_reports: Mapped[bool] = mapped_column(Boolean, default=True)
