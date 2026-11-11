"""orchestration: turn runs and steps, class announcements and assignments, usage path

Revision ID: 0008
Revises: 0007
Create Date: 2026-11-10 10:00:00.000000

specs/002-multi-agent-orchestration/data-model.md.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

OPEN = sa.text("status IN ('running', 'awaiting_user')")


def upgrade() -> None:
    op.create_table(
        "turn_runs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("conversation_id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("class_id", sa.String(length=36), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("request_message_id", sa.String(length=36), nullable=False),
        sa.Column("reply_message_id", sa.String(length=36), nullable=True),
        sa.Column("request_text", sa.Text(), nullable=False),
        sa.Column("lead_agent", sa.String(length=48), nullable=True),
        sa.Column("goal", sa.Text(), nullable=False),
        sa.Column("plan", sa.JSON(), nullable=False),
        sa.Column("plan_version", sa.Integer(), nullable=False),
        sa.Column("pending", sa.JSON(), nullable=True),
        sa.Column("clarify_rounds", sa.Integer(), nullable=False),
        sa.Column("replans", sa.Integer(), nullable=False),
        sa.Column("assumptions", sa.JSON(), nullable=False),
        sa.Column("resume_answers", sa.JSON(), nullable=False),
        sa.Column("confirmations", sa.JSON(), nullable=False),
        sa.Column("interactive", sa.Boolean(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["class_id"], ["classes.id"], name=op.f("fk_turn_runs_class_id_classes"), ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["conversation_id"],
            ["conversations.id"],
            name=op.f("fk_turn_runs_conversation_id_conversations"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name=op.f("fk_turn_runs_user_id_users"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_turn_runs")),
    )
    op.create_index(op.f("ix_turn_runs_conversation_id"), "turn_runs", ["conversation_id"], unique=False)
    op.create_index(
        "uq_turn_runs_open_conversation",
        "turn_runs",
        ["conversation_id"],
        unique=True,
        postgresql_where=OPEN,
        sqlite_where=OPEN,
    )

    op.create_table(
        "run_steps",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("run_id", sa.String(length=36), nullable=False),
        sa.Column("key", sa.String(length=16), nullable=False),
        sa.Column("agent_slug", sa.String(length=48), nullable=False),
        sa.Column("agent_version_id", sa.String(length=36), nullable=True),
        sa.Column("title", sa.String(length=80), nullable=False),
        sa.Column("task", sa.Text(), nullable=False),
        sa.Column("depends_on", sa.JSON(), nullable=False),
        sa.Column("origin", sa.String(length=16), nullable=False),
        sa.Column("requested_by", sa.String(length=16), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("note", sa.Text(), nullable=False),
        sa.Column("note_review", sa.String(length=12), nullable=False),
        sa.Column("signals", sa.JSON(), nullable=False),
        sa.Column("citations", sa.JSON(), nullable=False),
        sa.Column("tools", sa.JSON(), nullable=False),
        sa.Column("error", sa.String(length=300), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["run_id"], ["turn_runs.id"], name=op.f("fk_run_steps_run_id_turn_runs"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_run_steps")),
        sa.UniqueConstraint("run_id", "key", name="uq_run_steps_run_id_key"),
    )
    op.create_index(op.f("ix_run_steps_run_id"), "run_steps", ["run_id"], unique=False)

    op.create_table(
        "class_announcements",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("class_id", sa.String(length=36), nullable=False),
        sa.Column("author_id", sa.String(length=36), nullable=True),
        sa.Column("title", sa.String(length=120), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("audience", sa.String(length=16), nullable=False),
        sa.Column("source", sa.String(length=16), nullable=False),
        sa.Column("run_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["author_id"], ["users.id"], name=op.f("fk_class_announcements_author_id_users"), ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["class_id"], ["classes.id"], name=op.f("fk_class_announcements_class_id_classes"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_class_announcements")),
    )
    op.create_index(op.f("ix_class_announcements_class_id"), "class_announcements", ["class_id"], unique=False)
    op.create_index(op.f("ix_class_announcements_created_at"), "class_announcements", ["created_at"], unique=False)

    op.create_table(
        "assignments",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("class_id", sa.String(length=36), nullable=False),
        sa.Column("author_id", sa.String(length=36), nullable=True),
        sa.Column("title", sa.String(length=120), nullable=False),
        sa.Column("instructions", sa.Text(), nullable=False),
        sa.Column("questions", sa.JSON(), nullable=False),
        sa.Column("answer_key", sa.JSON(), nullable=True),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("source", sa.String(length=16), nullable=False),
        sa.Column("run_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["author_id"], ["users.id"], name=op.f("fk_assignments_author_id_users"), ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["class_id"], ["classes.id"], name=op.f("fk_assignments_class_id_classes"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_assignments")),
    )
    op.create_index(op.f("ix_assignments_class_id"), "assignments", ["class_id"], unique=False)
    op.create_index(op.f("ix_assignments_created_at"), "assignments", ["created_at"], unique=False)

    op.add_column("usage_ledger", sa.Column("path", sa.String(length=8), nullable=True))


def downgrade() -> None:
    op.drop_column("usage_ledger", "path")
    op.drop_index(op.f("ix_assignments_created_at"), table_name="assignments")
    op.drop_index(op.f("ix_assignments_class_id"), table_name="assignments")
    op.drop_table("assignments")
    op.drop_index(op.f("ix_class_announcements_created_at"), table_name="class_announcements")
    op.drop_index(op.f("ix_class_announcements_class_id"), table_name="class_announcements")
    op.drop_table("class_announcements")
    op.drop_index(op.f("ix_run_steps_run_id"), table_name="run_steps")
    op.drop_table("run_steps")
    op.drop_index("uq_turn_runs_open_conversation", table_name="turn_runs")
    op.drop_index(op.f("ix_turn_runs_conversation_id"), table_name="turn_runs")
    op.drop_table("turn_runs")
