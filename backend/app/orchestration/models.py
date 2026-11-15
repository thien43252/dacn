"""State of runs that wait on other agents, people or approvals (feature 003, data-model.md §2)."""

from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, false, func
from sqlalchemy.orm import Mapped, mapped_column

from app.auth.models import new_id
from app.db import Base

RUN_STATUSES = ("running", "waiting", "resumable", "done", "failed", "cancelled")
HANDOFF_STATUSES = ("refused", "queued", "running", "answered", "failed")
REQUEST_KINDS = ("question", "approval", "choice", "install_agent")
REQUEST_STATUSES = ("draft", "open", "answered", "expired", "cancelled", "undeliverable")
CARD_STATUSES = ("open", "allowed", "denied", "expired")
CARD_CHOICES = ("once", "conversation", "always", "deny", "did_it", "dont")
ACTION_KINDS = ("none", "change", "send", "share", "post", "delete", "settings", "money")
# Kinds that always ask, whatever the user's own switch says (OpenBot approvals.md).
ALWAYS_ASK = frozenset({"send", "share", "post", "delete", "settings", "money"})
KIND_MODES = ("members_choose", "ask_every_time", "do_it_yourself")


class AgentRun(Base):
    """One agent's run in a conversation. A run that hands off, asks a person or waits for an approval is saved here
    (transcript + pending tool calls) and resumed by the worker once every pending call has a result."""

    __tablename__ = "agent_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    # Always the origin conversation: answers, cards and questions land here.
    conversation_id: Mapped[str] = mapped_column(ForeignKey("conversations.id", ondelete="CASCADE"), index=True)
    # The person whose request started the chain; every run is rebuilt as this person.
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(String(16))
    class_id: Mapped[str | None] = mapped_column(ForeignKey("classes.id", ondelete="CASCADE"), nullable=True)
    agent_slug: Mapped[str] = mapped_column(String(48))
    agent_version_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    # Set when this run answers a handoff (the asked agent's scratch thread).
    handoff_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    depth: Mapped[int] = mapped_column(Integer, default=0)
    chain: Mapped[list] = mapped_column(JSON, default=list)
    handoff_count: Mapped[int] = mapped_column(Integer, default=0)
    root_run_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    trigger_message_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    # The message this run's visible reply was written to (the asking agent's first message).
    message_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    transcript: Mapped[list] = mapped_column(JSON, default=list)
    # {tool_call_id: {"type": "handoff"|"person"|"approval", "id": ..., "result": str | None}}
    pending: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(16), default="running", index=True)
    source: Mapped[str] = mapped_column(String(16), default="chat")
    # Text the user sent (redacted), kept for guards when the run resumes.
    user_text: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Handoff(Base):
    """One agent asking another (message_bot). The id doubles as the answer's idempotency key."""

    __tablename__ = "handoffs"
    __table_args__ = (UniqueConstraint("run_id", "tool_call_id", name="uq_handoffs_run_call"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    run_id: Mapped[str] = mapped_column(ForeignKey("agent_runs.id", ondelete="CASCADE"), index=True)
    tool_call_id: Mapped[str] = mapped_column(String(80))
    conversation_id: Mapped[str] = mapped_column(ForeignKey("conversations.id", ondelete="CASCADE"), index=True)
    parent_handoff_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    from_agent: Mapped[str] = mapped_column(String(48))
    to_agent: Mapped[str] = mapped_column(String(48))
    depth: Mapped[int] = mapped_column(Integer, default=1)
    task: Mapped[str] = mapped_column(Text, default="")
    bounds: Mapped[str] = mapped_column(Text, default="")
    good_answer: Mapped[str] = mapped_column(Text, default="")
    attachments: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(16), default="queued", index=True)
    # Internal reason: not_granted | unknown_or_hidden | disabled | depth_cap | per_run_cap | loop
    refusal_reason: Mapped[str | None] = mapped_column(String(200), nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    answer: Mapped[str | None] = mapped_column(Text, nullable=True)
    answer_visible: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    late: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class PersonRequest(Base):
    """A question or approval request an agent sends to a person (ask_person)."""

    __tablename__ = "person_requests"
    __table_args__ = (UniqueConstraint("run_id", "tool_call_id", name="uq_person_requests_run_call"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    run_id: Mapped[str | None] = mapped_column(ForeignKey("agent_runs.id", ondelete="CASCADE"), nullable=True)
    tool_call_id: Mapped[str] = mapped_column(String(80), default="")
    conversation_id: Mapped[str] = mapped_column(ForeignKey("conversations.id", ondelete="CASCADE"), index=True)
    class_id: Mapped[str | None] = mapped_column(ForeignKey("classes.id", ondelete="CASCADE"), nullable=True)
    requester_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    agent_slug: Mapped[str] = mapped_column(String(48))
    recipient_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(16), default="question")
    body: Mapped[str] = mapped_column(Text)
    options: Mapped[list] = mapped_column(JSON, default=list)
    # Extra data for kind-specific follow-up (e.g. install_agent: agent_id, version_id).
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    private_to_recipient: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    status: Mapped[str] = mapped_column(String(16), default="open", index=True)
    answer: Mapped[str | None] = mapped_column(Text, nullable=True)
    answer_hidden: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    answered_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    answered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ApprovalCard(Base):
    """An action held for the origin user's answer."""

    __tablename__ = "approval_cards"
    __table_args__ = (UniqueConstraint("run_id", "tool_call_id", name="uq_approval_cards_run_call"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    run_id: Mapped[str | None] = mapped_column(ForeignKey("agent_runs.id", ondelete="CASCADE"), nullable=True)
    tool_call_id: Mapped[str] = mapped_column(String(80), default="")
    conversation_id: Mapped[str] = mapped_column(ForeignKey("conversations.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    agent_slug: Mapped[str] = mapped_column(String(48))
    tool: Mapped[str] = mapped_column(String(64))
    arguments: Mapped[dict] = mapped_column(JSON, default=dict)
    action_kind: Mapped[str] = mapped_column(String(16))
    target: Mapped[str | None] = mapped_column(String(80), nullable=True)
    summary: Mapped[str] = mapped_column(String(300), default="")
    preview: Mapped[dict] = mapped_column(JSON, default=dict)
    choices: Mapped[list] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(16), default="open", index=True)
    answer: Mapped[str | None] = mapped_column(String(16), nullable=True)
    executed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ApprovalRule(Base):
    __tablename__ = "approval_rules"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    # user | class | admin | conversation
    scope: Mapped[str] = mapped_column(String(16), index=True)
    scope_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    action_kind: Mapped[str] = mapped_column(String(16))
    agent_slug: Mapped[str | None] = mapped_column(String(48), nullable=True)
    tool: Mapped[str | None] = mapped_column(String(64), nullable=True)
    target: Mapped[str | None] = mapped_column(String(80), nullable=True)
    # allow | deny | ask
    effect: Mapped[str] = mapped_column(String(8))
    # card | typed | admin | class: only an answer on a card can open an always-ask kind.
    source: Mapped[str] = mapped_column(String(16), default="card")
    created_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ApprovalKindMode(Base):
    __tablename__ = "approval_kind_modes"

    action_kind: Mapped[str] = mapped_column(String(16), primary_key=True)
    role: Mapped[str] = mapped_column(String(16), primary_key=True)
    mode: Mapped[str] = mapped_column(String(16), default="members_choose")


class UserSettings(Base):
    __tablename__ = "user_settings"

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    extra_vigilant: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
