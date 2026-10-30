import json

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
    client = Langfuse(public_key="pk-test", secret_key="sk-test", span_exporter=exporter, mask=tracing._mask)
    monkeypatch.setattr(tracing, "get_langfuse", lambda: client)
    use_chat_model(tracing.TracedChatModel(fake_llm))

    def finished():
        client.flush()
        return exporter.get_finished_spans()

    yield finished
    client.shutdown()


def attrs(span) -> dict:
    return dict(span.attributes or {})


async def test_chat_turn_is_one_trace_with_nodes_and_generations(as_user, fake_llm, spans) -> None:
    _, student, _, room = await class_with_student(as_user)
    fake_llm.script("Chào em!")
    await chat(student, "Xin chào, số của em là 0912345678", class_id=room["id"])

    exported = spans()
    by_name = {span.name: span for span in exported}
    assert {"chat", "screen", "classify", "select_agent", "gate", "run_agent", "review", "llm.main"} <= set(by_name)
    assert len({span.context.trace_id for span in exported}) == 1
    root = by_name["chat"]
    # Nodes hang off the root; the agent's model call nests under run_agent.
    assert by_name["screen"].parent.span_id == root.context.span_id
    assert by_name["llm.main"].parent.span_id == by_name["run_agent"].context.span_id
    assert attrs(by_name["llm.main"])["langfuse.observation.type"] == "generation"
    # User and session reach every observation, and personal data never leaves unredacted.
    assert all(attrs(span).get("user.id") for span in exported)
    payload = json.dumps([attrs(span) for span in exported], ensure_ascii=False)
    assert "0912345678" not in payload
    assert "Chào em!" in attrs(root)["langfuse.observation.output"]
