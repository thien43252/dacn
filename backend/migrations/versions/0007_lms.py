"""LMS lessons, files, assessments and notifications (feature 004).

Revision ID: 0007
Revises: 0006
Create Date: 2026-11-16 10:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "lessons",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("class_id", sa.String(length=36), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("lesson_date", sa.Date(), nullable=True),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("publish_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.String(length=36), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["class_id"], ["classes.id"], name=op.f("fk_lessons_class_id_classes"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["created_by"], ["users.id"], name=op.f("fk_lessons_created_by_users"), ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_lessons")),
    )
    op.create_index(op.f("ix_lessons_class_id"), "lessons", ["class_id"], unique=False)
    op.create_table(
        "lms_files",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("class_id", sa.String(length=36), nullable=False),
        sa.Column("owner_id", sa.String(length=36), nullable=False),
        sa.Column("purpose", sa.String(length=16), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("content_type", sa.String(length=100), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("storage_path", sa.String(length=500), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["class_id"], ["classes.id"], name=op.f("fk_lms_files_class_id_classes"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["owner_id"], ["users.id"], name=op.f("fk_lms_files_owner_id_users"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_lms_files")),
    )
    op.create_index(op.f("ix_lms_files_class_id"), "lms_files", ["class_id"], unique=False)
    op.create_index(op.f("ix_lms_files_owner_id"), "lms_files", ["owner_id"], unique=False)
    op.create_table(
        "lesson_items",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("lesson_id", sa.String(length=36), nullable=False),
        sa.Column("class_id", sa.String(length=36), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("url", sa.String(length=1000), nullable=True),
        sa.Column("embed_url", sa.String(length=1000), nullable=True),
        sa.Column("file_id", sa.String(length=36), nullable=True),
        sa.Column("document_id", sa.String(length=36), nullable=True),
        sa.Column("visible", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["class_id"], ["classes.id"], name=op.f("fk_lesson_items_class_id_classes"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["document_id"], ["documents.id"], name=op.f("fk_lesson_items_document_id_documents"), ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["file_id"], ["lms_files.id"], name=op.f("fk_lesson_items_file_id_lms_files"), ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["lesson_id"], ["lessons.id"], name=op.f("fk_lesson_items_lesson_id_lessons"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_lesson_items")),
    )
    op.create_index(op.f("ix_lesson_items_class_id"), "lesson_items", ["class_id"], unique=False)
    op.create_index(op.f("ix_lesson_items_lesson_id"), "lesson_items", ["lesson_id"], unique=False)
    op.create_table(
        "quizzes",
        sa.Column("item_id", sa.String(length=36), nullable=False),
        sa.Column("class_id", sa.String(length=36), nullable=False),
        sa.Column("open_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("close_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_minutes", sa.Integer(), nullable=True),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column("scoring_policy", sa.String(length=8), nullable=False),
        sa.Column("shuffle_questions", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("shuffle_options", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("show_score", sa.String(length=12), nullable=False),
        sa.Column("show_answers", sa.String(length=12), nullable=False),
        sa.Column("block_agents", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("ai_grading", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("weight", sa.Float(), nullable=False),
        sa.Column("counts_in_grade", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.ForeignKeyConstraint(
            ["class_id"], ["classes.id"], name=op.f("fk_quizzes_class_id_classes"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["item_id"], ["lesson_items.id"], name=op.f("fk_quizzes_item_id_lesson_items"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("item_id", name=op.f("pk_quizzes")),
    )
    op.create_index(op.f("ix_quizzes_class_id"), "quizzes", ["class_id"], unique=False)
    op.create_table(
        "quiz_questions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("quiz_id", sa.String(length=36), nullable=False),
        sa.Column("class_id", sa.String(length=36), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=12), nullable=False),
        sa.Column("prompt", sa.Text(), nullable=False),
        sa.Column("options", sa.JSON(), nullable=False),
        sa.Column("answer_key", sa.JSON(), nullable=True),
        sa.Column("multi_scoring", sa.String(length=16), nullable=False),
        sa.Column("points", sa.Float(), nullable=False),
        sa.Column("explanation", sa.Text(), nullable=False),
        sa.Column("rubric", sa.JSON(), nullable=True),
        sa.Column("source", sa.String(length=8), nullable=False),
        sa.Column("ai_suggestion_id", sa.String(length=36), nullable=True),
        sa.ForeignKeyConstraint(
            ["class_id"], ["classes.id"], name=op.f("fk_quiz_questions_class_id_classes"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["quiz_id"], ["quizzes.item_id"], name=op.f("fk_quiz_questions_quiz_id_quizzes"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_quiz_questions")),
    )
    op.create_index(op.f("ix_quiz_questions_class_id"), "quiz_questions", ["class_id"], unique=False)
    op.create_index(op.f("ix_quiz_questions_quiz_id"), "quiz_questions", ["quiz_id"], unique=False)
    op.create_table(
        "quiz_attempts",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("quiz_id", sa.String(length=36), nullable=False),
        sa.Column("class_id", sa.String(length=36), nullable=False),
        sa.Column("student_id", sa.String(length=36), nullable=False),
        sa.Column("attempt_no", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=12), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deadline_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("submit_reason", sa.String(length=8), nullable=True),
        sa.Column("snapshot", sa.JSON(), nullable=False),
        sa.Column("answers", sa.JSON(), nullable=False),
        sa.Column("item_scores", sa.JSON(), nullable=False),
        sa.Column("score", sa.Float(), nullable=True),
        sa.Column("max_score", sa.Float(), nullable=False),
        sa.ForeignKeyConstraint(
            ["class_id"], ["classes.id"], name=op.f("fk_quiz_attempts_class_id_classes"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["quiz_id"], ["quizzes.item_id"], name=op.f("fk_quiz_attempts_quiz_id_quizzes"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["student_id"], ["users.id"], name=op.f("fk_quiz_attempts_student_id_users"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_quiz_attempts")),
        sa.UniqueConstraint("quiz_id", "student_id", "attempt_no", name="uq_quiz_attempts_no"),
    )
    op.create_index(op.f("ix_quiz_attempts_class_id"), "quiz_attempts", ["class_id"], unique=False)
    op.create_index(op.f("ix_quiz_attempts_quiz_id"), "quiz_attempts", ["quiz_id"], unique=False)
    op.create_index(op.f("ix_quiz_attempts_status"), "quiz_attempts", ["status"], unique=False)
    op.create_index(op.f("ix_quiz_attempts_student_id"), "quiz_attempts", ["student_id"], unique=False)
    op.create_table(
        "assignments",
        sa.Column("item_id", sa.String(length=36), nullable=False),
        sa.Column("class_id", sa.String(length=36), nullable=False),
        sa.Column("prompt", sa.Text(), nullable=False),
        sa.Column("prompt_file_ids", sa.JSON(), nullable=False),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("max_points", sa.Float(), nullable=False),
        sa.Column("allow_late", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("late_penalty_per_day_pct", sa.Float(), nullable=False),
        sa.Column("late_penalty_max_pct", sa.Float(), nullable=False),
        sa.Column("rubric", sa.JSON(), nullable=True),
        sa.Column("ai_grading", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("weight", sa.Float(), nullable=False),
        sa.Column("counts_in_grade", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.ForeignKeyConstraint(
            ["class_id"], ["classes.id"], name=op.f("fk_assignments_class_id_classes"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["item_id"], ["lesson_items.id"], name=op.f("fk_assignments_item_id_lesson_items"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("item_id", name=op.f("pk_assignments")),
    )
    op.create_index(op.f("ix_assignments_class_id"), "assignments", ["class_id"], unique=False)
    op.create_table(
        "assignment_extensions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("assignment_id", sa.String(length=36), nullable=False),
        sa.Column("student_id", sa.String(length=36), nullable=False),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("granted_by", sa.String(length=36), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["assignment_id"],
            ["assignments.item_id"],
            name=op.f("fk_assignment_extensions_assignment_id_assignments"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["granted_by"], ["users.id"], name=op.f("fk_assignment_extensions_granted_by_users"), ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["student_id"], ["users.id"], name=op.f("fk_assignment_extensions_student_id_users"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_assignment_extensions")),
        sa.UniqueConstraint("assignment_id", "student_id", name="uq_assignment_extensions"),
    )
    op.create_index(
        op.f("ix_assignment_extensions_assignment_id"), "assignment_extensions", ["assignment_id"], unique=False
    )
    op.create_index(op.f("ix_assignment_extensions_student_id"), "assignment_extensions", ["student_id"], unique=False)
    op.create_table(
        "submissions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("assignment_id", sa.String(length=36), nullable=False),
        sa.Column("class_id", sa.String(length=36), nullable=False),
        sa.Column("student_id", sa.String(length=36), nullable=False),
        sa.Column("status", sa.String(length=12), nullable=False),
        sa.Column("latest_version", sa.Integer(), nullable=False),
        sa.Column("is_late", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("days_late", sa.Integer(), nullable=False),
        sa.Column("raw_score", sa.Float(), nullable=True),
        sa.Column("penalty", sa.Float(), nullable=False),
        sa.Column("penalty_waived", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("final_score", sa.Float(), nullable=True),
        sa.Column("feedback", sa.Text(), nullable=False),
        sa.Column("graded_by", sa.String(length=36), nullable=True),
        sa.Column("graded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("returned_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["assignment_id"],
            ["assignments.item_id"],
            name=op.f("fk_submissions_assignment_id_assignments"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["class_id"], ["classes.id"], name=op.f("fk_submissions_class_id_classes"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["graded_by"], ["users.id"], name=op.f("fk_submissions_graded_by_users"), ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["student_id"], ["users.id"], name=op.f("fk_submissions_student_id_users"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_submissions")),
        sa.UniqueConstraint("assignment_id", "student_id", name="uq_submissions_student"),
    )
    op.create_index(op.f("ix_submissions_assignment_id"), "submissions", ["assignment_id"], unique=False)
    op.create_index(op.f("ix_submissions_class_id"), "submissions", ["class_id"], unique=False)
    op.create_index(op.f("ix_submissions_student_id"), "submissions", ["student_id"], unique=False)
    op.create_table(
        "submission_versions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("submission_id", sa.String(length=36), nullable=False),
        sa.Column("version_no", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("file_ids", sa.JSON(), nullable=False),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("is_late", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.ForeignKeyConstraint(
            ["submission_id"],
            ["submissions.id"],
            name=op.f("fk_submission_versions_submission_id_submissions"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_submission_versions")),
        sa.UniqueConstraint("submission_id", "version_no", name="uq_submission_versions_no"),
    )
    op.create_index(
        op.f("ix_submission_versions_submission_id"), "submission_versions", ["submission_id"], unique=False
    )
    op.create_table(
        "ai_suggestions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("class_id", sa.String(length=36), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("target_type", sa.String(length=16), nullable=False),
        sa.Column("target_id", sa.String(length=80), nullable=False),
        sa.Column("agent_id", sa.String(length=36), nullable=True),
        sa.Column("agent_version_id", sa.String(length=36), nullable=True),
        sa.Column("request", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=True),
        sa.Column("final", sa.JSON(), nullable=True),
        sa.Column("error", sa.String(length=300), nullable=True),
        sa.Column("requested_by", sa.String(length=36), nullable=True),
        sa.Column("reviewed_by", sa.String(length=36), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False
        ),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["agent_id"], ["agents.id"], name=op.f("fk_ai_suggestions_agent_id_agents"), ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["agent_version_id"],
            ["agent_versions.id"],
            name=op.f("fk_ai_suggestions_agent_version_id_agent_versions"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["class_id"], ["classes.id"], name=op.f("fk_ai_suggestions_class_id_classes"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["requested_by"], ["users.id"], name=op.f("fk_ai_suggestions_requested_by_users"), ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["reviewed_by"], ["users.id"], name=op.f("fk_ai_suggestions_reviewed_by_users"), ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ai_suggestions")),
    )
    op.create_index(op.f("ix_ai_suggestions_class_id"), "ai_suggestions", ["class_id"], unique=False)
    op.create_index(op.f("ix_ai_suggestions_status"), "ai_suggestions", ["status"], unique=False)
    op.create_index(op.f("ix_ai_suggestions_target_id"), "ai_suggestions", ["target_id"], unique=False)
    op.create_table(
        "content_views",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("item_id", sa.String(length=36), nullable=False),
        sa.Column("class_id", sa.String(length=36), nullable=False),
        sa.Column("student_id", sa.String(length=36), nullable=False),
        sa.Column("first_viewed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_viewed_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["class_id"], ["classes.id"], name=op.f("fk_content_views_class_id_classes"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["item_id"], ["lesson_items.id"], name=op.f("fk_content_views_item_id_lesson_items"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["student_id"], ["users.id"], name=op.f("fk_content_views_student_id_users"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_content_views")),
        sa.UniqueConstraint("item_id", "student_id", name="uq_content_views"),
    )
    op.create_index(op.f("ix_content_views_class_id"), "content_views", ["class_id"], unique=False)
    op.create_index(op.f("ix_content_views_item_id"), "content_views", ["item_id"], unique=False)
    op.create_index(op.f("ix_content_views_student_id"), "content_views", ["student_id"], unique=False)
    op.create_table(
        "notifications",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("kind", sa.String(length=24), nullable=False),
        sa.Column("class_id", sa.String(length=36), nullable=True),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("link", sa.String(length=300), nullable=False),
        sa.Column("dedupe_key", sa.String(length=120), nullable=False),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["class_id"], ["classes.id"], name=op.f("fk_notifications_class_id_classes"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_notifications_user_id_users"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_notifications")),
        sa.UniqueConstraint("dedupe_key", name=op.f("uq_notifications_dedupe_key")),
    )
    op.create_index(op.f("ix_notifications_class_id"), "notifications", ["class_id"], unique=False)
    op.create_index(op.f("ix_notifications_user_id"), "notifications", ["user_id"], unique=False)
    op.create_table(
        "grade_audit",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("class_id", sa.String(length=36), nullable=False),
        sa.Column("actor_id", sa.String(length=36), nullable=True),
        sa.Column("action", sa.String(length=24), nullable=False),
        sa.Column("target_type", sa.String(length=24), nullable=False),
        sa.Column("target_id", sa.String(length=80), nullable=False),
        sa.Column("student_id", sa.String(length=36), nullable=True),
        sa.Column("before", sa.JSON(), nullable=True),
        sa.Column("after", sa.JSON(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["actor_id"], ["users.id"], name=op.f("fk_grade_audit_actor_id_users"), ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["class_id"], ["classes.id"], name=op.f("fk_grade_audit_class_id_classes"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["student_id"], ["users.id"], name=op.f("fk_grade_audit_student_id_users"), ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_grade_audit")),
    )
    op.create_index(op.f("ix_grade_audit_class_id"), "grade_audit", ["class_id"], unique=False)
    op.create_index(op.f("ix_grade_audit_student_id"), "grade_audit", ["student_id"], unique=False)
    op.create_index(op.f("ix_grade_audit_target_id"), "grade_audit", ["target_id"], unique=False)


def downgrade() -> None:
    op.drop_table("grade_audit")
    op.drop_table("notifications")
    op.drop_table("content_views")
    op.drop_table("ai_suggestions")
    op.drop_table("submission_versions")
    op.drop_table("submissions")
    op.drop_table("assignment_extensions")
    op.drop_table("assignments")
    op.drop_table("quiz_attempts")
    op.drop_table("quiz_questions")
    op.drop_table("quizzes")
    op.drop_table("lesson_items")
    op.drop_table("lms_files")
    op.drop_table("lessons")
