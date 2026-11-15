"""LMS: assignments (feature 004). See specs/004-lms-lessons/contracts/lms-api.md."""

from datetime import datetime

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from app import lms
from app.auth.deps import CurrentUser, DbSession
from app.auth.models import User
from app.classes.models import ClassMember
from app.lms import access, grading, lessons, schemas
from app.lms.models import (
    Assignment,
    AssignmentExtension,
    GradeAudit,
    LessonItem,
    LmsFile,
    Submission,
    SubmissionVersion,
)
from app.lms.notify import notify

router = APIRouter(tags=["lms"])


class AssignmentConfig(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)

    prompt: str = ""
    prompt_file_ids: list[str] = Field(default_factory=list)
    due_at: datetime | None = None
    max_points: float = Field(default=10, gt=0)
    allow_late: bool = True
    late_penalty_per_day_pct: float = Field(default=0, ge=0, le=100)
    late_penalty_max_pct: float = Field(default=0, ge=0, le=100)
    rubric: dict | None = None
    ai_grading: bool = True
    weight: float = Field(default=1, ge=0)
    counts_in_grade: bool = True


class ExtensionIn(BaseModel):
    due_at: datetime


class SubmissionIn(BaseModel):
    text: str = ""
    file_ids: list[str] = Field(default_factory=list)


class GradeIn(BaseModel):
    raw_score: float = Field(ge=0, allow_inf_nan=False)
    feedback: str = ""
    penalty_waived: bool | None = None


class ReturnIn(BaseModel):
    submission_ids: list[str] | None = None


class VersionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    version_no: int
    text: str
    file_ids: list[str]
    submitted_at: datetime
    is_late: bool


class ResultOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    raw_score: float | None
    penalty: float
    final_score: float | None
    feedback: str
    penalty_waived: bool


class SubmissionStudentOut(BaseModel):
    id: str
    assignment_id: str
    student_id: str
    status: str
    latest_version: int
    is_late: bool
    days_late: int
    returned_at: datetime | None
    versions: list[VersionOut]
    result: ResultOut | None = None


class SubmissionTeacherOut(SubmissionStudentOut):
    raw_score: float | None
    penalty: float
    final_score: float | None
    feedback: str
    penalty_waived: bool


async def _assignment(db, cid, asg, role):
    assignment = await db.get(Assignment, asg)
    item = await db.get(LessonItem, asg)
    if assignment is None or assignment.class_id != cid or item is None or item.class_id != cid:
        raise HTTPException(404, "Không tìm thấy bài tập.")
    if role != "teacher" and not await lessons.item_visible(db, item):
        raise HTTPException(404, "Không tìm thấy bài tập.")
    return assignment


async def _submission(db, cid, sid, room, user, role):
    row = await db.get(Submission, sid)
    if row is None or row.class_id != cid:
        raise HTTPException(404, "Không tìm thấy bài nộp.")
    if role != "teacher":
        student_id = await access.resolve_student(db, room, user, role, row.student_id)
        if student_id != row.student_id:
            raise HTTPException(404, "Không tìm thấy bài nộp.")
    await _assignment(db, cid, row.assignment_id, role)
    return row


async def _due(db, assignment, student_id):
    extension = await db.scalar(
        select(AssignmentExtension).where(
            AssignmentExtension.assignment_id == assignment.item_id,
            AssignmentExtension.student_id == student_id,
        )
    )
    return lms.aware(extension.due_at if extension else assignment.due_at)


async def _files(db, ids, cid, purpose, owner_id=None):
    for fid in set(ids):
        row = await db.get(LmsFile, fid)
        if (
            row is None
            or row.class_id != cid
            or row.purpose != purpose
            or (owner_id is not None and row.owner_id != owner_id)
        ):
            raise HTTPException(422, "Tệp đính kèm không hợp lệ.")


async def _out(db, row, role):
    versions = list(
        await db.scalars(
            select(SubmissionVersion)
            .where(SubmissionVersion.submission_id == row.id)
            .order_by(SubmissionVersion.version_no)
        )
    )
    values = {
        name: getattr(row, name) for name in SubmissionStudentOut.model_fields if name not in {"versions", "result"}
    }
    values["versions"] = [VersionOut.model_validate(v) for v in versions]
    if row.status == "returned":
        values["result"] = ResultOut.model_validate(row)
    if role == "teacher":
        values.update({name: getattr(row, name) for name in ResultOut.model_fields})
        return SubmissionTeacherOut(**values).model_dump(exclude_none=True)
    return SubmissionStudentOut(**values).model_dump(exclude_none=True)


def _audit(db, cid, user, action, row, before, after):
    db.add(
        GradeAudit(
            class_id=cid,
            actor_id=user.id,
            action=action,
            target_type="submission" if isinstance(row, Submission) else "assignment",
            target_id=row.id if isinstance(row, Submission) else row.item_id,
            student_id=row.student_id if isinstance(row, Submission) else after.get("student_id"),
            before=before,
            after=after,
            created_at=lms.now(),
        )
    )


async def _recompute(db, assignment, row):
    versions = list(await db.scalars(select(SubmissionVersion).where(SubmissionVersion.submission_id == row.id)))
    due = await _due(db, assignment, row.student_id)
    for version in versions:
        version.is_late = grading.days_late(lms.aware(version.submitted_at), due) > 0
    latest = max(versions, key=lambda v: v.version_no)
    result = grading.late_penalty(
        row.raw_score,
        assignment.max_points,
        lms.aware(latest.submitted_at),
        due,
        assignment.late_penalty_per_day_pct,
        assignment.late_penalty_max_pct,
        row.penalty_waived,
    )
    row.days_late = result.days_late
    row.is_late = result.days_late > 0
    row.penalty = result.penalty
    row.final_score = result.final


@router.get("/classes/{cid}/assignments/{asg}")
async def get_assignment(cid: str, asg: str, user: CurrentUser, db: DbSession, student_id: str | None = None):
    room, role = await access.load_lms_class(db, cid, user)
    if role == "student" and student_id is not None and student_id != user.id:
        raise HTTPException(404, "Không tìm thấy học sinh.")
    assignment = await _assignment(db, cid, asg, role)
    values = AssignmentConfig.model_validate(assignment, from_attributes=True).model_dump()
    values["item_id"] = assignment.item_id
    if role == "teacher":
        rows = await _roster(db, room, assignment)
        values["submissions"] = rows
        values["stats"] = {
            state: sum(r["state"] == state for r in rows)
            for state in ("submitted", "late", "missing", "graded", "returned")
        }
    else:
        student_id = await access.resolve_student(db, room, user, role, student_id)
        values["effective_due"] = await _due(db, assignment, student_id)
        row = await db.scalar(
            select(Submission).where(Submission.assignment_id == asg, Submission.student_id == student_id)
        )
        values["submission"] = await _out(db, row, role) if row else None
    return values


@router.patch("/classes/{cid}/assignments/{asg}")
async def patch_assignment(cid: str, asg: str, body: AssignmentConfig, user: CurrentUser, db: DbSession):
    _, role = await access.load_lms_class(db, cid, user, {"teacher"}, write=True)
    assignment = await _assignment(db, cid, asg, role)
    changes = body.model_dump(exclude_unset=True)
    if "prompt" in changes:
        changes["prompt"] = schemas.clean("đề bài", body.prompt)
    if "rubric" in changes and body.rubric is not None:
        changes["rubric"] = _clean_rubric(body.rubric)
    if "prompt_file_ids" in changes:
        await _files(db, body.prompt_file_ids, cid, "prompt")
    for name, value in changes.items():
        setattr(assignment, name, value)
    await db.flush()
    rows = await db.scalars(select(Submission).where(Submission.assignment_id == asg))
    for row in rows:
        await _recompute(db, assignment, row)
    await db.commit()
    return AssignmentConfig.model_validate(assignment, from_attributes=True)


def _clean_rubric(value):
    if isinstance(value, str):
        return schemas.clean("thang chấm", value)
    if isinstance(value, list):
        return [_clean_rubric(v) for v in value]
    if isinstance(value, dict):
        return {k: _clean_rubric(v) for k, v in value.items()}
    return value


async def _extension(cid, asg, student_id, body, user, db):
    room, role = await access.load_lms_class(db, cid, user, {"teacher"}, write=True)
    assignment = await _assignment(db, cid, asg, role)
    await access.resolve_student(db, room, user, role, student_id)
    old_due = await _due(db, assignment, student_id)
    extension = await db.scalar(
        select(AssignmentExtension).where(
            AssignmentExtension.assignment_id == asg, AssignmentExtension.student_id == student_id
        )
    )
    if body is None:
        if extension:
            await db.delete(extension)
    elif extension:
        extension.due_at = body.due_at
        extension.granted_by = user.id
    else:
        db.add(AssignmentExtension(assignment_id=asg, student_id=student_id, due_at=body.due_at, granted_by=user.id))
    await db.flush()
    due = await _due(db, assignment, student_id)
    row = await db.scalar(
        select(Submission).where(Submission.assignment_id == asg, Submission.student_id == student_id)
    )
    before = {"due_at": old_due.isoformat() if old_due else None}
    after = {"student_id": student_id, "due_at": due.isoformat() if due else None}
    _audit(db, cid, user, "extend", row or assignment, before, after)
    if row:
        await _recompute(db, assignment, row)
    await db.commit()
    return {"effective_due": due}


@router.put("/classes/{cid}/assignments/{asg}/extensions/{student_id}")
async def put_extension(cid: str, asg: str, student_id: str, body: ExtensionIn, user: CurrentUser, db: DbSession):
    return await _extension(cid, asg, student_id, body, user, db)


@router.delete("/classes/{cid}/assignments/{asg}/extensions/{student_id}")
async def delete_extension(cid: str, asg: str, student_id: str, user: CurrentUser, db: DbSession):
    return await _extension(cid, asg, student_id, None, user, db)


@router.post("/classes/{cid}/assignments/{asg}/submissions", status_code=201)
async def submit(cid: str, asg: str, body: SubmissionIn, user: CurrentUser, db: DbSession):
    room, role = await access.load_lms_class(db, cid, user, {"student"}, write=True)
    assignment = await _assignment(db, cid, asg, role)
    stamp = lms.now()
    due = await _due(db, assignment, user.id)
    days = grading.days_late(stamp, due)
    if days and not assignment.allow_late:
        raise HTTPException(409, "past_due")
    text = schemas.clean("bài nộp", body.text)
    if not text.strip() and not body.file_ids:
        raise HTTPException(422, "Bài nộp cần có văn bản hoặc tệp đính kèm.")
    await _files(db, body.file_ids, cid, "submission", user.id)
    row = await db.scalar(
        select(Submission).where(Submission.assignment_id == asg, Submission.student_id == user.id).with_for_update()
    )
    if row is None:
        row = Submission(assignment_id=asg, class_id=cid, student_id=user.id)
        db.add(row)
        await db.flush()
    row.latest_version += 1
    row.status = "submitted"
    row.returned_at = None
    row.raw_score = row.final_score = row.graded_at = row.graded_by = None
    row.feedback = ""
    db.add(
        SubmissionVersion(
            submission_id=row.id,
            version_no=row.latest_version,
            text=text,
            file_ids=body.file_ids,
            submitted_at=stamp,
            is_late=days > 0,
        )
    )
    await db.flush()
    await _recompute(db, assignment, row)
    teachers = list(
        await db.scalars(select(ClassMember.user_id).where(ClassMember.class_id == cid, ClassMember.role == "teacher"))
    )
    await notify(
        db,
        [room.owner_id, *teachers],
        "to_grade",
        "Có bài nộp mới cần chấm.",
        f"/teacher/classes/{cid}/assignments/{asg}",
        cid,
        f"to_grade:{asg}:{stamp.date()}",
    )
    await db.commit()
    return await _out(db, row, role)


async def _roster(db, room, assignment):
    ids = await access.student_ids(db, room.id)
    users = list(await db.scalars(select(User).where(User.id.in_(ids)).order_by(User.name, User.id)))
    submissions = {
        r.student_id: r
        for r in await db.scalars(select(Submission).where(Submission.assignment_id == assignment.item_id))
    }
    rows = []
    for user in users:
        row = submissions.get(user.id)
        latest = (
            await db.scalar(
                select(SubmissionVersion).where(
                    SubmissionVersion.submission_id == row.id, SubmissionVersion.version_no == row.latest_version
                )
            )
            if row
            else None
        )
        state = (
            ("late" if row.is_late else "submitted")
            if row and row.status == "submitted"
            else row.status
            if row
            else "missing"
        )
        rows.append(
            {
                "student_id": user.id,
                "name": user.name,
                "submission_id": row.id if row else None,
                "state": state,
                "effective_due": await _due(db, assignment, user.id),
                "submitted_at": lms.aware(latest.submitted_at) if latest else None,
            }
        )
    return rows


@router.get("/classes/{cid}/assignments/{asg}/submissions")
async def list_submissions(cid: str, asg: str, user: CurrentUser, db: DbSession):
    room, role = await access.load_lms_class(db, cid, user, {"teacher"})
    assignment = await _assignment(db, cid, asg, role)
    return await _roster(db, room, assignment)


@router.get("/classes/{cid}/submissions/{sid}")
async def get_submission(cid: str, sid: str, user: CurrentUser, db: DbSession):
    room, role = await access.load_lms_class(db, cid, user)
    row = await _submission(db, cid, sid, room, user, role)
    return await _out(db, row, role)


@router.put("/classes/{cid}/submissions/{sid}/grade")
async def grade_submission(cid: str, sid: str, body: GradeIn, user: CurrentUser, db: DbSession):
    room, role = await access.load_lms_class(db, cid, user, {"teacher"}, write=True)
    row = await _submission(db, cid, sid, room, user, role)
    assignment = await _assignment(db, cid, row.assignment_id, role)
    if body.raw_score > assignment.max_points:
        raise HTTPException(422, "Điểm vượt quá điểm tối đa.")
    before = ResultOut.model_validate(row).model_dump()
    row.feedback = schemas.clean("nhận xét", body.feedback)
    row.raw_score = body.raw_score
    if body.penalty_waived is not None:
        row.penalty_waived = body.penalty_waived
    await _recompute(db, assignment, row)
    row.status = "graded"
    row.graded_by = user.id
    row.graded_at = lms.now()
    row.returned_at = None
    after = ResultOut.model_validate(row).model_dump()
    _audit(db, cid, user, "grade", row, before, after)
    if before["penalty_waived"] != row.penalty_waived:
        _audit(db, cid, user, "waive_penalty", row, before, after)
    await db.commit()
    return await _out(db, row, role)


@router.post("/classes/{cid}/assignments/{asg}/return")
async def return_submissions(cid: str, asg: str, user: CurrentUser, db: DbSession, body: ReturnIn | None = None):
    _, role = await access.load_lms_class(db, cid, user, {"teacher"}, write=True)
    await _assignment(db, cid, asg, role)
    query = select(Submission).where(Submission.assignment_id == asg, Submission.status == "graded")
    if body and body.submission_ids:
        query = query.where(Submission.id.in_(body.submission_ids))
    rows = list(await db.scalars(query))
    for row in rows:
        row.status = "returned"
        row.returned_at = lms.now()
        _audit(db, cid, user, "return", row, {"status": "graded"}, {"status": "returned"})
        await notify(
            db,
            [row.student_id],
            "returned",
            "Bài tập đã được trả điểm.",
            f"/student/classes/{cid}/assignments/{asg}",
            cid,
            f"returned:{row.id}:{row.returned_at.isoformat()}",
        )
    await db.commit()
    return {"returned": len(rows)}
