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
from app.lms import aware, now
from app.lms.grading import late_penalty
from app.lms.lessons import embed_for
from app.lms.models import Assignment, Lesson, LessonItem, LmsFile, Quiz, QuizQuestion, Submission, SubmissionVersion
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


async def ensure_lms(db) -> None:
    """Add missing LMS demo content without replacing teachers' edits or students' work."""
    teacher = await get_user_by_email(db, "teacher@demo.edu.vn")
    if teacher is None:
        return
    room = await db.scalar(
        select(ClassRoom).where(ClassRoom.owner_id == teacher.id, ClassRoom.name == DEMO_CLASS["name"])
    )
    if room is None:
        return
    await install(db, "tro-giang-lms", installed_by=teacher, class_id=room.id)
    at = now()

    async def lesson(title, status, position):
        row = await db.scalar(select(Lesson).where(Lesson.class_id == room.id, Lesson.title == title))
        if row is None:
            row = Lesson(class_id=room.id, title=title, status=status, position=position, created_by=teacher.id)
            db.add(row)
            await db.flush()
        return row

    async def item(parent, title, kind, position, **values):
        row = await db.scalar(
            select(LessonItem).where(
                LessonItem.class_id == room.id, LessonItem.lesson_id == parent.id, LessonItem.title == title
            )
        )
        if row is None:
            row = LessonItem(class_id=room.id, lesson_id=parent.id, title=title, kind=kind, position=position, **values)
            db.add(row)
            await db.flush()
        return row

    first = await lesson("Buổi 1 - Phương trình bậc nhất", "published", 0)
    content = await item(first, "Tài liệu - Phương trình bậc nhất một ẩn", "file", 0)
    if content.file_id is None:
        source = SEED_DIR / "documents" / "chuong-3-phuong-trinh-bac-nhat.md"
        file = await db.scalar(
            select(LmsFile).where(
                LmsFile.class_id == room.id,
                LmsFile.owner_id == teacher.id,
                LmsFile.purpose == "content",
                LmsFile.filename == source.name,
            )
        )
        if file is None:
            file = LmsFile(
                class_id=room.id,
                owner_id=teacher.id,
                purpose="content",
                filename=source.name,
                content_type="text/markdown",
                size_bytes=source.stat().st_size,
            )
            db.add(file)
            await db.flush()
            target = knowledge.storage_root() / "lms" / room.id / f"{file.id}{source.suffix}"
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
            file.storage_path = str(target)
        content.file_id = file.id
        # document_id stays null: "cho agent đọc" is off.
    video_url = "https://www.youtube.com/watch?v=NybHckSEQBI"
    await item(first, "Video - Ôn tập phương trình", "video", 1, url=video_url, embed_url=embed_for(video_url)[1])
    await item(
        first,
        "Hướng dẫn học tập",
        "text",
        2,
        body="Đọc tài liệu, ôn quy tắc chuyển vế và quy tắc nhân. Giải 2x + 3 = 17 rồi thử lại nghiệm trước khi làm bài kiểm tra.",
    )
    quiz_item = await item(first, "Kiểm tra 15 phút", "quiz", 3)
    if await db.get(Quiz, quiz_item.id) is None:
        db.add(
            Quiz(
                item_id=quiz_item.id,
                class_id=room.id,
                duration_minutes=15,
                max_attempts=1,
                show_answers="after_close",
                close_at=at + timedelta(days=7),
                block_agents=True,
            )
        )
        await db.flush()
    questions = [
        {
            "kind": "single",
            "prompt": "Nghiệm của phương trình 3x - 6 = 0 là bao nhiêu?",
            "options": [{"id": "a", "text": "2"}, {"id": "b", "text": "-2"}, {"id": "c", "text": "6"}],
            "answer_key": "a",
            "points": 2,
            "explanation": "3x = 6 nên x = 2.",
        },
        {
            "kind": "multi",
            "prompt": "Chọn các phương trình có nghiệm x = 2.",
            "options": [
                {"id": "a", "text": "x + 3 = 5"},
                {"id": "b", "text": "2x = 4"},
                {"id": "c", "text": "x - 1 = 3"},
            ],
            "answer_key": ["a", "b"],
            "multi_scoring": "partial",
            "points": 2,
            "explanation": "Thay x = 2 vào từng phương trình để kiểm tra hai vế.",
        },
        {
            "kind": "true_false",
            "prompt": "Khi chuyển một hạng tử sang vế kia của phương trình, ta phải đổi dấu hạng tử đó.",
            "answer_key": True,
            "points": 1,
        },
        {
            "kind": "short",
            "prompt": "Giải phương trình 2x + 3 = 17.",
            "answer_key": ["7", "x = 7"],
            "points": 2,
        },
        {
            "kind": "essay",
            "prompt": "Giải phương trình 3(x - 2) = 2x + 1 và giải thích từng bước biến đổi.",
            "points": 3,
            "rubric": {
                "criteria": [
                    {
                        "name": "Lập luận",
                        "max_points": 2,
                        "description": "Khai triển và chuyển vế đúng, tìm được nghiệm.",
                    },
                    {"name": "Trình bày", "max_points": 1, "description": "Ghi rõ các bước và thử lại nghiệm."},
                ],
                "model_answer": "3x - 6 = 2x + 1; 3x - 2x = 1 + 6; x = 7. Thay lại: hai vế đều bằng 15.",
            },
        },
    ]
    for position, values in enumerate(questions):
        existing = await db.scalar(
            select(QuizQuestion.id).where(
                QuizQuestion.class_id == room.id,
                QuizQuestion.quiz_id == quiz_item.id,
                QuizQuestion.prompt == values["prompt"],
            )
        )
        if existing is None:
            db.add(QuizQuestion(class_id=room.id, quiz_id=quiz_item.id, position=position, **values))
    assignment_item = await item(first, "Bài tập về nhà 1", "assignment", 4)
    assignment = await db.get(Assignment, assignment_item.id)
    if assignment is None:
        assignment = Assignment(
            item_id=assignment_item.id,
            class_id=room.id,
            prompt="Giải 4x - 5 = 23 và 2(x + 3) = 18. Trình bày các bước biến đổi và thử lại mỗi nghiệm.",
            due_at=at + timedelta(days=3),
            max_points=10,
            allow_late=True,
            late_penalty_per_day_pct=10,
            late_penalty_max_pct=30,
            rubric={
                "criteria": [
                    {
                        "name": "Giải phương trình",
                        "max_points": 8,
                        "description": "Mỗi phương trình giải đúng được 4 điểm.",
                    },
                    {
                        "name": "Thử lại và trình bày",
                        "max_points": 2,
                        "description": "Thử lại cả hai nghiệm và ghi rõ kết luận.",
                    },
                ],
                "model_answer": "4x = 28 nên x = 7, thử lại 28 - 5 = 23. x + 3 = 9 nên x = 6, thử lại 2(6 + 3) = 18.",
            },
        )
        db.add(assignment)
        await db.flush()
    second = await lesson("Buổi 2 - Hệ phương trình", "draft", 1)
    await item(
        second,
        "Chuẩn bị cho buổi học tiếp theo",
        "text",
        0,
        body="Ôn cách thay giá trị vào biểu thức. Tìm hai số có tổng bằng 10 và hiệu bằng 2, rồi viết hai đẳng thức tương ứng.",
    )
    for email, text in (
        ("student@demo.edu.vn", "4x - 5 = 23 nên 4x = 28, x = 7. 2(x + 3) = 18 nên x + 3 = 9, x = 6."),
        ("student2@demo.edu.vn", "Bài 1: x = 7, thử lại 4 × 7 - 5 = 23. Bài 2: x = 6, thử lại 2 × (6 + 3) = 18."),
    ):
        student = await get_user_by_email(db, email)
        if student is None:
            continue
        member = await db.scalar(
            select(ClassMember.id).where(
                ClassMember.class_id == room.id, ClassMember.user_id == student.id, ClassMember.role == "student"
            )
        )
        if member is None or await db.scalar(
            select(Submission.id).where(
                Submission.assignment_id == assignment.item_id, Submission.student_id == student.id
            )
        ):
            continue
        result = late_penalty(
            8 if email == "student@demo.edu.vn" else None,
            assignment.max_points,
            at,
            aware(assignment.due_at),
            assignment.late_penalty_per_day_pct,
            assignment.late_penalty_max_pct,
        )
        submission = Submission(
            assignment_id=assignment.item_id,
            class_id=room.id,
            student_id=student.id,
            latest_version=1,
            is_late=result.days_late > 0,
            days_late=result.days_late,
            penalty=result.penalty,
        )
        db.add(submission)
        await db.flush()
        db.add(
            SubmissionVersion(
                submission_id=submission.id, version_no=1, text=text, submitted_at=at, is_late=submission.is_late
            )
        )
        if email == "student@demo.edu.vn":
            submission.status = "graded"
            submission.raw_score = 8
            submission.final_score = result.final
            submission.feedback = (
                "Em tìm đúng hai nghiệm và biến đổi rõ ràng. Cần bổ sung bước thử lại cả hai phương trình."
            )
            submission.graded_by = teacher.id
            submission.graded_at = at
            await db.flush()
            submission.status = "returned"
            submission.returned_at = at
    await db.commit()
    print("LMS demo ensured")


async def main() -> None:
    # Windows consoles default to cp1252; names and titles are Vietnamese.
    sys.stdout.reconfigure(encoding="utf-8")
    async for db in get_session():
        changed = await sync_platform_agents(db)
        print(f"platform agents synced ({', '.join(changed) or 'no changes'})")
        users = await seed_accounts(db)
        await seed_class(db, users)
        await ensure_lms(db)
        await seed_approval_modes(db)
    await dispose_engine()


if __name__ == "__main__":
    asyncio.run(main())
