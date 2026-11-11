"""A fake Dify for offline tests: recorded responses from tests/fixtures/dify/ served through httpx.MockTransport.

The `dify` fixture (registered in conftest.py) is autouse: every test talks to this fake instead of the Dify in the
repo-root .env, except tests marked `dify`, which need a real one. `knowledge` is its fake Knowledge API.
"""

import json
from pathlib import Path

import httpx
import pytest
from sqlalchemy import select

from app.config import get_settings
from app.knowledge import dify_datasets
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


def planner_body(name: str = "planner_multi.json", plan: dict | None = None, **changes) -> dict:
    """A recorded-shape planner response; `plan` replaces the plan, `changes` update its top-level keys."""
    body = json.loads(fixture_text(name))
    if plan is not None or changes:
        current = json.loads(body["data"]["outputs"]["plan"]) if plan is None else plan
        body["data"]["outputs"] = {"ok": "true", "plan": json.dumps({**current, **changes}, ensure_ascii=False)}
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


class FakeKnowledge:
    """Datasets, documents and indexing state in memory; every request is recorded."""

    def __init__(self) -> None:
        self.datasets: dict[str, list[str]] = {}  # dataset id -> Dify document ids
        self.status = "completed"  # what indexing-status reports
        self.fail_delete = False
        self.requests: list[tuple[str, str]] = []
        self.retrieved: list[str] = []  # dataset ids searched
        self.uploads = 0

    async def handler(self, request: httpx.Request) -> httpx.Response:
        path, method = request.url.path.removeprefix("/v1"), request.method
        self.requests.append((method, path))
        parts = path.strip("/").split("/")
        if method == "POST" and path == "/datasets":
            name = json.loads(request.content)["name"]
            if len(name) > 40:  # Dify 1.19 refuses longer names with 422
                return httpx.Response(
                    422, json={"code": "invalid_param", "message": "String should have at most 40 characters"}
                )
            assert name.startswith("class-")
            dataset_id = f"ds-{len(self.datasets) + 1}"
            self.datasets[dataset_id] = []
            body = json.loads(fixture_text("dataset_create.json"))
            return httpx.Response(200, json={**body, "id": dataset_id, "name": json.loads(request.content)["name"]})
        dataset_id = parts[1]
        if dataset_id not in self.datasets:
            return httpx.Response(
                404, json={"code": "dataset_not_found", "message": "Dataset not found.", "status": 404}
            )
        if path.endswith("/document/create-by-file"):
            self.uploads += 1
            document_id = f"doc-{dataset_id}-{self.uploads}"
            self.datasets[dataset_id].append(document_id)
            body = json.loads(fixture_text("document_create.json"))
            body["document"]["id"] = document_id
            return httpx.Response(200, json={**body, "batch": f"batch-{document_id}"})
        if path.endswith("/indexing-status"):
            name = "indexing_status_completed.json" if self.status == "completed" else "indexing_status_error.json"
            body = json.loads(fixture_text(name))
            if self.status not in ("completed", "error"):
                body["data"][0]["indexing_status"] = self.status
            return httpx.Response(200, json=body)
        if path.endswith("/retrieve"):
            self.retrieved.append(dataset_id)
            body = json.loads(fixture_text("dataset_retrieve.json"))
            documents = self.datasets[dataset_id]
            for record in body["records"]:
                record["segment"]["document_id"] = documents[0] if documents else "none"
            body["records"] = body["records"] if documents else []
            return httpx.Response(200, json=body)
        if method == "GET" and path.endswith("/segments"):
            if parts[3] not in self.datasets[dataset_id]:
                return httpx.Response(404, text=fixture_text("document_delete_missing.json"))
            body = json.loads(fixture_text("document_segments.json"))
            for segment in body["data"]:
                segment["document_id"] = parts[3]
            return httpx.Response(200, json=body)
        if method == "DELETE" and len(parts) == 4:
            if self.fail_delete:
                return httpx.Response(500, json={"code": "internal_server_error", "message": "boom", "status": 500})
            if parts[3] not in self.datasets[dataset_id]:
                return httpx.Response(404, text=fixture_text("document_delete_missing.json"))
            self.datasets[dataset_id].remove(parts[3])
            return httpx.Response(204)
        return httpx.Response(404, json={"code": "not_found", "message": "unknown", "status": 404})


class FakeDify:
    """Answers triage, runner, stop and suggested calls like Dify, and records every request."""

    def __init__(self) -> None:
        self.triage: dict | int = triage_body()
        # eduagent-review outputs, or "down" to fail; recorded under the path "/workflows/run#review".
        self.review: dict | str = {"verdict": "allow", "category": "", "reason": ""}
        # eduagent-planner response body (feature 002), an HTTP status, or "down"; recorded as "#planner".
        self.planner: dict | int | str = planner_body("planner_multi.json")
        # One entry per runner call: SSE text, or (status, json body) for a refused request.
        self.runner: list[str | tuple[int, dict]] = [fixture_text("runner_plain.sse")]
        # Follow-up questions for GET /messages/{id}/suggested, or an HTTP status to fail with.
        self.suggested: list[str] | int = json.loads(fixture_text("suggested.json"))["data"]
        self.tool_calls: list[tuple[str, dict]] = []  # made through the MCP handler before the runner answers
        self.requests: list[tuple[str, dict]] = []
        self.keys: list[tuple[str, str]] = []  # (path, API key) of every request
        self.knowledge = FakeKnowledge()

    def calls(self, kind: str) -> list[dict]:
        """Request bodies whose path contains `kind`; review and planner calls only when asked for ("#review",
        "#planner")."""
        return [body for path, body in self.requests if kind in path and ("#" in kind or "#" not in path)]

    async def handler(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content) if request.content else dict(request.url.params)
        key = request.headers.get("authorization", "").removeprefix("Bearer ")
        path = request.url.path
        if path.endswith("/workflows/run") and key == "app-planner":
            self.requests.append((path + "#planner", body))
            self.keys.append((path + "#planner", key))
            if self.planner == "down":
                raise httpx.ConnectError("Dify is down", request=request)
            if isinstance(self.planner, int):
                return httpx.Response(self.planner, json={"code": "internal_server_error", "message": "boom"})
            return httpx.Response(200, json=self.planner)
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


@pytest.fixture(autouse=True)
def dify(request, monkeypatch) -> FakeDify | None:
    if request.node.get_closest_marker("dify"):
        yield None  # a real Dify, from the environment
        return
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
        # On, as in a configured install: turns stay on the fast path unless triage says "full".
        "DIFY_PLANNER_KEY": "app-planner",
    }.items():
        monkeypatch.setenv(name, value)
    get_settings.cache_clear()
    monkeypatch.setattr(
        dify_turn, "make_client", lambda: DifyClient(httpx.AsyncClient(transport=httpx.MockTransport(fake.handler)))
    )
    monkeypatch.setattr(
        dify_datasets,
        "make_datasets",
        lambda: dify_datasets.DifyDatasets(httpx.AsyncClient(transport=httpx.MockTransport(fake.knowledge.handler))),
    )
    yield fake
    monkeypatch.undo()
    get_settings.cache_clear()


@pytest.fixture
def knowledge(dify) -> FakeKnowledge:
    return dify.knowledge


def utf16(text: str) -> int:
    return len(text.encode("utf-16-le")) // 2


async def rows(sessionmaker, model, *where):
    async with sessionmaker() as db:
        return list(await db.scalars(select(model).where(*where)))
