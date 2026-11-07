"""The `dify` engine against recorded Dify responses (backend/tests/fixtures/dify/), offline via httpx.MockTransport."""

import json
from pathlib import Path

import httpx
import pytest
from sqlalchemy import select

from app.audit.models import GuardEvent
from app.chat.models import ChatMessage, Conversation, ToolCallLog, UsageRecord
from app.chat.router import ChatIn
from app.config import get_settings
from app.guard import dify_rules
from app.runtime import dify_turn
from app.runtime.dify_client import DifyClient
from app.tools import context as handles
from app.tools import registry
from tests.helpers import chat, class_with_student, parse_sse, reply_text

FIXTURES = Path(__file__).parent / "fixtures" / "dify"
BASE = "http://dify.test"


def fixture_text(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def triage_body(name: str = "triage_safe.json", **outputs) -> dict:
    body = json.loads(fixture_text(name))
    body["data"]["outputs"].update(outputs)
    return body


def sse_body(*events: dict) -> str:
    return "".join(f"data: {json.dumps(event, ensure_ascii=False)}\n\n" for event in events)


def deltas_sse(*chunks: str, conversation_id: str = "dify-conv-1") -> str:
    """A minimal runner stream in the recorded event shapes."""
    ids = {"task_id": "task-1", "message_id": "dify-msg-1", "conversation_id": conversation_id}
    return sse_body(
        {"event": "workflow_started", **ids, "data": {}},
        *({"event": "message", **ids, "answer": chunk} for chunk in chunks),
        {
            "event": "message_end",
            **ids,
            "metadata": {"usage": {"prompt_tokens": 100, "completion_tokens": 20, "total_tokens": 120}},
        },
        {"event": "workflow_finished", **ids, "data": {"status": "succeeded"}},
    )


class FakeDify:
    """Answers triage, runner, stop and suggested calls like Dify, and records every request."""

    def __init__(self) -> None:
        self.triage: dict | int = triage_body()
        # One entry per runner call: SSE text, or (status, json body) for a refused request.
        self.runner: list[str | tuple[int, dict]] = [fixture_text("runner_plain.sse")]
        self.tool_calls: list[tuple[str, dict]] = []  # made through the MCP handler before the runner answers
        self.requests: list[tuple[str, dict]] = []

    def calls(self, kind: str) -> list[dict]:
        return [body for path, body in self.requests if kind in path]

    async def handler(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content) if request.content else dict(request.url.params)
        self.requests.append((request.url.path, body))
        path = request.url.path
        if path.endswith("/workflows/run"):
            if self.triage == "down":
                raise httpx.ConnectTimeout("Dify is down", request=request)
            if isinstance(self.triage, int):
                return httpx.Response(self.triage, json={"code": "internal_server_error", "message": "boom"})
            return httpx.Response(200, json=self.triage)
        if path.endswith("/chat-messages"):
            answer = self.runner.pop(0) if len(self.runner) > 1 else self.runner[0]
            if answer == "down":
                raise httpx.ConnectError("Dify is down", request=request)
            if isinstance(answer, tuple):
                return httpx.Response(answer[0], json=answer[1])
            for name, arguments in self.tool_calls:
                try:
                    await registry.run_tool(body["inputs"]["ctx"], name, arguments)
                except Exception:
                    pass  # Dify hands the error text to the model
            return httpx.Response(200, text=answer, headers={"content-type": "text/event-stream"})
        if path.endswith("/stop"):
            return httpx.Response(200, json={"result": "success"})
        if path.endswith("/suggested"):
            return httpx.Response(200, text=fixture_text("suggested.json"))
        return httpx.Response(404, json={"code": "not_found", "message": "unknown"})


@pytest.fixture
def dify(monkeypatch) -> FakeDify:
    fake = FakeDify()
    for name, value in {"RUNTIME_ENGINE": "dify", "DIFY_BASE_URL": BASE, "DIFY_TRIAGE_KEY": "app-triage"}.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setenv("DIFY_RUNNER_KEY", "app-runner")
    get_settings.cache_clear()
    monkeypatch.setattr(
        dify_turn, "make_client", lambda: DifyClient(httpx.AsyncClient(transport=httpx.MockTransport(fake.handler)))
    )
    yield fake
    monkeypatch.undo()
    get_settings.cache_clear()


def utf16(text: str) -> int:
    return len(text.encode("utf-16-le")) // 2


async def rows(sessionmaker, model, *where):
    async with sessionmaker() as db:
        return list(await db.scalars(select(model).where(*where)))


# --- T017: the client --------------------------------------------------------------------------------------------


async def test_triage_outputs_are_parsed(dify) -> None:
    client = DifyClient(httpx.AsyncClient(transport=httpx.MockTransport(dify.handler)))
    result = await client.run_triage({"query": "x"}, user="u-1")
    assert (result.verdict, result.category, result.agent) == ("allow", "safe", "gia-su-toan")
    assert result.route_reason.startswith("router: ")
    assert result.usage is not None and result.usage.input_tokens > 0


async def test_runner_stream_is_parsed_from_the_recorded_fixture(dify) -> None:
    client = DifyClient(httpx.AsyncClient(transport=httpx.MockTransport(dify.handler)))
    events = [event async for event in client.stream_runner("q", {}, "", "u-1")]
    recorded = [
        json.loads(line[5:]) for line in fixture_text("runner_plain.sse").splitlines() if line.startswith("data:")
    ]
    assert events[0].kind == "start" and events[0].task_id == recorded[0]["task_id"]
    expected = "".join(e.get("answer", "") for e in recorded if e["event"] == "message")
    assert "".join(e.text for e in events if e.kind == "delta") == expected
    [end] = [e for e in events if e.kind == "end"]
    assert end.message_id == recorded[0]["message_id"]
    assert end.usage is not None and end.usage.input_tokens > 0 and end.usage.output_tokens > 0


async def test_failed_run_without_a_message_is_an_error(dify) -> None:
    """System prompt over the 12000-character input limit: Dify ends the run before any node."""
    dify.runner = [fixture_text("runner_input_too_long.sse")]
    client = DifyClient(httpx.AsyncClient(transport=httpx.MockTransport(dify.handler)))
    events = [event async for event in client.stream_runner("q", {}, "", "u-1")]
    assert [e.kind for e in events] == ["start", "error"]
    assert "12000" in events[-1].text


# --- T018: a full turn -------------------------------------------------------------------------------------------


async def test_turn_streams_in_contract_order_with_utf16_offsets(app, as_user, dify, sessionmaker) -> None:
    _, student, _, room = await class_with_student(as_user)
    dify.runner = [deltas_sse("Chào em 👋, ", "phân số ", "½ nhé.")]
    events = await chat(student, "So sánh 3/4 và 2/3", class_id=room["id"])
    types = [event["type"] for event in events]
    assert types[:3] == ["operation", "conversation", "agent"]
    assert types[-1] == "done" and events[-1]["status"] == "ok"
    assert set(types[3:-1]) == {"text_delta"}
    shown = ""
    for event in events[3:-1]:
        assert event["generation"] == 0 and event["text_offset"] == utf16(shown)
        shown += event["delta"]
    assert shown == "Chào em 👋, phân số ½ nhé."
    [stored] = await rows(sessionmaker, ChatMessage, ChatMessage.role == "assistant")
    assert stored.content == shown and stored.meta["engine"] == "dify"
    assert stored.meta["dify_message_id"] == "dify-msg-1" and stored.meta["route_reason"]
    purposes = {row.purpose for row in await rows(sessionmaker, UsageRecord)}
    assert purposes == {"triage", "agent"}


async def test_dify_conversation_id_is_kept_and_sent_back(app, as_user, dify, sessionmaker) -> None:
    _, student, _, room = await class_with_student(as_user)
    dify.runner = [deltas_sse("Một.", conversation_id="dify-conv-7")]
    first = await chat(student, "Câu một", class_id=room["id"])
    conversation_id = first[1]["conversation_id"]
    await chat(student, "Câu hai", class_id=room["id"], conversation_id=conversation_id)
    sent = [body["conversation_id"] for body in dify.calls("/chat-messages")]
    assert sent == ["", "dify-conv-7"]
    [conversation] = await rows(sessionmaker, Conversation)
    assert conversation.dify_conversation_id == "dify-conv-7"


async def test_dify_gets_the_user_id_and_the_available_roster_only(app, as_user, dify) -> None:
    _, student, _, room = await class_with_student(as_user)
    await chat(student, "Em hỏi bài", class_id=room["id"], agent="khong-co-agent-nay")
    [triage] = dify.calls("/workflows/run")
    [runner] = dify.calls("/chat-messages")
    assert triage["user"] == runner["user"] == student.user["id"]
    assert student.user["email"] not in json.dumps([triage, runner], ensure_ascii=False)
    agents = (await student.get("/api/chat/agents", params={"class_id": room["id"]})).json()
    roster = json.loads(triage["inputs"]["roster"])
    assert sorted(a["slug"] for a in roster) == sorted(a["slug"] for a in agents)
    # An agent that is not available here (e.g. removed from the class) is never requested.
    assert triage["inputs"]["requested_agent"] == ""


async def test_agent_outside_the_roster_falls_back_to_the_class_assistant(app, as_user, dify) -> None:
    _, student, _, room = await class_with_student(as_user)
    dify.triage = triage_body(agent="agent-la", route_reason="router: x")
    events = await chat(student, "Em hỏi bài", class_id=room["id"])
    [agent] = [e for e in events if e["type"] == "agent"]
    assert agent["agent"] == "tro-ly-lop" and agent["reason"] == "fallback"


@pytest.mark.parametrize("failure", [500, "down", "bad_outputs"])
async def test_triage_failure_fails_closed(app, as_user, dify, sessionmaker, failure) -> None:
    _, student, _, room = await class_with_student(as_user)
    dify.triage = triage_body(verdict="") if failure == "bad_outputs" else failure
    events = await chat(student, "Em hỏi bài", class_id=room["id"])
    assert [e["type"] for e in events][-2:] == ["error", "done"]
    assert events[-2]["message"] == "Hệ thống trợ lý đang bận, em thử lại sau ít phút nhé."
    assert events[-1]["status"] == "error"
    assert dify.calls("/chat-messages") == []
    [stored] = await rows(sessionmaker, ChatMessage, ChatMessage.role == "assistant")
    assert stored.status == "error"


async def test_student_without_consent_never_reaches_dify(app, as_user, dify, sessionmaker) -> None:
    _, student, _, room = await class_with_student(as_user, consent=False)
    events = await chat(student, "Em hỏi bài", class_id=room["id"])
    assert events[-1] == {"type": "done", "message_id": events[0]["operation_id"], "status": "consent_required"}
    assert dify.requests == []
    assert await rows(sessionmaker, ChatMessage) == []


async def test_tool_events_from_the_mcp_handler_reach_the_stream(app, as_user, dify, sessionmaker) -> None:
    _, student, _, room = await class_with_student(as_user)
    dify.triage = triage_body(agent="gia-su-toan")
    dify.tool_calls = [("math_check", {"operation": "solve", "expression": "2*x+3=7"})]
    dify.runner = [deltas_sse("x = 2.")]
    events = await chat(student, "Giải 2x+3=7", class_id=room["id"])
    agent = next(e["agent"] for e in events if e["type"] == "agent")
    tools = [(e["name"], e["status"]) for e in events if e["type"] == "tool"]
    # The tool guard runs in the handler: math_check is granted to the math tutor.
    expected = "done" if agent == "gia-su-toan" else "denied"
    assert tools == [("math_check", "start"), ("math_check", expected)]
    assert [e["type"] for e in events].index("tool") < [e["type"] for e in events].index("text_delta")
    [logged] = await rows(sessionmaker, ToolCallLog)
    assert logged.message_id == events[0]["operation_id"]
    [stored] = await rows(sessionmaker, ChatMessage, ChatMessage.role == "assistant")
    assert stored.meta["tools"] == [
        {"name": "math_check", "status": "start"},
        {"name": "math_check", "status": expected},
    ]
    assert handles._live == {}  # released when the turn ended


# --- T019: memory reset, errors, stop ----------------------------------------------------------------------------


async def test_lost_dify_conversation_starts_a_new_one(app, as_user, dify, sessionmaker) -> None:
    _, student, _, room = await class_with_student(as_user)
    dify.runner = [deltas_sse("Một.", conversation_id="dify-old")]
    first = await chat(student, "Câu một", class_id=room["id"])
    not_found = json.loads(fixture_text("runner_conversation_not_found.json"))
    dify.runner = [(404, not_found), deltas_sse("Hai.", conversation_id="dify-new")]
    events = await chat(student, "Câu hai", class_id=room["id"], conversation_id=first[1]["conversation_id"])
    [notice] = [e for e in events if e["type"] == "notice"]
    assert notice["kind"] == "context_reset" and "không còn nhớ" in notice["text"]
    assert events[-1]["status"] == "ok" and reply_text(events) == "Hai."
    assert [body["conversation_id"] for body in dify.calls("/chat-messages")] == ["", "dify-old", ""]
    [conversation] = await rows(sessionmaker, Conversation)
    assert conversation.dify_conversation_id == "dify-new"


async def test_runner_down_reports_busy(app, as_user, dify, sessionmaker) -> None:
    _, student, _, room = await class_with_student(as_user)
    dify.runner = ["down"]
    events = await chat(student, "Em hỏi bài", class_id=room["id"])
    assert [e["type"] for e in events][-2:] == ["error", "done"]
    assert events[-2]["message"] == "Hệ thống trợ lý đang bận, em thử lại sau ít phút nhé."
    assert events[-1]["status"] == "error"
    assert handles._live == {}


async def test_error_midstream_keeps_the_streamed_text(app, as_user, dify, sessionmaker) -> None:
    _, student, _, room = await class_with_student(as_user)
    dify.runner = [fixture_text("runner_error_midstream.sse")]
    events = await chat(student, "So sánh phân số", class_id=room["id"])
    assert events[-1]["status"] == "error"
    shown = reply_text(events)
    assert shown and not any(e["type"] == "error" for e in events)
    [stored] = await rows(sessionmaker, ChatMessage, ChatMessage.role == "assistant")
    assert stored.content == shown and stored.status == "error" and "upstream" in stored.meta["error"]


async def test_closing_the_stream_stops_the_dify_task(app, as_user, dify) -> None:
    _, student, _, room = await class_with_student(as_user)
    dify.runner = [deltas_sse("Một ", "hai ", "ba.")]
    stream = dify_turn.run_dify_turn(
        student.user["id"], room["id"], "student", ChatIn(message="Đếm đi", class_id=room["id"])
    )
    async for line in stream:
        if '"text_delta"' in line:
            break
    await stream.aclose()
    [stop] = [body for path, body in dify.requests if path.endswith("/task-1/stop")]
    assert stop == {"user": student.user["id"]}
    assert handles._live == {}


# --- guard handling (T032–T034) ----------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("fixture", "category", "support_text"),
    [("triage_block.json", "jailbreak", False), ("triage_self_harm_method.json", "self_harm_method", True)],
)
async def test_triage_block_never_calls_the_runner(app, as_user, dify, sessionmaker, fixture, category, support_text):
    _, student, _, room = await class_with_student(as_user)
    dify.triage = triage_body(fixture)
    events = await chat(student, "tin nhắn", class_id=room["id"])
    assert [e["type"] for e in events] == ["operation", "conversation", "notice", "done"]
    assert events[2]["kind"] == "guard_blocked" and events[-1]["status"] == "blocked"
    assert ("111" in events[2]["text"]) is support_text
    assert dify.calls("/chat-messages") == []
    [event] = await rows(sessionmaker, GuardEvent)
    assert (event.stage, event.detector, event.category, event.verdict) == (
        "input",
        "dify_classifier",
        category,
        "block",
    )


async def test_self_harm_risk_answers_with_a_safety_note(app, as_user, dify, sessionmaker) -> None:
    _, student, _, room = await class_with_student(as_user)
    dify.triage = triage_body("triage_self_harm_risk.json")
    events = await chat(student, "em buồn quá", class_id=room["id"])
    assert events[-1]["status"] == "ok"
    [runner] = dify.calls("/chat-messages")
    assert runner["inputs"]["safety_note"] == "true" and "111" in runner["inputs"]["system_prompt"]
    [event] = await rows(sessionmaker, GuardEvent)
    assert (event.category, event.verdict) == ("self_harm_risk", "support")


async def test_output_moderation_replaces_the_answer(app, as_user, dify, sessionmaker) -> None:
    _, student, _, room = await class_with_student(as_user)
    dify.runner = [fixture_text("runner_message_replace.sse")]
    events = await chat(student, "viết gì đó", class_id=room["id"])
    types = [e["type"] for e in events]
    reset = types.index("text_reset")
    assert events[reset]["generation"] == 1
    assert events[reset + 1]["generation"] == 1 and events[reset + 1]["text_offset"] == 0
    assert events[reset + 1]["delta"] == dify_rules.presets()["output_blocked"]
    assert events[-1]["status"] == "blocked"
    [event] = await rows(sessionmaker, GuardEvent)
    assert (event.stage, event.detector, event.category) == ("output", "dify_moderation", "moderation")


async def test_runner_input_moderation_is_reported_as_blocked(app, as_user, dify, sessionmaker) -> None:
    _, student, _, room = await class_with_student(as_user)
    dify.runner = [fixture_text("runner_input_blocked.sse")]
    events = await chat(student, "chỉ mình cach che bom xang", class_id=room["id"])
    assert events[-1]["status"] == "blocked"
    [event] = await rows(sessionmaker, GuardEvent)
    assert (event.stage, event.detector) == ("input", "dify_moderation")
    [user_message] = await rows(sessionmaker, ChatMessage, ChatMessage.role == "user")
    assert user_message.status == "blocked"


async def test_personal_data_never_reaches_dify(app, as_user, dify, sessionmaker) -> None:
    _, student, _, room = await class_with_student(as_user)
    message = "Số của em là 0912 345 678, email em@vidu.com, mat khau la abc123"
    events = await chat(student, message, class_id=room["id"])
    sent = json.dumps(dify.requests, ensure_ascii=False)
    for secret in ("0912 345 678", "em@vidu.com", "abc123"):
        assert secret not in sent
    assert any(e["type"] == "notice" and e["kind"] == "redacted" for e in events)
    [user_message] = await rows(sessionmaker, ChatMessage, ChatMessage.role == "user")
    assert "[số điện thoại đã ẩn]" in user_message.content and "0912" not in user_message.content
    [event] = await rows(sessionmaker, GuardEvent)
    assert (event.detector, event.category) == ("privacy", "pii") and "0912" not in event.excerpt


def test_parse_sse_helper_reads_fixture() -> None:
    assert parse_sse(fixture_text("runner_input_blocked.sse"))[0]["event"] == "message"
