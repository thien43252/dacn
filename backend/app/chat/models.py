from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    false,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.auth.models import new_id
from app.db import Base, TimestampMixin

# direct: one person and one agent (or the auto-routing assistant when direct_agent_slug is null);
# group: people and agents of one class; sandbox: an author trying a draft agent in the builder.
CONVERSATION_KINDS = ("direct", "group", "sandbox")


class Conversation(TimestampMixin, Base):
    __tablename__ = "conversations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    # The creator; for a direct chat, the only person in it.
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    # Null for a personal conversation outside any class.
    class_id: Mapped[str | None] = mapped_column(
        ForeignKey("classes.id", ondelete="CASCADE"), index=True, nullable=True
    )
    title: Mapped[str] = mapped_column(String(200), default="")
    kind: Mapped[str] = mapped_column(String(16), default="direct", server_default="direct")
    # The agent of a direct chat. Null keeps the pre-feature behaviour: the orchestrator picks an agent per message.
    direct_agent_slug: Mapped[str | None] = mapped_column(String(48), nullable=True)
    # The agent that answers unnamed messages in a group.
    default_agent_slug: Mapped[str | None] = mapped_column(String(48), nullable=True)
    last_seq: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    # Set when the user starts a fresh direct chat with the same agent.
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ConversationMember(Base):
    """A person or an agent in a conversation. Exactly one of user_id and agent_slug is set."""

    __tablename__ = "conversation_members"
    __table_args__ = (
        UniqueConstraint("conversation_id", "user_id", name="uq_conversation_members_user"),
        UniqueConstraint("conversation_id", "agent_slug", name="uq_conversation_members_agent"),
        CheckConstraint("(user_id IS NULL) <> (agent_slug IS NULL)", name="one_member_kind"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    conversation_id: Mapped[str] = mapped_column(ForeignKey("conversations.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=True)
    agent_slug: Mapped[str | None] = mapped_column(String(48), nullable=True)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    # Messages with seq <= joined_seq stay hidden unless can_see_history.
    joined_seq: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    can_see_history: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    last_read_seq: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    left_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ChatMessage(Base):
    __tablename__ = "chat_messages"
    __table_args__ = (
        UniqueConstraint("conversation_id", "seq", name="uq_chat_messages_conversation_seq"),
        UniqueConstraint("handoff_id", name="uq_chat_messages_handoff_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    conversation_id: Mapped[str] = mapped_column(ForeignKey("conversations.id", ondelete="CASCADE"), index=True)
    seq: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    role: Mapped[str] = mapped_column(String(16))  # "user" | "assistant" | "system"
    content: Mapped[str] = mapped_column(Text)
    sender_user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    agent_slug: Mapped[str | None] = mapped_column(String(48), nullable=True)
    agent_version_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    # ok | blocked (a guard refused it) | error (the model call failed) | hidden (moderation hid it from viewers)
    status: Mapped[str] = mapped_column(String(16), default="ok")
    meta: Mapped[dict] = mapped_column(JSON, default=dict)
    # The verbatim answer of a handoff (unique: an answer is written once).
    handoff_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    # "trả lời cho <agent>" label in groups.
    reply_to_agent: Mapped[str | None] = mapped_column(String(48), nullable=True)
    person_request_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    approval_card_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    run_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    # Null: every member; a list of user ids: only those people (e.g. a safety reply in a group).
    visible_to: Mapped[list | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)


class ToolCallLog(Base):
    __tablename__ = "tool_calls"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    conversation_id: Mapped[str] = mapped_column(ForeignKey("conversations.id", ondelete="CASCADE"), index=True)
    message_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    agent_slug: Mapped[str] = mapped_column(String(48))
    tool: Mapped[str] = mapped_column(String(64))
    arguments: Mapped[dict] = mapped_column(JSON, default=dict)
    result: Mapped[str] = mapped_column(Text, default="")
    is_error: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    # Set when the tool guard refused the call before it ran.
    denied_reason: Mapped[str | None] = mapped_column(String(300), nullable=True)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class UsageRecord(Base):
    """One model or embedding call, with tokens and (when the price is known) cost."""

    __tablename__ = "usage_ledger"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True, nullable=True)
    class_id: Mapped[str | None] = mapped_column(
        ForeignKey("classes.id", ondelete="SET NULL"), index=True, nullable=True
    )
    conversation_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    # agent | router | input_guard | output_guard | tool | embed | certify | judge | handoff
    purpose: Mapped[str] = mapped_column(String(24))
    provider: Mapped[str] = mapped_column(String(24))
    model: Mapped[str] = mapped_column(String(80))
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cost_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
