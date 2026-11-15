"""Create the demo accounts shown on the login page plus one demo class. Idempotent: existing data is left untouched,
so dev.ps1 runs it on every start (`--ensure`) to add what a newer version of the demo needs.

Usage (from backend/): uv run python -m scripts.seed_demo [--ensure]
"""

import asyncio
import shutil
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import yaml
from sqlalchemy import select

from app.agents.manifest import AgentManifest
from app.agents.models import Agent, AgentVersion, Installation
from app.agents.service import latest_version, sync_platform_agents
from app.auth.models import Role, User
from app.auth.service import EmailTakenError, create_user, get_user_by_email
from app.chat.models import ChatMessage, Conversation, ConversationMember
from app.classes import service as classes
from app.classes.models import ClassMember, ClassRoom
from app.db import dispose_engine, get_session
from app.knowledge import service as knowledge
from app.knowledge.models import Document
from app.orchestration.models import ALWAYS_ASK, ApprovalKindMode

SEED_DIR = Path(__file__).resolve().parents[2] / "seed"
EVAL_DIR = SEED_DIR.parent / "eval"
# Teacher-built agents for the certification demo: one good, one that static checks reject.
DEMO_AGENTS = ["on-thi-hoa-9", "giai-bai-nhanh"]
# (days ago, agent, question, answer) for the parent report and class progress.
DEMO_HISTORY = [
    (
        6,
        "gia-su-toan",
        "Mình chưa hiểu cách chuyển vế trong phương trình bậc nhất.",
        "Khi chuyển một hạng tử sang vế kia, em đổi dấu của nó. Em thử với 3x + 7 = 2x - 5 nhé: bước đầu tiên em sẽ chuyển hạng tử nào?",
    ),
    (5, "gia-su-toan", "Em ra x = -12 có đúng không ạ?", "Đúng rồi! Em đã chuyển vế và rút gọn chính xác."),
    (
        5,
        "on-tap-tai-lieu",
        "Tóm tắt chương 3 trong tài liệu cô gửi.",
        "Chương 3 gồm: định nghĩa phương trình bậc nhất một ẩn, quy tắc chuyển vế, quy tắc nhân, các bước giải (Nguồn: Chương 3).",
    ),
    (
        3,
        "gia-su-toan",
        "Phương trình tích là gì?",
        "Phương trình tích có dạng A(x)·B(x) = 0. Em nghĩ xem: tích bằng 0 khi nào?",
    ),
    (
        2,
        "cham-van",
        "Nhận xét mở bài của mình về mùa thu.",
        "Điểm mạnh: hình ảnh gợi cảm. Cần sửa: câu thứ hai hơi dài. Em thử tách thành hai câu xem sao?",
    ),
    (
        1,
        "gia-su-toan",
        "Giải bài toán chuyển động bằng phương trình thế nào?",
        "Em gọi đại lượng cần tìm là x trước nhé. Đề bài hỏi gì?",
    ),
    (
        0,
        "on-tap-tai-lieu",
        "Cho mình 3 câu hỏi ôn tập chương 3.",
        "Câu 1: Phương trình bậc nhất một ẩn có dạng nào? Câu 2: ... Em trả lời xong mình chấm nhé.",
    ),
]
CLASS_AGENTS = ["gia-su-toan", "on-tap-tai-lieu", "tao-de", "cham-van"]

DEMO_PASSWORD = "Demo123!"
DEMO_ACCOUNTS = [
    ("Cô Nguyễn Thu Hà", "teacher@demo.edu.vn", Role.TEACHER),
    ("Nguyễn Minh Anh", "student@demo.edu.vn", Role.STUDENT),
    ("Nguyễn Văn Bình", "parent@demo.edu.vn", Role.PARENT),
    ("Quản trị viên", "admin@demo.edu.vn", Role.ADMIN),
    ("Trần Gia Bảo", "bao@demo.edu.vn", Role.STUDENT),
    # Feature 003: a subject teacher and a second family, for groups and questions to people.
    ("Thầy Lê Văn Toàn", "toan@demo.edu.vn", Role.TEACHER),
    ("Phạm Thanh Bình", "student2@demo.edu.vn", Role.STUDENT),
    ("Phạm Văn Hùng", "parent2@demo.edu.vn", Role.PARENT),
]
DEMO_GROUP = "Ôn thi HK1 - Toán 8A1"
DEMO_CLASS = {
    "name": "Toán 8A1",
    "subject": "toan",
    "grade": 8,
    "description": "Lớp demo: phương trình bậc nhất và hình học lớp 8.",
}


async def seed_accounts(db) -> dict[str, User]:
    users: dict[str, User] = {}
    for name, email, role in DEMO_ACCOUNTS:
        try:
            users[email] = await create_user(db, name=name, email=email, password=DEMO_PASSWORD, role=role)
            print(f"created {role.value:8} {email}")
        except EmailTakenError:
            users[email] = await get_user_by_email(db, email)
            print(f"exists  {role.value:8} {email}")
    return users


async def install(db, agent_slug: str, *, installed_by: User, class_id: str | None = None, user_id: str | None = None):
    agent = await db.scalar(select(Agent).where(Agent.slug == agent_slug))
    version = await latest_version(db, agent.id)
    scope = "class" if class_id else "personal"
    existing = await db.scalar(
        select(Installation).where(
            Installation.agent_id == agent.id,
            Installation.scope == scope,
            Installation.class_id == class_id if class_id else Installation.user_id == user_id,
        )
    )
    if existing is not None and agent.is_platform and existing.agent_version_id != version.id:
        # Demo installations follow the platform's latest version (e.g. feature 003 added handoff grants).
        existing.agent_version_id = version.id
        print(f"updated {agent_slug} ({scope}) to v{version.version}")
    if existing is None:
        db.add(
            Installation(
                agent_id=agent.id,
                agent_version_id=version.id,
                scope=scope,
                class_id=class_id,
                user_id=user_id,
                installed_by=installed_by.id,
            )
        )
        print(f"installed {agent_slug} ({scope})")
    await db.commit()


async def seed_document(db, room: ClassRoom, teacher: User) -> None:
    source = SEED_DIR / "documents" / "chuong-3-phuong-trinh-bac-nhat.md"
    title = "Chương 3 - Phương trình bậc nhất một ẩn"
    if await db.scalar(select(Document.id).where(Document.class_id == room.id, Document.title == title)):
        return
    document = Document(
        class_id=room.id,
        uploaded_by=teacher.id,
        title=title,
        filename=source.name,
        content_type="text/markdown",
        size_bytes=source.stat().st_size,
        storage_path="",
    )
    db.add(document)
    await db.flush()
    target = knowledge.storage_root() / room.id / f"{document.id}.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, target)
    document.storage_path = str(target)
    await db.commit()
    await knowledge.process_document(document.id)
    print(f"document {title}")


async def seed_class(db, users: dict[str, User]) -> None:
    teacher = users["teacher@demo.edu.vn"]
    query = select(ClassRoom).where(ClassRoom.owner_id == teacher.id, ClassRoom.name == DEMO_CLASS["name"])
    room = await db.scalar(query)
    if room is None:
        room = await classes.create_class(db, teacher, **DEMO_CLASS)
        print(f"created class {room.name} (code {room.join_code})")
    for email in ("student@demo.edu.vn", "bao@demo.edu.vn", "student2@demo.edu.vn"):
        await classes.add_student(db, room, users[email])
    student, parent = users["student@demo.edu.vn"], users["parent@demo.edu.vn"]
    await classes.link_parent(db, parent, student)
    await classes.set_consent(db, parent, student.id, allow_agents=True, allow_reports=True)
    second, second_parent = users["student2@demo.edu.vn"], users["parent2@demo.edu.vn"]
    await classes.link_parent(db, second_parent, second)
    await classes.set_consent(db, second_parent, second.id, allow_agents=True, allow_reports=True)
    await seed_subject_teacher(db, room, users["toan@demo.edu.vn"], "toan")
    # Bảo has no linked parent, so the consent gate is visible in the demo.
    for slug in CLASS_AGENTS:
        await install(db, slug, installed_by=teacher, class_id=room.id)
    await install(db, "tro-ly-phu-huynh", installed_by=parent, user_id=parent.id)
    await seed_document(db, room, teacher)
    await seed_history(db, room, student)
    await seed_teacher_agents(db, teacher)
    await seed_group(db, room, users)


async def seed_subject_teacher(db, room: ClassRoom, teacher: User, subject: str) -> None:
    member = await db.scalar(
        select(ClassMember).where(ClassMember.class_id == room.id, ClassMember.user_id == teacher.id)
    )
    if member is None:
        db.add(ClassMember(class_id=room.id, user_id=teacher.id, role="teacher", subject=subject))
        print(f"subject teacher {teacher.email} ({subject})")
    elif member.subject != subject:
        member.subject = subject
    await db.commit()


async def seed_group(db, room: ClassRoom, users: dict[str, User]) -> None:
    """A demo group: homeroom and maths teachers, two students, one parent, the class assistant and the tutor."""
    exists = await db.scalar(
        select(Conversation.id).where(Conversation.class_id == room.id, Conversation.title == DEMO_GROUP)
    )
    if exists:
        return
    homeroom = users["teacher@demo.edu.vn"]
    group = Conversation(
        user_id=homeroom.id, class_id=room.id, kind="group", title=DEMO_GROUP, default_agent_slug="tro-ly-lop"
    )
    db.add(group)
    await db.flush()
    people = ["teacher@demo.edu.vn", "toan@demo.edu.vn", "student@demo.edu.vn", "student2@demo.edu.vn"]
    people.append("parent@demo.edu.vn")
    for email in people:
        person = users[email]
        db.add(
            ConversationMember(
                conversation_id=group.id, user_id=person.id, is_admin=person.role == "teacher", can_see_history=True
            )
        )
    for slug in ("tro-ly-lop", "gia-su-toan"):
        db.add(ConversationMember(conversation_id=group.id, agent_slug=slug, can_see_history=True))
    await db.commit()
    print(f"group {DEMO_GROUP}")


async def seed_approval_modes(db) -> None:
    """Students get "ask every time" for every always-ask action (FR-035); teachers and parents choose."""
    modes = (("student", "ask_every_time"), ("teacher", "members_choose"), ("parent", "members_choose"))
    for kind in sorted(ALWAYS_ASK):
        for role, mode in modes:
            if await db.get(ApprovalKindMode, (kind, role)) is None:
                db.add(ApprovalKindMode(action_kind=kind, role=role, mode=mode))
    await db.commit()


async def seed_history(db, room: ClassRoom, student: User) -> None:
    existing = await db.scalar(
        select(Conversation.id).where(Conversation.user_id == student.id, Conversation.kind.in_(("chat", "direct")))
    )
    if existing:
        return
    now = datetime.now(UTC)
    for days_ago, slug, question, answer in DEMO_HISTORY:
        at = now - timedelta(days=days_ago, hours=2)
        # Past auto-routed chats (direct_agent_slug null), as they were before feature 003.
        conversation = Conversation(
            user_id=student.id,
            class_id=room.id,
            title=question[:80],
            created_at=at,
            updated_at=at,
            kind="direct",
            last_seq=2,
        )
        db.add(conversation)
        await db.flush()
        db.add(
            ConversationMember(
                conversation_id=conversation.id,
                user_id=student.id,
                is_admin=True,
                can_see_history=True,
                last_read_seq=2,
            )
        )
        db.add(
            ChatMessage(
                conversation_id=conversation.id,
                seq=1,
                role="user",
                content=question,
                created_at=at,
                sender_user_id=student.id,
            )
        )
        db.add(
            ChatMessage(
                conversation_id=conversation.id,
                seq=2,
                role="assistant",
                content=answer,
                agent_slug=slug,
                created_at=at + timedelta(seconds=5),
                meta={"route_reason": "llm"},
            )
        )
    await db.commit()
    print(f"history {len(DEMO_HISTORY)} conversations for {student.email}")


async def seed_teacher_agents(db, teacher: User) -> None:
    entries = {e["manifest"]["slug"]: e for e in yaml.safe_load((EVAL_DIR / "certify_agents.yaml").read_text("utf-8"))}
    for slug in DEMO_AGENTS:
        if await db.scalar(select(Agent.id).where(Agent.slug == slug)):
            continue
        manifest = AgentManifest.model_validate(entries[slug]["manifest"]).model_dump(mode="json")
        agent = Agent(slug=slug, owner_id=teacher.id, visibility="private", draft_manifest=manifest)
        db.add(agent)
        await db.flush()
        db.add(AgentVersion(agent_id=agent.id, version=1, manifest=manifest))
        print(f"teacher agent {slug} (v1, uncertified)")
    await db.commit()


async def main() -> None:
    # Windows consoles default to cp1252; names and titles are Vietnamese.
    sys.stdout.reconfigure(encoding="utf-8")
    async for db in get_session():
        changed = await sync_platform_agents(db)
        print(f"platform agents synced ({', '.join(changed) or 'no changes'})")
        users = await seed_accounts(db)
        await seed_class(db, users)
        await seed_approval_modes(db)
    await dispose_engine()


if __name__ == "__main__":
    asyncio.run(main())
