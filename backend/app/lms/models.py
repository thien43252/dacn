"""Feature 004 (LMS): lessons, content items, files, quizzes, assignments, AI suggestions, notifications, grade audit.

See specs/004-lms-lessons/data-model.md. Every table carries `class_id` so access checks never need a join.
"""

from datetime import date, datetime

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    false,
    func,
    true,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.auth.models import new_id
from app.db import Base, TimestampMixin

LESSON_STATUSES = ("draft", "published", "archived")
ITEM_KINDS = ("file", "video", "link", "text", "assignment", "quiz")
QUESTION_KINDS = ("single", "multi", "true_false", "short", "essay")
SCORING_POLICIES = ("best", "last", "average")
REVEAL_MODES = ("on_submit", "after_close", "never")
FILE_PURPOSES = ("content", "prompt", "submission")


def _class_fk() -> Mapped[str]:
    return mapped_column(ForeignKey("classes.id", ondelete="CASCADE"), index=True)


class Lesson(TimestampMixin, Base):
    __tablename__ = "lessons"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    class_id: Mapped[str] = _class_fk()
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    lesson_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    position: Mapped[int] = mapped_column(Integer, default=0)
    # draft -> published -> archived (archived -> draft restores)
    status: Mapped[str] = mapped_column(String(16), default="draft")
    # Null: visible as soon as it is published.
    publish_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)


class LmsFile(Base):
    __tablename__ = "lms_files"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    class_id: Mapped[str] = _class_fk()
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    # content | prompt | submission
    purpose: Mapped[str] = mapped_column(String(16))
    filename: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[str] = mapped_column(String(100))
    size_bytes: Mapped[int] = mapped_column(Integer)
    storage_path: Mapped[str] = mapped_column(String(500), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class LessonItem(Base):
    __tablename__ = "lesson_items"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    lesson_id: Mapped[str] = mapped_column(ForeignKey("lessons.id", ondelete="CASCADE"), index=True)
    class_id: Mapped[str] = _class_fk()
    # file | video | link | text | assignment | quiz
    kind: Mapped[str] = mapped_column(String(16))
    title: Mapped[str] = mapped_column(String(200))
    position: Mapped[int] = mapped_column(Integer, default=0)
    body: Mapped[str] = mapped_column(Text, default="")
    url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    embed_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    file_id: Mapped[str | None] = mapped_column(ForeignKey("lms_files.id", ondelete="SET NULL"), nullable=True)
    # Set while "cho agent đọc" is on: the knowledge-base copy of this file (research R3).
    document_id: Mapped[str | None] = mapped_column(ForeignKey("documents.id", ondelete="SET NULL"), nullable=True)
    visible: Mapped[bool] = mapped_column(Boolean, default=True, server_default=true())
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Quiz(Base):
    __tablename__ = "quizzes"

    item_id: Mapped[str] = mapped_column(ForeignKey("lesson_items.id", ondelete="CASCADE"), primary_key=True)
    class_id: Mapped[str] = _class_fk()
    open_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    close_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # 0 = unlimited
    max_attempts: Mapped[int] = mapped_column(Integer, default=1)
    scoring_policy: Mapped[str] = mapped_column(String(8), default="best")
    shuffle_questions: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    shuffle_options: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    show_score: Mapped[str] = mapped_column(String(12), default="on_submit")
    show_answers: Mapped[str] = mapped_column(String(12), default="after_close")
    # FR-028: every agent withholds answers to this quiz from a student mid-attempt.
    block_agents: Mapped[bool] = mapped_column(Boolean, default=True, server_default=true())
    ai_grading: Mapped[bool] = mapped_column(Boolean, default=True, server_default=true())
    weight: Mapped[float] = mapped_column(Float, default=1.0)
    counts_in_grade: Mapped[bool] = mapped_column(Boolean, default=True, server_default=true())


class QuizQuestion(Base):
    __tablename__ = "quiz_questions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    quiz_id: Mapped[str] = mapped_column(ForeignKey("quizzes.item_id", ondelete="CASCADE"), index=True)
    class_id: Mapped[str] = _class_fk()
    position: Mapped[int] = mapped_column(Integer, default=0)
    # single | multi | true_false | short | essay
    kind: Mapped[str] = mapped_column(String(12))
    prompt: Mapped[str] = mapped_column(Text)
    # [{id, text}] for single/multi; ids stay stable across edits and shuffling.
    options: Mapped[list] = mapped_column(JSON, default=list)
    # single: option_id; multi: [option_id]; true_false: bool; short: [accepted]; essay: null
    answer_key: Mapped[object | None] = mapped_column(JSON, nullable=True)
    multi_scoring: Mapped[str] = mapped_column(String(16), default="all_or_nothing")
    points: Mapped[float] = mapped_column(Float, default=1.0)
    explanation: Mapped[str] = mapped_column(Text, default="")
    # essay: {criteria: [{name, max_points, description}], model_answer}
    rubric: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # manual | ai
    source: Mapped[str] = mapped_column(String(8), default="manual")
    ai_suggestion_id: Mapped[str | None] = mapped_column(String(36), nullable=True)


class QuizAttempt(Base):
    __tablename__ = "quiz_attempts"
    __table_args__ = (UniqueConstraint("quiz_id", "student_id", "attempt_no", name="uq_quiz_attempts_no"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    quiz_id: Mapped[str] = mapped_column(ForeignKey("quizzes.item_id", ondelete="CASCADE"), index=True)
    class_id: Mapped[str] = _class_fk()
    student_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    attempt_no: Mapped[int] = mapped_column(Integer)
    # in_progress -> submitted (essays await grading) -> graded
    status: Mapped[str] = mapped_column(String(12), default="in_progress", index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    deadline_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # manual | timeout | closed
    submit_reason: Mapped[str | None] = mapped_column(String(8), nullable=True)
    # The paper as served: [{question_id, kind, prompt, options, points}], never answer keys.
    snapshot: Mapped[list] = mapped_column(JSON, default=list)
    answers: Mapped[dict] = mapped_column(JSON, default=dict)
    # {question_id: {points, graded_by: "auto" | user_id, feedback}}
    item_scores: Mapped[dict] = mapped_column(JSON, default=dict)
    score: Mapped[float | None] = mapped_column(Float, nullable=True)
    max_score: Mapped[float] = mapped_column(Float, default=0.0)


class Assignment(Base):
    __tablename__ = "assignments"

    item_id: Mapped[str] = mapped_column(ForeignKey("lesson_items.id", ondelete="CASCADE"), primary_key=True)
    class_id: Mapped[str] = _class_fk()
    prompt: Mapped[str] = mapped_column(Text, default="")
    prompt_file_ids: Mapped[list] = mapped_column(JSON, default=list)
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    max_points: Mapped[float] = mapped_column(Float, default=10.0)
    allow_late: Mapped[bool] = mapped_column(Boolean, default=True, server_default=true())
    late_penalty_per_day_pct: Mapped[float] = mapped_column(Float, default=0.0)
    late_penalty_max_pct: Mapped[float] = mapped_column(Float, default=0.0)
    rubric: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    ai_grading: Mapped[bool] = mapped_column(Boolean, default=True, server_default=true())
    weight: Mapped[float] = mapped_column(Float, default=1.0)
    counts_in_grade: Mapped[bool] = mapped_column(Boolean, default=True, server_default=true())


class AssignmentExtension(Base):
    __tablename__ = "assignment_extensions"
    __table_args__ = (UniqueConstraint("assignment_id", "student_id", name="uq_assignment_extensions"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    assignment_id: Mapped[str] = mapped_column(ForeignKey("assignments.item_id", ondelete="CASCADE"), index=True)
    student_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    granted_by: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Submission(Base):
    __tablename__ = "submissions"
    __table_args__ = (UniqueConstraint("assignment_id", "student_id", name="uq_submissions_student"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    assignment_id: Mapped[str] = mapped_column(ForeignKey("assignments.item_id", ondelete="CASCADE"), index=True)
    class_id: Mapped[str] = _class_fk()
    student_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    # submitted -> graded -> returned
    status: Mapped[str] = mapped_column(String(12), default="submitted")
    latest_version: Mapped[int] = mapped_column(Integer, default=0)
    is_late: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    days_late: Mapped[int] = mapped_column(Integer, default=0)
    raw_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    penalty: Mapped[float] = mapped_column(Float, default=0.0)
    penalty_waived: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    final_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    feedback: Mapped[str] = mapped_column(Text, default="")
    graded_by: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    graded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    returned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class SubmissionVersion(Base):
    __tablename__ = "submission_versions"
    __table_args__ = (UniqueConstraint("submission_id", "version_no", name="uq_submission_versions_no"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    submission_id: Mapped[str] = mapped_column(ForeignKey("submissions.id", ondelete="CASCADE"), index=True)
    version_no: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text, default="")
    file_ids: Mapped[list] = mapped_column(JSON, default=list)
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    is_late: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())


class AISuggestion(Base):
    __tablename__ = "ai_suggestions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    class_id: Mapped[str] = _class_fk()
    # questions | grading
    kind: Mapped[str] = mapped_column(String(16))
    # quiz | submission | attempt_question
    target_type: Mapped[str] = mapped_column(String(16))
    target_id: Mapped[str] = mapped_column(String(80), index=True)
    agent_id: Mapped[str | None] = mapped_column(ForeignKey("agents.id", ondelete="SET NULL"), nullable=True)
    agent_version_id: Mapped[str | None] = mapped_column(
        ForeignKey("agent_versions.id", ondelete="SET NULL"), nullable=True
    )
    request: Mapped[dict] = mapped_column(JSON, default=dict)
    # pending -> ready | failed | skipped_consent; ready -> approved | edited | discarded
    status: Mapped[str] = mapped_column(String(16), default="pending", index=True)
    payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    final: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error: Mapped[str | None] = mapped_column(String(300), nullable=True)
    requested_by: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    reviewed_by: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ContentView(Base):
    __tablename__ = "content_views"
    __table_args__ = (UniqueConstraint("item_id", "student_id", name="uq_content_views"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    item_id: Mapped[str] = mapped_column(ForeignKey("lesson_items.id", ondelete="CASCADE"), index=True)
    class_id: Mapped[str] = _class_fk()
    student_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    first_viewed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_viewed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    # lesson_published | assigned | due_soon | returned | to_grade | ai_ready
    kind: Mapped[str] = mapped_column(String(24))
    class_id: Mapped[str | None] = mapped_column(
        ForeignKey("classes.id", ondelete="CASCADE"), index=True, nullable=True
    )
    title: Mapped[str] = mapped_column(String(200))
    link: Mapped[str] = mapped_column(String(300), default="")
    dedupe_key: Mapped[str] = mapped_column(String(120), unique=True)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class GradeAudit(Base):
    __tablename__ = "grade_audit"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    class_id: Mapped[str] = _class_fk()
    actor_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    # grade | regrade | edit_score | waive_penalty | extend | return | delete_submission | ai_approve
    action: Mapped[str] = mapped_column(String(24))
    target_type: Mapped[str] = mapped_column(String(24))
    target_id: Mapped[str] = mapped_column(String(80), index=True)
    student_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True, nullable=True
    )
    before: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    after: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
