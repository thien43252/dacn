from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, UniqueConstraint, false, func, true
from sqlalchemy.orm import Mapped, mapped_column

from app.auth.models import new_id
from app.db import Base, TimestampMixin

# Certification status of one immutable version (the pipeline that sets it arrives in week 9).
CERT_STATUSES = ("uncertified", "pending", "certified", "needs_review", "rejected")


class Agent(TimestampMixin, Base):
    __tablename__ = "agents"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    slug: Mapped[str] = mapped_column(String(48), unique=True, index=True)
    # Null for platform agents loaded from seed/agents.
    owner_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True, nullable=True)
    is_platform: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    # private: only the owner can install it; public: listed on the Hub once a version is certified.
    visibility: Mapped[str] = mapped_column(String(16), default="private")
    forked_from_id: Mapped[str | None] = mapped_column(ForeignKey("agents.id", ondelete="SET NULL"), nullable=True)
    # Work in progress; installs and certification always point at an immutable AgentVersion.
    draft_manifest: Mapped[dict] = mapped_column(JSON)


class AgentVersion(Base):
    __tablename__ = "agent_versions"
    __table_args__ = (UniqueConstraint("agent_id", "version", name="uq_agent_versions_agent_version"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    agent_id: Mapped[str] = mapped_column(ForeignKey("agents.id", ondelete="CASCADE"), index=True)
    version: Mapped[int] = mapped_column(Integer)
    manifest: Mapped[dict] = mapped_column(JSON)
    certification_status: Mapped[str] = mapped_column(String(16), default="uncertified")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Installation(Base):
    """An agent version made available in a class (scope "class") or to one user everywhere (scope "personal")."""

    __tablename__ = "installations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    agent_id: Mapped[str] = mapped_column(ForeignKey("agents.id", ondelete="CASCADE"), index=True)
    agent_version_id: Mapped[str] = mapped_column(ForeignKey("agent_versions.id", ondelete="CASCADE"))
    scope: Mapped[str] = mapped_column(String(16))  # "class" | "personal"
    class_id: Mapped[str | None] = mapped_column(
        ForeignKey("classes.id", ondelete="CASCADE"), index=True, nullable=True
    )
    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=True)
    installed_by: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, server_default=true())
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
