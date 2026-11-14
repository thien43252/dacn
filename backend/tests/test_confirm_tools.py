"""The five teacher tools that act outside the conversation (specs/002-multi-agent-orchestration research R18,
contracts/mcp-tools.md, FR-047 to FR-050)."""

import json

import pytest
from mcp.server.mcpserver.exceptions import ToolError
from sqlalchemy import select

from app.audit.models import GuardEvent
from app.class_feed.models import Assignment, ClassAnnouncement
from app.classes.models import ClassRoom
from app.config import get_settings
from app.orchestrator.models import TurnRun
from app.tools import actions, registry
from app.tools import context as handles
from tests.dify_fake import deltas_sse, rows, triage_body
from tests.helpers import chat, class_with_student

ANNOUNCEMENT = {"title": "Kiểm tra 15 phút", "body": "Thứ Sáu lớp kiểm tra 15 phút chương 2.", "audience": "students"}
PRACTICE = {
    "title": "Luyện Pytago",
    "instructions": "Làm trong 20 phút.",
    "questions": [{"question": "Tam giác vuông có hai cạnh góc vuông 6 và 8. Cạnh huyền?", "options": ["10", "12"]}],
    "answer_key": [{"index": 1, "answer": "BI-MAT-DAP-AN", "explanation": "6² + 8² = 100"}],
}


def teacher_context(user_id: str, class_id: str, **changes) -> registry.ToolContext:
    base = {
        "user_id": user_id,
        "role": "teacher",
        "class_id": class_id,
        "grade": 8,
        "conversation_id": None,
        "agent_slug": "tro-ly-lop",
        "allowed_tools": frozenset(actions.TEACHER_TOOLS),
        "log_calls": True,
    }
    return registry.ToolContext(**{**base, **changes})


async def call(ctx: registry.ToolContext, name: str, arguments: dict) -> str:
    handle = handles.register(ctx)
    try:
        return await registry.run_tool(handle, name, arguments)
    finally:
        handles.release(handle)


@pytest.fixture
async def room(as_user):
    teacher, student, parent, room = await class_with_student(as_user)
    return teacher, student, parent, room


# --- Guard: who may call, what may be shared --------------------------------------------------------------------------


@pytest.mark.parametrize("role", ["student", "parent"])
async def test_students_and_parents_are_refused(room, role) -> None:
    teacher, _, _, info = room
    ctx = teacher_context(teacher.user["id"], info["id"], role=role)
    with pytest.raises(ToolError, match="Vai trò"):
        await call(ctx, "post_class_announcement", ANNOUNCEMENT)
    assert ctx.signals == []


async def test_a_teacher_of_another_class_is_refused(room, as_user) -> None:
    _, _, _, info = room
    other = await as_user("teacher")
    ctx = teacher_context(other.user["id"], info["id"])
    with pytest.raises(ToolError, match=registry.NOT_CLASS_TEACHER):
        await call(ctx, "post_class_announcement", ANNOUNCEMENT)
    assert ctx.signals == []


async def test_blocked_words_are_not_shared(room, sessionmaker) -> None:
    from app.guard import dify_rules

    teacher, _, _, info = room
    ctx = teacher_context(teacher.user["id"], info["id"])
    bad = {**ANNOUNCEMENT, "body": f"Nội dung có {dify_rules.keywords()[0]} trong đó."}
    with pytest.raises(ToolError, match="Nội dung không phù hợp để chia sẻ"):
        await call(ctx, "post_class_announcement", bad)
    assert ctx.signals == []
    [event] = await rows(sessionmaker, GuardEvent, GuardEvent.category == "share_blocked")
    assert event.stage == "tool" and event.detector == "keyword"


async def test_the_share_review_can_block(room, dify, sessionmaker) -> None:
    teacher, _, _, info = room
    dify.review = {"verdict": "block", "category": "privacy", "reason": "Lộ số điện thoại"}
    ctx = teacher_context(teacher.user["id"], info["id"])
    with pytest.raises(ToolError, match="Lộ số điện thoại"):
        await call(ctx, "post_class_announcement", ANNOUNCEMENT)
    [event] = await rows(sessionmaker, GuardEvent, GuardEvent.category == "share_blocked")
    assert event.detector == "dify_review"
    review = dify.calls("#review")[-1]["inputs"]
    assert review["role"] == "student" and review["no_direct_answers"] == "false"


@pytest.mark.parametrize("failure", ["slow", "down"])
async def test_a_review_that_fails_or_is_too_slow_blocks(room, dify, sessionmaker, monkeypatch, failure) -> None:
    teacher, _, _, info = room
    monkeypatch.setenv("ORCH_SHARE_REVIEW_TIMEOUT_S", "0.1")
    get_settings.cache_clear()
    if failure == "slow":
        dify.review_delay = 0.5
    else:
        dify.review = "down"
    ctx = teacher_context(teacher.user["id"], info["id"])
    with pytest.raises(ToolError, match="Chưa kiểm duyệt được nội dung, thử lại sau."):
        await call(ctx, "assign_practice", PRACTICE)
    assert ctx.signals == []
    [event] = await rows(sessionmaker, GuardEvent, GuardEvent.category == "share_blocked")
    assert event.detector == "timeout"


async def test_the_answer_key_is_never_sent_to_review(room, dify) -> None:
    teacher, _, _, info = room
    ctx = teacher_context(teacher.user["id"], info["id"])
    await call(ctx, "assign_practice", PRACTICE)
    review = dify.calls("#review")[-1]["inputs"]
    assert "Cạnh huyền" in review["reply"] and "BI-MAT-DAP-AN" not in review["reply"]


# --- Previews (FR-048) ----------------------------------------------------------------------------------------------


@pytest.mark.parametrize(("audience", "count"), [("students", 1), ("parents", 1), ("all", 2)])
async def test_an_announcement_preview_counts_its_audience(room, audience, count) -> None:
    teacher, _, _, info = room
    ctx = teacher_context(teacher.user["id"], info["id"])
    text = await call(ctx, "post_class_announcement", {**ANNOUNCEMENT, "audience": audience})
    assert "xác nhận" in json.loads(text)["message"]
    [signal] = ctx.signals
    assert signal["type"] == "confirm_tool" and signal["tool"] == "post_class_announcement"
    assert signal["audience_count"] == count
    assert signal["preview"] == {"title": ANNOUNCEMENT["title"], "body": ANNOUNCEMENT["body"]}
    assert "Kiểm tra 15 phút" in signal["summary"] and info["name"] in signal["summary"]
    assert signal["args"] == {**ANNOUNCEMENT, "audience": audience}


async def test_previews_of_the_other_tools(room, sessionmaker) -> None:
    teacher, _, _, info = room
    ctx = teacher_context(teacher.user["id"], info["id"])
    await call(ctx, "assign_practice", PRACTICE)
    await call(ctx, "save_class_document", {"title": "Ôn Pytago", "content": "# Pytago\n" + "a² + b² = c². " * 100})
    await call(ctx, "set_agent_notes", {"notes": "Xưng cô, gọi em.", "mode": "replace"})
    await call(ctx, "install_agent", {"agent": "gia-su-toan"})
    practice, document, notes, install = ctx.signals
    assert practice["preview"]["items"] == [PRACTICE["questions"][0]["question"]] and "không có hạn" in practice["summary"]
    assert len(document["preview"]["body"]) <= actions.PREVIEW_CHARS + 1
    assert notes["preview"] == {"before": "", "after": "Xưng cô, gọi em."}
    assert "Gia sư" in install["summary"] or "gia" in install["summary"].lower()


# --- Running after "Đồng ý" -------------------------------------------------------------------------------------------


async def approve_through_chat(teacher, info, dify, tool: str, arguments: dict) -> list[dict]:
    dify.triage = triage_body(agent="tro-ly-lop")
    dify.tool_calls = [(tool, arguments)]
    dify.runner = [deltas_sse("Cần cô xác nhận.")]
    events = await chat(teacher, "Làm giúp cô", class_id=info["id"])
    ask = [e for e in events if e["type"] == "ask"][-1]
    conversation_id = next(e["conversation_id"] for e in events if e["type"] == "conversation")
    dify.tool_calls = []
    dify.runner = [deltas_sse("Xong rồi ạ.")]
    return await chat(
        teacher, "Đồng ý", class_id=info["id"], conversation_id=conversation_id,
        reply={"run_id": ask["run_id"], "decision": "approve"},
    )


async def test_an_approved_announcement_is_posted_with_its_run(room, dify, sessionmaker) -> None:
    teacher, _, _, info = room
    events = await approve_through_chat(teacher, info, dify, "post_class_announcement", ANNOUNCEMENT)
    assert events[-1]["status"] == "ok"
    [posted] = await rows(sessionmaker, ClassAnnouncement)
    assert posted.title == ANNOUNCEMENT["title"] and posted.source == "agent" and posted.author_id == teacher.user["id"]
    [run] = await rows(sessionmaker, TurnRun)
    assert posted.run_id == run.id and run.confirmations[0]["result_ref"] == posted.id
    assert run.confirmations[0]["result"]["link"] == f"/classes/{info['id']}?tab=feed"


async def test_an_approved_practice_set_keeps_its_answer_key(room, dify, sessionmaker) -> None:
    teacher, _, _, info = room
    # tro-ly-lop does not list assign_practice; install tao-de and let it answer.
    hub = {agent["slug"]: agent for agent in (await teacher.get("/api/hub/agents")).json()}
    await teacher.post(f"/api/classes/{info['id']}/agents", json={"agent_id": hub["tao-de"]["id"]})
    dify.triage = triage_body(agent="tao-de")
    dify.tool_calls = [("assign_practice", PRACTICE)]
    events = await chat(teacher, "Giao bài", class_id=info["id"])
    ask = [e for e in events if e["type"] == "ask"][-1]
    conversation_id = next(e["conversation_id"] for e in events if e["type"] == "conversation")
    dify.tool_calls = []
    await chat(teacher, "Đồng ý", class_id=info["id"], conversation_id=conversation_id,
               reply={"run_id": ask["run_id"], "decision": "approve"})
    [assignment] = await rows(sessionmaker, Assignment)
    assert assignment.answer_key[0]["answer"] == "BI-MAT-DAP-AN" and len(assignment.questions) == 1


async def test_notes_change_only_notes_for_agents(room, dify, sessionmaker) -> None:
    teacher, _, _, info = room
    url = f"/api/classes/{info['id']}/policy"
    before = (await teacher.get(url)).json()
    await teacher.put(url, json={**before, "notes_for_agents": "Cũ.", "no_direct_answers": False})
    await approve_through_chat(teacher, info, dify, "set_agent_notes", {"notes": "Mới.", "mode": "append"})
    after = (await teacher.get(url)).json()
    assert after["notes_for_agents"] == "Cũ.\nMới."
    assert after["no_direct_answers"] is False and after["multi_step"] == before["multi_step"]


async def test_installing_an_agent_already_there_is_not_an_error(room, dify, sessionmaker) -> None:
    teacher, _, _, info = room
    hub = {agent["slug"]: agent for agent in (await teacher.get("/api/hub/agents")).json()}
    await teacher.post(f"/api/classes/{info['id']}/agents", json={"agent_id": hub["gia-su-toan"]["id"]})
    await approve_through_chat(teacher, info, dify, "install_agent", {"agent": "gia-su-toan"})
    [run] = await rows(sessionmaker, TurnRun)
    result = run.confirmations[0]["result"]
    assert result["done"] is True and "đã có sẵn" in result["summary"]


async def test_rights_lost_while_waiting_mean_nothing_runs(room, dify, sessionmaker, as_user) -> None:
    teacher, _, _, info = room
    dify.triage = triage_body(agent="tro-ly-lop")
    dify.tool_calls = [("post_class_announcement", ANNOUNCEMENT)]
    events = await chat(teacher, "Đăng thông báo", class_id=info["id"])
    ask = [e for e in events if e["type"] == "ask"][-1]
    conversation_id = next(e["conversation_id"] for e in events if e["type"] == "conversation")
    other = await as_user("teacher")
    async with sessionmaker() as db:
        (await db.get(ClassRoom, info["id"])).owner_id = other.user["id"]
        from app.classes.models import ClassMember

        for member in await db.scalars(select(ClassMember).where(ClassMember.user_id == teacher.user["id"])):
            await db.delete(member)
        await db.commit()
    dify.tool_calls = []
    # The teacher can no longer open the class's chat at all; the run is decided through the stored handle only.
    response = await teacher.post(
        "/api/chat/stream",
        json={"message": "Đồng ý", "class_id": info["id"], "conversation_id": conversation_id,
              "reply": {"run_id": ask["run_id"], "decision": "approve"}},
    )
    assert response.status_code in (403, 404)
    assert await rows(sessionmaker, ClassAnnouncement) == []


async def test_permissions_are_checked_again_when_running(room, dify, sessionmaker, as_user, monkeypatch) -> None:
    """Even if the request gets through, the action re-checks that the user still teaches the class."""
    teacher, _, _, info = room
    dify.triage = triage_body(agent="tro-ly-lop")
    dify.tool_calls = [("post_class_announcement", ANNOUNCEMENT)]
    events = await chat(teacher, "Đăng thông báo", class_id=info["id"])
    ask = [e for e in events if e["type"] == "ask"][-1]
    conversation_id = next(e["conversation_id"] for e in events if e["type"] == "conversation")

    async def no_longer(user_id, class_id):
        return False

    monkeypatch.setattr(actions, "is_class_teacher", no_longer)
    dify.tool_calls = []
    dify.runner = [deltas_sse("Chưa đăng được.")]
    await chat(teacher, "Đồng ý", class_id=info["id"], conversation_id=conversation_id,
               reply={"run_id": ask["run_id"], "decision": "approve"})
    assert await rows(sessionmaker, ClassAnnouncement) == []
    [run] = await rows(sessionmaker, TurnRun)
    assert run.confirmations[0]["result"]["reason"] == "permission"
