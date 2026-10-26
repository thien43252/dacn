from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.auth.models import new_id
from app.db import Base


class GuardEvent(Base):
    """A guard decision other than a plain "allow": what was stopped, changed or flagged, at which stage and why.

    `excerpt` is the triggering text with personal data redacted, so the audit log never stores what the guard hid.
    """

    __tablename__ = "guard_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    # chat | sandbox | certify
    source: Mapped[str] = mapped_column(String(16), default="chat", index=True)
    class_id: Mapped[str | None] = mapped_column(
        ForeignKey("classes.id", ondelete="SET NULL"), index=True, nullable=True
    )
    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True, nullable=True)
    role: Mapped[str] = mapped_column(String(16), default="")
    conversation_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    message_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    agent_slug: Mapped[str | None] = mapped_column(String(48), nullable=True)
    # input | tool | output
    stage: Mapped[str] = mapped_column(String(16))
    # block | support | redact | flag
    verdict: Mapped[str] = mapped_column(String(16), index=True)
    category: Mapped[str] = mapped_column(String(40), default="")
    # rule | policy | llm
    detector: Mapped[str] = mapped_column(String(16))
    severity: Mapped[str] = mapped_column(String(8), default="low")
    reason: Mapped[str] = mapped_column(String(300), default="")
    excerpt: Mapped[str] = mapped_column(String(300), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
