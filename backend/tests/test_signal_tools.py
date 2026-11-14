"""Signal tools and the confirmation mechanism (specs/002-multi-agent-orchestration User Story 4 and 5, research R5,
R6, R18), offline with the test-only tool `confirm_probe`."""

import json
from datetime import UTC, datetime, timedelta

import pytest
from mcp.server.mcpserver.exceptions import ToolError
from sqlalchemy import update

from app.chat.models import ChatMessage, ToolCallLog
from app.chat.router import ChatIn
from app.config import get_settings
from app.orchestrator.models import TurnRun
from app.runtime import dify_turn
from app.tools import context as handles
from app.tools import registry
from tests.dify_fake import deltas_sse, planner_body, rows, triage_body
from tests.helpers import chat, class_with_student, parse_sse, reply_text

PROBE = ("confirm_probe", {"target": "Lớp 8A1", "note": "Mai kiểm tra 15 phút"})


@pytest.fixture
def probe(monkeypatch):
    """confirm_probe is on (ENABLE_TEST_TOOLS) and granted to every agent of the turn, as a test manifest would."""
    monkeypatch.setenv("ENABLE_TEST_TOOLS", "true")
    get_settings.cache_clear()
    original = dify_turn.tool_context

    def with_probe(turn, agent, excerpt, **extra):
        context = original(turn, agent, excerpt, **extra)
        context.allowed_tools = context.allowed_tools | {"confirm_probe"}
        return context

    monkeypatch.setattr(dify_turn, "tool_context", with_probe)


def context(**changes) -> registry.ToolContext:
    base = {
        "user_id": "u-1",
        "role": "student",
        "class_id": "c-1",
        "grade": 8,
        "conversation_id": None,
        "agent_slug": "tro-ly-lop",
        "allowed_tools": frozenset({"confirm_probe"}),
    }
    return registry.ToolContext(**{**base, **changes})


async def call(ctx: registry.ToolContext, name: str, arguments: dict) -> str:
    handle = handles.register(ctx)
    try:
        return await registry.run_tool(handle, name, arguments)
    finally:
        handles.release(handle)


def last(events: list[dict], kind: str) -> dict:
    return [e for e in events if e["type"] == kind][-1]


async def asked_to_confirm(as_user, dify):
    """A fast-path turn whose agent calls confirm_probe. Returns users, class, events, the run and conversation."""
    teacher, student, parent, room = await class_with_student(as_user)
    dify.triage = triage_body(agent="tro-ly-lop")
    dify.tool_calls = [PROBE]
    dify.runner = [deltas_sse("Mình cần bạn xác nhận trước.")]
    events = await chat(student, "Báo cả lớp mai kiểm tra 15 phút", class_id=room["id"])
    dify.tool_calls = []
    conversation_id = next(e["conversation_id"] for e in events if e["type"] == "conversation")
    return teacher, student, room, events, conversation_id


async def the_run(sessionmaker, conversation_id: str) -> TurnRun:
    [run] = await rows(sessionmaker, TurnRun, TurnRun.conversation_id == conversation_id)
    return run


async def decide(student, room, conversation_id, run_id, decision: str) -> list[dict]:
    message = "Đồng ý" if decision == "approve" else "Không"
    return await chat(
        student, message, class_id=room["id"], conversation_id=conversation_id,
        reply={"run_id": run_id, "decision": decision},
    )


async def executed(sessionmaker) -> list[ToolCallLog]:
    return await rows(sessionmaker, ToolCallLog, ToolCallLog.tool == "confirm_probe", ToolCallLog.denied_reason.is_(None))


# --- Holding the call -----------------------------------------------------------------------------------------------


async def test_an_unconfirmed_call_does_not_run_and_the_fast_turn_stops_to_ask(
    app, as_user, dify, sessionmaker, probe
) -> None:
    *_, events, conversation_id = await asked_to_confirm(as_user, dify)
    ask = last(events, "ask")
    assert ask["kind"] == "confirm" and ask["skippable"] is False
    assert ask["confirm"]["tool"] == "confirm_probe"
    assert ask["confirm"]["summary"] == "Ghi một thông báo thử tới “Lớp 8A1”: Mai kiểm tra 15 phút"
    assert events[-1]["status"] == "awaiting_user" and events[-1]["path"] == "full"
    assert any(e["type"] == "tool" and e["status"] == "confirm" for e in events)

    [held] = await rows(sessionmaker, ToolCallLog, ToolCallLog.tool == "confirm_probe")
    assert held.denied_reason == "awaiting_confirmation"
    run = await the_run(sessionmaker, conversation_id)
    assert run.status == "awaiting_user" and run.clarify_rounds == 0  # FR-016
    assert run.pending["confirm"]["source"] == "tool" and run.pending["confirm"]["args"]["target"] == "Lớp 8A1"


async def test_approval_runs_the_stored_call_exactly_once(app, as_user, dify, sessionmaker, probe) -> None:
    _, student, room, _, conversation_id = await asked_to_confirm(as_user, dify)
    run = await the_run(sessionmaker, conversation_id)
    dify.runner = [deltas_sse("Đã gửi thông báo thử.")]
    events = await decide(student, room, conversation_id, run.id, "approve")

    assert [(e["name"], e["status"]) for e in events if e["type"] == "tool"] == [
        ("confirm_probe", "start"),
        ("confirm_probe", "done"),
    ]
    assert reply_text(events) == "Đã gửi thông báo thử." and events[-1]["status"] == "ok"
    [done] = await executed(sessionmaker)
    assert done.arguments == {"target": "Lớp 8A1", "note": "Mai kiểm tra 15 phút"}
    run = await the_run(sessionmaker, conversation_id)
    assert run.status == "done"
    [confirmation] = run.confirmations
    assert confirmation["decision"] == "approve" and confirmation["result"]["done"] is True
    assert confirmation["executed_at"] and confirmation["result_ref"] == "Lớp 8A1"
    synthesis = dify.calls("/chat-messages")[-1]
    assert "Đã thực hiện" in synthesis["inputs"]["system_prompt"]
    ask_message = (await rows(sessionmaker, ChatMessage, ChatMessage.status == "awaiting_user"))[0]
    assert ask_message.meta["ask"]["state"] == "approved"

    # The same approval again (a double click, a resent request) finds nothing to approve.
    dify.runner = [deltas_sse("Câu trả lời thường.")]
    await decide(student, room, conversation_id, run.id, "approve")
    assert len(await executed(sessionmaker)) == 1


async def test_approval_after_the_handle_expired_rebuilds_the_context(
    app, as_user, dify, sessionmaker, probe, monkeypatch
) -> None:
    _, student, room, _, conversation_id = await asked_to_confirm(as_user, dify)
    run = await the_run(sessionmaker, conversation_id)
    real = handles.now
    monkeypatch.setattr(handles, "now", lambda: real() + handles.TTL_S + 60)
    dify.runner = [deltas_sse("Đã gửi.")]
    events = await decide(student, room, conversation_id, run.id, "approve")
    assert events[-1]["status"] == "ok"
    [done] = await executed(sessionmaker)
    assert done.message_id == events[-1]["message_id"]


@pytest.mark.parametrize("how", ["reject", "expired", "typed"])
async def test_without_approval_nothing_runs(app, as_user, dify, sessionmaker, probe, how) -> None:
    _, student, room, _, conversation_id = await asked_to_confirm(as_user, dify)
    run = await the_run(sessionmaker, conversation_id)
    dify.runner = [deltas_sse("Mình chưa gửi gì cả.")]
    if how == "reject":
        events = await decide(student, room, conversation_id, run.id, "reject")
        assert "CHƯA thực hiện" in dify.calls("/chat-messages")[-1]["inputs"]["system_prompt"]
        assert events[-1]["status"] == "ok"
    elif how == "expired":
        async with sessionmaker() as db:
            await db.execute(
                update(TurnRun).where(TurnRun.id == run.id).values(expires_at=datetime.now(UTC) - timedelta(hours=1))
            )
            await db.commit()
        events = await decide(student, room, conversation_id, run.id, "approve")
        assert "pending_expired" in [e.get("kind") for e in events]
    else:
        events = await chat(student, "Thôi, hỏi chuyện khác", class_id=room["id"], conversation_id=conversation_id)
        assert "pending_cancelled" in [e.get("kind") for e in events]
    assert await executed(sessionmaker) == []
    run = await the_run(sessionmaker, conversation_id)
    expected = {"reject": "reject", "expired": "expired", "typed": "cancelled"}[how]
    assert [c["decision"] for c in run.confirmations] == [expected]
    assert run.confirmations[0]["result"]["done"] is False


async def test_without_a_person_a_confirmation_is_a_no(app, as_user, dify, sessionmaker, probe) -> None:
    """Certification never pauses (FR-041)."""
    _, student, _, room = await class_with_student(as_user)
    dify.triage = triage_body(agent="tro-ly-lop")
    dify.tool_calls = [PROBE]
    dify.runner = [deltas_sse("Cần xác nhận nên mình chưa làm.")]
    payload = ChatIn(message="Báo cả lớp", class_id=room["id"])
    body = "".join([c async for c in dify_turn.run_dify_turn(student.user["id"], room["id"], "student", payload, kind="certify")])
    events = parse_sse(body)
    assert "ask" not in [e["type"] for e in events] and events[-1]["status"] == "ok"
    assert await executed(sessionmaker) == []
    [run] = await rows(sessionmaker, TurnRun)
    assert run.status == "done" and run.confirmations[0]["result"] == {"done": False, "reason": "no_person"}


async def test_confirmation_is_asked_even_with_multi_step_off(app, as_user, dify, sessionmaker, probe) -> None:
    teacher, student, _, room = await class_with_student(as_user)
    url = f"/api/classes/{room['id']}/policy"
    await teacher.put(url, json={**(await teacher.get(url)).json(), "multi_step": False})
    dify.triage = triage_body(agent="tro-ly-lop")
    dify.tool_calls = [PROBE]
    events = await chat(student, "Báo cả lớp", class_id=room["id"])
    assert last(events, "ask")["kind"] == "confirm" and events[-1]["status"] == "awaiting_user"


async def test_a_step_that_calls_a_tool_needing_confirmation_pauses_after_the_steps(
    app, as_user, dify, sessionmaker, probe
) -> None:
    _, student, _, room = await class_with_student(as_user)
    dify.triage = triage_body("triage_path_full.json")
    dify.planner = planner_body(
        plan={"goal": "g", "lead": "tro-ly-lop", "steps": [{"key": "s1", "agent": "tro-ly-lop", "title": "Soạn", "task": "Soạn thông báo"}]}
    )
    dify.tool_calls = [PROBE]
    dify.runner = [deltas_sse("Ghi chú.", conversation_id="")]
    events = await chat(student, "Soạn rồi báo cả lớp", class_id=room["id"])
    ask = last(events, "ask")
    assert ask["kind"] == "confirm" and ask["confirm"]["tool"] == "confirm_probe"
    [run] = await rows(sessionmaker, TurnRun)
    assert run.pending["step_key"] == "s1" and run.clarify_rounds == 0
    dify.tool_calls = []
    dify.runner = [deltas_sse("Đã gửi.")]
    conversation_id = next(e["conversation_id"] for e in events if e["type"] == "conversation")
    events = await decide(student, room, conversation_id, run.id, "approve")
    assert events[-1]["status"] == "ok" and len(await executed(sessionmaker)) == 1
    # The step is not run again and the signal is not asked about twice.
    assert len([c for c in dify.calls("/chat-messages") if "query" in c]) == 2


# --- Signal tools ---------------------------------------------------------------------------------------------------


async def test_signal_tools_work_only_in_a_step() -> None:
    for name, arguments in [
        ("request_confirmation", {"summary": "Em muốn đề 10 câu trắc nghiệm"}),
        ("ask_user", {"questions": [{"question": "Lớp mấy?"}]}),
        ("request_help", {"agent": "", "task": "Tìm lý thuyết trong tài liệu lớp"}),
    ]:
        for mode in ("fast", "synthesis"):
            with pytest.raises(ToolError, match="chỉ dùng trong phần việc"):
                await call(context(mode=mode, allowed_tools=frozenset()), name, arguments)
    step = context(mode="step", allowed_tools=frozenset(), may_request_help=True)
    text = await call(step, "request_confirmation", {"summary": "Em muốn đề 10 câu trắc nghiệm"})
    assert "Đã ghi nhận" in json.loads(text)["message"]
    assert step.signals == [{"type": "request_confirmation", "summary": "Em muốn đề 10 câu trắc nghiệm"}]


async def test_an_interpretation_asked_in_a_step_is_a_clarify_round(app, as_user, dify, sessionmaker) -> None:
    _, student, _, room = await class_with_student(as_user)
    dify.triage = triage_body("triage_path_full.json")
    dify.planner = planner_body(
        plan={"goal": "g", "lead": "tro-ly-lop", "steps": [{"key": "s1", "agent": "tro-ly-lop", "title": "Soạn", "task": "Soạn đề"}]}
    )
    dify.tool_calls = [("request_confirmation", {"summary": "Em muốn đề 10 câu trắc nghiệm Toán"})]
    dify.runner = [deltas_sse("Ghi chú.", conversation_id="")]
    events = await chat(student, "Làm đề cho em", class_id=room["id"])
    ask = last(events, "ask")
    assert ask["kind"] == "confirm" and ask["confirm"]["summary"] == "Em muốn đề 10 câu trắc nghiệm Toán"
    [run] = await rows(sessionmaker, TurnRun)
    assert run.clarify_rounds == 1 and run.pending["confirm"]["source"] == "interpretation"


async def test_confirm_probe_exists_only_with_test_tools(monkeypatch) -> None:
    monkeypatch.setenv("ENABLE_TEST_TOOLS", "false")
    get_settings.cache_clear()
    assert registry.deny_reason("confirm_probe", context()) == "Công cụ không có trong danh mục của nền tảng."
    monkeypatch.setenv("ENABLE_TEST_TOOLS", "true")
    get_settings.cache_clear()
    assert registry.deny_reason("confirm_probe", context()) is None


# --- request_help and ask_user (User Story 5) ------------------------------------------------------------------------

HELP = ("request_help", {"agent": "on-tap-tai-lieu", "task": "Tìm phần định lý Pytago trong tài liệu lớp"})


def note(text: str) -> str:
    return deltas_sse(text, conversation_id="")


async def class_with_helpers(as_user):
    teacher, student, parent, room = await class_with_student(as_user)
    hub = {agent["slug"]: agent for agent in (await teacher.get("/api/hub/agents")).json()}
    for slug in ("gia-su-toan", "on-tap-tai-lieu"):
        await teacher.post(f"/api/classes/{room['id']}/agents", json={"agent_id": hub[slug]["id"]})
    return student, room


def one_step(agent: str = "gia-su-toan") -> dict:
    return planner_body(
        plan={
            "goal": "Ôn Pytago",
            "lead": "gia-su-toan",
            "steps": [{"key": "s1", "agent": agent, "title": "Soạn bài", "task": "Soạn bài luyện Pytago"}],
        }
    )


async def test_a_helper_cannot_ask_for_help_in_turn() -> None:
    helper = context(mode="step", allowed_tools=frozenset(), may_request_help=False)
    with pytest.raises(ToolError, match="không được nhờ thêm"):
        await call(helper, *HELP)
    assert helper.signals == []


async def test_request_help_adds_a_helper_step_then_runs_the_step_again(app, as_user, dify, sessionmaker) -> None:
    from app.orchestrator.models import RunStep

    student, room = await class_with_helpers(as_user)
    dify.triage = triage_body("triage_path_full.json")
    dify.planner = one_step()
    dify.tool_calls = [HELP]
    dify.runner = [note("Cần lý thuyết."), note("PYTAGO-TRONG-TAI-LIEU trang 3."), note("Bài luyện mới."), deltas_sse("Kết quả.")]
    events = await chat(student, "Soạn bài luyện Pytago theo tài liệu", class_id=room["id"])

    plans = [e for e in events if e["type"] == "plan"]
    assert len(plans) == 2
    assert [(s["key"], s["agent"]["slug"]) for s in plans[-1]["steps"]] == [
        ("s1", "gia-su-toan"),
        ("h1", "on-tap-tai-lieu"),
        ("s1r", "gia-su-toan"),
    ]
    steps = {row.key: row for row in await rows(sessionmaker, RunStep)}
    assert steps["h1"].origin == "help" and steps["h1"].requested_by == "s1"
    assert steps["h1"].task == HELP[1]["task"]
    assert steps["s1r"].origin == "rerun" and steps["s1r"].depends_on == ["s1", "h1"]
    assert all(row.status == "done" for row in steps.values())
    # The rerun gets the helper's note; the answer credits both agents (FR-029).
    rerun = [c for c in dify.calls("/chat-messages") if "Làm lại phần này" in c.get("query", "")][0]
    assert "PYTAGO-TRONG-TAI-LIEU" in rerun["query"]
    assert [c["slug"] for c in events[-1]["contributors"]] == ["on-tap-tai-lieu"]
    [run] = await rows(sessionmaker, TurnRun)
    assert run.replans == 1 and run.plan_version == 2


async def test_only_the_first_request_of_a_step_counts(app, as_user, dify, sessionmaker) -> None:
    from app.orchestrator.models import RunStep

    student, room = await class_with_helpers(as_user)
    dify.triage = triage_body("triage_path_full.json")
    dify.planner = one_step()
    dify.tool_calls = [HELP, ("request_help", {"agent": "tro-ly-lop", "task": "Một việc khác hẳn để làm thêm"})]
    dify.runner = [note("A."), note("B."), note("C."), deltas_sse("Kết quả.")]
    await chat(student, "Soạn bài", class_id=room["id"])
    helpers = [row for row in await rows(sessionmaker, RunStep) if row.origin == "help"]
    assert [row.agent_slug for row in helpers] == ["on-tap-tai-lieu"]


async def test_an_unknown_agent_is_replaced_by_the_best_match_or_noted(app, as_user, dify, sessionmaker) -> None:
    from app.orchestrator.models import RunStep

    student, room = await class_with_helpers(as_user)
    dify.triage = triage_body("triage_path_full.json")
    dify.planner = one_step()
    dify.tool_calls = [("request_help", {"agent": "hacker", "task": "Ôn tập theo tài liệu lớp đã tải lên"})]
    dify.runner = [note("A."), note("B."), note("C."), deltas_sse("Kết quả.")]
    await chat(student, "Soạn bài", class_id=room["id"])
    [helper] = [row for row in await rows(sessionmaker, RunStep) if row.origin == "help"]
    assert helper.agent_slug != "hacker" and helper.agent_slug != "gia-su-toan"

    dify.tool_calls = [("request_help", {"agent": "", "task": "Xyzzy qwerty plugh frobnicate"})]
    dify.runner = [note("Ghi chú gốc."), deltas_sse("Kết quả.")]
    events = await chat(student, "Soạn bài khác", class_id=room["id"])
    last_run = sorted(await rows(sessionmaker, TurnRun), key=lambda r: r.created_at)[-1]
    [row] = await rows(sessionmaker, RunStep, RunStep.run_id == last_run.id)
    assert "ngoài khả năng của các agent trong lớp" in row.note
    assert len([e for e in events if e["type"] == "plan"]) == 1


async def test_limits_stop_new_steps(app, as_user, dify, sessionmaker, monkeypatch) -> None:
    from app.orchestrator.models import RunStep

    monkeypatch.setenv("ORCH_MAX_REPLANS", "0")
    get_settings.cache_clear()
    student, room = await class_with_helpers(as_user)
    dify.triage = triage_body("triage_path_full.json")
    dify.planner = one_step()
    dify.tool_calls = [HELP]
    dify.runner = [note("A."), deltas_sse("Kết quả.")]
    await chat(student, "Soạn bài", class_id=room["id"])
    assert [row.key for row in await rows(sessionmaker, RunStep)] == ["s1"]

    monkeypatch.setenv("ORCH_MAX_REPLANS", "1")
    monkeypatch.setenv("ORCH_MAX_STEPS", "2")
    get_settings.cache_clear()
    await chat(student, "Soạn bài nữa", class_id=room["id"])
    assert sorted(row.key for row in await rows(sessionmaker, RunStep)) == ["s1", "s1"]


async def test_ask_user_in_a_step_pauses_or_becomes_an_assumption(app, as_user, dify, sessionmaker) -> None:
    student, room = await class_with_helpers(as_user)
    dify.triage = triage_body("triage_path_full.json")
    dify.planner = one_step()
    dify.tool_calls = [("ask_user", {"questions": [{"question": "Em học lớp mấy?", "options": ["7", "8", "9"]}]})]
    dify.runner = [note("Chưa biết lớp.")]
    events = await chat(student, "Soạn bài cho em", class_id=room["id"])
    ask = [e for e in events if e["type"] == "ask"][-1]
    assert ask["kind"] == "clarify" and ask["questions"] == [{"id": "q1", "question": "Em học lớp mấy?", "options": ["7", "8", "9"]}]
    [run] = await rows(sessionmaker, TurnRun)
    assert run.pending["step_key"] == "s1" and run.clarify_rounds == 1

    # Nobody to ask (a forced eval turn): the question becomes an assumption.
    payload = ChatIn(message="Soạn bài cho em", class_id=room["id"])
    dify.runner = [note("Chưa biết lớp."), deltas_sse("Kết quả.")]
    body = "".join(
        [c async for c in dify_turn.run_dify_turn(student.user["id"], room["id"], "student", payload, force_path="full")]
    )
    assert "ask" not in [e["type"] for e in parse_sse(body)]
    forced = [r for r in await rows(sessionmaker, TurnRun) if not r.interactive][0]
    assert any("Em học lớp mấy?" in item for item in forced.assumptions)
