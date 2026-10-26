from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, String, false, func
from sqlalchemy.orm import Mapped, mapped_column

from app.auth.models import new_id
from app.db import Base

# running -> certified | needs_review | rejected | failed; an admin review turns needs_review into one of the others.
CERTIFICATION_RESULTS = ("certified", "needs_review", "rejected")


class Certification(Base):
    """One run of the certification pipeline on one immutable agent version."""

    __tablename__ = "certifications"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    agent_id: Mapped[str] = mapped_column(ForeignKey("agents.id", ondelete="CASCADE"), index=True)
    agent_version_id: Mapped[str] = mapped_column(ForeignKey("agent_versions.id", ondelete="CASCADE"), index=True)
    requested_by: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    # Make the agent public on the Hub once this version is certified.
    publish: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    status: Mapped[str] = mapped_column(String(16), default="running", index=True)
    # Share of red-team and benign cases judged safe and helpful, 0..1; null until the dynamic stage ran.
    score: Mapped[float | None] = mapped_column(Float, nullable=True)
    # {"done": n, "total": m} while running.
    progress: Mapped[dict] = mapped_column(JSON, default=dict)
    # Static checks, per-category results, failed cases and the reasons behind the decision.
    report: Mapped[dict] = mapped_column(JSON, default=dict)
    reviewer_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    review_note: Mapped[str] = mapped_column(String(500), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
