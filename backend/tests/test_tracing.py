import json
import uuid

import pytest
from langfuse import Langfuse
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from app import tracing
from app.llm.registry import use_chat_model
from tests.helpers import chat, class_with_student


@pytest.fixture
def spans(monkeypatch, fake_llm):
    """Turns tracing on with an in-memory exporter (nothing leaves the process) and returns the exported spans."""
    exporter = InMemorySpanExporter()
    # A key per test: Langfuse keeps one resource manager per public key, and the previous test shut its own down.
    client = Langfuse(
        public_key=f"pk-test-{uuid.uuid4()}", secret_key="sk-test", span_exporter=exporter, mask=tracing._mask
    )
    monkeypatch.setattr(tracing, "get_langfuse", lambda: client)
    use_chat_model(tracing.TracedChatModel(fake_llm))

    def finished():
        client.flush()
        return exporter.get_finished_spans()

    yield finished
    client.shutdown()


def attrs(span) -> dict:
    return dict(span.attributes or {})


async def test_chat_turn_traces_triage_and_run_agent(as_user, dify, spans) -> None:
    _, student, _, room = await class_with_student(as_user)
    await chat(student, "So sánh phân số, số của em là 0912345678", class_id=room["id"])

    exported = spans()
    by_name = {span.name: span for span in exported}
    assert {"chat", "triage", "run_agent"} <= set(by_name)
    assert len({span.context.trace_id for span in exported}) == 1
    root = by_name["chat"]
    assert by_name["triage"].parent.span_id == root.context.span_id
    assert by_name["run_agent"].parent.span_id == root.context.span_id
    root_attrs = json.dumps(attrs(root), ensure_ascii=False)
    # The ids to find the same turn in Dify's own logs.
    assert "dify_message_id" in root_attrs and "dify_conversation_id" in root_attrs
    assert "0912345678" not in json.dumps([attrs(span) for span in exported], ensure_ascii=False)


async def test_backend_model_calls_are_generations_without_personal_data(fake_llm, spans) -> None:
    """Reports, judges and tools call the backend's own model; each call is a generation, redacted like turns."""
    from app.llm.base import Message, complete
    from app.llm.registry import get_chat_model

    fake_llm.script("Đã nhận.")
    message = Message(role="user", content="Số của em là 0912345678")
    await complete(get_chat_model(), [message], system="Trả lời ngắn.", tier="main")
    exported = spans()
    [generation] = [span for span in exported if span.name == "llm.main"]
    assert attrs(generation)["langfuse.observation.type"] == "generation"
    assert "0912345678" not in json.dumps([attrs(span) for span in exported], ensure_ascii=False)
