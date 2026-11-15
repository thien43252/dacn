"""Teacher-only AI drafts, applied to questions and grades only after review."""

from copy import deepcopy
from typing import Literal

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy import func, select

from app import db as database
from app import lms
from app.agents.models import Agent, AgentVersion, Installation
from app.auth.deps import CurrentUser, DbSession
from app.auth.models import new_id
from app.chat.models import UsageRecord
from app.classes import service as classes
from app.classes.models import ClassRoom
from app.knowledge.models import Document
from app.lms import access, grading, quizzes, schemas
from app.lms.models import (
    AISuggestion,
    Assignment,
    AssignmentExtension,
    GradeAudit,
    LessonItem,
    Quiz,
    QuizAttempt,
    QuizQuestion,
    Submission,
    SubmissionVersion,
)
from app.lms.notify import notify
from app.tools import impl
from app.tools.registry import ToolContext

router = APIRouter(tags=["lms"])
Capability = Literal["questions", "grading"]
Action = Literal["approve", "edit", "discard"]
NO_AGENT = "Lớp chưa cài agent trợ giảng phù hợp. Cài từ Agent Hub để dùng gợi ý."
NO_CONSENT = "Phụ huynh chưa đồng ý cho agent xử lý bài của học sinh này."


class QuestionsIn(quizzes.InputModel):
    agent_slug: str | None = None
    count: int = Field(default=5, ge=1, le=20)
    kinds: list[quizzes.QuestionKind] = Field(default_factory=lambda: ["single"], min_length=1)
    level: Literal["nhan_biet", "thong_hieu", "van_dung", "van_dung_cao", "hon_hop"] = "hon_hop"
    document_ids: list[str] | None = None


class TargetIn(quizzes.InputModel):
    type: Literal["submission", "attempt_question"]
    id: str


class GradingIn(quizzes.InputModel):
    targets: list[TargetIn] = Field(min_length=1, max_length=100)
    agent_slug: str | None = None


class Decision(quizzes.InputModel):
    index: int = Field(ge=0)
    action: Action
    question: dict | None = None


class ReviewIn(quizzes.InputModel):
    decisions: list[Decision] | None = None
    action: Action | None = None
    points: float | None = Field(default=None, ge=0)
    feedback: str | None = None


class SuggestionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    kind: str
    target_type: str
    target_id: str
    agent_id: str | None
    status: str
    payload: dict | None
    final: dict | None
    error: str | None


async def eligible_agents(db, room, capability: Capability) -> list[dict]:
    tool = "quiz_generator" if capability == "questions" else "rubric_grader"
    rows = await db.execute(
        select(Agent, AgentVersion)
        .join(Installation, Installation.agent_id == Agent.id)
        .join(AgentVersion, AgentVersion.id == Installation.agent_version_id)
        .where(
            Installation.class_id == room.id,
            Installation.scope == "class",
            Installation.enabled.is_(True),
            AgentVersion.agent_id == Agent.id,
            AgentVersion.certification_status == "certified",
        )
        .order_by(Agent.slug)
    )
    subjects = {room.subject, "chung"}
    found = [
        {
            "slug": agent.slug,
            "name": version.manifest.get("name", agent.slug),
            "agent_id": agent.id,
            "version_id": version.id,
            "manifest": version.manifest,
        }
        for agent, version in rows
        if "teacher" in version.manifest.get("target_roles", []) and tool in version.manifest.get("tools", [])
    ]
    # Default choice (first item) is an agent for this class's subject or a general one, e.g. Trợ giảng LMS rather
    # than the literature grader in a maths class.
    return sorted(found, key=lambda a: not subjects & set(a["manifest"].get("subjects", ["chung"])))


async def _agent(db, room, capability, slug):
    agents = await eligible_agents(db, room, capability)
    selected = next((a for a in agents if slug is None or a["slug"] == slug), None)
    if selected is None:
        raise HTTPException(409, NO_AGENT)
    return selected


async def _quiz(db, cid, qid):
    quiz = await db.scalar(select(Quiz).where(Quiz.item_id == qid, Quiz.class_id == cid).with_for_update())
    item = await db.get(LessonItem, qid)
    if quiz is None or quiz.class_id != cid or item is None or item.class_id != cid:
        raise classes.not_found()
    return quiz, item


async def _target(db, cid, target_type, target_id):
    """Resolve a target within the class before reading any student work."""
    if target_type == "submission":
        row = await db.scalar(
            select(Submission).where(Submission.id == target_id, Submission.class_id == cid).with_for_update()
        )
        if row is None:
            raise classes.not_found()
        assignment = await db.get(Assignment, row.assignment_id)
        if assignment is None or assignment.class_id != cid:
            raise classes.not_found()
        if not assignment.ai_grading:
            raise HTTPException(409, "Bài tập đã tắt gợi ý chấm bằng AI.")
        version = await db.scalar(
            select(SubmissionVersion).where(
                SubmissionVersion.submission_id == row.id,
                SubmissionVersion.version_no == row.latest_version,
            )
        )
        if version is None:
            raise HTTPException(409, "Không có phiên bản bài nộp để chấm.")
        return row, assignment.max_points, version.text, assignment.rubric, assignment.prompt
    aid, separator, qid = target_id.partition(":")
    row = await db.scalar(
        select(QuizAttempt).where(QuizAttempt.id == aid, QuizAttempt.class_id == cid).with_for_update()
    )
    if not separator or row is None:
        raise classes.not_found()
    quiz, _ = await _quiz(db, cid, row.quiz_id)
    if not quiz.ai_grading:
        raise HTTPException(409, "Bài kiểm tra đã tắt gợi ý chấm bằng AI.")
    if row.status == "in_progress":
        raise HTTPException(409, "Học sinh chưa nộp bài.")
    served = next((q for q in row.snapshot if q["question_id"] == qid), None)
    question = await db.get(QuizQuestion, qid)
    if served is None or served["kind"] != "essay" or question is None or question.quiz_id != row.quiz_id:
        raise HTTPException(422, "Chỉ gợi ý chấm câu tự luận thuộc bài đã nộp.")
    return row, served["points"], row.answers.get(qid) or "", question.rubric, served["prompt"]


def _screen_question(value: dict) -> dict:
    # The same public schema validates manual and suggested questions, including answer IDs.
    data = quizzes.QuestionIn.model_validate({k: v for k, v in value.items() if k != "source"}).model_dump()

    def clean(value):
        if isinstance(value, str):
            return schemas.clean("Câu hỏi", value)
        if isinstance(value, list):
            return [clean(v) for v in value]
        if isinstance(value, dict):
            return {k: clean(v) for k, v in value.items()}
        return value

    data = clean(data)
    for option in data["options"]:
        if option["id"] is None:
            option["id"] = new_id()
    if not data["prompt"].strip() or any(not o["text"].strip() for o in data["options"]):
        raise HTTPException(422, "Câu hỏi và lựa chọn không được để trống.")
    # Validate again after guard redaction, which can also affect short answers.
    return quizzes.QuestionIn.model_validate(data).model_dump()


def _questions(data, kinds):
    result = []
    for raw in data.get("questions", []):
        try:
            kind = raw.get("kind", {"mcq": "single"}.get(raw.get("type"), raw.get("type")))
            if kind not in kinds:
                continue
            options = (
                [{"id": new_id(), "text": text} for text in raw.get("options", [])]
                if kind in {"single", "multi"}
                else []
            )
            answer = raw.get("answer")

            def option_id(index, options=options):
                if type(index) is int and 0 <= index < len(options):
                    return options[index]["id"]
                raise ValueError("Đáp án không hợp lệ.")

            if kind == "single":
                answer = option_id(answer)
            elif kind == "multi":
                answer = [option_id(i) for i in answer]
            rubric = raw.get("rubric") if kind == "essay" else None
            if kind == "essay":
                if not isinstance(answer, str) or not answer.strip():
                    continue
                rubric = {**(rubric or {}), "model_answer": answer}
                answer = None
            question = _screen_question(
                {
                    "kind": kind,
                    "prompt": raw.get("question"),
                    "options": options,
                    "answer_key": answer,
                    "points": 1,
                    "explanation": raw.get("explanation", ""),
                    "rubric": rubric,
                }
            )
            result.append({**question, "source": raw.get("source", "")})
        except (ValidationError, ValueError, TypeError, AttributeError, HTTPException):
            continue
    return {"questions": result}


async def run_suggestion(sgid: str):
    """Background jobs own their sessions; the HTTP request has already committed its draft."""
    async with database.session_factory()() as db:
        suggestion = await db.get(AISuggestion, sgid)
        if suggestion is None or suggestion.status != "pending":
            return
        ctx = None
        try:
            room = await db.get(ClassRoom, suggestion.class_id)
            agent = await _agent(db, room, suggestion.kind, suggestion.request["agent_slug"])
            if agent["version_id"] != suggestion.agent_version_id:
                raise HTTPException(409, NO_AGENT)
            ctx = ToolContext(
                user_id=suggestion.requested_by,
                role="teacher",
                class_id=room.id,
                grade=room.grade,
                conversation_id=None,
                agent_slug=agent["slug"],
                allowed_tools=frozenset(agent["manifest"]["tools"]),
            )
            system_prompt = agent["manifest"].get("system_prompt", "")
            if suggestion.kind == "questions":
                _, item = await _quiz(db, room.id, suggestion.target_id)
                args = suggestion.request
                data = await impl.quiz_generator(
                    ctx,
                    impl.QuizArgs(
                        topic=f"Câu hỏi cho bài {item.title}"[:300],
                        num_questions=args["count"],
                        question_types=args["kinds"],
                        level=args["level"],
                        document_ids=args["document_ids"],
                        with_answers=True,
                        system_prompt=system_prompt,
                    ),
                )
                suggestion.payload = _questions(data, args["kinds"])
            else:
                target, maximum, text, rubric, prompt = await _target(
                    db, room.id, suggestion.target_type, suggestion.target_id
                )
                if not await classes.student_can_use_agents(db, room, target.student_id):
                    suggestion.status, suggestion.error = "skipped_consent", NO_CONSENT
                    await db.commit()
                    return
                text = schemas.screen_text("Bài làm", text).text
                if not text.strip():
                    raise HTTPException(422, "Bài làm chưa có văn bản để AI chấm.")
                suggestion.payload = await impl.rubric_grader(
                    ctx,
                    impl.RubricArgs(
                        essay=text,
                        rubric=rubric,
                        assignment=prompt[:500],
                        max_points=maximum,
                        system_prompt=system_prompt,
                    ),
                )
            suggestion.status = "ready"
            await notify(
                db,
                [suggestion.requested_by],
                "ai_ready",
                "Gợi ý AI đã sẵn sàng để duyệt.",
                f"/teacher/classes/{room.id}",
                room.id,
                f"ai_ready:{sgid}",
            )
        except HTTPException as error:
            suggestion.status, suggestion.error = "failed", str(error.detail)[:300]
        except (impl.ToolFailure, ValidationError, ValueError, TypeError, KeyError) as error:
            suggestion.status, suggestion.error = "failed", f"Không tạo được gợi ý AI: {error}"[:300]
        except Exception:
            suggestion.status, suggestion.error = "failed", "Không tạo được gợi ý AI. Vui lòng thử lại."
        if ctx:
            for purpose, usage in ctx.usage:
                db.add(
                    UsageRecord(
                        user_id=ctx.user_id,
                        class_id=ctx.class_id,
                        purpose=purpose,
                        provider=usage.provider,
                        model=usage.model,
                        input_tokens=usage.input_tokens,
                        output_tokens=usage.output_tokens,
                    )
                )
        await db.commit()


@router.get("/classes/{cid}/assist/agents")
async def list_agents(cid: str, db: DbSession, user: CurrentUser, capability: Capability = "questions"):
    room, _ = await access.load_lms_class(db, cid, user, {"teacher"})
    return [{k: a[k] for k in ("slug", "name", "agent_id")} for a in await eligible_agents(db, room, capability)]


@router.post("/classes/{cid}/quizzes/{qid}/suggest-questions")
async def suggest_questions(
    cid: str, qid: str, body: QuestionsIn, background: BackgroundTasks, db: DbSession, user: CurrentUser
):
    room, _ = await access.load_lms_class(db, cid, user, {"teacher"}, write=True)
    agent = await _agent(db, room, "questions", body.agent_slug)
    _, item = await _quiz(db, cid, qid)
    ids = body.document_ids
    if ids is None:
        ids = list(
            await db.scalars(
                select(LessonItem.document_id).where(
                    LessonItem.lesson_id == item.lesson_id,
                    LessonItem.class_id == cid,
                    LessonItem.document_id.is_not(None),
                )
            )
        )
    existing = set(await db.scalars(select(Document.id).where(Document.id.in_(ids), Document.class_id == cid)))
    if set(ids) != existing:
        raise HTTPException(422, "Tài liệu không thuộc lớp này.")
    row = AISuggestion(
        class_id=cid,
        kind="questions",
        target_type="quiz",
        target_id=qid,
        agent_id=agent["agent_id"],
        agent_version_id=agent["version_id"],
        requested_by=user.id,
        request={**body.model_dump(), "agent_slug": agent["slug"], "document_ids": ids},
    )
    db.add(row)
    await db.commit()
    response = SuggestionOut.model_validate(row)
    background.add_task(run_suggestion, row.id)
    return response


@router.post("/classes/{cid}/suggest-grading")
async def suggest_grading(cid: str, body: GradingIn, background: BackgroundTasks, db: DbSession, user: CurrentUser):
    room, _ = await access.load_lms_class(db, cid, user, {"teacher"}, write=True)
    agent = await _agent(db, room, "grading", body.agent_slug)
    rows = []
    for target in body.targets:
        work, _, text, _, _ = await _target(db, cid, target.type, target.id)
        row = AISuggestion(
            class_id=cid,
            kind="grading",
            target_type=target.type,
            target_id=target.id,
            agent_id=agent["agent_id"],
            agent_version_id=agent["version_id"],
            requested_by=user.id,
            request={"agent_slug": agent["slug"]},
            status="pending",
        )
        if not await classes.student_can_use_agents(db, room, work.student_id):
            row.status, row.error = "skipped_consent", NO_CONSENT
        else:
            try:
                schemas.screen_text("Bài làm", text)
            except HTTPException as error:
                row.status, row.error = "failed", str(error.detail)[:300]
        db.add(row)
        rows.append(row)
    await db.commit()
    response = [SuggestionOut.model_validate(row) for row in rows]
    for row in rows:
        if row.status == "pending":
            background.add_task(run_suggestion, row.id)
    return response


async def _suggestion(db, cid, sgid):
    row = await db.scalar(
        select(AISuggestion).where(AISuggestion.id == sgid, AISuggestion.class_id == cid).with_for_update()
    )
    if row is None:
        raise classes.not_found()
    return row


@router.get("/classes/{cid}/suggestions/{sgid}")
async def get_suggestion(cid: str, sgid: str, db: DbSession, user: CurrentUser):
    await access.load_lms_class(db, cid, user, {"teacher"})
    return SuggestionOut.model_validate(await _suggestion(db, cid, sgid))


async def _review_questions(db, row, decisions):
    if decisions is None:
        raise HTTPException(422, "Cần có quyết định cho câu hỏi.")
    await _quiz(db, row.class_id, row.target_id)
    questions = row.payload["questions"]
    indexes = [d.index for d in decisions]
    if len(indexes) != len(set(indexes)) or any(i >= len(questions) for i in indexes):
        raise HTTPException(422, "Chỉ số câu hỏi không hợp lệ hoặc bị lặp.")
    prepared = []
    try:
        for decision in decisions:
            if decision.action == "discard":
                continue
            value = decision.question if decision.action == "edit" else questions[decision.index]
            if value is None:
                raise HTTPException(422, "Cần cung cấp câu hỏi đã sửa.")
            prepared.append(_screen_question(value))
    except ValidationError:
        raise HTTPException(422, "Câu hỏi hoặc đáp án không hợp lệ.") from None
    position = await db.scalar(select(func.max(QuizQuestion.position)).where(QuizQuestion.quiz_id == row.target_id))
    created = []
    for offset, data in enumerate(prepared, 1):
        question = QuizQuestion(
            id=new_id(),
            quiz_id=row.target_id,
            class_id=row.class_id,
            position=(position if position is not None else -1) + offset,
            source="ai",
            ai_suggestion_id=row.id,
            **data,
        )
        db.add(question)
        created.append({"id": question.id, **data, "source": "ai", "ai_suggestion_id": row.id})
    row.final = {"questions": created}
    row.status = "edited" if any(d.action == "edit" for d in decisions) else "approved" if created else "discarded"


async def _review_grading(db, row, body, user):
    if body.action is None:
        raise HTTPException(422, "Cần có quyết định duyệt điểm.")
    if body.action == "discard":
        row.status, row.final = "discarded", {}
        return
    target, maximum, _, _, _ = await _target(db, row.class_id, row.target_type, row.target_id)
    points = body.points if body.action == "edit" and body.points is not None else row.payload["points"]
    if points is None or not 0 <= points <= maximum:
        raise HTTPException(422, "Điểm phải nằm trong thang điểm của bài.")
    points = round(points, 2)
    feedback = schemas.clean(
        "Nhận xét", body.feedback if body.feedback is not None else row.payload.get("feedback", "")
    )
    if row.target_type == "submission":
        before = {"raw_score": target.raw_score, "feedback": target.feedback, "final_score": target.final_score}
        assignment = await db.get(Assignment, target.assignment_id)
        latest = await db.scalar(
            select(SubmissionVersion).where(
                SubmissionVersion.submission_id == target.id,
                SubmissionVersion.version_no == target.latest_version,
            )
        )
        extension = await db.scalar(
            select(AssignmentExtension).where(
                AssignmentExtension.assignment_id == target.assignment_id,
                AssignmentExtension.student_id == target.student_id,
            )
        )
        penalty = grading.late_penalty(
            points,
            maximum,
            lms.aware(latest.submitted_at),
            lms.aware(extension.due_at if extension else assignment.due_at),
            assignment.late_penalty_per_day_pct,
            assignment.late_penalty_max_pct,
            target.penalty_waived,
        )
        target.raw_score, target.feedback = points, feedback
        target.penalty, target.final_score = penalty.penalty, penalty.final
        target.days_late, target.is_late = penalty.days_late, penalty.days_late > 0
        target.status, target.graded_by, target.graded_at, target.returned_at = "graded", user.id, lms.now(), None
        after = {"raw_score": points, "feedback": feedback, "final_score": target.final_score}
    else:
        qid = row.target_id.partition(":")[2]
        before = {"item_scores": deepcopy(target.item_scores), "score": target.score}
        target.item_scores = {**target.item_scores, qid: {"points": points, "graded_by": user.id, "feedback": feedback}}
        target.score = grading.attempt_total(target.item_scores, (q["question_id"] for q in target.snapshot))
        target.status = "submitted" if target.score is None else "graded"
        after = {"item_scores": deepcopy(target.item_scores), "score": target.score}
    row.final, row.status = {"points": points, "feedback": feedback}, "edited" if body.action == "edit" else "approved"
    db.add(
        GradeAudit(
            class_id=row.class_id,
            actor_id=user.id,
            action="ai_approve",
            target_type=row.target_type,
            target_id=row.target_id,
            student_id=target.student_id,
            before=before,
            after=after,
        )
    )


@router.post("/classes/{cid}/suggestions/{sgid}/review")
async def review_suggestion(cid: str, sgid: str, body: ReviewIn, db: DbSession, user: CurrentUser):
    await access.load_lms_class(db, cid, user, {"teacher"}, write=True)
    row = await _suggestion(db, cid, sgid)
    if row.status != "ready":
        raise HTTPException(409, "Gợi ý chưa sẵn sàng hoặc đã được duyệt.")
    if row.kind == "questions":
        await _review_questions(db, row, body.decisions)
    else:
        await _review_grading(db, row, body, user)
    row.reviewed_by, row.reviewed_at = user.id, lms.now()
    await db.commit()
    return SuggestionOut.model_validate(row)
