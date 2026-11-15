"""Who may read or change LMS data in a class (research R15).

Class roles come from `classes.service.class_role`: teacher (owner or co-teacher member), student, parent (of a student
member). Admins act as teachers. Personal data (attempts, submissions, grades) always goes through `resolve_student`.
"""

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.models import User
from app.classes import service as classes
from app.classes.models import ClassMember, ClassRoom

ARCHIVED = "Lớp đã lưu trữ, chỉ xem được."


async def load_lms_class(
    db: AsyncSession, class_id: str, user: User, roles: set[str] | None = None, *, write: bool = False
) -> tuple[ClassRoom, str]:
    """The class and the caller's role in it; 404 when not a member, 403 for a role outside `roles`, 409 when
    `write` is requested on an archived class."""
    room, role = await classes.load_class(db, class_id, user, roles)
    if write and room.archived:
        raise HTTPException(status.HTTP_409_CONFLICT, ARCHIVED)
    return room, role


def is_teacher(role: str) -> bool:
    return role == "teacher"


async def is_student_member(db: AsyncSession, class_id: str, student_id: str) -> bool:
    return bool(
        await db.scalar(
            select(func.count()).where(
                ClassMember.class_id == class_id, ClassMember.user_id == student_id, ClassMember.role == "student"
            )
        )
    )


async def student_ids(db: AsyncSession, class_id: str) -> list[str]:
    return list(
        await db.scalars(
            select(ClassMember.user_id).where(ClassMember.class_id == class_id, ClassMember.role == "student")
        )
    )


async def resolve_student(db: AsyncSession, room: ClassRoom, user: User, role: str, student_id: str | None) -> str:
    """The student whose data the caller may read: students always get themselves, parents only their own children in
    this class, teachers any student of the class. Anything else is 404 so ids of other students leak nothing."""
    if role == "student":
        return user.id
    if role == "parent":
        children = set(await classes.children_of(db, user.id))
        if student_id is None and len(children) == 1:
            student_id = next(iter(children))
        if student_id is None or student_id not in children or not await is_student_member(db, room.id, student_id):
            raise classes.not_found()
        return student_id
    if student_id is None or not await is_student_member(db, room.id, student_id):
        raise classes.not_found()
    return student_id


def require_teacher(role: str) -> None:
    if role != "teacher":
        raise classes.forbidden()


def require_student(role: str) -> None:
    if role != "student":
        raise classes.forbidden()
