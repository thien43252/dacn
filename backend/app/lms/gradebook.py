"""Gradebook, personal results, outstanding work and due-soon notifications."""

import csv
import io
from collections import defaultdict
from datetime import datetime, timedelta

from fastapi import APIRouter
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select

from app import lms
from app.auth.deps import CurrentUser, DbSession
from app.auth.models import User
from app.classes import service as classes
from app.classes.models import ClassMember, ClassRoom
from app.lms import access, grading, jobs, lessons
from app.lms.models import (
    Assignment,
    AssignmentExtension,
    GradeAudit,
    Lesson,
    LessonItem,
    Quiz,
    QuizAttempt,
    QuizQuestion,
    Submission,
)
from app.lms.notify import notify
from app.textnorm import words

# Vietnamese labels for cells without a score in the CSV export.
STATE_LABELS = {
    "not_assigned": "Không được giao",
    "missing": "Chưa nộp",
    "open": "Chưa nộp",
    "in_progress": "Đang làm",
    "pending": "Chờ chấm",
    "graded": "Đã chấm",
    "returned": "Đã trả",
}

router = APIRouter(tags=["lms"])


async def _data(db, class_ids, sid=None):
    """Load all cells in bulk, never querying inside the student/column loop."""
    items = list(
        await db.execute(
            select(LessonItem, Lesson)
            .join(Lesson, Lesson.id == LessonItem.lesson_id)
            .where(
                LessonItem.class_id.in_(class_ids),
                Lesson.status != "draft",
                LessonItem.kind.in_(["quiz", "assignment"]),
            )
            .order_by(Lesson.position, LessonItem.position, LessonItem.id)
        )
    )
    assignments = {r.item_id: r for r in await db.scalars(select(Assignment).where(Assignment.class_id.in_(class_ids)))}
    quizzes = {r.item_id: r for r in await db.scalars(select(Quiz).where(Quiz.class_id.in_(class_ids)))}
    maxima = dict(
        (
            await db.execute(
                select(QuizQuestion.quiz_id, func.sum(QuizQuestion.points))
                .where(QuizQuestion.class_id.in_(class_ids))
                .group_by(QuizQuestion.quiz_id)
            )
        ).all()
    )
    sq = select(Submission).where(Submission.class_id.in_(class_ids))
    aq = select(QuizAttempt).where(QuizAttempt.class_id.in_(class_ids))
    eq = select(AssignmentExtension).where(AssignmentExtension.assignment_id.in_(assignments))
    if sid is not None:
        sq = sq.where(Submission.student_id == sid)
        aq = aq.where(QuizAttempt.student_id == sid)
        eq = eq.where(AssignmentExtension.student_id == sid)
    submissions = {(r.student_id, r.assignment_id): r for r in await db.scalars(sq)}
    attempts = defaultdict(list)
    for row in await db.scalars(aq):
        attempts[row.student_id, row.quiz_id].append(row)
    extensions = {(r.student_id, r.assignment_id): lms.aware(r.due_at) for r in await db.scalars(eq)}
    return items, assignments, quizzes, maxima, submissions, attempts, extensions


def _column(item, lesson, config, maxima):
    return dict(
        item_id=item.id,
        kind=item.kind,
        title=item.title,
        lesson_title=lesson.title,
        max_points=config.max_points if item.kind == "assignment" else maxima.get(item.id, 0),
        weight=config.weight,
        counts_in_grade=config.counts_in_grade,
        counts=config.counts_in_grade,
        archived=lesson.status == "archived",
    )


def _cell(item, config, sid, joined, submissions, attempts, extensions):
    score = final = None
    due = lms.aware(config.due_at if item.kind == "assignment" else config.close_at)
    if item.kind == "assignment":
        due = extensions.get((sid, item.id), due)
        row = submissions.get((sid, item.id))
        has_data = row is not None
        state = "missing" if due and due < lms.now() else "open"
        if row:
            state = "pending" if row.status == "submitted" else row.status
            if row.status in {"graded", "returned"}:
                score, final = row.raw_score, row.final_score
    else:
        rows = attempts.get((sid, item.id), [])
        has_data = bool(rows)
        score = final = grading.quiz_score(
            [grading.GradedAttempt(r.attempt_no, r.score, r.max_score) for r in rows if r.status == "graded"],
            config.scoring_policy,
        )
        if score is not None:
            state = "graded"
        elif any(r.status == "submitted" for r in rows):
            state = "pending"
        elif rows:
            state = "in_progress"
        else:
            state = "missing" if due and due <= lms.now() else "open"
    if not has_data and joined is not None and due and due < lms.now() and lms.aware(joined) > due:
        state = "not_assigned"
    return dict(item_id=item.id, state=state, score=score, final=final)


def _average(columns, cells):
    total = weight = 0.0
    for col, cell in zip(columns, cells, strict=True):
        value = grading.to_ten(0 if cell["state"] == "missing" else cell["final"], col["max_points"])
        if col["counts_in_grade"] and value is not None:
            total += value * col["weight"]
            weight += col["weight"]
    return round(total / weight, 2) if weight else None


async def _book(db, cid):
    items, assignments, quizzes, maxima, submissions, attempts, extensions = await _data(db, [cid])
    configs = {**assignments, **quizzes}
    items = [(i, lesson) for i, lesson in items if i.id in configs]
    columns = [_column(i, lesson, configs[i.id], maxima) for i, lesson in items]
    roster = list(
        await db.execute(
            select(User, ClassMember.joined_at)
            .join(ClassMember, ClassMember.user_id == User.id)
            .where(ClassMember.class_id == cid, ClassMember.role == "student")
            .order_by(User.name, User.id)
        )
    )
    current_ids = {student.id for student, _ in roster}
    departed_ids = {sid for sid, _ in submissions} | {sid for sid, _ in attempts}
    departed = await db.scalars(
        select(User).where(User.id.in_(departed_ids - current_ids)).order_by(User.name, User.id)
    )
    roster.extend((student, None) for student in departed)
    rows = []
    for student, joined in roster:
        cells = [_cell(i, configs[i.id], student.id, joined, submissions, attempts, extensions) for i, _ in items]
        rows.append(
            dict(
                student=dict(id=student.id, name=student.name),
                left_class=student.id not in current_ids,
                cells=cells,
                average=_average(columns, cells),
            )
        )
    return dict(columns=columns, rows=rows)


@router.get("/classes/{cid}/gradebook")
async def gradebook(cid: str, user: CurrentUser, db: DbSession):
    await access.load_lms_class(db, cid, user, {"teacher"})
    return await _book(db, cid)


class ColumnIn(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    weight: float = Field(default=1, ge=0)
    counts_in_grade: bool = True


@router.patch("/classes/{cid}/gradebook/columns/{item_id}")
async def patch_column(cid: str, item_id: str, body: ColumnIn, user: CurrentUser, db: DbSession):
    await access.load_lms_class(db, cid, user, {"teacher"}, write=True)
    row = await db.get(Assignment, item_id) or await db.get(Quiz, item_id)
    if row is None or row.class_id != cid:
        raise classes.not_found()
    for name, value in body.model_dump(exclude_unset=True).items():
        setattr(row, name, value)
    await db.commit()
    return dict(item_id=item_id, weight=row.weight, counts_in_grade=row.counts_in_grade)


@router.get("/classes/{cid}/gradebook.csv")
async def gradebook_csv(cid: str, user: CurrentUser, db: DbSession):
    room, _ = await access.load_lms_class(db, cid, user, {"teacher"})
    book = await _book(db, cid)
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(["Học sinh", *(c["title"] for c in book["columns"]), "Điểm TB", "Ghi chú"])
    for row in book["rows"]:
        writer.writerow(
            [
                row["student"]["name"],
                *(
                    c["final"] if c["final"] is not None else STATE_LABELS.get(c["state"], c["state"])
                    for c in row["cells"]
                ),
                row["average"],
                "Đã rời lớp" if row["left_class"] else "",
            ]
        )
    slug = "-".join(words(room.name)) or "lop"
    return Response(
        output.getvalue().encode("utf-8-sig"),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="so-diem-{slug}.csv"'},
    )


async def _student(db, room, user, role, student_id):
    if role == "student" and student_id is not None and student_id != user.id:
        raise classes.not_found()
    return await access.resolve_student(db, room, user, role, student_id)


@router.get("/classes/{cid}/my-grades")
async def my_grades(cid: str, user: CurrentUser, db: DbSession, student_id: str | None = None):
    room, role = await access.load_lms_class(db, cid, user, {"student", "parent"})
    sid = await _student(db, room, user, role, student_id)
    items, assignments, quizzes, maxima, submissions, attempts, extensions = await _data(db, [cid], sid)
    member = await db.scalar(select(ClassMember).where(ClassMember.class_id == cid, ClassMember.user_id == sid))
    columns, cells = [], []
    for item, lesson in items:
        config = assignments.get(item.id) or quizzes.get(item.id)
        if config is None:
            continue
        cell = _cell(item, config, sid, member.joined_at, submissions, attempts, extensions)
        if item.kind == "assignment":
            visible = cell["state"] == "returned"
        else:
            visible = cell["state"] == "graded" and (
                config.show_score == "on_submit"
                or (config.show_score == "after_close" and config.close_at and lms.aware(config.close_at) <= lms.now())
            )
        if visible:
            columns.append(_column(item, lesson, config, maxima))
            cells.append(cell)
    average = _average(columns, cells)
    results = []
    for column, cell in zip(columns, cells, strict=True):
        submission = submissions.get((sid, column["item_id"]))
        results.append(
            dict(
                **column,
                state=cell["state"],
                score=cell["final"],
                returned_at=lms.aware(submission.returned_at) if submission else None,
            )
        )
    return dict(student_id=sid, items=results, overall_average=average, columns=columns, cells=cells, average=average)


async def _outstanding(db, sid):
    rooms = list(
        await db.scalars(
            select(ClassRoom)
            .join(ClassMember, ClassMember.class_id == ClassRoom.id)
            .where(ClassMember.user_id == sid, ClassMember.role == "student", ClassRoom.archived.is_(False))
        )
    )
    by_id = {r.id: r for r in rooms}
    items, assignments, quizzes, _, submissions, attempts, extensions = await _data(db, list(by_id), sid)
    result = []
    for item, _lesson in items:
        if not await lessons.item_visible(db, item):
            continue
        state = "open"
        if item.kind == "assignment":
            config = assignments.get(item.id)
            if config is None or (sid, item.id) in submissions:
                continue
            due = extensions.get((sid, item.id), lms.aware(config.due_at))
            if due and due < lms.now():
                if not config.allow_late:
                    continue
                state = "missing"
        else:
            config = quizzes.get(item.id)
            rows = attempts.get((sid, item.id), [])
            if config is None or any(r.status != "in_progress" for r in rows):
                continue
            due = lms.aware(config.close_at)
            if (config.open_at and lms.aware(config.open_at) > lms.now()) or (due and due <= lms.now()):
                continue
            active = any(r.status == "in_progress" for r in rows)
            if config.max_attempts and len(rows) >= config.max_attempts and not active:
                continue
            state = "in_progress" if active else "open"
        result.append(
            dict(
                class_id=item.class_id,
                class_name=by_id[item.class_id].name,
                item_id=item.id,
                kind=item.kind,
                title=item.title,
                due_at=due,
                state=state,
                status=state,
                link=f"/student/classes/{item.class_id}/{'assignments' if item.kind == 'assignment' else 'quizzes'}/{item.id}",
            )
        )
    return sorted(result, key=lambda r: (r["due_at"] is None, r["due_at"] or lms.now(), r["item_id"]))


@router.get("/todo")
async def todo(user: CurrentUser, db: DbSession, student_id: str | None = None):
    if user.role == "student":
        if student_id is not None and student_id != user.id:
            raise classes.not_found()
        sid = user.id
    elif user.role == "parent":
        children = await classes.children_of(db, user.id)
        sid = student_id or (children[0] if len(children) == 1 else None)
        if sid is None or sid not in children:
            raise classes.not_found()
    else:
        raise classes.forbidden()
    return await _outstanding(db, sid)


@jobs.step
async def remind_due_soon(db):
    stamp = lms.now()
    members = await db.execute(
        select(ClassMember.class_id, ClassMember.user_id)
        .join(ClassRoom, ClassRoom.id == ClassMember.class_id)
        .where(ClassMember.role == "student", ClassRoom.archived.is_(False))
    )
    roster = defaultdict(list)
    for cid, sid in members:
        roster[cid].append(sid)
    items, assignments, quizzes, _, submissions, attempts, extensions = await _data(db, list(roster))
    for item, _lesson in items:
        if not await lessons.item_visible(db, item):
            continue
        config = assignments.get(item.id) or quizzes.get(item.id)
        if config is None:
            continue
        for sid in roster[item.class_id]:
            if item.kind == "assignment":
                if (sid, item.id) in submissions:
                    continue
                due = extensions.get((sid, item.id), lms.aware(config.due_at))
            else:
                if any(r.status != "in_progress" for r in attempts.get((sid, item.id), [])):
                    continue
                due = lms.aware(config.close_at)
            if due and stamp <= due <= stamp + timedelta(hours=24):
                kind_path = "assignments" if item.kind == "assignment" else "quizzes"
                await notify(
                    db,
                    [sid],
                    "due_soon",
                    f"Sắp đến hạn: {item.title}",
                    f"/student/classes/{item.class_id}/{kind_path}/{item.id}",
                    item.class_id,
                    f"due_soon:{item.id}",
                )
    await db.commit()


class GradeAuditOut(BaseModel):
    id: str
    class_id: str
    actor_id: str | None
    actor_name: str | None = None
    action: str
    target_type: str
    target_id: str
    student_id: str | None
    student_name: str | None = None
    before: dict | None
    after: dict | None
    created_at: datetime


@router.get("/classes/{cid}/grade-audit", response_model=list[GradeAuditOut])
async def grade_audit(
    cid: str,
    user: CurrentUser,
    db: DbSession,
    student_id: str | None = None,
    target_id: str | None = None,
    limit: int = 200,
) -> list[GradeAuditOut]:
    """FR-030: who changed which grade and when. Teachers of the class only."""
    await access.load_lms_class(db, cid, user, {"teacher"})
    query = select(GradeAudit).where(GradeAudit.class_id == cid)
    if student_id:
        query = query.where(GradeAudit.student_id == student_id)
    if target_id:
        query = query.where(GradeAudit.target_id == target_id)
    rows = list(await db.scalars(query.order_by(GradeAudit.created_at.desc()).limit(min(max(limit, 1), 500))))
    ids = {r.actor_id for r in rows} | {r.student_id for r in rows}
    names = dict((await db.execute(select(User.id, User.name).where(User.id.in_(ids - {None})))).all())
    return [
        GradeAuditOut(
            id=r.id,
            class_id=r.class_id,
            actor_id=r.actor_id,
            actor_name=names.get(r.actor_id),
            action=r.action,
            target_type=r.target_type,
            target_id=r.target_id,
            student_id=r.student_id,
            student_name=names.get(r.student_id),
            before=r.before,
            after=r.after,
            created_at=r.created_at,
        )
        for r in rows
    ]
