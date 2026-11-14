"""The full path (specs/002-multi-agent-orchestration): path choice, planner checks, steps and synthesis, offline
against recorded or recorded-shape Dify responses (tests/fixtures/dify/README.md)."""

import asyncio
import json
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from app.agents.manifest import builtin_manifests
from app.agents.service import SEED_DIR, ResolvedAgent
from app.audit.models import GuardEvent
from app.chat.models import ChatMessage, UsageRecord
from app.guard import dify_rules
from app.orchestrator.models import RunStep, TurnRun
from app.orchestrator.planner import Limits, format_history, validate_plan
from app.orchestrator.prompts import (
    MAX_SYSTEM_PROMPT,
    NOTES_BUDGET,
    build_step_query,
    build_synthesis_prompt,
    build_synthesis_query,
)
from app.runtime.dify_client import TriageResult
from app.runtime.dify_turn import takes_full_path
from app.runtime.prompts import planner_roster
from tests.dify_fake import Slow, deltas_sse, fixture_text, planner_body, rows, triage_body
from tests.helpers import chat, class_with_student, reply_text

MANIFESTS = builtin_manifests(SEED_DIR)


def resolved(*slugs: str) -> list[ResolvedAgent]:
    return [ResolvedAgent(slug, slug, 1, MANIFESTS[slug], "class", "certified") for slug in slugs]


AGENTS = resolved("tro-ly-lop", "gia-su-toan", "on-tap-tai-lieu", "tao-de", "cham-van")


def step(key: str, agent: str, depends_on: list[str] | None = None, **extra) -> dict:
    return {
        "key": key,
        "agent": agent,
        "title": f"Việc {key}",
        "task": f"Làm {key}",
        "depends_on": depends_on or [],
        **extra,
    }


def plan(*steps: dict, **extra) -> dict:
    return {"goal": "Mục tiêu", "lead": "gia-su-toan", "missing": [], "steps": list(steps), **extra}


# --- Path choice (research R2) -----------------------------------------------------------------------------------


def turn_like(kind: str = "chat", policy: dict | None = None, in_class: bool = True) -> SimpleNamespace:
    room = SimpleNamespace(policy=policy if policy is not None else {}) if in_class else None
    return SimpleNamespace(kind=kind, room=room)


def triage(verdict: str = "allow", path: str = "full") -> TriageResult:
    return TriageResult(verdict, "safe", "", "gia-su-toan", "router: x", path=path)


def test_full_path_needs_every_condition(monkeypatch) -> None:
    assert takes_full_path(turn_like(), triage())
    assert takes_full_path(turn_like(in_class=False), triage())  # personal space: always on
    assert takes_full_path(turn_like(policy={"multi_step": True}), triage())
    assert not takes_full_path(turn_like(), triage(verdict="support"))  # FR-038
    assert not takes_full_path(turn_like(), triage(verdict="block"))
    assert not takes_full_path(turn_like(), triage(path="fast"))
    assert not takes_full_path(turn_like(kind="sandbox"), triage())
    assert not takes_full_path(turn_like(kind="certify"), triage())
    assert not takes_full_path(turn_like(policy={"multi_step": False}), triage())  # FR-046
    # Eval forces a path; safety still comes first.
    assert takes_full_path(turn_like(kind="certify"), triage(path="fast"), force_path="full")
    assert not takes_full_path(turn_like(), triage(), force_path="fast")
    assert not takes_full_path(turn_like(), triage(verdict="support"), force_path="full")


def test_no_planner_key_means_fast_path(monkeypatch) -> None:
    from app.config import get_settings

    monkeypatch.setenv("DIFY_PLANNER_KEY", "")
    get_settings.cache_clear()
    assert not takes_full_path(turn_like(), triage())
    assert not takes_full_path(turn_like(), triage(), force_path="full")


def test_triage_path_is_parsed_and_defaults_to_fast() -> None:
    assert triage_body("triage_path_full.json")["data"]["outputs"]["path"] == "full"
    assert TriageResult("allow", "safe", "", "x", "").path == "fast"


# --- Planner checks (contracts/dify-apps.md §2), one rule per case --------------------------------------------------


def test_unusable_plans_mean_fast_path() -> None:
    assert validate_plan(None, AGENTS) is None
    assert validate_plan("plan", AGENTS) is None
    assert validate_plan({"steps": "s1"}, AGENTS) is None
    assert validate_plan(plan(step("s1", "gia-su-toan")), []) is None


def test_lead_must_be_in_the_roster_and_the_requested_agent_wins() -> None:
    assert validate_plan(plan(step("s1", "tao-de"), lead="hacker"), AGENTS).lead == "tro-ly-lop"
    assert validate_plan(plan(step("s1", "tao-de"), lead="tao-de"), AGENTS).lead == "tao-de"
    chosen = validate_plan(plan(step("s1", "tao-de"), lead="tao-de"), AGENTS, requested_agent="cham-van")
    assert chosen.lead == "cham-van"
    no_fallback = resolved("gia-su-toan", "tao-de")
    assert validate_plan(plan(step("s1", "tao-de"), lead="x"), no_fallback).lead == "gia-su-toan"


def test_unknown_agents_become_the_lead() -> None:
    """FR-039: a slug outside the roster (from the plan or injected through the message) never runs."""
    checked = validate_plan(plan(step("s1", "hacker-agent"), step("s2", "tao-de")), AGENTS)
    assert [s["agent"] for s in checked.steps] == ["gia-su-toan", "tao-de"]


def test_repeated_keys_and_broken_dependencies_are_dropped() -> None:
    checked = validate_plan(
        plan(step("s1", "tao-de"), step("s1", "cham-van"), step("s2", "tao-de", ["s1", "s9", "s2"])), AGENTS
    )
    assert [(s["key"], s["agent"], s["depends_on"]) for s in checked.steps] == [
        ("s1", "tao-de", []),
        ("s2", "tao-de", ["s1"]),
    ]


def test_a_cycle_means_fast_path() -> None:
    assert validate_plan(plan(step("s1", "tao-de", ["s2"]), step("s2", "cham-van", ["s1"])), AGENTS) is None


def test_steps_are_cut_in_dependency_order_to_the_limits() -> None:
    raw = plan(
        step("s3", "cham-van", ["s1"]),
        step("s1", "on-tap-tai-lieu"),
        step("s2", "tao-de", ["s1"]),
        step("s4", "gia-su-toan", ["s3"]),
    )
    # Agents: lead gia-su-toan + on-tap-tai-lieu + cham-van = 3; tao-de is the fourth and is cut.
    checked = validate_plan(raw, AGENTS, limits=Limits(max_steps=5, max_agents=3))
    assert [s["key"] for s in checked.steps] == ["s1", "s3", "s4"]
    checked = validate_plan(raw, AGENTS, limits=Limits(max_steps=2, max_agents=5))
    assert [s["key"] for s in checked.steps] == ["s1", "s3"]
    # A kept step loses the edge to a step that was cut.
    checked = validate_plan(plan(step("s1", "tao-de"), step("s2", "cham-van", ["s1"])), AGENTS, limits=Limits(5, 2))
    assert [(s["key"], s["depends_on"]) for s in checked.steps] == [("s1", [])]


def test_questions_are_cut_to_the_limits() -> None:
    long_question = "Câu hỏi " + "rất dài " * 40
    raw = plan(
        step("s1", "tao-de"),
        missing=[
            {"id": "q1", "question": long_question, "options": [str(i) for i in range(9)]},
            {"id": "q1", "question": "Lớp mấy?", "options": ["7", "x" * 100]},
            {"question": ""},
            {"id": "q3", "question": "Mấy câu?"},
            {"id": "q4", "question": "Hạn nộp?"},
        ],
    )
    checked = validate_plan(raw, AGENTS, limits=Limits(max_questions=3))
    assert len(checked.missing) == 3
    first, second, _ = checked.missing
    assert len(first["question"]) == 200 and len(first["options"]) == 6
    assert second["id"] != "q1" and len(second["options"][1]) == 60


def test_without_asking_questions_and_interpretation_become_assumptions() -> None:
    raw = plan(
        step("s1", "tao-de"),
        missing=[{"id": "q1", "question": "Lớp mấy?", "options": ["7"]}],
        confirm_interpretation="Em muốn đề trắc nghiệm 10 câu",
        assumptions=["Mức trung bình"],
    )
    for kwargs in ({"interactive": False}, {"can_ask": False}):
        checked = validate_plan(raw, AGENTS, **kwargs)
        assert checked.missing == [] and checked.confirm_interpretation == ""
        assert checked.assumptions[0] == "Mức trung bình"
        assert any("Lớp mấy?" in a for a in checked.assumptions)
        assert "Em muốn đề trắc nghiệm 10 câu" in checked.assumptions
    asked = validate_plan(raw, AGENTS)
    assert asked.missing and asked.confirm_interpretation


def test_no_steps_means_one_step_for_the_lead() -> None:
    checked = validate_plan(plan(goal="Giải thích Pytago"), AGENTS)
    assert checked.steps == [
        {
            "key": "s1",
            "agent": "gia-su-toan",
            "title": f"Phần việc của {MANIFESTS['gia-su-toan'].name}",
            "task": "Giải thích Pytago",
            "depends_on": [],
        }
    ]


def test_titles_are_cut_and_screened() -> None:
    keyword = dify_rules.keywords()[0]
    checked = validate_plan(
        plan(step("s1", "tao-de", title="T" * 120), step("s2", "cham-van", title=f"Tìm {keyword} giúp")), AGENTS
    )
    assert len(checked.steps[0]["title"]) == 80
    assert checked.steps[1]["title"] == f"Phần việc của {MANIFESTS['cham-van'].name}"


def test_roster_lists_tools_and_the_fallback_and_skips_other_roles() -> None:
    roster = json.loads(planner_roster(AGENTS, "student"))
    slugs = {item["slug"] for item in roster}
    assert "tao-de" not in slugs  # teachers only
    fallback = next(item for item in roster if item["slug"] == "tro-ly-lop")
    assert fallback["is_fallback"] is True and isinstance(fallback["tools"], list)


def test_history_keeps_the_newest_messages_within_budget() -> None:
    messages = [("user" if i % 2 == 0 else "assistant", f"tin {i} " + "x" * 900) for i in range(10)]
    history = format_history(messages)
    assert history.count("\n") <= 5 and len(history) <= 3000
    assert history.endswith("x" * 10) and "tin 9" in history and "tin 0" not in history


# --- Prompts (research R4, R8) -------------------------------------------------------------------------------------


def test_step_and_synthesis_queries() -> None:
    query = build_step_query(
        "Mục tiêu", {"task": "Soạn bài"}, [("Tìm lý thuyết", "Pytago: a²+b²=c²"), ("Lỗi", "")], "giải thích Pytago"
    )
    assert "Soạn bài" in query and "a²+b²=c²" in query and "không có kết quả" in query and "giải thích Pytago" in query
    assert build_synthesis_query("Yêu cầu") == "Yêu cầu"
    extra = build_synthesis_query("Yêu cầu", [{"question": "Lớp mấy?", "answer": "8"}])
    assert extra.startswith("Yêu cầu") and "Thông tin bổ sung" in extra and "Lớp mấy?: 8" in extra


def test_synthesis_prompt_fits_and_keeps_the_class_policy() -> None:
    base = "QUY TẮC\n" + "a" * 6000 + "\nCHÍNH SÁCH LỚP"
    notes = [{"title": f"Việc {i}", "agent": "A", "status": "done", "note": "n" * 5000} for i in range(3)]
    notes.append({"title": "Hỏng", "agent": "B", "status": "error", "note": ""})
    prompt = build_synthesis_prompt(base, notes, assumptions=["Mức trung bình"])
    assert len(prompt) <= MAX_SYSTEM_PROMPT
    assert prompt.startswith(base) and "Chế độ tổng hợp" in prompt
    assert "Phần chưa làm được" in prompt and "Hỏng" in prompt and "Mức trung bình" in prompt
    # Every note is kept, each shortened to fit.
    kept = [len(chunk.split("\n", 1)[1].split("\n\n")[0]) for chunk in prompt.split("## Việc ")[1:]]
    assert len(kept) == 3 and all(100 < size < 5000 for size in kept)
    assert len(build_synthesis_prompt("x", notes[:1])) < len("x") + NOTES_BUDGET + 2000


# --- A full turn ---------------------------------------------------------------------------------------------------


async def class_with_agents(as_user, *slugs: str):
    teacher, student, parent, room = await class_with_student(as_user)
    hub = {agent["slug"]: agent for agent in (await teacher.get("/api/hub/agents")).json()}
    for slug in slugs:
        response = await teacher.post(f"/api/classes/{room['id']}/agents", json={"agent_id": hub[slug]["id"]})
        assert response.status_code == 201, response.text
    return teacher, student, parent, room


def step_note(answer: str = "") -> str:
    return fixture_text("runner_step_note.sse") if not answer else deltas_sse(answer, conversation_id="")


async def test_full_turn_runs_planner_steps_and_synthesis(app, as_user, dify, sessionmaker) -> None:
    _, student, _, room = await class_with_agents(as_user, "gia-su-toan", "on-tap-tai-lieu")
    dify.triage = triage_body("triage_path_full.json")
    # planner_multi: s1 on-tap-tai-lieu, s2 tao-de (teachers only, so it becomes the lead's step).
    dify.runner = [step_note(), step_note("Bài luyện: tam giác vuông cạnh 6 và 8."), deltas_sse("Kết quả ", "cuối.")]
    events = await chat(
        student, "Giải thích lại định lý Pytago theo tài liệu cô gửi rồi cho em một bài luyện", class_id=room["id"]
    )

    kinds = [(e["type"], e.get("key"), e.get("status")) for e in events if e["type"] in ("step", "plan", "agent")]
    assert kinds == [
        ("step", "analyze", "running"),
        ("step", "analyze", "done"),
        ("plan", None, None),
        ("step", "s1", "running"),
        ("step", "s1", "done"),
        ("step", "s2", "running"),
        ("step", "s2", "done"),
        ("step", "synthesis", "running"),
        ("agent", None, None),
    ]
    [plan_event] = [e for e in events if e["type"] == "plan"]
    assert plan_event["lead"]["slug"] == "gia-su-toan" and plan_event["resumed"] is False
    assert [(s["key"], s["agent"]["slug"], s["depends_on"]) for s in plan_event["steps"]] == [
        ("s1", "on-tap-tai-lieu", []),
        ("s2", "gia-su-toan", ["s1"]),
    ]
    assert reply_text(events) == "Kết quả cuối."
    done = events[-1]
    assert done["type"] == "done" and done["status"] == "ok" and done["path"] == "full"
    assert done["agent"] == "gia-su-toan"

    # Steps run on fresh Dify conversations with STEP_MODE; s2 gets s1's note; the synthesis runs on the main one.
    first, second, synthesis = dify.calls("/chat-messages")
    assert first["conversation_id"] == "" and second["conversation_id"] == ""
    assert "Chế độ phần việc" in first["inputs"]["system_prompt"]
    assert "Tóm tắt định lý Pytago" in second["query"]
    assert "Chế độ tổng hợp" in synthesis["inputs"]["system_prompt"]
    assert "tam giác vuông cạnh 6 và 8" in synthesis["inputs"]["system_prompt"]
    assert synthesis["query"].startswith("Giải thích lại định lý Pytago")
    [planner_call] = dify.calls("#planner")
    assert planner_call["inputs"]["role"] == "student" and planner_call["inputs"]["interactive"] == "true"
    assert "tao-de" not in planner_call["inputs"]["roster"]

    [run] = await rows(sessionmaker, TurnRun)
    assert run.status == "done" and run.lead_agent == "gia-su-toan" and run.reply_message_id == done["message_id"]
    steps = sorted(await rows(sessionmaker, RunStep), key=lambda s: s.key)
    assert [(s.key, s.status, s.origin) for s in steps] == [("s1", "done", "plan"), ("s2", "done", "plan")]
    assert "Pytago" in steps[0].note and steps[0].note_review == "unreviewed"
    [reply] = await rows(sessionmaker, ChatMessage, ChatMessage.role == "assistant")
    assert reply.meta["path"] == "full" and reply.meta["run_id"] == run.id
    assert reply.meta["assumptions"] == ["Bài luyện mức trung bình"]

    usage = await rows(sessionmaker, UsageRecord)
    assert {u.purpose for u in usage} == {"triage", "planner", "step", "synthesis", "output_guard"}
    assert {u.path for u in usage} == {"full"}


async def test_unusable_plan_falls_back_to_the_fast_path(app, as_user, dify, sessionmaker) -> None:
    _, student, _, room = await class_with_student(as_user)
    dify.triage = triage_body("triage_path_full.json")
    for planner in (planner_body("planner_invalid.json"), "down", 500):
        dify.planner = planner
        dify.runner = [deltas_sse("Trả lời nhanh.")]
        events = await chat(student, "Làm đề ôn tập cho em", class_id=room["id"])
        steps = [(e["key"], e["status"]) for e in events if e["type"] == "step"]
        assert steps == [("analyze", "running"), ("analyze", "skipped")]
        assert reply_text(events) == "Trả lời nhanh."
        assert events[-1]["status"] == "ok" and events[-1]["path"] == "fast"
    assert await rows(sessionmaker, TurnRun) == []
    assert {u.path for u in await rows(sessionmaker, UsageRecord)} == {"fast"}


@pytest.mark.parametrize("triage_name", ["triage_path_fast.json", "triage_self_harm_risk.json"])
async def test_fast_path_does_not_call_the_planner(app, as_user, dify, sessionmaker, triage_name) -> None:
    _, student, _, room = await class_with_student(as_user)
    dify.triage = triage_body(triage_name, path="full") if "self_harm" in triage_name else triage_body(triage_name)
    events = await chat(student, "Định lý Pytago dùng để làm gì?", class_id=room["id"])
    assert dify.calls("#planner") == []
    assert "step" not in {e["type"] for e in events} and "plan" not in {e["type"] for e in events}
    assert events[-1]["path"] == "fast"
    [reply] = await rows(sessionmaker, ChatMessage, ChatMessage.role == "assistant")
    assert reply.meta["path"] == "fast"


async def test_class_switch_keeps_every_turn_on_the_fast_path(app, as_user, dify) -> None:
    teacher, student, _, room = await class_with_student(as_user)
    url = f"/api/classes/{room['id']}/policy"
    policy = (await teacher.get(url)).json()
    await teacher.put(url, json={**policy, "multi_step": False})
    dify.triage = triage_body("triage_path_full.json")
    events = await chat(student, "Làm đề ôn tập cho em", class_id=room["id"])
    assert dify.calls("#planner") == [] and events[-1]["path"] == "fast"


async def test_a_blocked_step_is_logged_with_its_agent_and_the_rest_continues(app, as_user, dify, sessionmaker) -> None:
    _, student, _, room = await class_with_agents(as_user, "gia-su-toan", "on-tap-tai-lieu")
    dify.triage = triage_body("triage_path_full.json")
    dify.planner = planner_body(plan=plan(step("s1", "on-tap-tai-lieu"), step("s2", "gia-su-toan", ["s1"])))
    dify.runner = [fixture_text("runner_step_replaced.sse"), step_note("Ghi chú s2."), deltas_sse("Xong.")]
    events = await chat(student, "Tìm lý thuyết rồi soạn bài", class_id=room["id"])
    assert [(e["key"], e["status"]) for e in events if e["type"] == "step" and e["key"] in ("s1", "s2")][1::2] == [
        ("s1", "blocked"),
        ("s2", "done"),
    ]
    [_, _, synthesis] = dify.calls("/chat-messages")
    assert "Phần chưa làm được" in synthesis["inputs"]["system_prompt"]
    [event] = await rows(sessionmaker, GuardEvent, GuardEvent.stage == "step")
    assert event.agent_slug == "on-tap-tai-lieu" and event.verdict == "block"
    assert events[-1]["status"] == "ok"


async def test_every_step_failing_gives_a_friendly_error(app, as_user, dify, sessionmaker) -> None:
    _, student, _, room = await class_with_student(as_user)
    dify.triage = triage_body("triage_path_full.json")
    dify.planner = planner_body(plan=plan(step("s1", "tro-ly-lop"), lead="tro-ly-lop"))
    dify.runner = ["down"]
    events = await chat(student, "Làm giúp em", class_id=room["id"])
    assert [(e["key"], e["status"]) for e in events if e["type"] == "step"][-1] == ("s1", "error")
    assert reply_text(events) == ""
    assert any(e["type"] == "error" for e in events)
    assert events[-1]["status"] == "error" and events[-1]["path"] == "full"
    [run] = await rows(sessionmaker, TurnRun)
    assert run.status == "error"
    # Only the planner was asked after triage: no synthesis on nothing.
    assert len(dify.calls("/chat-messages")) == 1


# --- Several agents (User Story 2) -----------------------------------------------------------------------------------


def three_steps() -> dict:
    """s1 and s2 are independent (one layer), s3 needs both."""
    return plan(step("s1", "on-tap-tai-lieu"), step("s2", "gia-su-toan"), step("s3", "gia-su-toan", ["s1", "s2"]))


def statuses(events: list[dict]) -> dict[str, str]:
    """The last status of every plan step."""
    return {e["key"]: e["status"] for e in events if e["type"] == "step" and e["key"] not in ("analyze", "synthesis")}


async def test_steps_of_one_layer_run_at_the_same_time(app, as_user, dify, sessionmaker) -> None:
    _, student, _, room = await class_with_agents(as_user, "gia-su-toan", "on-tap-tai-lieu")
    dify.triage = triage_body("triage_path_full.json")
    dify.planner = planner_body(plan=three_steps())
    note = deltas_sse("Ghi chú song song.", conversation_id="")
    dify.runner = [Slow(note, 0.3), Slow(note, 0.3), step_note("Ghi chú s3."), deltas_sse("Kết quả.")]
    events = await chat(student, "Tìm lý thuyết, soạn bài rồi tổng hợp", class_id=room["id"])

    assert dify.max_parallel == 2
    order = [(e["key"], e["status"]) for e in events if e["type"] == "step" and e["key"].startswith("s")]
    assert order[:2] == [("s1", "running"), ("s2", "running")]
    assert order.index(("s3", "running")) > max(order.index(("s1", "done")), order.index(("s2", "done")))
    # s3 gets the notes of both steps it depends on.
    s3 = dify.calls("/chat-messages")[2]
    assert "Kết quả của phần “Việc s1”" in s3["query"] and "Kết quả của phần “Việc s2”" in s3["query"]
    assert all(e["duration_ms"] >= 0 for e in events if e["type"] == "step" and e["status"] == "done")

    # FR-029: the lead (gia-su-toan) is not listed; on-tap-tai-lieu is.
    done = events[-1]
    assert [c["slug"] for c in done["contributors"]] == ["on-tap-tai-lieu"]
    [reply] = await rows(sessionmaker, ChatMessage, ChatMessage.role == "assistant")
    assert reply.meta["contributors"] == done["contributors"]


async def test_a_slow_step_times_out_and_the_rest_goes_on(app, as_user, dify, sessionmaker, monkeypatch) -> None:
    from app.config import get_settings

    monkeypatch.setenv("ORCH_STEP_TIMEOUT_S", "0.3")
    get_settings.cache_clear()
    _, student, _, room = await class_with_agents(as_user, "gia-su-toan", "on-tap-tai-lieu")
    dify.triage = triage_body("triage_path_full.json")
    dify.planner = planner_body(
        plan=plan(step("s1", "on-tap-tai-lieu"), step("s2", "gia-su-toan"), step("s3", "gia-su-toan", ["s1"]))
    )
    dify.runner = [Slow(step_note(), 3), step_note("Ghi chú s2."), step_note("Ghi chú s3."), deltas_sse("Kết quả.")]
    events = await chat(student, "Làm ba việc", class_id=room["id"])

    assert statuses(events) == {"s1": "error", "s2": "done", "s3": "done"}
    # A step after a failed one still runs, told that part has no result (FR-026).
    s3 = [c for c in dify.calls("/chat-messages") if "Làm s3" in c.get("query", "")][0]
    assert "phần “Việc s1” không có kết quả" in s3["query"]
    prompt = [c for c in dify.calls("/chat-messages") if "query" in c][-1]["inputs"]["system_prompt"]
    assert "Phần chưa làm được" in prompt and "Việc s1" in prompt
    assert events[-1]["status"] == "ok"
    s1 = [s for s in await rows(sessionmaker, RunStep) if s.key == "s1"][0]
    assert s1.status == "error" and s1.error == "Phần việc quá thời gian."
    assert dify.calls("/stop")  # the timed-out Dify task was stopped


async def test_past_the_deadline_the_remaining_steps_are_skipped(app, as_user, dify, monkeypatch) -> None:
    from app.config import get_settings

    monkeypatch.setenv("ORCH_DEADLINE_S", "0.4")
    get_settings.cache_clear()
    _, student, _, room = await class_with_agents(as_user, "gia-su-toan", "on-tap-tai-lieu")
    dify.triage = triage_body("triage_path_full.json")
    dify.planner = planner_body(plan=plan(step("s1", "on-tap-tai-lieu"), step("s2", "gia-su-toan", ["s1"])))
    dify.runner = [Slow(step_note(), 0.6), deltas_sse("Kết quả.")]
    events = await chat(student, "Làm hai việc", class_id=room["id"])
    assert statuses(events) == {"s1": "done", "s2": "skipped"}
    assert events[-1]["status"] == "ok"


async def test_a_mentioned_agent_leads_the_plan(app, as_user, dify) -> None:
    _, student, _, room = await class_with_agents(as_user, "gia-su-toan", "on-tap-tai-lieu")
    dify.triage = triage_body("triage_path_full.json", agent="on-tap-tai-lieu", route_reason="mention")
    dify.planner = planner_body(plan=plan(step("s1", "gia-su-toan"), lead="gia-su-toan"))
    dify.runner = [step_note("Ghi chú."), deltas_sse("Kết quả.")]
    events = await chat(student, "@on-tap-tai-lieu tóm tắt rồi cho bài luyện", class_id=room["id"])
    [plan_event] = [e for e in events if e["type"] == "plan"]
    assert plan_event["lead"]["slug"] == "on-tap-tai-lieu"
    assert dify.calls("#planner")[0]["inputs"]["requested_agent"] == "on-tap-tai-lieu"
    assert events[-1]["agent"] == "on-tap-tai-lieu"
    assert [c["slug"] for c in events[-1]["contributors"]] == ["gia-su-toan"]


async def test_citations_of_every_step_are_merged(app, as_user, dify, sessionmaker, monkeypatch) -> None:
    from app.orchestrator import steps as steps_module

    original = steps_module.run_step

    async def with_citation(turn, client, agent, agents, row, **kwargs):
        outcome = await original(turn, client, agent, agents, row, **kwargs)
        outcome.citations = [{"document_id": f"doc-{row.key}", "title": row.key, "location": "trang 1", "excerpt": "x"}]
        return outcome

    monkeypatch.setattr(steps_module, "run_step", with_citation)
    _, student, _, room = await class_with_agents(as_user, "gia-su-toan", "on-tap-tai-lieu")
    dify.triage = triage_body("triage_path_full.json")
    dify.planner = planner_body(plan=plan(step("s1", "on-tap-tai-lieu"), step("s2", "gia-su-toan", ["s1"])))
    dify.runner = [step_note("A."), step_note("B."), deltas_sse("Kết quả.")]
    events = await chat(student, "Tìm rồi soạn", class_id=room["id"])
    [citations] = [e for e in events if e["type"] == "citations"]
    assert [c["document_id"] for c in citations["items"]] == ["doc-s1", "doc-s2"]
    [reply] = await rows(sessionmaker, ChatMessage, ChatMessage.role == "assistant")
    assert [c["document_id"] for c in reply.meta["citations"]] == ["doc-s1", "doc-s2"]


async def test_leaving_mid_run_cancels_the_steps_and_stops_dify(app, as_user, dify, sessionmaker) -> None:
    """FR-040: the client goes away while steps run."""
    from app.chat.router import ChatIn
    from app.runtime.dify_turn import run_dify_turn
    from tests.helpers import parse_sse

    _, student, _, room = await class_with_agents(as_user, "gia-su-toan", "on-tap-tai-lieu")
    dify.triage = triage_body("triage_path_full.json")
    dify.planner = planner_body(plan=plan(step("s1", "on-tap-tai-lieu"), step("s2", "gia-su-toan")))
    dify.runner = [Slow(step_note(), 5)]
    payload = ChatIn(message="Làm hai việc", class_id=room["id"])
    stream = run_dify_turn(student.user["id"], room["id"], "student", payload)
    async for chunk in stream:
        if any(e["type"] == "step" and e["key"] == "s2" and e["status"] == "running" for e in parse_sse(chunk)):
            break
    await asyncio.sleep(0.05)  # the steps' Dify streams have started
    await stream.aclose()

    assert dify.calls("/stop")
    [run] = await rows(sessionmaker, TurnRun)
    assert run.status == "cancelled"
    assert await rows(sessionmaker, ChatMessage, ChatMessage.role == "assistant") == []


# --- Phase 9 convergence --------------------------------------------------------------------------------------------


async def test_the_synthesis_query_holds_no_working_note(app, as_user, dify) -> None:
    """T087, FR-031: working notes go only in the system prompt, never into the main Dify conversation."""
    _, student, _, room = await class_with_agents(as_user, "gia-su-toan", "on-tap-tai-lieu")
    dify.triage = triage_body("triage_path_full.json")
    dify.planner = planner_body(plan=plan(step("s1", "on-tap-tai-lieu"), step("s2", "gia-su-toan", ["s1"])))
    dify.runner = [step_note("GHI-CHU-MOT"), step_note("GHI-CHU-HAI"), deltas_sse("Kết quả.")]
    await chat(student, "Tìm rồi soạn", class_id=room["id"])
    synthesis = dify.calls("/chat-messages")[-1]
    assert synthesis["query"] == "Tìm rồi soạn"
    prompt = synthesis["inputs"]["system_prompt"]
    assert "GHI-CHU-MOT" in prompt and "GHI-CHU-HAI" in prompt


async def test_a_step_tool_event_carries_its_step_key(app, as_user, dify, sessionmaker) -> None:
    """T088, FR-032: a tool called inside a step reaches the stream with the step's key and is kept on the step."""
    _, student, _, room = await class_with_agents(as_user, "gia-su-toan")
    dify.triage = triage_body("triage_path_full.json")
    dify.planner = planner_body(plan=plan(step("s1", "gia-su-toan")))
    dify.runner = [step_note("Đã kiểm tra."), deltas_sse("Kết quả.")]
    dify.tool_calls = [("math_check", {"expression": "3**2 + 4**2", "expected": "25"})]
    events = await chat(student, "Kiểm tra 3² + 4² rồi giải thích", class_id=room["id"])
    step_tools = [e for e in events if e["type"] == "tool" and e.get("step_key") == "s1"]
    assert step_tools and step_tools[0]["name"] == "math_check"
    # The synthesis' own call has no step key.
    assert any(e["type"] == "tool" and e.get("step_key") is None for e in events)
    [row] = await rows(sessionmaker, RunStep)
    assert any(tool["name"] == "math_check" for tool in row.tools)


# --- Working notes (User Story 3, research R9) ----------------------------------------------------------------------


async def full_answer(as_user, dify, who: str = "student"):
    """A finished full-path answer with s1 done and s2 failed. Returns (client, other user, final message id)."""
    teacher, student, parent, room = await class_with_agents(as_user, "gia-su-toan", "on-tap-tai-lieu")
    dify.triage = triage_body("triage_path_full.json")
    dify.planner = planner_body(plan=plan(step("s1", "on-tap-tai-lieu"), step("s2", "gia-su-toan", ["s1"])))
    dify.runner = [step_note("Pytago: a² + b² = c², trang 3."), "down", deltas_sse("Kết quả.")]
    viewer = student if who == "student" else teacher
    events = await chat(viewer, "Tìm lý thuyết rồi soạn bài", class_id=room["id"])
    assert events[-1]["status"] == "ok"
    other = parent if who == "student" else student
    return viewer, other, events[-1]["message_id"]


def note_url(message_id: str, key: str) -> str:
    return f"/api/chat/messages/{message_id}/steps/{key}/note"


async def test_meta_process_rebuilds_the_panel(app, as_user, dify, sessionmaker) -> None:
    _, _, message_id = await full_answer(as_user, dify)
    [reply] = await rows(sessionmaker, ChatMessage, ChatMessage.id == message_id)
    process = reply.meta["process"]
    assert process["agents"] == 2 and process["duration_ms"] >= 0
    assert [(s["key"], s["agent"], s["status"]) for s in process["steps"]] == [
        ("s1", "on-tap-tai-lieu", "done"),
        ("s2", "gia-su-toan", "error"),
    ]


async def test_a_note_is_reviewed_once_then_served_from_storage(app, as_user, dify, sessionmaker) -> None:
    student, _, message_id = await full_answer(as_user, dify)
    reviews = len(dify.calls("#review"))
    first = await student.get(note_url(message_id, "s1"))
    assert first.status_code == 200
    body = first.json()
    assert body["visibility"] == "visible" and "a² + b² = c²" in body["note"] and body["agent"] == "on-tap-tai-lieu"
    assert len(dify.calls("#review")) == reviews + 1
    review = dify.calls("#review")[-1]["inputs"]
    assert review["role"] == "student" and review["no_direct_answers"] == "true"
    second = await student.get(note_url(message_id, "s1"))
    assert second.json() == body and len(dify.calls("#review")) == reviews + 1
    [row] = await rows(sessionmaker, RunStep, RunStep.key == "s1")
    assert row.note_review == "visible"
    assert any(u.purpose == "note_review" and u.path == "full" for u in await rows(sessionmaker, UsageRecord))


async def test_only_the_owner_sees_a_note(app, as_user, dify) -> None:
    _, other, message_id = await full_answer(as_user, dify)
    assert (await other.get(note_url(message_id, "s1"))).status_code == 404
    student, _, _ = await full_answer(as_user, dify)
    assert (await student.get(note_url(message_id, "s9"))).status_code == 404


async def test_a_failed_step_has_no_note(app, as_user, dify) -> None:
    student, _, message_id = await full_answer(as_user, dify)
    body = (await student.get(note_url(message_id, "s2"))).json()
    assert body["visibility"] == "unavailable" and body["note"] is None


async def test_a_failed_review_hides_the_note_without_storing(app, as_user, dify, sessionmaker) -> None:
    student, _, message_id = await full_answer(as_user, dify)
    dify.review = "down"
    body = (await student.get(note_url(message_id, "s1"))).json()
    assert body["visibility"] == "hidden" and body["note"] is None and body["reason_text"] == "Nội dung này đã được ẩn"
    [row] = await rows(sessionmaker, RunStep, RunStep.key == "s1")
    assert row.note_review == "unreviewed"
    dify.review = {"verdict": "allow", "category": "", "reason": ""}
    assert (await student.get(note_url(message_id, "s1"))).json()["visibility"] == "visible"


async def test_a_blocked_note_is_hidden_and_logged_with_its_agent(app, as_user, dify, sessionmaker) -> None:
    student, _, message_id = await full_answer(as_user, dify)
    dify.review = {"verdict": "block", "category": "academic_integrity", "reason": "Lời giải hoàn chỉnh"}
    body = (await student.get(note_url(message_id, "s1"))).json()
    assert body["visibility"] == "hidden" and body["note"] is None
    [event] = await rows(sessionmaker, GuardEvent, GuardEvent.stage == "step_note")
    assert event.detector == "dify_review" and event.agent_slug == "on-tap-tai-lieu" and event.verdict == "block"
    [row] = await rows(sessionmaker, RunStep, RunStep.key == "s1")
    assert row.note_review == "hidden"


async def test_a_blocked_answer_hides_every_note(app, as_user, dify, sessionmaker) -> None:
    student, _, message_id = await full_answer(as_user, dify)
    async with sessionmaker() as db:
        message = await db.get(ChatMessage, message_id)
        message.status = "blocked"
        await db.commit()
    reviews = len(dify.calls("#review"))
    assert (await student.get(note_url(message_id, "s1"))).json()["visibility"] == "hidden"
    assert len(dify.calls("#review")) == reviews


async def test_teachers_get_the_keyword_check_only(app, as_user, dify, sessionmaker) -> None:
    teacher, _, message_id = await full_answer(as_user, dify, who="teacher")
    reviews = len(dify.calls("#review"))
    assert (await teacher.get(note_url(message_id, "s1"))).json()["visibility"] == "visible"
    assert len(dify.calls("#review")) == reviews
    keyword = dify_rules.keywords()[0]
    async with sessionmaker() as db:
        [row] = list(await db.scalars(select(RunStep).where(RunStep.key == "s1")))
        row.note, row.note_review = f"Có {keyword} ở đây", "unreviewed"
        await db.commit()
    assert (await teacher.get(note_url(message_id, "s1"))).json()["visibility"] == "hidden"
    [event] = await rows(sessionmaker, GuardEvent, GuardEvent.stage == "step_note")
    assert event.agent_slug == "on-tap-tai-lieu"
