"""A fake Dify for offline tests: recorded responses from tests/fixtures/dify/ served through httpx.MockTransport.

The `dify` fixture (registered in conftest.py) switches the engine to Dify and routes every Dify call of a turn here.
"""

import json
from pathlib import Path

import httpx
import pytest
from sqlalchemy import select

from app.config import get_settings
from app.runtime import dify_turn
from app.runtime.dify_client import DifyClient
from app.tools import registry

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
        # eduagent-review outputs, or "down" to fail; recorded under the path "/workflows/run#review".
        self.review: dict | str = {"verdict": "allow", "category": "", "reason": ""}
        # One entry per runner call: SSE text, or (status, json body) for a refused request.
        self.runner: list[str | tuple[int, dict]] = [fixture_text("runner_plain.sse")]
        # Follow-up questions for GET /messages/{id}/suggested, or an HTTP status to fail with.
        self.suggested: list[str] | int = json.loads(fixture_text("suggested.json"))["data"]
        self.tool_calls: list[tuple[str, dict]] = []  # made through the MCP handler before the runner answers
        self.requests: list[tuple[str, dict]] = []
        self.keys: list[tuple[str, str]] = []  # (path, API key) of every request

    def calls(self, kind: str) -> list[dict]:
        """Request bodies whose path contains `kind`; review calls only when asked for ("#review")."""
        return [body for path, body in self.requests if kind in path and ("#review" in kind or "#review" not in path)]

    async def handler(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content) if request.content else dict(request.url.params)
        key = request.headers.get("authorization", "").removeprefix("Bearer ")
        path = request.url.path
        if path.endswith("/workflows/run") and key == "app-review":
            self.requests.append((path + "#review", body))
            self.keys.append((path + "#review", key))
            if self.review == "down":
                raise httpx.ConnectError("Dify is down", request=request)
            outputs = self.review
            data = {"status": "succeeded", "outputs": outputs, "total_tokens": 300}
            return httpx.Response(200, json={"task_id": "t-review", "data": data})
        self.requests.append((path, body))
        self.keys.append((path, key))
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
            if isinstance(self.suggested, int):
                return httpx.Response(self.suggested, json={"code": "error", "message": "boom"})
            return httpx.Response(200, json={"result": "success", "data": self.suggested})
        return httpx.Response(404, json={"code": "not_found", "message": "unknown"})


@pytest.fixture
def dify(monkeypatch) -> FakeDify:
    fake = FakeDify()
    # Fake keys: the repo-root .env may hold real ones.
    for name, value in {
        "RUNTIME_ENGINE": "dify",
        "DIFY_BASE_URL": BASE,
        "DIFY_TRIAGE_KEY": "app-triage",
        "DIFY_RUNNER_KEY": "app-runner",
        "DIFY_RUNNER_RAW_KEY": "app-runner-raw",
        "DIFY_DATASET_KEY": "dataset-key",
        "DIFY_REVIEW_KEY": "app-review",
    }.items():
        monkeypatch.setenv(name, value)
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
