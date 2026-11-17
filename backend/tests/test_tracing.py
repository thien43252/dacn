import json
import uuid

import pytest
from langfuse import Langfuse
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from app import tracing
from app.llm.base import Message, ToolCall
from app.llm.fake import Scripted
from app.llm.registry import use_chat_model, use_embedder
from tests.helpers import chat, class_with_student
from tests.test_documents_tools import LESSON, upload


@pytest.fixture
def spans(monkeypatch, fake_llm, fake_embedder):
    """Turns tracing on with an in-memory exporter (nothing leaves the process) and returns the exported spans."""
    exporter = InMemorySpanExporter()
    # The SDK keeps one exporter per public key for the process, so each test needs its own key.
    client = Langfuse(
        public_key=f"pk-test-{uuid.uuid4().hex}", secret_key="sk-test", span_exporter=exporter, mask=tracing._mask
    )
    monkeypatch.setattr(tracing, "get_langfuse", lambda: client)
    use_chat_model(tracing.TracedChatModel(fake_llm))
    use_embedder(tracing.TracedEmbedder(fake_embedder))

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


async def test_tool_turn_nests_retrieval_and_renders_tool_calls(as_user, fake_llm, spans) -> None:
    teacher, student, _, room = await class_with_student(as_user)
    await upload(teacher, room["id"], "bai.txt", LESSON.encode(), "text/plain", "Bài giảng")
    ingest = [span for span in spans() if span.name == "ingest-document"]
    assert len(ingest) == 1
    # The background ingest is one trace: the document batch embedding nests under it.
    embeds = [span for span in spans() if span.name == "embed-texts"]
    assert embeds and embeds[0].parent.span_id == ingest[0].context.span_id
    assert attrs(embeds[0])["langfuse.observation.type"] == "embedding"

    fake_llm.script(
        Scripted(tool_calls=[ToolCall(id="s1", name="class_doc_search", arguments={"query": "quang hợp là gì"})]),
        "Theo tài liệu lớp, quang hợp là ...",
    )
    await chat(student, "Quang hợp là gì?", class_id=room["id"])
    turn = [span for span in spans() if span.context.trace_id != ingest[0].context.trace_id]
    by_name = {span.name: span for span in turn}
    tool, retriever = by_name["class_doc_search"], by_name["retrieve-class-docs"]
    assert tool.parent.span_id == by_name["run_agent"].context.span_id
    # The tool is the retriever's direct parent: no second, empty `tools/call` span from the MCP SDK in between.
    assert retriever.parent.span_id == tool.context.span_id
    assert [span.name for span in turn].count("class_doc_search") == 1
    assert attrs(retriever)["langfuse.observation.type"] == "retriever"
    assert "Quang hợp" in json.loads(attrs(retriever)["langfuse.observation.output"])[0]["content"]
    assert by_name["embed-texts"].parent.span_id == retriever.context.span_id
    # The second model call sees the tool call in OpenAI shape (JSON-string arguments), so the UI renders a card.
    generations = [span for span in turn if span.name == "llm.main"]
    replay = json.loads(attrs(generations[-1])["langfuse.observation.input"])
    assistant = next(message for message in replay if message.get("tool_calls"))
    assert assistant["tool_calls"][0] == {
        "id": "s1",
        "type": "function",
        "function": {"name": "class_doc_search", "arguments": '{"query": "quang hợp là gì"}'},
    }
    assert any(message.get("role") == "tool" and message.get("tool_call_id") == "s1" for message in replay)


def test_thinking_is_shown_on_assistant_messages() -> None:
    anthropic = Message(
        role="assistant",
        content="4",
        raw=[{"type": "thinking", "thinking": "2 + 2 = 4", "signature": "x"}, {"type": "text", "text": "4"}],
        raw_provider="anthropic",
    )
    openai = Message(
        role="assistant",
        raw=[{"type": "reasoning", "summary": [{"type": "summary_text", "text": "Cộng hai số."}]}],
        raw_provider="openai",
    )
    gemini = Message(
        role="assistant", raw={"parts": [{"text": "Nghĩ", "thought": True}, {"text": "4"}]}, raw_provider="gemini"
    )
    assert tracing._message(anthropic)["reasoning"] == "2 + 2 = 4"
    assert tracing._message(openai)["reasoning"] == "Cộng hai số."
    assert tracing._message(gemini)["reasoning"] == "Nghĩ"
    encrypted_only = Message(role="assistant", raw=[{"type": "reasoning", "summary": []}], raw_provider="openai")
    assert "reasoning" not in tracing._message(encrypted_only)
