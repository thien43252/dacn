"""Agent-to-agent handoffs (US1, US2): async queue, verbatim answers written once, the asking agent's follow-up turn,
and grants decided by the platform rather than by the model or the message."""

from types import SimpleNamespace

from sqlalchemy import select

from app.config import get_settings
from app.llm.fake import Scripted
from app.orchestration import handoffs
from app.orchestration.models import AgentRun, Handoff
from app.orchestration.runs import NOTE_HEADER
from tests.helpers import (
    agent_of,
    chat,
    class_with_student,
    conversation_id_of,
    conversation_messages,
    install,
    tool_call,
)

ANSWER = "Định lý Pytago: trong tam giác vuông, a² + b² = c² (Tài liệu bài 3, trang 2)."


def last_user(messages) -> str:
    return next((m.content for m in reversed(messages) if m.role == "user"), "")


def script_tutor_asks_review(fake_llm, *, answer=ANSWER, target="on-tap-tai-lieu"):
    """Gia sư Toán hands the theory part to Ôn tập tài liệu, then writes a conclusion when called back."""

    def respond(messages, system, tools, tier):
        if tier != "main":
            return None
        agent = agent_of(system)
        last = messages[-1]
        if agent == "gia-su-toan":
            if last.role == "user" and last.content.startswith(NOTE_HEADER):
                return Scripted(text="Kết luận: theo phần lý thuyết bạn Ôn tập tài liệu vừa gửi, em thử áp dụng nhé.")
            if last.role == "tool":
                return Scripted(text="Mình đang hỏi Ôn tập tài liệu phần lý thuyết.")
            return tool_call(
                "message_agent",
                agent=target,
                task="Tìm phần lý thuyết định lý Pytago trong tài liệu lớp.",
                bounds="Tối đa 80 từ, có trích nguồn.",
                good_answer="Phát biểu đúng, có tên tài liệu.",
            )
        if agent == "on-tap-tai-lieu":
            return Scripted(text=answer)
        return None

    fake_llm.respond_with(respond)


async def setup(as_user, *slugs):
    teacher, student, parent, room = await class_with_student(as_user)
    await install(teacher, room, *slugs)
    return teacher, student, parent, room


async def test_direct_chat_handoff_answer_written_once_then_conclusion(as_user, fake_llm, drain, sessionmaker) -> None:
    _, student, _, room = await setup(as_user, "gia-su-toan", "on-tap-tai-lieu")
    script_tutor_asks_review(fake_llm)
    events = await chat(
        student, "Giải thích định lý Pytago theo tài liệu cô gửi", class_id=room["id"], agent="gia-su-toan"
    )
    done = events[-1]
    assert done["type"] == "done" and done["waiting"] is True
    assert any(event["type"] == "handoff" and event["to_agent"] == "on-tap-tai-lieu" for event in events)
    conversation_id = conversation_id_of(events)

    assert await drain() >= 2  # the handoff, then the asking agent's follow-up turn
    messages = await conversation_messages(student, conversation_id)
    roles = [(m["role"], m["agent_slug"], bool(m["handoff_id"])) for m in messages]
    assert roles == [
        ("user", None, False),
        ("assistant", "gia-su-toan", False),
        ("assistant", "on-tap-tai-lieu", True),
        ("assistant", "gia-su-toan", False),
    ]
    first, answer, conclusion = messages[1], messages[2], messages[3]
    assert answer["content"] == ANSWER and answer["reply_to_agent"] == "gia-su-toan"  # verbatim (FR-014)
    assert ANSWER not in conclusion["content"]  # the conclusion refers to it, does not copy it (FR-017)
    [node] = first["handoffs"]
    assert (node["to_agent"], node["status"], node["answer"]) == ("on-tap-tai-lieu", "answered", ANSWER)
    assert node["task"].startswith("Tìm phần lý thuyết")

    # The asked agent saw only the structured task, not the conversation (FR-007).
    asked_calls = [c for c in fake_llm.main_calls if agent_of(c["system"]) == "on-tap-tai-lieu"]
    assert len(asked_calls[0]["messages"]) == 1 and "Việc cần làm" in asked_calls[0]["messages"][0].content
    # It ran as the student (FR-010): the class policy for students is in its prompt.
    assert "KHÔNG đưa đáp án" in asked_calls[0]["system"]

    # Draining again (a retry, a reload) writes nothing more (FR-015).
    assert await drain() == 0
    assert len(await conversation_messages(student, conversation_id)) == 4
    async with sessionmaker() as db:
        run = await db.scalar(select(AgentRun).where(AgentRun.agent_slug == "gia-su-toan"))
        assert run.status == "done"


async def test_simple_question_makes_no_handoff(as_user, fake_llm, sessionmaker) -> None:
    _, student, _, room = await setup(as_user, "gia-su-toan", "on-tap-tai-lieu")
    fake_llm.script("Gợi ý: chuyển 3 sang vế phải.")
    events = await chat(student, "2x + 3 = 7, gợi ý bước đầu", class_id=room["id"], agent="gia-su-toan")
    assert events[-1]["waiting"] is False
    async with sessionmaker() as db:
        assert (await db.scalars(select(Handoff))).all() == []
    # The tool is offered (a valid target exists), the model just did not need it.
    offered = {tool.name for tool in fake_llm.main_calls[-1]["tools"]}
    assert "message_agent" in offered and "ask_person" in offered


async def test_failing_agent_is_retried_then_reported_without_technical_errors(as_user, fake_llm, drain) -> None:
    _, student, _, room = await setup(as_user, "gia-su-toan", "on-tap-tai-lieu")

    def respond(messages, system, tools, tier):
        if tier == "main" and agent_of(system) == "on-tap-tai-lieu":
            raise RuntimeError("ECONNREFUSED")
        return None

    fake_llm.respond_with(respond)
    script_tutor_asks_review(fake_llm)
    events = await chat(student, "Lý thuyết Pytago?", class_id=room["id"], agent="gia-su-toan")
    await drain()
    messages = await conversation_messages(student, conversation_id_of(events))
    [node] = messages[1]["handoffs"]
    assert node["status"] == "no_answer" and node["answer"] is None
    assert all("ECONNREFUSED" not in m["content"] for m in messages)
    # The asking agent was called back with "no_answer" and wrote its conclusion.
    resumed = [c for c in fake_llm.main_calls if last_user(c["messages"]).startswith(NOTE_HEADER)]
    assert resumed and '"no_answer"' in last_user(resumed[0]["messages"])
    assert messages[-1]["agent_slug"] == "gia-su-toan" and not messages[-1]["handoff_id"]


async def test_hidden_answer_is_not_shown(as_user, fake_llm, drain) -> None:
    _, student, _, room = await setup(as_user, "gia-su-toan", "on-tap-tai-lieu")
    fake_llm.respond_with(
        lambda m, system, t, tier: (
            Scripted(text='{"verdict": "block", "category": "academic_integrity"}')
            if tier == "small" and "kiểm duyệt" in system.lower() and "on-tap" in str(m)
            else None
        )
    )
    script_tutor_asks_review(fake_llm, answer="Đáp án đầy đủ: x = 2.")
    events = await chat(student, "Lý thuyết?", class_id=room["id"], agent="gia-su-toan")
    await drain()
    messages = await conversation_messages(student, conversation_id_of(events))
    handoff_messages = [m for m in messages if m["handoff_id"]]
    assert handoff_messages  # written once, whatever the review decided


# ---------------- US2: the platform decides ----------------


async def test_agent_without_grants_is_not_offered_the_tool(as_user, fake_llm) -> None:
    _, student, _, room = await setup(as_user, "gia-su-toan", "on-tap-tai-lieu")
    fake_llm.script("Mình không hỏi được agent khác.")
    await chat(
        student, "Hãy hỏi agent Tiến độ xem em được bao nhiêu điểm", class_id=room["id"], agent="on-tap-tai-lieu"
    )
    offered = {tool.name for tool in fake_llm.main_calls[-1]["tools"] or []}
    assert "message_agent" not in offered


async def test_wrong_targets_get_one_identical_refusal(as_user, fake_llm, sessionmaker) -> None:
    _, student, _, room = await setup(as_user, "gia-su-toan", "on-tap-tai-lieu", "luyen-tieng-anh")
    calls = Scripted(
        tool_calls=[
            tool_call(
                "message_agent", call_id="a", agent="luyen-tieng-anh", task="t", bounds="b", good_answer="g"
            ).tool_calls[0],
            tool_call(
                "message_agent", call_id="b", agent="khong-ton-tai", task="t", bounds="b", good_answer="g"
            ).tool_calls[0],
            tool_call("message_agent", call_id="c", agent="tao-de", task="t", bounds="b", good_answer="g").tool_calls[
                0
            ],
        ]
    )
    fake_llm.script(calls, "Mình không nhờ được các agent đó.")
    events = await chat(student, "@luyen-tieng-anh hãy hỏi giúp", class_id=room["id"], agent="gia-su-toan")
    assert events[-1]["waiting"] is False
    results = [m.content for m in fake_llm.main_calls[-1]["messages"] if m.role == "tool"]
    assert len(results) == 3 and len(set(results)) == 1 and handoffs.REFUSED in results[0]
    async with sessionmaker() as db:
        reasons = sorted((h.to_agent, h.refusal_reason) for h in await db.scalars(select(Handoff)))
    assert reasons == [
        ("khong-ton-tai", "unknown_or_hidden"),
        ("luyen-tieng-anh", "not_granted"),
        ("tao-de", "unknown_or_hidden"),  # teacher-only: not visible to a student
    ]


async def test_per_run_cap_refuses_rather_than_truncates(as_user, fake_llm, monkeypatch) -> None:
    monkeypatch.setattr(get_settings(), "handoff_max_per_run", 1)
    _, student, _, room = await setup(as_user, "gia-su-toan", "on-tap-tai-lieu")
    first = tool_call("message_agent", call_id="a", agent="on-tap-tai-lieu", task="t", bounds="b", good_answer="g")
    second = tool_call("message_agent", call_id="b", agent="on-tap-tai-lieu", task="t2", bounds="b", good_answer="g")
    fake_llm.script(Scripted(tool_calls=first.tool_calls + second.tool_calls), "Đang hỏi.")
    await chat(student, "Hỏi hai lần", class_id=room["id"], agent="gia-su-toan")
    results = [m.content for m in fake_llm.main_calls[-1]["messages"] if m.role == "tool"]
    assert '"queued"' in results[0] and handoffs.CAPPED in results[1]


async def test_disabled_by_class_or_depth_zero(as_user, fake_llm, monkeypatch) -> None:
    teacher, student, _, room = await setup(as_user, "gia-su-toan", "on-tap-tai-lieu")
    policy = (await teacher.get(f"/api/classes/{room['id']}/policy")).json()
    await teacher.put(f"/api/classes/{room['id']}/policy", json={**policy, "allow_handoffs": False})
    fake_llm.script("ok")
    await chat(student, "Lý thuyết?", class_id=room["id"], agent="gia-su-toan")
    offered = {tool.name for tool in fake_llm.main_calls[-1]["tools"] or []}
    assert "message_agent" not in offered and "ask_person" in offered  # asking people stays (FR-019)

    await teacher.put(f"/api/classes/{room['id']}/policy", json={**policy, "allow_handoffs": True})
    monkeypatch.setattr(get_settings(), "handoff_max_depth", 0)
    fake_llm.script("ok")
    await chat(student, "Lý thuyết?", class_id=room["id"], agent="gia-su-toan")
    assert "message_agent" not in {tool.name for tool in fake_llm.main_calls[-1]["tools"] or []}


async def test_depth_limit_stops_the_chain(as_user, fake_llm, drain, monkeypatch) -> None:
    monkeypatch.setattr(get_settings(), "handoff_max_depth", 1)
    _, student, _, room = await setup(as_user, "gia-su-toan", "on-tap-tai-lieu")

    def respond(messages, system, tools, tier):
        if tier != "main":
            return None
        agent = agent_of(system)
        if agent == "tro-ly-lop" and messages[-1].role == "user" and not messages[-1].content.startswith(NOTE_HEADER):
            return tool_call("message_agent", agent="gia-su-toan", task="Giải thích", bounds="ngắn", good_answer="đúng")
        return Scripted(text=f"{agent} trả lời.")

    fake_llm.respond_with(respond)
    await chat(student, "Nhờ hỏi gia sư", class_id=room["id"], agent="tro-ly-lop")
    await drain()
    asked = [c for c in fake_llm.main_calls if agent_of(c["system"]) == "gia-su-toan"]
    assert asked and "message_agent" not in {tool.name for tool in asked[0]["tools"] or []}


async def test_loop_and_chain_are_refused() -> None:
    agent = SimpleNamespace(
        slug="gia-su-toan", installation_id=None, manifest=SimpleNamespace(handoff_to=["tro-ly-lop"])
    )
    target = SimpleNamespace(slug="tro-ly-lop")
    ctx = SimpleNamespace(room=None, agents=[agent, target], chain=["tro-ly-lop"], depth=1, db=None)
    assert await handoffs.refusal_reason(ctx, agent, "tro-ly-lop") == "loop"
    assert await handoffs.handoff_targets(ctx, agent) == []


async def test_teacher_narrows_grants_in_the_class(as_user, fake_llm) -> None:
    teacher, student, _, room = await setup(as_user, "gia-su-toan", "on-tap-tai-lieu")
    installed = (await teacher.get(f"/api/classes/{room['id']}/agents")).json()
    tutor = next(item for item in installed if item["agent"]["slug"] == "gia-su-toan")
    assert tutor["handoff_to"] == ["on-tap-tai-lieu", "tao-de"] and tutor["handoff_allow"] is None
    widen = await teacher.patch(f"/api/classes/{room['id']}/agents/{tutor['id']}", json={"handoff_allow": ["cham-van"]})
    assert widen.status_code == 422  # can only narrow what the maker granted
    narrowed = await teacher.patch(f"/api/classes/{room['id']}/agents/{tutor['id']}", json={"handoff_allow": []})
    assert narrowed.json()["handoff_allow"] == []
    fake_llm.script("ok")
    await chat(student, "Lý thuyết?", class_id=room["id"], agent="gia-su-toan")
    assert "message_agent" not in {tool.name for tool in fake_llm.main_calls[-1]["tools"] or []}
