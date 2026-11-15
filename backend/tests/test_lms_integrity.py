"""Feature 004, FR-028: while a student is taking a quiz with `block_agents`, no agent gives them its answers, in a
class chat, with their own agent, or in a group; the block is never shown to teachers."""

from datetime import timedelta

from sqlalchemy import select

from app import lms
from app.audit.models import GuardEvent
from app.llm.fake import Scripted
from app.lms import integrity
from app.lms.models import Lesson, LessonItem, Quiz, QuizAttempt, QuizQuestion
from tests.helpers import chat, class_with_student, reply_text

QUESTION = "Giải phương trình 2x + 3 = 17. Giá trị của x là bao nhiêu?"
OPTIONS = [{"id": "a", "text": "x = 5"}, {"id": "b", "text": "x = 7"}]


async def open_exam(sessionmaker, room_id: str, student_id: str, *, block_agents: bool = True, status="in_progress"):
    async with sessionmaker() as db:
        lesson = Lesson(class_id=room_id, title="Buổi 1", status="published")
        db.add(lesson)
        await db.flush()
        item = LessonItem(lesson_id=lesson.id, class_id=room_id, kind="quiz", title="Kiểm tra 15 phút")
        db.add(item)
        await db.flush()
        db.add(Quiz(item_id=item.id, class_id=room_id, block_agents=block_agents, duration_minutes=15))
        question = QuizQuestion(
            quiz_id=item.id, class_id=room_id, kind="single", prompt=QUESTION, options=OPTIONS, answer_key="b"
        )
        db.add(question)
        started = lms.now()
        db.add(
            QuizAttempt(
                quiz_id=item.id,
                class_id=room_id,
                student_id=student_id,
                attempt_no=1,
                status=status,
                started_at=started,
                deadline_at=started + timedelta(minutes=15),
            )
        )
        await db.commit()
        return item.id


async def exam_events(sessionmaker) -> list[GuardEvent]:
    async with sessionmaker() as db:
        return list(await db.scalars(select(GuardEvent).where(GuardEvent.category == "exam_integrity")))


def blocked_notice(events: list[dict]) -> bool:
    return any(e["type"] == "notice" and e.get("text") == integrity.EXAM_BLOCKED for e in events)


async def test_quoting_an_open_question_never_reaches_the_agent(as_user, fake_llm, sessionmaker) -> None:
    teacher, student, _, room = await class_with_student(as_user)
    await open_exam(sessionmaker, room["id"], student.user["id"])

    events = await chat(student, f"Giúp mình câu này: {QUESTION}", class_id=room["id"])
    assert blocked_notice(events)
    assert fake_llm.main_calls == []
    logged = await exam_events(sessionmaker)
    assert [(e.stage, e.private_space) for e in logged] == [("input", True)]

    # The same question in the student's personal space (their own agents, no class) is blocked too.
    events = await chat(student, QUESTION)
    assert blocked_notice(events)
    assert fake_llm.main_calls == []

    # Unrelated questions still go through.
    events = await chat(student, "Thủ đô của Việt Nam là gì?", class_id=room["id"])
    assert not blocked_notice(events)
    assert fake_llm.main_calls


async def test_no_block_after_submit_or_for_practice_quizzes(as_user, fake_llm, sessionmaker) -> None:
    teacher, student, _, room = await class_with_student(as_user)
    await open_exam(sessionmaker, room["id"], student.user["id"], status="submitted")
    assert not blocked_notice(await chat(student, QUESTION, class_id=room["id"]))

    other_teacher, other_student, _, other_room = await class_with_student(as_user)
    await open_exam(sessionmaker, other_room["id"], other_student.user["id"], block_agents=False)
    assert not blocked_notice(await chat(other_student, QUESTION, class_id=other_room["id"]))


async def test_a_reply_giving_the_answer_is_withdrawn(as_user, fake_llm, sessionmaker) -> None:
    teacher, student, _, room = await class_with_student(as_user)
    await open_exam(sessionmaker, room["id"], student.user["id"])

    def respond(messages, system, tools, tier):
        if tier == "main":
            return Scripted(text="Phương trình 2x + 3 = 17 có nghiệm x = 7 nhé.")
        return None

    fake_llm.respond_with(respond)
    # Paraphrased so the input check lets it through; the reply quotes the question and gives the key.
    events = await chat(student, "Phương trình bậc nhất ở câu 1 ra mấy vậy bạn?", class_id=room["id"])
    assert any(e["type"] == "text_reset" for e in events)
    assert integrity.EXAM_BLOCKED in reply_text(events)
    assert [e.stage for e in await exam_events(sessionmaker)] == ["output"]


async def test_reviewer_catches_paraphrased_answers(as_user, fake_llm, sessionmaker) -> None:
    teacher, student, _, room = await class_with_student(as_user)
    await open_exam(sessionmaker, room["id"], student.user["id"])
    seen_context: list[str] = []

    def respond(messages, system, tools, tier):
        if tier == "main":
            return Scripted(text="Chuyển 3 sang vế phải rồi chia đôi là ra thôi.")
        if "BÀI KIỂM TRA ĐANG MỞ" in system:
            seen_context.append(system)
            return Scripted(text='{"verdict": "block", "category": "exam_integrity", "reason": "lộ cách giải"}')
        return None

    fake_llm.respond_with(respond)
    events = await chat(student, "Làm sao tìm x trong bài đó?", class_id=room["id"])
    assert integrity.EXAM_BLOCKED in reply_text(events)
    assert seen_context and QUESTION in seen_context[0]


async def test_group_reply_is_checked_for_every_student_reader(as_user, fake_llm, sessionmaker) -> None:
    teacher, student, _, room = await class_with_student(as_user)
    other = await as_user("student")
    await other.post("/api/classes/join", json={"code": room["join_code"]})
    parent = await as_user("parent")
    code = (await other.get("/api/me/link-code")).json()["code"]
    await parent.post("/api/parent/children", json={"code": code})
    await parent.put(f"/api/parent/children/{other.user['id']}/consent", json={"allow_agents": True})
    group = (
        await teacher.post(
            "/api/chat/groups",
            json={
                "class_id": room["id"],
                "title": "Nhóm ôn tập",
                "members": [student.user["id"], other.user["id"]],
                "agents": ["tro-ly-lop"],
            },
        )
    ).json()
    await open_exam(sessionmaker, room["id"], student.user["id"])

    def respond(messages, system, tools, tier):
        if tier == "main":
            return Scripted(text=f"{QUESTION} Đáp án là x = 7.")
        return None

    fake_llm.respond_with(respond)
    # The asker is not taking the exam, but a reader in the group is.
    events = await chat(
        other, "@tro-ly-lop giải giúp bài phương trình này", class_id=room["id"], conversation_id=group["id"]
    )
    assert integrity.EXAM_BLOCKED in reply_text(events)

    # Teachers never see these events, even for groups they are in; admins see them without the excerpt.
    teacher_log = (await teacher.get(f"/api/classes/{room['id']}/audit")).json()
    assert all(e["category"] != "exam_integrity" for e in teacher_log["events"])
    admin = await as_user("admin")
    admin_log = (await admin.get("/api/audit/events")).json()
    rows = [e for e in admin_log["events"] if e["category"] == "exam_integrity"]
    assert rows and all(e["excerpt"] == "" for e in rows)


def test_matching_rules() -> None:
    exam = integrity.ActiveExam(
        "a", "q", "s", [integrity.ExamQuestion(QUESTION, ["x = 7"]), integrity.ExamQuestion("2 + 2 = ?", ["4"])]
    )
    assert integrity.matches_question(QUESTION.upper(), [exam]) is not None
    assert integrity.matches_question("giai phuong trinh 2x+3=17, gia tri cua x la bao nhieu", [exam]) is not None
    # Short questions are too generic to match alone.
    assert integrity.matches_question("2 + 2 = ?", [exam]) is None
    assert integrity.reveals_answer("x = 7", QUESTION, [exam])
    assert not integrity.reveals_answer("x = 7", "một câu khác hẳn", [exam])
    assert not integrity.reveals_answer("Hãy thử chuyển vế.", QUESTION, [exam])
    assert "đáp án: x = 7" in integrity.exam_context([exam])


async def test_handed_off_answers_are_checked_too(as_user, fake_llm, sessionmaker, drain) -> None:
    from app.orchestration.runs import NOTE_HEADER
    from tests.helpers import agent_of, conversation_id_of, conversation_messages, install, tool_call

    teacher, student, _, room = await class_with_student(as_user)
    await install(teacher, room, "gia-su-toan", "on-tap-tai-lieu")
    await open_exam(sessionmaker, room["id"], student.user["id"])

    def respond(messages, system, tools, tier):
        if tier != "main":
            return None
        agent = agent_of(system)
        last = messages[-1]
        if agent == "gia-su-toan":
            if last.role == "user" and last.content.startswith(NOTE_HEADER):
                return Scripted(text="Mình đã hỏi bạn Ôn tập tài liệu rồi.")
            if last.role == "tool":
                return Scripted(text="Đang hỏi Ôn tập tài liệu.")
            return tool_call(
                "message_agent",
                agent="on-tap-tai-lieu",
                task="Tìm lý thuyết phương trình bậc nhất trong tài liệu.",
                bounds="Ngắn gọn.",
                good_answer="Có trích nguồn.",
            )
        if agent == "on-tap-tai-lieu":
            return Scripted(text=f"{QUESTION} Nghiệm là x = 7 (tài liệu bài 2).")
        return None

    fake_llm.respond_with(respond)
    events = await chat(student, "@gia-su-toan ôn giúp mình phương trình bậc nhất", class_id=room["id"])
    await drain()
    messages = await conversation_messages(student, conversation_id_of(events))
    assert all("x = 7" not in m["content"] for m in messages)
    # The asked agent's answer is withheld (the handoff message is hidden), and the GuardEvent says why.
    handed = next(m for m in messages if m.get("agent_slug") == "on-tap-tai-lieu")
    assert handed["status"] == "hidden"
    assert "output" in [e.stage for e in await exam_events(sessionmaker)]
