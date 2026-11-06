"""MCP over streamable HTTP at /mcp, the way Dify calls the platform's tools (contracts/mcp-tools.md)."""

import asyncio
import json
from contextlib import asynccontextmanager

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.audit.models import GuardEvent
from app.chat.models import Conversation, ToolCallLog
from app.config import get_settings
from app.tools import context as handles
from app.tools import registry
from tests.helpers import class_with_student

TOKEN = "test-mcp-token"
INVALID = "Ngữ cảnh gọi công cụ không hợp lệ hoặc đã hết hạn."


@pytest.fixture
def mcp_token(monkeypatch):
    monkeypatch.setenv("MCP_TOKEN", TOKEN)
    get_settings.cache_clear()
    yield
    monkeypatch.undo()
    get_settings.cache_clear()


@asynccontextmanager
async def mcp_client(app):
    """An HTTP client for /mcp with the session manager running (httpx's ASGITransport skips the lifespan).

    A context manager rather than a fixture: the manager's task group must be entered and left in one task."""
    async with app.state.mcp_manager.run():
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            yield client


async def call(client, name: str, arguments: dict, token: str | None = TOKEN):
    headers = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}
    if token is not None:
        headers["Authorization"] = f"Bearer {token}"
    body = {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": name, "arguments": arguments}}
    return await client.post("/mcp", headers=headers, content=json.dumps(body))


def result_of(response) -> tuple[str, bool]:
    assert response.status_code == 200, response.text
    result = response.json()["result"]
    text = "\n".join(item.get("text", "") for item in result.get("content", []))
    return text, bool(result.get("isError"))


async def turn_context(as_user, sessionmaker, *, role="student", tools=("math_check",), in_class=True):
    """A Dify-style tool context for a real conversation, with an event queue like the Dify engine's."""
    teacher, student, parent, room = await class_with_student(as_user)
    user = {"student": student, "teacher": teacher, "parent": parent}[role].user
    async with sessionmaker() as db:
        conversation = Conversation(user_id=user["id"], class_id=room["id"] if in_class else None, title="t")
        db.add(conversation)
        await db.commit()
        conversation_id = conversation.id
    context = registry.ToolContext(
        user_id=user["id"],
        role=role,
        class_id=room["id"] if in_class else None,
        grade=8 if in_class else None,
        conversation_id=conversation_id,
        agent_slug="gia-su-toan",
        allowed_tools=frozenset(tools),
        log_calls=True,
        message_id="m-1",
        excerpt="Em hỏi bài, số của em là 0912 345 678",
        events=asyncio.Queue(),
    )
    return context, handles.register(context)


def drained(context: registry.ToolContext) -> list[str]:
    statuses = []
    while not context.events.empty():
        statuses.append(context.events.get_nowait()["status"])
    return statuses


async def rows(sessionmaker, model):
    async with sessionmaker() as db:
        return list(await db.scalars(select(model)))


@pytest.mark.parametrize("token", [None, "wrong-token"])
async def test_missing_or_wrong_bearer_is_rejected_before_any_tool_runs(
    app, mcp_token, as_user, sessionmaker, token
) -> None:
    async with mcp_client(app) as mcp:
        context, handle = await turn_context(as_user, sessionmaker)
        response = await call(mcp, "math_check", {"ctx": handle, "operation": "solve", "expression": "x+1=2"}, token)
        assert response.status_code == 401
        assert drained(context) == []
        assert await rows(sessionmaker, ToolCallLog) == []


async def test_endpoint_refuses_everything_without_a_configured_token(app, monkeypatch) -> None:
    monkeypatch.setenv("MCP_TOKEN", "")
    get_settings.cache_clear()
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await call(client, "math_check", {}, token="")
    finally:
        monkeypatch.undo()
        get_settings.cache_clear()
    assert response.status_code == 401


async def test_unknown_handle_is_a_tool_error(app, mcp_token) -> None:
    async with mcp_client(app) as mcp:
        text, is_error = result_of(
            await call(mcp, "math_check", {"ctx": "nope", "operation": "solve", "expression": "x=1"})
        )
        assert is_error and INVALID in text


async def test_expired_handle_is_refused(app, mcp_token, as_user, sessionmaker, monkeypatch) -> None:
    async with mcp_client(app) as mcp:
        context, handle = await turn_context(as_user, sessionmaker)
        later = handles.now() + handles.TTL_S + 1
        monkeypatch.setattr(handles, "now", lambda: later)
        text, is_error = result_of(
            await call(mcp, "math_check", {"ctx": handle, "operation": "solve", "expression": "x=1"})
        )
        assert is_error and INVALID in text
        assert handles.lookup(handle) is None


async def test_granted_tool_runs_and_is_logged_without_ctx(app, mcp_token, as_user, sessionmaker) -> None:
    async with mcp_client(app) as mcp:
        context, handle = await turn_context(as_user, sessionmaker)
        arguments = {"ctx": handle, "operation": "solve", "expression": "2*x+3=7"}
        text, is_error = result_of(await call(mcp, "math_check", arguments))
        assert not is_error and "2" in text
        assert drained(context) == ["start", "done"]
        [logged] = await rows(sessionmaker, ToolCallLog)
        assert logged.tool == "math_check" and logged.message_id == "m-1" and not logged.is_error
        assert "ctx" not in logged.arguments and logged.arguments["expression"] == "2*x+3=7"
        assert await rows(sessionmaker, GuardEvent) == []
        handles.release(handle)


@pytest.mark.parametrize(
    ("role", "tools", "in_class", "tool", "arguments", "reason"),
    [
        ("student", ("math_check",), True, "rubric_grader", {"essay": "Bài văn"}, "không được cấp"),
        ("parent", ("rubric_grader",), True, "rubric_grader", {"essay": "Bài văn"}, "Vai trò"),
        ("student", ("class_doc_search",), False, "class_doc_search", {"query": "phân số"}, "trong một lớp"),
    ],
)
async def test_tool_guard_denials_are_logged_as_guard_events(
    app, mcp_token, as_user, sessionmaker, role, tools, in_class, tool, arguments, reason
) -> None:
    async with mcp_client(app) as mcp:
        context, handle = await turn_context(as_user, sessionmaker, role=role, tools=tools, in_class=in_class)
        text, is_error = result_of(await call(mcp, tool, {"ctx": handle, **arguments}))
        assert is_error and reason in text
        assert drained(context) == ["start", "denied"]
        [logged] = await rows(sessionmaker, ToolCallLog)
        assert logged.denied_reason and reason in logged.denied_reason
        [event] = await rows(sessionmaker, GuardEvent)
        assert (event.stage, event.category, event.verdict) == ("tool", "tool_denied", "block")
        # The excerpt goes through redact(): the phone number in the user's message is not stored.
        assert "0912" not in event.excerpt
        handles.release(handle)


async def test_invalid_arguments_are_an_error_without_guard_event(app, mcp_token, as_user, sessionmaker) -> None:
    async with mcp_client(app) as mcp:
        context, handle = await turn_context(as_user, sessionmaker)
        text, is_error = result_of(
            await call(mcp, "math_check", {"ctx": handle, "operation": "solve", "expression": ""})
        )
        assert is_error and "Tham số không hợp lệ" in text
        assert drained(context) == ["start", "error"]
        [logged] = await rows(sessionmaker, ToolCallLog)
        assert logged.is_error and logged.denied_reason is None
        assert await rows(sessionmaker, GuardEvent) == []
        handles.release(handle)
