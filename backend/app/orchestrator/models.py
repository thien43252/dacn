"""Run state of the full path (specs/002-multi-agent-orchestration/data-model.md).

A `TurnRun` is one request handled through planner → steps → synthesis; it may span several chat requests when it
pauses for the user. The fast path never creates one.
"""

from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from app.auth.models import new_id
from app.db import Base, TimestampMixin

# running · awaiting_user are open; the rest are final.
OPEN_STATUSES = ("running", "awaiting_user")
_OPEN_SQL = text("status IN ('running', 'awaiting_user')")


class TurnRun(TimestampMixin, Base):
    __tablename__ = "turn_runs"
    __table_args__ = (
        # At most one open run per conversation (research R7).
        Index(
            "uq_turn_runs_open_conversation",
            "conversation_id",
            unique=True,
            postgresql_where=_OPEN_SQL,
            sqlite_where=_OPEN_SQL,
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    conversation_id: Mapped[str] = mapped_column(ForeignKey("conversations.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    class_id: Mapped[str | None] = mapped_column(ForeignKey("classes.id", ondelete="SET NULL"), nullable=True)
    # running · awaiting_user · done · error · cancelled · expired
    status: Mapped[str] = mapped_column(String(16), default="running")
    request_message_id: Mapped[str] = mapped_column(String(36))
    reply_message_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    # The request after redaction; resuming plans from it.
    request_text: Mapped[str] = mapped_column(Text, default="")
    lead_agent: Mapped[str | None] = mapped_column(String(48), nullable=True)
    goal: Mapped[str] = mapped_column(Text, default="")
    plan: Mapped[dict] = mapped_column(JSON, default=dict)
    plan_version: Mapped[int] = mapped_column(Integer, default=1)
    pending: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    clarify_rounds: Mapped[int] = mapped_column(Integer, default=0)
    replans: Mapped[int] = mapped_column(Integer, default=0)
    assumptions: Mapped[list] = mapped_column(JSON, default=list)
    resume_answers: Mapped[list] = mapped_column(JSON, default=list)
    confirmations: Mapped[list] = mapped_column(JSON, default=list)
    interactive: Mapped[bool] = mapped_column(Boolean, default=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class RunStep(Base):
    __tablename__ = "run_steps"
    __table_args__ = (UniqueConstraint("run_id", "key", name="uq_run_steps_run_id_key"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    run_id: Mapped[str] = mapped_column(ForeignKey("turn_runs.id", ondelete="CASCADE"), index=True)
    key: Mapped[str] = mapped_column(String(16))
    agent_slug: Mapped[str] = mapped_column(String(48))
    agent_version_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    title: Mapped[str] = mapped_column(String(80), default="")
    task: Mapped[str] = mapped_column(Text, default="")
    depends_on: Mapped[list] = mapped_column(JSON, default=list)
    # plan · help · rerun
    origin: Mapped[str] = mapped_column(String(16), default="plan")
    requested_by: Mapped[str | None] = mapped_column(String(16), nullable=True)
    # pending · running · done · error · blocked · skipped
    status: Mapped[str] = mapped_column(String(16), default="pending")
    note: Mapped[str] = mapped_column(Text, default="")
    # unreviewed · visible · hidden (research R9)
    note_review: Mapped[str] = mapped_column(String(12), default="unreviewed")
    signals: Mapped[list] = mapped_column(JSON, default=list)
    citations: Mapped[list] = mapped_column(JSON, default=list)
    tools: Mapped[list] = mapped_column(JSON, default=list)
    error: Mapped[str | None] = mapped_column(String(300), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
