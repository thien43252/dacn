"""groups, handoffs, people and approvals (feature 003)

Revision ID: 0006
Revises: 0005
Create Date: 2026-11-15 10:00:00
"""

import uuid
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

NOW = sa.text("CURRENT_TIMESTAMP")


def _timestamps() -> list[sa.Column]:
    return [sa.Column("created_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False)]


def upgrade() -> None:
    # --- existing tables -------------------------------------------------------------------------------------------
    with op.batch_alter_table("conversations") as batch:
        batch.add_column(sa.Column("direct_agent_slug", sa.String(48), nullable=True))
        batch.add_column(sa.Column("default_agent_slug", sa.String(48), nullable=True))
        batch.add_column(sa.Column("last_seq", sa.Integer(), server_default="0", nullable=False))
        batch.add_column(sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True))
        batch.alter_column("kind", server_default="direct")

    with op.batch_alter_table("chat_messages") as batch:
        batch.add_column(sa.Column("seq", sa.Integer(), server_default="0", nullable=False))
        batch.add_column(sa.Column("sender_user_id", sa.String(36), nullable=True))
        batch.add_column(sa.Column("handoff_id", sa.String(36), nullable=True))
        batch.add_column(sa.Column("reply_to_agent", sa.String(48), nullable=True))
        batch.add_column(sa.Column("person_request_id", sa.String(36), nullable=True))
        batch.add_column(sa.Column("approval_card_id", sa.String(36), nullable=True))
        batch.add_column(sa.Column("run_id", sa.String(36), nullable=True))
        batch.add_column(sa.Column("visible_to", sa.JSON(), nullable=True))
        batch.create_foreign_key(
            "fk_chat_messages_sender_user_id_users", "users", ["sender_user_id"], ["id"], ondelete="SET NULL"
        )
        batch.create_index("ix_chat_messages_sender_user_id", ["sender_user_id"])
        batch.create_index("ix_chat_messages_person_request_id", ["person_request_id"])
        batch.create_index("ix_chat_messages_approval_card_id", ["approval_card_id"])
        batch.create_index("ix_chat_messages_run_id", ["run_id"])

    with op.batch_alter_table("class_members") as batch:
        batch.add_column(sa.Column("subject", sa.String(16), nullable=True))
    with op.batch_alter_table("installations") as batch:
        batch.add_column(sa.Column("handoff_allow", sa.JSON(), nullable=True))
    with op.batch_alter_table("guard_events") as batch:
        batch.add_column(sa.Column("private_space", sa.Boolean(), server_default=sa.true(), nullable=False))

    # --- new tables ------------------------------------------------------------------------------------------------
    op.create_table(
        "conversation_members",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "conversation_id", sa.String(36), sa.ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=True),
        sa.Column("agent_slug", sa.String(48), nullable=True),
        sa.Column("is_admin", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("joined_seq", sa.Integer(), server_default="0", nullable=False),
        sa.Column("can_see_history", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("last_read_seq", sa.Integer(), server_default="0", nullable=False),
        sa.Column("left_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
        sa.UniqueConstraint("conversation_id", "user_id", name="uq_conversation_members_user"),
        sa.UniqueConstraint("conversation_id", "agent_slug", name="uq_conversation_members_agent"),
        sa.CheckConstraint("(user_id IS NULL) <> (agent_slug IS NULL)", name="ck_conversation_members_one_member_kind"),
    )
    op.create_index("ix_conversation_members_conversation_id", "conversation_members", ["conversation_id"])
    op.create_index("ix_conversation_members_user_id", "conversation_members", ["user_id"])

    op.create_table(
        "agent_runs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "conversation_id", sa.String(36), sa.ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("class_id", sa.String(36), sa.ForeignKey("classes.id", ondelete="CASCADE"), nullable=True),
        sa.Column("agent_slug", sa.String(48), nullable=False),
        sa.Column("agent_version_id", sa.String(36), nullable=True),
        sa.Column("handoff_id", sa.String(36), nullable=True),
        sa.Column("depth", sa.Integer(), nullable=False),
        sa.Column("chain", sa.JSON(), nullable=False),
        sa.Column("handoff_count", sa.Integer(), nullable=False),
        sa.Column("root_run_id", sa.String(36), nullable=True),
        sa.Column("trigger_message_id", sa.String(36), nullable=True),
        sa.Column("message_id", sa.String(36), nullable=True),
        sa.Column("transcript", sa.JSON(), nullable=False),
        sa.Column("pending", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("source", sa.String(16), nullable=False),
        sa.Column("user_text", sa.Text(), nullable=False),
        *_timestamps(),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
    )
    for column in ("conversation_id", "user_id", "handoff_id", "root_run_id", "status"):
        op.create_index(f"ix_agent_runs_{column}", "agent_runs", [column])

    op.create_table(
        "handoffs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("run_id", sa.String(36), sa.ForeignKey("agent_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("tool_call_id", sa.String(80), nullable=False),
        sa.Column(
            "conversation_id", sa.String(36), sa.ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("parent_handoff_id", sa.String(36), nullable=True),
        sa.Column("from_agent", sa.String(48), nullable=False),
        sa.Column("to_agent", sa.String(48), nullable=False),
        sa.Column("depth", sa.Integer(), nullable=False),
        sa.Column("task", sa.Text(), nullable=False),
        sa.Column("bounds", sa.Text(), nullable=False),
        sa.Column("good_answer", sa.Text(), nullable=False),
        sa.Column("attachments", sa.Text(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("refusal_reason", sa.String(200), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("lease_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("answer", sa.Text(), nullable=True),
        sa.Column("answer_visible", sa.Boolean(), nullable=True),
        sa.Column("late", sa.Boolean(), server_default=sa.false(), nullable=False),
        *_timestamps(),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("run_id", "tool_call_id", name="uq_handoffs_run_call"),
    )
    for column in ("run_id", "conversation_id", "status"):
        op.create_index(f"ix_handoffs_{column}", "handoffs", [column])

    op.create_table(
        "person_requests",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("run_id", sa.String(36), sa.ForeignKey("agent_runs.id", ondelete="CASCADE"), nullable=True),
        sa.Column("tool_call_id", sa.String(80), nullable=False),
        sa.Column(
            "conversation_id", sa.String(36), sa.ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("class_id", sa.String(36), sa.ForeignKey("classes.id", ondelete="CASCADE"), nullable=True),
        sa.Column("requester_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("agent_slug", sa.String(48), nullable=False),
        sa.Column("recipient_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("options", sa.JSON(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("private_to_recipient", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("answer", sa.Text(), nullable=True),
        sa.Column("answer_hidden", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("answered_by", sa.String(36), nullable=True),
        sa.Column("answered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
        sa.UniqueConstraint("run_id", "tool_call_id", name="uq_person_requests_run_call"),
    )
    for column in ("conversation_id", "requester_id", "recipient_id", "status"):
        op.create_index(f"ix_person_requests_{column}", "person_requests", [column])

    op.create_table(
        "approval_cards",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("run_id", sa.String(36), sa.ForeignKey("agent_runs.id", ondelete="CASCADE"), nullable=True),
        sa.Column("tool_call_id", sa.String(80), nullable=False),
        sa.Column(
            "conversation_id", sa.String(36), sa.ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("agent_slug", sa.String(48), nullable=False),
        sa.Column("tool", sa.String(64), nullable=False),
        sa.Column("arguments", sa.JSON(), nullable=False),
        sa.Column("action_kind", sa.String(16), nullable=False),
        sa.Column("target", sa.String(80), nullable=True),
        sa.Column("summary", sa.String(300), nullable=False),
        sa.Column("preview", sa.JSON(), nullable=False),
        sa.Column("choices", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("answer", sa.String(16), nullable=True),
        sa.Column("executed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        *_timestamps(),
        sa.UniqueConstraint("run_id", "tool_call_id", name="uq_approval_cards_run_call"),
    )
    for column in ("conversation_id", "user_id", "status"):
        op.create_index(f"ix_approval_cards_{column}", "approval_cards", [column])

    op.create_table(
        "approval_rules",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("scope", sa.String(16), nullable=False),
        sa.Column("scope_id", sa.String(36), nullable=True),
        sa.Column("action_kind", sa.String(16), nullable=False),
        sa.Column("agent_slug", sa.String(48), nullable=True),
        sa.Column("tool", sa.String(64), nullable=True),
        sa.Column("target", sa.String(80), nullable=True),
        sa.Column("effect", sa.String(8), nullable=False),
        sa.Column("source", sa.String(16), nullable=False),
        sa.Column("created_by", sa.String(36), nullable=True),
        *_timestamps(),
    )
    op.create_index("ix_approval_rules_scope", "approval_rules", ["scope"])
    op.create_index("ix_approval_rules_scope_id", "approval_rules", ["scope_id"])

    op.create_table(
        "approval_kind_modes",
        sa.Column("action_kind", sa.String(16), primary_key=True),
        sa.Column("role", sa.String(16), primary_key=True),
        sa.Column("mode", sa.String(16), nullable=False),
    )
    op.create_table(
        "user_settings",
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("extra_vigilant", sa.Boolean(), server_default=sa.false(), nullable=False),
    )

    # --- data: old chats become direct chats ------------------------------------------------------------------------
    bind = op.get_bind()
    bind.execute(sa.text("UPDATE conversations SET kind = 'direct' WHERE kind = 'chat'"))
    # Old chats were auto-routed; direct_agent_slug stays null so they keep that behaviour.
    conversations = bind.execute(sa.text("SELECT id, user_id FROM conversations")).fetchall()
    for conversation_id, user_id in conversations:
        bind.execute(
            sa.text(
                "INSERT INTO conversation_members (id, conversation_id, user_id, is_admin, joined_seq, "
                "can_see_history, last_read_seq) VALUES (:id, :c, :u, :t, 0, :t, 0)"
            ),
            {"id": str(uuid.uuid4()), "c": conversation_id, "u": user_id, "t": True},
        )
        rows = bind.execute(
            sa.text("SELECT id FROM chat_messages WHERE conversation_id = :c ORDER BY created_at, id"),
            {"c": conversation_id},
        ).fetchall()
        for seq, (message_id,) in enumerate(rows, start=1):
            bind.execute(sa.text("UPDATE chat_messages SET seq = :s WHERE id = :m"), {"s": seq, "m": message_id})
        bind.execute(
            sa.text("UPDATE conversations SET last_seq = :s WHERE id = :c"), {"s": len(rows), "c": conversation_id}
        )
    bind.execute(
        sa.text(
            "UPDATE chat_messages SET sender_user_id = (SELECT user_id FROM conversations WHERE "
            "conversations.id = chat_messages.conversation_id) WHERE role = 'user'"
        )
    )

    with op.batch_alter_table("chat_messages") as batch:
        batch.create_unique_constraint("uq_chat_messages_conversation_seq", ["conversation_id", "seq"])
        batch.create_unique_constraint("uq_chat_messages_handoff_id", ["handoff_id"])


def downgrade() -> None:
    with op.batch_alter_table("chat_messages") as batch:
        batch.drop_constraint("uq_chat_messages_handoff_id", type_="unique")
        batch.drop_constraint("uq_chat_messages_conversation_seq", type_="unique")
    for table in (
        "user_settings",
        "approval_kind_modes",
        "approval_rules",
        "approval_cards",
        "person_requests",
        "handoffs",
        "agent_runs",
        "conversation_members",
    ):
        op.drop_table(table)
    with op.batch_alter_table("guard_events") as batch:
        batch.drop_column("private_space")
    with op.batch_alter_table("installations") as batch:
        batch.drop_column("handoff_allow")
    with op.batch_alter_table("class_members") as batch:
        batch.drop_column("subject")
    with op.batch_alter_table("chat_messages") as batch:
        for index in ("run_id", "approval_card_id", "person_request_id", "sender_user_id"):
            batch.drop_index(f"ix_chat_messages_{index}")
        batch.drop_constraint("fk_chat_messages_sender_user_id_users", type_="foreignkey")
        for column in (
            "visible_to",
            "run_id",
            "approval_card_id",
            "person_request_id",
            "reply_to_agent",
            "handoff_id",
            "sender_user_id",
            "seq",
        ):
            batch.drop_column(column)
    op.execute("UPDATE conversations SET kind = 'chat' WHERE kind = 'direct'")
    with op.batch_alter_table("conversations") as batch:
        batch.alter_column("kind", server_default="chat")
        for column in ("archived_at", "last_seq", "default_agent_slug", "direct_agent_slug"):
            batch.drop_column(column)
