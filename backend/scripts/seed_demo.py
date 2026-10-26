"""Create the demo accounts shown on the login page plus one demo class. Idempotent: existing data is left untouched.

Usage (from backend/): uv run python -m scripts.seed_demo
"""

import asyncio
import shutil
import sys
from pathlib import Path

from sqlalchemy import select

from app.agents.models import Agent, Installation
from app.agents.service import latest_version, sync_platform_agents
from app.auth.models import Role, User
from app.auth.service import EmailTakenError, create_user, get_user_by_email
from app.classes import service as classes
from app.classes.models import ClassRoom
from app.db import dispose_engine, get_session
from app.knowledge import service as knowledge
from app.knowledge.models import Document

SEED_DIR = Path(__file__).resolve().parents[2] / "seed"
CLASS_AGENTS = ["gia-su-toan", "on-tap-tai-lieu", "tao-de", "cham-van"]

DEMO_PASSWORD = "Demo123!"
DEMO_ACCOUNTS = [
    ("Cô Nguyễn Thu Hà", "teacher@demo.edu.vn", Role.TEACHER),
    ("Nguyễn Minh Anh", "student@demo.edu.vn", Role.STUDENT),
    ("Nguyễn Văn Bình", "parent@demo.edu.vn", Role.PARENT),
    ("Quản trị viên", "admin@demo.edu.vn", Role.ADMIN),
    ("Trần Gia Bảo", "bao@demo.edu.vn", Role.STUDENT),
]
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
    for email in ("student@demo.edu.vn", "bao@demo.edu.vn"):
        await classes.add_student(db, room, users[email])
    student, parent = users["student@demo.edu.vn"], users["parent@demo.edu.vn"]
    await classes.link_parent(db, parent, student)
    await classes.set_consent(db, parent, student.id, allow_agents=True, allow_reports=True)
    # Bảo has no linked parent, so the consent gate is visible in the demo.
    for slug in CLASS_AGENTS:
        await install(db, slug, installed_by=teacher, class_id=room.id)
    await install(db, "tro-ly-phu-huynh", installed_by=parent, user_id=parent.id)
    await seed_document(db, room, teacher)


async def main() -> None:
    # Windows consoles default to cp1252; names and titles are Vietnamese.
    sys.stdout.reconfigure(encoding="utf-8")
    async for db in get_session():
        changed = await sync_platform_agents(db)
        print(f"platform agents synced ({', '.join(changed) or 'no changes'})")
        users = await seed_accounts(db)
        await seed_class(db, users)
    await dispose_engine()


if __name__ == "__main__":
    asyncio.run(main())
