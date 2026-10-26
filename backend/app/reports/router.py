"""Learning reports: a parent's report on their child, and a teacher's class progress."""

import time
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import select

from app.auth.deps import DbSession, require_roles
from app.auth.models import Role, User
from app.chat.router import record_usage
from app.classes import service as classes
from app.classes.models import ClassMember, Consent
from app.llm.registry import get_chat_model
from app.reports import service

router = APIRouter(tags=["reports"])
Parent = Annotated[User, Depends(require_roles(Role.PARENT))]
Teacher = Annotated[User, Depends(require_roles(Role.TEACHER, Role.ADMIN))]
Days = Annotated[int, Query(ge=1, le=60)]


class ReportOut(BaseModel):
    student_id: str
    student_name: str
    activity: dict[str, Any]
    narrative: dict[str, Any]
    generated_at: datetime


class ProgressRow(BaseModel):
    student_id: str
    student_name: str
    activity: dict[str, Any]


async def _report(db, viewer: User, student: User, days: int, audience: str, class_id: str | None) -> ReportOut:
    data = await service.activity(db, student.id, days, class_id)
    started = time.perf_counter()
    text, usage = await service.narrative(get_chat_model(), student.name, data, audience)
    if usage is not None:
        record_usage(db, viewer.id, class_id, None, [("report", usage, int((time.perf_counter() - started) * 1000))])
        await db.commit()
    return ReportOut(
        student_id=student.id, student_name=student.name, activity=data, narrative=text, generated_at=datetime.now()
    )


@router.get("/parent/children/{student_id}/report", response_model=ReportOut)
async def child_report(student_id: str, user: Parent, db: DbSession, days: Days = 7) -> ReportOut:
    if student_id not in await classes.children_of(db, user.id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Không tìm thấy con đã liên kết.")
    allowed = await db.scalar(
        select(Consent.allow_progress_reports).where(Consent.parent_id == user.id, Consent.student_id == student_id)
    )
    if allowed is False:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Bạn đã tắt báo cáo học tập cho con. Bật lại trong mục “Đồng ý & quyền riêng tư”.",
        )
    student = await db.get(User, student_id)
    assert student is not None
    return await _report(db, user, student, days, "parent", None)


async def _students(db, class_id: str) -> list[User]:
    ids = await db.scalars(
        select(ClassMember.user_id).where(ClassMember.class_id == class_id, ClassMember.role == "student")
    )
    return [student for student in [await db.get(User, i) for i in ids] if student]


@router.get("/classes/{class_id}/progress", response_model=list[ProgressRow])
async def class_progress(class_id: str, user: Teacher, db: DbSession, days: Days = 7) -> list[ProgressRow]:
    room, _ = await classes.load_class(db, class_id, user, {"teacher"})
    rows = [
        ProgressRow(student_id=s.id, student_name=s.name, activity=await service.activity(db, s.id, days, room.id))
        for s in await _students(db, room.id)
    ]
    return sorted(rows, key=lambda row: row.student_name)


@router.get("/classes/{class_id}/students/{student_id}/report", response_model=ReportOut)
async def student_report(class_id: str, student_id: str, user: Teacher, db: DbSession, days: Days = 7) -> ReportOut:
    room, _ = await classes.load_class(db, class_id, user, {"teacher"})
    student = next((s for s in await _students(db, room.id) if s.id == student_id), None)
    if student is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Không tìm thấy học sinh trong lớp.")
    return await _report(db, user, student, days, "teacher", room.id)
