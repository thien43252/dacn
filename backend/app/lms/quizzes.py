"""Quiz authoring, immutable attempt papers and permission-aware results (feature 004)."""

import random
from copy import deepcopy
from datetime import datetime, timedelta
from typing import Literal
from uuid import uuid4

from fastapi import APIRouter, HTTPException
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app import lms
from app.auth.deps import CurrentUser, DbSession
from app.auth.models import User, new_id
from app.classes import service as classes
from app.classes.models import ClassMember, ClassRoom
from app.lms import access, grading, jobs, lessons
from app.lms.models import GradeAudit, Lesson, LessonItem, Quiz, QuizAttempt, QuizQuestion
from app.lms.notify import notify
from app.lms.schemas import clean

router = APIRouter(tags=["lms"])
RevealMode = Literal["on_submit", "after_close", "never"]
QuestionKind = Literal["single", "multi", "true_false", "short", "essay"]


class InputModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class QuizConfig(InputModel):
    open_at: datetime | None = None
    close_at: datetime | None = None
    duration_minutes: int | None = Field(default=None, gt=0)
    max_attempts: int = Field(default=1, ge=0)
    scoring_policy: Literal["best", "last", "average"] = "best"
    shuffle_questions: bool = False
    shuffle_options: bool = False
    show_score: RevealMode = "on_submit"
    show_answers: RevealMode = "after_close"
    block_agents: bool = True
    ai_grading: bool = True
    weight: float = Field(default=1, ge=0)
    counts_in_grade: bool = True

    @model_validator(mode="after")
    def valid_window(self):
        if self.open_at and self.close_at and lms.aware(self.close_at) <= lms.aware(self.open_at):
            raise ValueError("Thời điểm đóng phải sau thời điểm mở.")
        return self


class OptionIn(InputModel):
    id: str | None = None
    text: str = Field(min_length=1)


class OptionOut(BaseModel):
    id: str
    text: str


class RubricCriterion(InputModel):
    name: str = Field(min_length=1)
    max_points: float = Field(gt=0)
    description: str = ""


class Rubric(InputModel):
    criteria: list[RubricCriterion] = Field(default_factory=list)
    model_answer: str = ""


class QuestionIn(InputModel):
    kind: QuestionKind
    prompt: str = Field(min_length=1)
    options: list[OptionIn] = Field(default_factory=list)
    answer_key: object = None
    points: float = Field(default=1, gt=0)
    multi_scoring: Literal["all_or_nothing", "partial"] = "all_or_nothing"
    explanation: str = ""
    rubric: Rubric | None = None

    @model_validator(mode="after")
    def valid_answer(self):
        key = self.answer_key
        ids = [o.id for o in self.options if o.id is not None]
        if len(ids) != len(set(ids)):
            raise ValueError("Mã lựa chọn không được trùng nhau.")
        if self.kind in {"single", "multi"}:
            if len(self.options) < 2:
                raise ValueError("Cần ít nhất hai lựa chọn.")
            if self.kind == "single" and (not isinstance(key, str) or key not in ids):
                raise ValueError("Đáp án phải là mã một lựa chọn.")
            if self.kind == "multi" and (
                not isinstance(key, list) or not key or any(not isinstance(k, str) or k not in ids for k in key)
            ):
                raise ValueError("Đáp án phải gồm ít nhất một mã lựa chọn hợp lệ.")
        elif self.options:
            raise ValueError("Loại câu hỏi này không có lựa chọn.")
        if self.kind == "true_false" and not isinstance(key, bool):
            raise ValueError("Đáp án phải là đúng hoặc sai.")
        if self.kind == "short" and (
            not isinstance(key, list) or not key or any(not isinstance(k, str) or not k.strip() for k in key)
        ):
            raise ValueError("Cần ít nhất một đáp án ngắn không rỗng.")
        if self.kind == "essay" and key is not None:
            raise ValueError("Câu tự luận không có đáp án tự động.")
        if self.kind != "essay" and self.rubric is not None:
            raise ValueError("Chỉ câu tự luận mới có thang chấm.")
        return self


class QuestionPatch(InputModel):
    kind: QuestionKind | None = None
    prompt: str | None = None
    options: list[OptionIn] | None = None
    answer_key: object = None
    points: float | None = None
    multi_scoring: Literal["all_or_nothing", "partial"] | None = None
    explanation: str | None = None
    rubric: Rubric | None = None


class QuestionTeacherOut(QuestionIn):
    id: str
    position: int
    source: str
    affects_submitted: int = 0


class StudentQuestion(BaseModel):
    """A served question cannot contain an answer key, explanation or rubric."""

    question_id: str
    kind: QuestionKind
    prompt: str
    options: list[OptionOut]
    points: float


class RevealedQuestion(StudentQuestion):
    correct: str | bool | list[str] | None
    explanation: str


class AttemptView(BaseModel):
    id: str
    quiz_id: str
    student_id: str
    attempt_no: int
    status: str
    started_at: datetime
    deadline_at: datetime | None
    submitted_at: datetime | None
    submit_reason: str | None
    server_now: datetime
    questions: list[StudentQuestion]
    answers: dict[str, str | bool | list[str] | None]
    max_score: float


class ItemScore(BaseModel):
    points: float
    graded_by: str
    feedback: str = ""


class AttemptResult(AttemptView):
    questions: list[RevealedQuestion] | list[StudentQuestion]
    score: float | None = None
    item_scores: dict[str, ItemScore] | None = None


class QuizStudentView(QuizConfig):
    item_id: str
    title: str
    question_count: int
    max_points: float
    state: Literal["upcoming", "open", "closed"]
    attempts: list[AttemptView]


class QuizTeacherOut(QuizConfig):
    item_id: str
    title: str
    questions: list[QuestionTeacherOut]


class AnswerIn(InputModel):
    question_id: str
    value: object


class ScoreIn(InputModel):
    points: float = Field(ge=0)
    feedback: str = ""


class OrderIn(InputModel):
    ids: list[str]


class CopyIn(InputModel):
    target_lesson_id: str


def _response(model: BaseModel) -> JSONResponse:
    return JSONResponse(jsonable_encoder(model, exclude_unset=True))


def _config(quiz: Quiz) -> dict:
    return {name: getattr(quiz, name) for name in QuizConfig.model_fields}


def _question_data(question: QuizQuestion) -> dict:
    return {name: getattr(question, name) for name in QuestionIn.model_fields}


def _teacher_question(question: QuizQuestion, affects_submitted: int = 0) -> QuestionTeacherOut:
    return QuestionTeacherOut(
        **_question_data(question),
        id=question.id,
        position=question.position,
        source=question.source,
        affects_submitted=affects_submitted,
    )


async def _questions(db: AsyncSession, quiz_id: str) -> list[QuizQuestion]:
    return list(
        await db.scalars(
            select(QuizQuestion).where(QuizQuestion.quiz_id == quiz_id).order_by(QuizQuestion.position, QuizQuestion.id)
        )
    )


async def quiz_ready(db: AsyncSession, quiz_id: str) -> bool:
    """Publishing requires at least one question."""
    return bool(await db.scalar(select(func.count()).where(QuizQuestion.quiz_id == quiz_id)))


async def _quiz(db: AsyncSession, cid: str, qid: str, *, lock: bool = False) -> tuple[Quiz, LessonItem]:
    query = select(Quiz).where(Quiz.item_id == qid, Quiz.class_id == cid)
    if lock:
        query = query.with_for_update()
    quiz = await db.scalar(query)
    item = await db.get(LessonItem, qid)
    if quiz is None or item is None or item.class_id != cid:
        raise classes.not_found()
    return quiz, item


async def _question(db: AsyncSession, cid: str, question_id: str) -> QuizQuestion:
    question = await db.get(QuizQuestion, question_id)
    if question is None or question.class_id != cid:
        raise classes.not_found()
    return question


async def _teacher_quiz(db: AsyncSession, quiz: Quiz, item: LessonItem) -> QuizTeacherOut:
    return QuizTeacherOut(
        **_config(quiz),
        item_id=quiz.item_id,
        title=item.title,
        questions=[_teacher_question(q) for q in await _questions(db, quiz.item_id)],
    )


def _prepare_question(body: QuestionIn, existing: QuizQuestion | None = None) -> dict:
    data = body.model_dump()
    data["prompt"] = clean("Câu hỏi", body.prompt)
    data["explanation"] = clean("Lời giải", body.explanation)
    if not data["prompt"].strip():
        raise HTTPException(422, "Câu hỏi không được để trống.")
    existing_ids = {o["id"] for o in existing.options} if existing else set()
    mapping = {}
    for option in data["options"]:
        old_id = option["id"]
        option["id"] = old_id if old_id in existing_ids else uuid4().hex[:12]
        if old_id is not None:
            mapping[old_id] = option["id"]
        option["text"] = clean("Lựa chọn", option["text"])
        if not option["text"].strip():
            raise HTTPException(422, "Lựa chọn không được để trống.")
    if body.kind == "single":
        data["answer_key"] = mapping[body.answer_key]
    elif body.kind == "multi":
        data["answer_key"] = list(dict.fromkeys(mapping[k] for k in body.answer_key))
    elif body.kind == "short":
        data["answer_key"] = [clean("Đáp án", value) for value in body.answer_key]
        if any(not value.strip() for value in data["answer_key"]):
            raise HTTPException(422, "Đáp án không được để trống.")
    if data["rubric"]:
        data["rubric"]["model_answer"] = clean("Đáp án mẫu", data["rubric"]["model_answer"])
        for criterion in data["rubric"]["criteria"]:
            criterion["name"] = clean("Tiêu chí", criterion["name"])
            criterion["description"] = clean("Mô tả tiêu chí", criterion["description"])
    return data


def _paper(questions: list[QuizQuestion], quiz: Quiz, attempt_id: str) -> list[dict]:
    rng = random.Random(attempt_id)
    paper = [
        StudentQuestion(
            question_id=q.id,
            kind=q.kind,
            prompt=q.prompt,
            options=q.options,
            points=q.points,
        ).model_dump()
        for q in questions
    ]
    if quiz.shuffle_questions:
        rng.shuffle(paper)
    if quiz.shuffle_options:
        for question in paper:
            rng.shuffle(question["options"])
    return paper


def _attempt_view(attempt: QuizAttempt) -> AttemptView:
    return AttemptView(
        id=attempt.id,
        quiz_id=attempt.quiz_id,
        student_id=attempt.student_id,
        attempt_no=attempt.attempt_no,
        status=attempt.status,
        started_at=lms.aware(attempt.started_at),
        deadline_at=lms.aware(attempt.deadline_at),
        submitted_at=lms.aware(attempt.submitted_at),
        submit_reason=attempt.submit_reason,
        server_now=lms.now(),
        questions=[StudentQuestion.model_validate(q) for q in attempt.snapshot],
        answers=attempt.answers,
        max_score=attempt.max_score,
    )


def _revealed(mode: str, quiz: Quiz) -> bool:
    close_at = lms.aware(quiz.close_at)
    return mode == "on_submit" or (mode == "after_close" and (close_at is None or lms.now() >= close_at))


async def _attempt_result(db: AsyncSession, attempt: QuizAttempt, quiz: Quiz, role: str) -> AttemptView:
    view = _attempt_view(attempt)
    if attempt.status == "in_progress":
        return view
    data = view.model_dump()
    if role == "teacher" or _revealed(quiz.show_score, quiz):
        data.update(score=attempt.score, item_scores=attempt.item_scores)
    if role == "teacher" or _revealed(quiz.show_answers, quiz):
        current = {q.id: q for q in await _questions(db, quiz.item_id)}
        data["questions"] = [
            RevealedQuestion(
                **q.model_dump(),
                correct=current[q.question_id].answer_key if q.question_id in current else None,
                explanation=current[q.question_id].explanation if q.question_id in current else "",
            )
            for q in view.questions
        ]
    return AttemptResult(**data)


def _update_total(attempt: QuizAttempt) -> None:
    attempt.score = grading.attempt_total(attempt.item_scores, (q["question_id"] for q in attempt.snapshot))
    attempt.status = "submitted" if attempt.score is None else "graded"


def _grade_served(served: dict, question: QuizQuestion | None, value: object) -> float | None:
    if served["kind"] == "essay":
        return None
    # A deleted question or a key for a different question kind cannot grade the original paper.
    if question is None or question.kind != served["kind"]:
        return 0.0
    return grading.grade_question(served["kind"], question.answer_key, value, served["points"], question.multi_scoring)


async def finalize(db: AsyncSession, attempt: QuizAttempt, reason: str) -> None:
    """Finalize using the served kind/points and current keys; the caller owns the transaction."""
    if attempt.status != "in_progress":
        return
    questions = {q.id: q for q in await _questions(db, attempt.quiz_id)}
    scores = {}
    for served in attempt.snapshot:
        qid = served["question_id"]
        question = questions.get(qid)
        points = _grade_served(served, question, attempt.answers.get(qid))
        if points is not None:
            scores[qid] = {"points": points, "graded_by": "auto"}
    attempt.item_scores = scores
    attempt.submitted_at = lms.now()
    attempt.submit_reason = reason
    _update_total(attempt)
    if attempt.status == "submitted":
        await _notify_to_grade(db, attempt)


async def _notify_to_grade(db: AsyncSession, attempt: QuizAttempt) -> None:
    """FR-025: teachers hear about a quiz attempt whose essays wait for grading, once per quiz and day."""
    quiz = await db.get(Quiz, attempt.quiz_id)
    room = await db.get(ClassRoom, quiz.class_id) if quiz else None
    if room is None:
        return
    teachers = await db.scalars(
        select(ClassMember.user_id).where(ClassMember.class_id == room.id, ClassMember.role == "teacher")
    )
    await notify(
        db,
        list(dict.fromkeys([room.owner_id, *teachers])),
        "to_grade",
        "Có bài kiểm tra cần chấm tự luận.",
        f"/teacher/classes/{room.id}/quizzes/{quiz.item_id}",
        room.id,
        f"to_grade:{quiz.item_id}:{lms.now().date()}",
    )


async def _notify_graded(db: AsyncSession, attempt: QuizAttempt, quiz: Quiz) -> None:
    """FR-025: the student hears once every essay of the attempt is graded, unless the score is never shown."""
    if quiz.show_score == "never":
        return
    await notify(
        db,
        [attempt.student_id],
        "returned",
        "Bài kiểm tra đã được chấm xong.",
        f"/student/classes/{quiz.class_id}/quizzes/{quiz.item_id}",
        quiz.class_id,
        f"returned:{attempt.id}",
    )


async def _expire(db: AsyncSession, attempt: QuizAttempt, quiz: Quiz) -> bool:
    deadline = lms.aware(attempt.deadline_at)
    if attempt.status != "in_progress" or deadline is None or lms.now() <= deadline:
        return False
    close = lms.aware(quiz.close_at)
    await finalize(db, attempt, "closed" if close is not None and close == deadline else "timeout")
    return True


@jobs.step
async def finalize_overdue(db: AsyncSession) -> None:
    attempts = list(
        await db.scalars(
            select(QuizAttempt)
            .where(
                QuizAttempt.status == "in_progress",
                QuizAttempt.deadline_at < lms.now(),
            )
            .with_for_update()
        )
    )
    for attempt in attempts:
        quiz = await db.get(Quiz, attempt.quiz_id)
        if quiz is not None:
            await _expire(db, attempt, quiz)
    await db.commit()


async def _load_attempt(
    db: AsyncSession, cid: str, aid: str, user: User, *, write: bool = False, student_only: bool = False
):
    room, role = await access.load_lms_class(db, cid, user, {"student"} if student_only else None, write=write)
    if student_only:
        access.require_student(role)
    attempt = await db.scalar(
        select(QuizAttempt).where(QuizAttempt.id == aid, QuizAttempt.class_id == cid).with_for_update()
    )
    if attempt is None:
        raise classes.not_found()
    if role != "teacher":
        student_id = await access.resolve_student(db, room, user, role, attempt.student_id)
        if student_id != attempt.student_id:
            raise classes.not_found()
    quiz, _ = await _quiz(db, cid, attempt.quiz_id)
    if await _expire(db, attempt, quiz):
        # A rejected late autosave must still persist the automatic submission.
        await db.commit()
    return attempt, quiz, role


async def _affected(db: AsyncSession, question: QuizQuestion) -> list[QuizAttempt]:
    attempts = await db.scalars(
        select(QuizAttempt)
        .where(
            QuizAttempt.quiz_id == question.quiz_id,
            QuizAttempt.status != "in_progress",
        )
        .with_for_update()
    )
    return [a for a in attempts if any(q["question_id"] == question.id for q in a.snapshot)]


@router.get("/classes/{cid}/quizzes/{qid}")
async def get_quiz(cid: str, qid: str, db: DbSession, user: CurrentUser, student_id: str | None = None):
    room, role = await access.load_lms_class(db, cid, user)
    if role == "student" and student_id is not None and student_id != user.id:
        raise classes.not_found()
    quiz, item = await _quiz(db, cid, qid)
    if role == "teacher":
        return await _teacher_quiz(db, quiz, item)
    if not await lessons.item_visible(db, item):
        raise classes.not_found()
    sid = await access.resolve_student(db, room, user, role, student_id)
    attempts = list(
        await db.scalars(
            select(QuizAttempt)
            .where(
                QuizAttempt.quiz_id == qid,
                QuizAttempt.student_id == sid,
            )
            .order_by(QuizAttempt.attempt_no)
            .with_for_update()
        )
    )
    for attempt in attempts:
        await _expire(db, attempt, quiz)
    await db.commit()
    questions = await _questions(db, qid)
    state = "open"
    if quiz.open_at and lms.now() < lms.aware(quiz.open_at):
        state = "upcoming"
    if quiz.close_at and lms.now() >= lms.aware(quiz.close_at):
        state = "closed"
    return _response(
        QuizStudentView(
            **_config(quiz),
            item_id=qid,
            title=item.title,
            question_count=len(questions),
            max_points=sum(q.points for q in questions),
            state=state,
            attempts=[_attempt_view(a) for a in attempts],
        )
    )


@router.patch("/classes/{cid}/quizzes/{qid}")
async def patch_quiz(cid: str, qid: str, body: QuizConfig, db: DbSession, user: CurrentUser):
    _, role = await access.load_lms_class(db, cid, user, {"teacher"}, write=True)
    access.require_teacher(role)
    quiz, item = await _quiz(db, cid, qid, lock=True)
    try:
        config = QuizConfig.model_validate({**_config(quiz), **body.model_dump(exclude_unset=True)})
    except ValidationError:
        raise HTTPException(422, "Cấu hình bài kiểm tra không hợp lệ.") from None
    for name, value in config.model_dump().items():
        setattr(quiz, name, value)
    await db.commit()
    return await _teacher_quiz(db, quiz, item)


@router.post("/classes/{cid}/quizzes/{qid}/questions", status_code=201)
async def create_question(cid: str, qid: str, body: QuestionIn, db: DbSession, user: CurrentUser):
    _, role = await access.load_lms_class(db, cid, user, {"teacher"}, write=True)
    access.require_teacher(role)
    await _quiz(db, cid, qid, lock=True)
    position = await db.scalar(select(func.max(QuizQuestion.position)).where(QuizQuestion.quiz_id == qid))
    question = QuizQuestion(
        quiz_id=qid, class_id=cid, position=0 if position is None else position + 1, **_prepare_question(body)
    )
    db.add(question)
    await db.commit()
    return _teacher_question(question)


@router.patch("/classes/{cid}/questions/{question_id}")
async def patch_question(cid: str, question_id: str, body: QuestionPatch, db: DbSession, user: CurrentUser):
    _, role = await access.load_lms_class(db, cid, user, {"teacher"}, write=True)
    access.require_teacher(role)
    question = await _question(db, cid, question_id)
    try:
        merged = QuestionIn.model_validate({**_question_data(question), **body.model_dump(exclude_unset=True)})
    except ValidationError:
        raise HTTPException(422, "Câu hỏi hoặc đáp án không hợp lệ.") from None
    count = len(await _affected(db, question))
    for name, value in _prepare_question(merged, question).items():
        setattr(question, name, value)
    await db.commit()
    return _teacher_question(question, count)


@router.delete("/classes/{cid}/questions/{question_id}")
async def delete_question(cid: str, question_id: str, db: DbSession, user: CurrentUser):
    _, role = await access.load_lms_class(db, cid, user, {"teacher"}, write=True)
    access.require_teacher(role)
    question = await _question(db, cid, question_id)
    count = len(await _affected(db, question))
    await db.delete(question)
    await db.commit()
    return {"affects_submitted": count}


@router.put("/classes/{cid}/quizzes/{qid}/questions/order")
async def order_questions(cid: str, qid: str, body: OrderIn, db: DbSession, user: CurrentUser):
    _, role = await access.load_lms_class(db, cid, user, {"teacher"}, write=True)
    access.require_teacher(role)
    await _quiz(db, cid, qid, lock=True)
    questions = {q.id: q for q in await _questions(db, qid)}
    if len(body.ids) != len(questions) or set(body.ids) != set(questions):
        raise HTTPException(422, "Danh sách phải chứa mỗi câu hỏi đúng một lần.")
    for position, question_id in enumerate(body.ids):
        questions[question_id].position = position
    await db.commit()
    return {"ids": body.ids}


@router.post("/classes/{cid}/quizzes/{qid}/attempts")
async def start_attempt(cid: str, qid: str, db: DbSession, user: CurrentUser):
    _, role = await access.load_lms_class(db, cid, user, {"student"}, write=True)
    access.require_student(role)
    quiz, item = await _quiz(db, cid, qid, lock=True)
    if not await lessons.item_visible(db, item):
        raise HTTPException(409, "Bài kiểm tra chưa được mở cho học sinh.")
    attempts = list(
        await db.scalars(
            select(QuizAttempt)
            .where(
                QuizAttempt.quiz_id == qid,
                QuizAttempt.student_id == user.id,
            )
            .order_by(QuizAttempt.attempt_no)
            .with_for_update()
        )
    )
    for attempt in attempts:
        if attempt.status == "in_progress":
            if not await _expire(db, attempt, quiz):
                return _response(_attempt_view(attempt))
            await db.commit()
    clock = lms.now()
    if quiz.open_at and clock < lms.aware(quiz.open_at):
        raise HTTPException(409, "Bài kiểm tra chưa đến giờ mở.")
    if quiz.close_at and clock >= lms.aware(quiz.close_at):
        raise HTTPException(409, "Bài kiểm tra đã đóng.")
    if quiz.max_attempts and len(attempts) >= quiz.max_attempts:
        raise HTTPException(409, "Bạn đã hết lượt làm bài kiểm tra.")
    questions = await _questions(db, qid)
    if not questions:
        raise HTTPException(409, "Bài kiểm tra chưa có câu hỏi.")
    attempt_id = new_id()
    deadlines = [lms.aware(quiz.close_at)] if quiz.close_at else []
    if quiz.duration_minutes is not None:
        deadlines.append(clock + timedelta(minutes=quiz.duration_minutes))
    attempt = QuizAttempt(
        id=attempt_id,
        quiz_id=qid,
        class_id=cid,
        student_id=user.id,
        attempt_no=max((a.attempt_no for a in attempts), default=0) + 1,
        started_at=clock,
        deadline_at=min(deadlines) if deadlines else None,
        snapshot=_paper(questions, quiz, attempt_id),
        max_score=sum(q.points for q in questions),
    )
    db.add(attempt)
    try:
        await db.commit()
    except IntegrityError:
        # The attempt number constraint also catches simultaneous starts on SQLite (no row locks).
        await db.rollback()
        attempt = await db.scalar(
            select(QuizAttempt).where(
                QuizAttempt.quiz_id == qid,
                QuizAttempt.student_id == user.id,
                QuizAttempt.status == "in_progress",
            )
        )
        if attempt is None:
            raise HTTPException(409, "Lượt làm đã thay đổi, vui lòng tải lại.") from None
    return _response(_attempt_view(attempt))


@router.get("/classes/{cid}/attempts/{aid}")
async def get_attempt(cid: str, aid: str, db: DbSession, user: CurrentUser):
    attempt, quiz, role = await _load_attempt(db, cid, aid, user)
    return _response(await _attempt_result(db, attempt, quiz, role))


def _answer_value(served: dict, value: object):
    if value is None:
        return None
    kind = served["kind"]
    ids = {o["id"] for o in served["options"]}
    valid = False
    if kind == "single":
        valid = isinstance(value, str) and (value in ids or value == "")
    elif kind == "multi":
        valid = isinstance(value, list) and all(isinstance(v, str) and v in ids for v in value)
    elif kind == "true_false":
        valid = isinstance(value, bool)
    elif kind in {"short", "essay"}:
        valid = isinstance(value, str)
        if valid:
            value = clean("Câu trả lời", value)
    if not valid:
        raise HTTPException(422, "Câu trả lời không hợp lệ cho loại câu hỏi này.")
    return value


@router.put("/classes/{cid}/attempts/{aid}/answers")
async def save_answer(cid: str, aid: str, body: AnswerIn, db: DbSession, user: CurrentUser):
    attempt, _, _ = await _load_attempt(db, cid, aid, user, write=True, student_only=True)
    if attempt.status != "in_progress":
        raise HTTPException(409, "attempt_closed")
    served = next((q for q in attempt.snapshot if q["question_id"] == body.question_id), None)
    if served is None:
        raise HTTPException(422, "Câu hỏi không thuộc lượt làm này.")
    attempt.answers = {**attempt.answers, body.question_id: _answer_value(served, body.value)}
    await db.commit()
    return {"saved_at": lms.now()}


@router.post("/classes/{cid}/attempts/{aid}/submit")
async def submit_attempt(cid: str, aid: str, db: DbSession, user: CurrentUser):
    attempt, quiz, role = await _load_attempt(db, cid, aid, user, write=True, student_only=True)
    await finalize(db, attempt, "manual")
    await db.commit()
    return _response(await _attempt_result(db, attempt, quiz, role))


def _audit(db: AsyncSession, attempt: QuizAttempt, actor_id: str, action: str, question_id: str, before: dict):
    db.add(
        GradeAudit(
            class_id=attempt.class_id,
            actor_id=actor_id,
            action=action,
            target_type="attempt_question",
            target_id=f"{attempt.id}:{question_id}",
            student_id=attempt.student_id,
            before=before,
            after={"item_scores": deepcopy(attempt.item_scores), "score": attempt.score},
        )
    )


@router.put("/classes/{cid}/attempts/{aid}/scores/{question_id}")
async def grade_attempt_question(cid: str, aid: str, question_id: str, body: ScoreIn, db: DbSession, user: CurrentUser):
    _, role = await access.load_lms_class(db, cid, user, {"teacher"}, write=True)
    access.require_teacher(role)
    attempt, quiz, _ = await _load_attempt(db, cid, aid, user, write=True)
    if attempt.status == "in_progress":
        raise HTTPException(409, "Học sinh chưa nộp bài.")
    served = next((q for q in attempt.snapshot if q["question_id"] == question_id), None)
    if served is None:
        raise classes.not_found()
    if served["kind"] != "essay" or body.points > served["points"]:
        raise HTTPException(422, "Điểm phải nằm trong thang điểm câu tự luận.")
    before = {"item_scores": deepcopy(attempt.item_scores), "score": attempt.score}
    attempt.item_scores = {
        **attempt.item_scores,
        question_id: {
            "points": round(body.points, 2),
            "graded_by": user.id,
            "feedback": clean("Nhận xét", body.feedback),
        },
    }
    _update_total(attempt)
    _audit(db, attempt, user.id, "grade", question_id, before)
    if before["score"] is None and attempt.score is not None:
        await _notify_graded(db, attempt, quiz)
    await db.commit()
    return _response(await _attempt_result(db, attempt, quiz, role))


@router.post("/classes/{cid}/questions/{question_id}/regrade")
async def regrade_question(cid: str, question_id: str, db: DbSession, user: CurrentUser):
    _, role = await access.load_lms_class(db, cid, user, {"teacher"}, write=True)
    access.require_teacher(role)
    question = await _question(db, cid, question_id)
    attempts = await _affected(db, question)
    updated = 0
    for attempt in attempts:
        served = next(q for q in attempt.snapshot if q["question_id"] == question_id)
        points = _grade_served(served, question, attempt.answers.get(question_id))
        if points is None:
            continue
        before = {"item_scores": deepcopy(attempt.item_scores), "score": attempt.score}
        attempt.item_scores = {**attempt.item_scores, question_id: {"points": points, "graded_by": "auto"}}
        _update_total(attempt)
        _audit(db, attempt, user.id, "regrade", question_id, before)
        updated += 1
    await db.commit()
    return {"updated": updated}


@router.get("/classes/{cid}/quizzes/{qid}/results")
async def quiz_results(cid: str, qid: str, db: DbSession, user: CurrentUser):
    _, role = await access.load_lms_class(db, cid, user)
    access.require_teacher(role)
    quiz, _ = await _quiz(db, cid, qid)
    rows = list(
        (
            await db.execute(
                select(QuizAttempt, User.name)
                .join(User, User.id == QuizAttempt.student_id)
                .where(
                    QuizAttempt.quiz_id == qid,
                )
                .order_by(User.name, QuizAttempt.attempt_no)
                .with_for_update(of=QuizAttempt)
            )
        ).all()
    )
    per_student = {}
    attempts_out = []
    for attempt, name in rows:
        await _expire(db, attempt, quiz)
        if attempt.status != "in_progress":
            per_student.setdefault(attempt.student_id, []).append(
                grading.GradedAttempt(
                    attempt.attempt_no,
                    grading.to_ten(attempt.score, attempt.max_score),
                    10,
                )
            )
        data = (await _attempt_result(db, attempt, quiz, role)).model_dump(exclude_unset=True)
        attempts_out.append({**data, "student_name": name})
    await db.commit()
    scores = [s for group in per_student.values() if (s := grading.quiz_score(group, quiz.scoring_policy)) is not None]
    distribution = {str(i): 0 for i in range(11)}
    for score in scores:
        distribution[str(min(10, max(0, int(score))))] += 1
    per_question = []
    for question in await _questions(db, qid):
        graded = [
            (a.item_scores[question.id]["points"], served["points"])
            for a, _ in rows
            if a.status != "in_progress"
            for served in a.snapshot
            if served["question_id"] == question.id and question.id in a.item_scores
        ]
        per_question.append(
            {
                "question_id": question.id,
                "correct_rate": round(sum(p >= maximum for p, maximum in graded) / len(graded), 4) if graded else None,
            }
        )
    return {
        "attempts": attempts_out,
        "stats": {
            "attempted_students": len({a.student_id for a, _ in rows}),
            "average": round(sum(scores) / len(scores), 2) if scores else None,
            "distribution": distribution,
            "per_question": per_question,
        },
    }


@router.post("/classes/{cid}/quizzes/{qid}/copy", status_code=201)
async def copy_quiz(cid: str, qid: str, body: CopyIn, db: DbSession, user: CurrentUser):
    _, role = await access.load_lms_class(db, cid, user, {"teacher"}, write=True)
    access.require_teacher(role)
    quiz, item = await _quiz(db, cid, qid)
    target = await db.get(Lesson, body.target_lesson_id)
    if target is None:
        raise classes.not_found()
    _, target_role = await access.load_lms_class(db, target.class_id, user, write=True)
    if target_role != "teacher":
        raise classes.not_found()
    position = await db.scalar(select(func.max(LessonItem.position)).where(LessonItem.lesson_id == target.id))
    copied_item = LessonItem(
        class_id=target.class_id,
        lesson_id=target.id,
        kind="quiz",
        title=item.title,
        body=item.body,
        visible=item.visible,
        position=0 if position is None else position + 1,
    )
    db.add(copied_item)
    await db.flush()
    copied = Quiz(item_id=copied_item.id, class_id=target.class_id, **_config(quiz))
    db.add(copied)
    await db.flush()
    for question in await _questions(db, qid):
        db.add(
            QuizQuestion(
                quiz_id=copied.item_id,
                class_id=target.class_id,
                position=question.position,
                source=question.source,
                **deepcopy(_question_data(question)),
            )
        )
    await db.commit()
    return await _teacher_quiz(db, copied, copied_item)
