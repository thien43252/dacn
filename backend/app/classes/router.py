from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select

from app.auth.deps import CurrentUser, DbSession, require_roles
from app.auth.models import Role, User
from app.auth.service import get_user_by_email
from app.classes import service
from app.classes.models import ClassMember, ClassRoom
from app.classes.schemas import (
    AddMemberIn,
    ChildClassOut,
    ChildOut,
    ClassIn,
    ClassOut,
    ClassPatch,
    ConsentIn,
    ConsentOut,
    JoinIn,
    LinkChildIn,
    LinkCodeOut,
    LinkParentIn,
    MemberOut,
    PersonOut,
    PolicyModel,
)

router = APIRouter(tags=["classes"])
Teacher = Annotated[User, Depends(require_roles(Role.TEACHER, Role.ADMIN))]
Student = Annotated[User, Depends(require_roles(Role.STUDENT))]
Parent = Annotated[User, Depends(require_roles(Role.PARENT))]


async def _out(db: DbSession, room: ClassRoom, role: str, children: list[str] | None = None) -> ClassOut:
    owner = await db.get(User, room.owner_id)
    return ClassOut(
        id=room.id,
        name=room.name,
        subject=room.subject,
        grade=room.grade,
        description=room.description,
        teacher_name=owner.name if owner else "",
        my_role=role,
        student_count=await service.student_count(db, room.id),
        require_parent_consent=room.require_parent_consent,
        archived=room.archived,
        created_at=room.created_at,
        join_code=room.join_code if role == "teacher" else None,
        children=children or [],
    )


def _person(user: User) -> PersonOut:
    return PersonOut(id=user.id, name=user.name, email=user.email)


@router.post("/classes", response_model=ClassOut, status_code=status.HTTP_201_CREATED)
async def create_class(payload: ClassIn, user: Teacher, db: DbSession) -> ClassOut:
    room = await service.create_class(db, user, **payload.model_dump())
    return await _out(db, room, "teacher")


@router.get("/classes", response_model=list[ClassOut])
async def list_classes(user: CurrentUser, db: DbSession) -> list[ClassOut]:
    return [await _out(db, room, role, kids) for room, role, kids in await service.classes_for(db, user)]


@router.post("/classes/join", response_model=ClassOut)
async def join_class(payload: JoinIn, user: CurrentUser, db: DbSession) -> ClassOut:
    room = await service.join_by_code(db, user, payload.code)
    return await _out(db, room, "student")


@router.get("/classes/{class_id}", response_model=ClassOut)
async def get_class(class_id: str, user: CurrentUser, db: DbSession) -> ClassOut:
    room, role = await service.load_class(db, class_id, user)
    kids = []
    if role == "parent":
        kids = [kid for room_, _, kids_ in await service.classes_for(db, user) if room_.id == room.id for kid in kids_]
    return await _out(db, room, role, kids)


@router.patch("/classes/{class_id}", response_model=ClassOut)
async def update_class(class_id: str, payload: ClassPatch, user: CurrentUser, db: DbSession) -> ClassOut:
    room, role = await service.load_class(db, class_id, user, {"teacher"})
    for key, value in payload.model_dump(exclude_unset=True).items():
        if value is not None:
            setattr(room, key, value)
    await db.commit()
    await db.refresh(room)
    return await _out(db, room, role)


@router.post("/classes/{class_id}/join-code", response_model=ClassOut)
async def rotate_join_code(class_id: str, user: CurrentUser, db: DbSession) -> ClassOut:
    """Issues a new code; the old one stops working, existing members stay."""
    room, role = await service.load_class(db, class_id, user, {"teacher"})
    room.join_code = await service.unique_code(db, ClassRoom.join_code)
    await db.commit()
    await db.refresh(room)
    return await _out(db, room, role)


@router.get("/classes/{class_id}/members", response_model=list[MemberOut])
async def list_members(class_id: str, user: CurrentUser, db: DbSession) -> list[MemberOut]:
    room, _ = await service.load_class(db, class_id, user, {"teacher"})
    rows = list(
        await db.execute(
            select(ClassMember, User)
            .join(User, User.id == ClassMember.user_id)
            .where(ClassMember.class_id == room.id)
            .order_by(ClassMember.role.desc(), User.name)
        )
    )
    student_ids = [member.user_id for member, _ in rows if member.role == "student"]
    parents = await service.parents_of(db, student_ids)
    out = []
    for member, person in rows:
        can_use = member.role == "teacher" or await service.student_can_use_agents(db, room, person.id)
        out.append(
            MemberOut(
                user_id=person.id,
                name=person.name,
                email=person.email,
                role=member.role,
                joined_at=member.joined_at,
                parents=[_person(parent) for parent in parents.get(person.id, [])],
                can_use_agents=can_use,
            )
        )
    return out


@router.post("/classes/{class_id}/members", response_model=list[MemberOut], status_code=status.HTTP_201_CREATED)
async def add_member(class_id: str, payload: AddMemberIn, user: CurrentUser, db: DbSession) -> list[MemberOut]:
    room, _ = await service.load_class(db, class_id, user, {"teacher"})
    student = await get_user_by_email(db, payload.email.strip().lower())
    if student is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, "Chưa có tài khoản với email này. Hãy gửi mã lớp để học sinh tự tham gia."
        )
    await service.add_student(db, room, student)
    return await list_members(class_id, user, db)


@router.delete("/classes/{class_id}/members/{member_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_member(class_id: str, member_id: str, user: CurrentUser, db: DbSession) -> None:
    room, _ = await service.load_class(db, class_id, user, {"teacher"})
    if member_id == room.owner_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Không thể xoá giáo viên chủ nhiệm khỏi lớp.")
    member = await db.scalar(
        select(ClassMember).where(ClassMember.class_id == room.id, ClassMember.user_id == member_id)
    )
    if member:
        await db.delete(member)
        await db.commit()


@router.post("/classes/{class_id}/parents", response_model=list[MemberOut])
async def link_parent_to_student(
    class_id: str, payload: LinkParentIn, user: CurrentUser, db: DbSession
) -> list[MemberOut]:
    room, _ = await service.load_class(db, class_id, user, {"teacher"})
    is_member = await db.scalar(
        select(ClassMember.id).where(
            ClassMember.class_id == room.id, ClassMember.user_id == payload.student_id, ClassMember.role == "student"
        )
    )
    student = await db.get(User, payload.student_id) if is_member else None
    if student is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Học sinh không có trong lớp.")
    parent = await get_user_by_email(db, payload.parent_email.strip().lower())
    if parent is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Chưa có tài khoản phụ huynh với email này.")
    await service.link_parent(db, parent, student)
    return await list_members(class_id, user, db)


@router.get("/classes/{class_id}/policy", response_model=PolicyModel)
async def get_policy(class_id: str, user: CurrentUser, db: DbSession) -> PolicyModel:
    room, _ = await service.load_class(db, class_id, user, {"teacher"})
    return PolicyModel.model_validate(room.policy or {})


@router.put("/classes/{class_id}/policy", response_model=PolicyModel)
async def put_policy(class_id: str, payload: PolicyModel, user: CurrentUser, db: DbSession) -> PolicyModel:
    room, _ = await service.load_class(db, class_id, user, {"teacher"})
    room.policy = payload.model_dump()
    await db.commit()
    return payload


# ---- Student: personal link code for parents ----


@router.get("/me/link-code", response_model=LinkCodeOut)
async def my_link_code(user: Student, db: DbSession) -> LinkCodeOut:
    code = await service.link_code_for(db, user)
    parents = (await service.parents_of(db, [user.id]))[user.id]
    return LinkCodeOut(code=code, parents=[_person(parent) for parent in parents])


# ---- Parent: children and consent ----


async def _children(db: DbSession, parent: User) -> list[ChildOut]:
    child_ids = await service.children_of(db, parent.id)
    consents = await service.consents_for(db, child_ids)
    out = []
    for child_id in child_ids:
        child = await db.get(User, child_id)
        if child is None:
            continue
        rooms = await service.classes_for(db, child)
        mine = next((consent for consent in consents[child_id] if consent.parent_id == parent.id), None)
        classes = []
        for room, role, _ in rooms:
            if role != "student":
                continue
            owner = await db.get(User, room.owner_id)
            classes.append(
                ChildClassOut(
                    id=room.id,
                    name=room.name,
                    subject=room.subject,
                    grade=room.grade,
                    teacher_name=owner.name if owner else "",
                )
            )
        out.append(
            ChildOut(
                id=child.id,
                name=child.name,
                email=child.email,
                classes=classes,
                consent=ConsentOut(
                    allow_agents=mine.allow_agents if mine else False,
                    allow_progress_reports=mine.allow_progress_reports if mine else True,
                    updated_at=mine.updated_at if mine else None,
                ),
            )
        )
    return out


@router.get("/parent/children", response_model=list[ChildOut])
async def list_children(user: Parent, db: DbSession) -> list[ChildOut]:
    return await _children(db, user)


@router.post("/parent/children", response_model=list[ChildOut], status_code=status.HTTP_201_CREATED)
async def link_child(payload: LinkChildIn, user: Parent, db: DbSession) -> list[ChildOut]:
    student = await service.student_by_link_code(db, payload.code)
    if student is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, "Mã liên kết không đúng. Hãy hỏi con mã trong mục “Lớp của tôi”."
        )
    await service.link_parent(db, user, student)
    return await _children(db, user)


@router.put("/parent/children/{student_id}/consent", response_model=ConsentOut)
async def put_consent(student_id: str, payload: ConsentIn, user: Parent, db: DbSession) -> ConsentOut:
    consent = await service.set_consent(db, user, student_id, payload.allow_agents, payload.allow_progress_reports)
    return ConsentOut(
        allow_agents=consent.allow_agents,
        allow_progress_reports=consent.allow_progress_reports,
        updated_at=consent.updated_at,
    )
