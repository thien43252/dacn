"""Class announcements and assigned practice (specs/002-multi-agent-orchestration/contracts/class-actions.md).

Teachers post announcements here or through the confirmed `post_class_announcement` tool; practice sets come only from
the confirmed `assign_practice` tool. Students see what is meant for students, parents what is meant for parents of
the class, and only the class's teachers see answer keys.
"""

from datetime import datetime
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.auth.deps import CurrentUser, DbSession
from app.auth.models import User
from app.class_feed.models import ANNOUNCEMENT_BODY_MAX, Assignment, ClassAnnouncement
from app.classes import service as classes
from app.guard import dify_rules

router = APIRouter(tags=["class-feed"])

FEED_LIMIT = 50
BLOCKED = "Nội dung không phù hợp để chia sẻ."
# What each class role reads; teachers read everything.
AUDIENCES = {"student": ("students", "all"), "parent": ("parents", "all"), "teacher": ("students", "parents", "all")}


class AnnouncementIn(BaseModel):
    title: str = Field(min_length=3, max_length=120)
    body: str = Field(min_length=10, max_length=ANNOUNCEMENT_BODY_MAX)
    audience: Literal["students", "parents", "all"] = "all"


class AnnouncementOut(BaseModel):
    id: str
    title: str
    body: str
    audience: str
    author_name: str | None
    source: str
    created_at: datetime


class AssignmentOut(BaseModel):
    id: str
    title: str
    instructions: str
    questions: list[dict[str, Any]]
    due_at: datetime | None
    author_name: str | None
    source: str
    created_at: datetime
    answer_key: list[dict[str, Any]] | None = None


async def _names(db, ids: set[str | None]) -> dict[str, str]:
    wanted = {i for i in ids if i}
    if not wanted:
        return {}
    return {user.id: user.name for user in await db.scalars(select(User).where(User.id.in_(wanted)))}


def announcement_out(row: ClassAnnouncement, names: dict[str, str]) -> AnnouncementOut:
    return AnnouncementOut(
        id=row.id,
        title=row.title,
        body=row.body,
        audience=row.audience,
        author_name=names.get(row.author_id or ""),
        source=row.source,
        created_at=row.created_at,
    )


def assignment_out(row: Assignment, names: dict[str, str], *, teacher: bool) -> AssignmentOut:
    return AssignmentOut(
        id=row.id,
        title=row.title,
        instructions=row.instructions,
        questions=list(row.questions or []),
        due_at=row.due_at,
        author_name=names.get(row.author_id or ""),
        source=row.source,
        created_at=row.created_at,
        answer_key=list(row.answer_key or []) if teacher and row.answer_key else None,
    )


# ---------------- Announcements ----------------


@router.get("/classes/{class_id}/announcements", response_model=list[AnnouncementOut])
async def list_announcements(class_id: str, user: CurrentUser, db: DbSession) -> list[AnnouncementOut]:
    room, role = await classes.load_class(db, class_id, user)
    rows = list(
        await db.scalars(
            select(ClassAnnouncement)
            .where(ClassAnnouncement.class_id == room.id, ClassAnnouncement.audience.in_(AUDIENCES[role]))
            .order_by(ClassAnnouncement.created_at.desc())
            .limit(FEED_LIMIT)
        )
    )
    names = await _names(db, {row.author_id for row in rows})
    return [announcement_out(row, names) for row in rows]


@router.post("/classes/{class_id}/announcements", response_model=AnnouncementOut, status_code=status.HTTP_201_CREATED)
async def post_announcement(class_id: str, payload: AnnouncementIn, user: CurrentUser, db: DbSession) -> AnnouncementOut:
    room, _ = await classes.load_class(db, class_id, user, {"teacher"})
    if dify_rules.contains_blocked_keyword(payload.title) or dify_rules.contains_blocked_keyword(payload.body):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, BLOCKED)
    row = ClassAnnouncement(
        class_id=room.id,
        author_id=user.id,
        title=payload.title.strip(),
        body=payload.body.strip(),
        audience=payload.audience,
        source="ui",
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return announcement_out(row, {user.id: user.name})


@router.delete("/classes/{class_id}/announcements/{announcement_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_announcement(class_id: str, announcement_id: str, user: CurrentUser, db: DbSession) -> None:
    room, _ = await classes.load_class(db, class_id, user, {"teacher"})
    row = await db.get(ClassAnnouncement, announcement_id)
    if row is None or row.class_id != room.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Không tìm thấy thông báo.")
    await db.delete(row)
    await db.commit()


# ---------------- Assignments ----------------


@router.get("/classes/{class_id}/assignments", response_model=list[AssignmentOut])
async def list_assignments(class_id: str, user: CurrentUser, db: DbSession) -> list[AssignmentOut]:
    room, role = await classes.load_class(db, class_id, user)
    rows = list(
        await db.scalars(
            select(Assignment)
            .where(Assignment.class_id == room.id)
            .order_by(Assignment.created_at.desc())
            .limit(FEED_LIMIT)
        )
    )
    names = await _names(db, {row.author_id for row in rows})
    return [assignment_out(row, names, teacher=role == "teacher") for row in rows]


async def _assignment(db, class_id: str, assignment_id: str) -> Assignment:
    row = await db.get(Assignment, assignment_id)
    if row is None or row.class_id != class_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Không tìm thấy bài luyện.")
    return row


@router.get("/classes/{class_id}/assignments/{assignment_id}", response_model=AssignmentOut)
async def get_assignment(class_id: str, assignment_id: str, user: CurrentUser, db: DbSession) -> AssignmentOut:
    room, role = await classes.load_class(db, class_id, user)
    row = await _assignment(db, room.id, assignment_id)
    return assignment_out(row, await _names(db, {row.author_id}), teacher=role == "teacher")


@router.delete("/classes/{class_id}/assignments/{assignment_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_assignment(class_id: str, assignment_id: str, user: CurrentUser, db: DbSession) -> None:
    room, _ = await classes.load_class(db, class_id, user, {"teacher"})
    row = await _assignment(db, room.id, assignment_id)
    await db.delete(row)
    await db.commit()
