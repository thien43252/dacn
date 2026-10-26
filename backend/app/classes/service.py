"""Class membership, parent links and consent. Every access check for class-scoped data goes through here."""

import secrets

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.models import Role, User
from app.classes.models import DEFAULT_POLICY, ClassMember, ClassRoom, Consent, ParentLink, StudentLinkCode

# No 0/O or 1/I so codes read cleanly off a projector or a phone screen.
CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def new_code(length: int = 6) -> str:
    return "".join(secrets.choice(CODE_ALPHABET) for _ in range(length))


def normalize_code(code: str) -> str:
    return "".join(code.split()).replace("-", "").upper()


def not_found() -> HTTPException:
    # One answer for "does not exist" and "not yours", so class IDs cannot be probed.
    return HTTPException(status.HTTP_404_NOT_FOUND, "Không tìm thấy lớp học.")


def forbidden(message: str = "Bạn không có quyền thực hiện thao tác này trong lớp.") -> HTTPException:
    return HTTPException(status.HTTP_403_FORBIDDEN, message)


async def unique_code(db: AsyncSession, column) -> str:
    while True:
        code = new_code()
        if await db.scalar(select(func.count()).where(column == code)) == 0:
            return code


async def create_class(db: AsyncSession, owner: User, **fields) -> ClassRoom:
    room = ClassRoom(
        owner_id=owner.id, join_code=await unique_code(db, ClassRoom.join_code), policy=dict(DEFAULT_POLICY)
    )
    for key, value in fields.items():
        setattr(room, key, value)
    db.add(room)
    await db.flush()
    db.add(ClassMember(class_id=room.id, user_id=owner.id, role="teacher"))
    await db.commit()
    await db.refresh(room)
    return room


async def children_of(db: AsyncSession, parent_id: str) -> list[str]:
    return list(await db.scalars(select(ParentLink.student_id).where(ParentLink.parent_id == parent_id)))


async def class_role(db: AsyncSession, room: ClassRoom, user: User) -> str | None:
    """The user's role in this class: teacher, student, parent (of a student member), or None."""
    member_role = await db.scalar(
        select(ClassMember.role).where(ClassMember.class_id == room.id, ClassMember.user_id == user.id)
    )
    if member_role:
        return member_role
    if user.role == Role.PARENT:
        children = await children_of(db, user.id)
        if children and await db.scalar(
            select(func.count()).where(ClassMember.class_id == room.id, ClassMember.user_id.in_(children))
        ):
            return "parent"
    return None


async def load_class(
    db: AsyncSession, class_id: str, user: User, roles: set[str] | None = None
) -> tuple[ClassRoom, str]:
    """Fetches a class the user belongs to; `roles` narrows which class roles may proceed."""
    room = await db.get(ClassRoom, class_id)
    if room is None:
        raise not_found()
    role = await class_role(db, room, user)
    if role is None and user.role != Role.ADMIN:
        raise not_found()
    role = role or "teacher"  # admins act with teacher rights for moderation
    if roles is not None and role not in roles:
        raise forbidden()
    return room, role


async def student_count(db: AsyncSession, class_id: str) -> int:
    return (
        await db.scalar(select(func.count()).where(ClassMember.class_id == class_id, ClassMember.role == "student"))
        or 0
    )


async def classes_for(db: AsyncSession, user: User) -> list[tuple[ClassRoom, str, list[str]]]:
    """(class, my role, children in class) for every class the user can see."""
    if user.role == Role.PARENT:
        children = await children_of(db, user.id)
        if not children:
            return []
        rows = await db.execute(
            select(ClassRoom, ClassMember.user_id)
            .join(ClassMember, ClassMember.class_id == ClassRoom.id)
            .where(ClassMember.user_id.in_(children), ClassMember.role == "student")
            .order_by(ClassRoom.created_at.desc())
        )
        grouped: dict[str, tuple[ClassRoom, list[str]]] = {}
        for room, child_id in rows:
            grouped.setdefault(room.id, (room, []))[1].append(child_id)
        return [(room, "parent", kids) for room, kids in grouped.values()]

    rows = await db.execute(
        select(ClassRoom, ClassMember.role)
        .join(ClassMember, ClassMember.class_id == ClassRoom.id)
        .where(ClassMember.user_id == user.id)
        .order_by(ClassRoom.created_at.desc())
    )
    return [(room, role, []) for room, role in rows]


async def join_by_code(db: AsyncSession, user: User, code: str) -> ClassRoom:
    if user.role != Role.STUDENT:
        raise forbidden("Chỉ tài khoản học sinh tham gia lớp bằng mã. Phụ huynh liên kết với con bằng mã của con.")
    room = await db.scalar(select(ClassRoom).where(ClassRoom.join_code == normalize_code(code)))
    if room is None or room.archived:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Mã lớp không đúng hoặc lớp đã đóng.")
    await add_student(db, room, user)
    return room


async def add_student(db: AsyncSession, room: ClassRoom, student: User) -> None:
    if student.role != Role.STUDENT:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Tài khoản này không phải tài khoản học sinh.")
    exists = await db.scalar(
        select(func.count()).where(ClassMember.class_id == room.id, ClassMember.user_id == student.id)
    )
    if not exists:
        db.add(ClassMember(class_id=room.id, user_id=student.id, role="student"))
        await db.commit()


async def link_parent(db: AsyncSession, parent: User, student: User) -> None:
    if parent.role != Role.PARENT:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Tài khoản này không phải tài khoản phụ huynh.")
    exists = await db.scalar(
        select(func.count()).where(ParentLink.parent_id == parent.id, ParentLink.student_id == student.id)
    )
    if not exists:
        db.add(ParentLink(parent_id=parent.id, student_id=student.id))
        await db.commit()


async def link_code_for(db: AsyncSession, student: User) -> str:
    row = await db.get(StudentLinkCode, student.id)
    if row is None:
        row = StudentLinkCode(student_id=student.id, code=await unique_code(db, StudentLinkCode.code))
        db.add(row)
        await db.commit()
    return row.code


async def student_by_link_code(db: AsyncSession, code: str) -> User | None:
    row = await db.scalar(select(StudentLinkCode).where(StudentLinkCode.code == normalize_code(code)))
    return await db.get(User, row.student_id) if row else None


async def parents_of(db: AsyncSession, student_ids: list[str]) -> dict[str, list[User]]:
    result: dict[str, list[User]] = {student_id: [] for student_id in student_ids}
    if not student_ids:
        return result
    rows = await db.execute(
        select(ParentLink.student_id, User)
        .join(User, User.id == ParentLink.parent_id)
        .where(ParentLink.student_id.in_(student_ids))
    )
    for student_id, parent in rows:
        result[student_id].append(parent)
    return result


async def consents_for(db: AsyncSession, student_ids: list[str]) -> dict[str, list[Consent]]:
    result: dict[str, list[Consent]] = {student_id: [] for student_id in student_ids}
    if student_ids:
        for consent in await db.scalars(select(Consent).where(Consent.student_id.in_(student_ids))):
            result[consent.student_id].append(consent)
    return result


async def student_can_use_agents(db: AsyncSession, room: ClassRoom, student_id: str) -> bool:
    """Consent gate: in a class that requires it, at least one linked guardian must have allowed agents."""
    if not room.require_parent_consent:
        return True
    return bool(
        await db.scalar(select(func.count()).where(Consent.student_id == student_id, Consent.allow_agents.is_(True)))
    )


async def set_consent(
    db: AsyncSession, parent: User, student_id: str, allow_agents: bool, allow_reports: bool
) -> Consent:
    if student_id not in await children_of(db, parent.id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Không tìm thấy học sinh đã liên kết.")
    consent = await db.scalar(select(Consent).where(Consent.parent_id == parent.id, Consent.student_id == student_id))
    if consent is None:
        consent = Consent(parent_id=parent.id, student_id=student_id)
        db.add(consent)
    consent.allow_agents = allow_agents
    consent.allow_progress_reports = allow_reports
    await db.commit()
    await db.refresh(consent)
    return consent
