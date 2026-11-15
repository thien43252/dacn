"""Group chats of one class (FR-039 to FR-047).

Members come from the class: teachers (with their subject), students, parents linked to the class's students, and
the agents usable in the class. When a student adds people, only classmates, the class's teachers and the student's
own linked parents qualify. Groups are fully private: only members know a group exists.
"""

from typing import Any

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.agents.service import available_agents
from app.auth.deps import CurrentUser, DbSession
from app.auth.models import User
from app.chat import service as chat_service
from app.chat import visibility
from app.chat.models import Conversation, ConversationMember
from app.chat.serialize import agent_card, conversation_out, role_label
from app.classes import service as classes
from app.classes.models import ClassMember, ClassRoom, ParentLink

router = APIRouter(prefix="/chat", tags=["chat"])
MAX_PEOPLE = 50
MAX_AGENTS = 8


class GroupIn(BaseModel):
    class_id: str
    title: str = Field(min_length=1, max_length=120)
    members: list[str] = Field(default_factory=list, max_length=MAX_PEOPLE)
    agents: list[str] = Field(default_factory=list, max_length=MAX_AGENTS)
    default_agent: str | None = None


class GroupPatch(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=120)
    default_agent: str | None = None


class MembersIn(BaseModel):
    users: list[str] = Field(default_factory=list, max_length=MAX_PEOPLE)
    agents: list[str] = Field(default_factory=list, max_length=MAX_AGENTS)
    can_see_history: bool = False


async def class_people(db, room: ClassRoom) -> dict[str, User]:
    people: dict[str, User] = {}
    owner = await db.get(User, room.owner_id)
    if owner:
        people[owner.id] = owner
    members = await db.scalars(
        select(User).join(ClassMember, ClassMember.user_id == User.id).where(ClassMember.class_id == room.id)
    )
    for person in members:
        people[person.id] = person
    student_ids = [p.id for p in people.values() if p.role == "student"]
    if student_ids:
        parents = await db.scalars(
            select(User).join(ParentLink, ParentLink.parent_id == User.id).where(ParentLink.student_id.in_(student_ids))
        )
        for parent in parents:
            people[parent.id] = parent
    return {key: value for key, value in people.items() if value.is_active}


async def addable_people(db, actor: User, actor_role: str, room: ClassRoom) -> dict[str, User]:
    """FR-039: a student may add classmates, the class's teachers and their own linked parents, nobody else."""
    people = await class_people(db, room)
    if actor_role != "student":
        return {key: value for key, value in people.items() if key != actor.id}
    own_parents = set(await db.scalars(select(ParentLink.parent_id).where(ParentLink.student_id == actor.id)))
    return {
        key: person
        for key, person in people.items()
        if key != actor.id and (person.role in ("student", "teacher") or key in own_parents)
    }


async def addable_agents(db, actor: User, actor_role: str, room: ClassRoom):
    """Agents a member may add: those usable in the class. Teachers may add agents made for any role of the class
    (e.g. a students' tutor); each agent still answers under the role and policy of whoever calls it."""
    roles = ("teacher", "student", "parent") if actor_role == "teacher" else (actor_role,)
    found = {}
    for role in roles:
        for agent in await available_agents(db, actor, room, role):
            # FR-003: only agents installed in the class (or the platform's own) join a group; a member's personal or
            # self-made agent needs certification and the teacher's approval to enter the class first.
            if agent.source not in ("class", "platform"):
                continue
            found.setdefault(agent.slug, agent)
    return list(found.values())


async def _load_group(db, user: User, conversation_id: str, *, admin: bool = False):
    conversation, member = await visibility.viewable(db, user, conversation_id)
    if conversation.kind != "group":
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Không tìm thấy nhóm.")
    if admin and not member.is_admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Chỉ người tạo nhóm và giáo viên trong nhóm được làm việc này.")
    room = await db.get(ClassRoom, conversation.class_id)
    return conversation, member, room


async def _add_members(db, conversation, actor, actor_role, room, users, agents, can_see_history):
    addable = await addable_people(db, actor, actor_role, room)
    unknown = [user_id for user_id in users if user_id not in addable]
    if unknown:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Có người không thể thêm vào nhóm này.")
    usable = {agent.slug for agent in await addable_agents(db, actor, actor_role, room)}
    bad_agents = [slug for slug in agents if slug not in usable]
    if bad_agents:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Có agent không dùng được trong lớp này.")
    current = list(
        await db.scalars(
            select(ConversationMember).where(
                ConversationMember.conversation_id == conversation.id, ConversationMember.left_at.is_(None)
            )
        )
    )
    people_count = sum(1 for m in current if m.user_id) + len(
        [u for u in users if u not in {m.user_id for m in current}]
    )
    agent_count = sum(1 for m in current if m.agent_slug) + len(
        [a for a in agents if a not in {m.agent_slug for m in current}]
    )
    if people_count > MAX_PEOPLE or agent_count > MAX_AGENTS:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, f"Nhóm tối đa {MAX_PEOPLE} người và {MAX_AGENTS} agent."
        )
    for user_id in users:
        await chat_service.add_member(
            db,
            conversation,
            user_id=user_id,
            is_admin=addable[user_id].role == "teacher",
            can_see_history=can_see_history,
        )
    for slug in agents:
        await chat_service.add_member(db, conversation, agent_slug=slug, can_see_history=True)


@router.get("/groups/candidates")
async def candidates(user: CurrentUser, db: DbSession, class_id: str = Query()) -> dict[str, Any]:
    room, role = await classes.load_class(db, class_id, user)
    people = await addable_people(db, user, role, room)
    agents = await addable_agents(db, user, role, room)
    return {
        "people": [
            {
                "id": person.id,
                "name": person.name,
                "role": person.role,
                "role_label": await role_label(db, person, room.id),
            }
            for person in sorted(people.values(), key=lambda p: (p.role, p.name))
        ],
        "agents": [{"slug": a.slug, "name": a.manifest.name, "avatar": a.manifest.avatar} for a in agents],
        "can_create": role == "teacher" or bool((room.policy or {}).get("members_can_create_groups", True)),
    }


@router.get("/groups/{conversation_id}/candidates")
async def group_candidates(conversation_id: str, user: CurrentUser, db: DbSession) -> dict[str, Any]:
    conversation, _, room = await _load_group(db, user, conversation_id)
    data = await candidates(user, db, room.id)
    present = set(
        await db.scalars(
            select(ConversationMember.user_id).where(
                ConversationMember.conversation_id == conversation.id, ConversationMember.left_at.is_(None)
            )
        )
    )
    data["people"] = [person for person in data["people"] if person["id"] not in present]
    return data


@router.post("/groups", status_code=status.HTTP_201_CREATED)
async def create_group(payload: GroupIn, user: CurrentUser, db: DbSession) -> dict[str, Any]:
    room, role = await classes.load_class(db, payload.class_id, user)
    if role != "teacher" and not (room.policy or {}).get("members_can_create_groups", True):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "Giáo viên chưa cho học sinh và phụ huynh tạo nhóm trong lớp này."
        )
    if role == "student" and not await classes.student_can_use_agents(db, room, user.id) and payload.agents:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Cần phụ huynh đồng ý trước khi em dùng agent.")
    conversation = Conversation(user_id=user.id, class_id=room.id, kind="group", title=payload.title.strip())
    db.add(conversation)
    await db.flush()
    await chat_service.add_member(db, conversation, user_id=user.id, is_admin=True, can_see_history=True)
    members = [member for member in dict.fromkeys(payload.members) if member != user.id]
    agents = list(dict.fromkeys(payload.agents))
    await _add_members(db, conversation, user, role, room, members, agents, True)
    if payload.default_agent and payload.default_agent in agents:
        conversation.default_agent_slug = payload.default_agent
    elif "tro-ly-lop" in agents:
        conversation.default_agent_slug = "tro-ly-lop"
    elif agents:
        conversation.default_agent_slug = agents[0]
    await db.commit()
    return await conversation_out(db, conversation, user.id)


@router.patch("/groups/{conversation_id}")
async def update_group(conversation_id: str, payload: GroupPatch, user: CurrentUser, db: DbSession) -> dict[str, Any]:
    conversation, _, _ = await _load_group(db, user, conversation_id, admin=True)
    if payload.title:
        conversation.title = payload.title.strip()
    if payload.default_agent is not None:
        is_member = await db.scalar(
            select(ConversationMember.id).where(
                ConversationMember.conversation_id == conversation.id,
                ConversationMember.agent_slug == payload.default_agent,
                ConversationMember.left_at.is_(None),
            )
        )
        if not is_member:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Agent mặc định phải là thành viên của nhóm.")
        conversation.default_agent_slug = payload.default_agent
    await db.commit()
    return await conversation_out(db, conversation, user.id)


@router.get("/groups/{conversation_id}/members")
async def list_members(conversation_id: str, user: CurrentUser, db: DbSession) -> list[dict[str, Any]]:
    conversation, _, room = await _load_group(db, user, conversation_id)
    rows = list(
        await db.scalars(
            select(ConversationMember).where(
                ConversationMember.conversation_id == conversation.id, ConversationMember.left_at.is_(None)
            )
        )
    )
    out = []
    for member in rows:
        if member.user_id:
            person = await db.get(User, member.user_id)
            out.append(
                {
                    "id": member.id,
                    "kind": "user",
                    "user_id": member.user_id,
                    "name": person.name if person else "",
                    "role_label": await role_label(db, person, room.id) if person else "",
                    "is_admin": member.is_admin,
                }
            )
        else:
            card = await agent_card(db, member.agent_slug) or {}
            out.append(
                {
                    "id": member.id,
                    "kind": "agent",
                    "agent_slug": member.agent_slug,
                    "name": card.get("name"),
                    "avatar": card.get("avatar"),
                    "role_label": "Agent",
                    "is_admin": False,
                }
            )
    return out


@router.post("/groups/{conversation_id}/members")
async def add_members(
    conversation_id: str, payload: MembersIn, user: CurrentUser, db: DbSession
) -> list[dict[str, Any]]:
    conversation, _, room = await _load_group(db, user, conversation_id, admin=True)
    _, role = await classes.load_class(db, room.id, user)
    await _add_members(
        db,
        conversation,
        user,
        role,
        room,
        list(dict.fromkeys(payload.users)),
        list(dict.fromkeys(payload.agents)),
        payload.can_see_history,
    )
    await db.commit()
    return await list_members(conversation_id, user, db)


@router.delete("/groups/{conversation_id}/members/{member_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_member(conversation_id: str, member_id: str, user: CurrentUser, db: DbSession) -> None:
    from datetime import UTC, datetime

    conversation, me, _ = await _load_group(db, user, conversation_id)
    member = await db.get(ConversationMember, member_id)
    if member is None or member.conversation_id != conversation.id or member.left_at is not None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Không tìm thấy thành viên.")
    if member.user_id != user.id and not me.is_admin:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "Chỉ người tạo nhóm và giáo viên trong nhóm được bớt thành viên."
        )
    member.left_at = datetime.now(UTC)
    if member.agent_slug and conversation.default_agent_slug == member.agent_slug:
        conversation.default_agent_slug = None
    await db.commit()
