"""Provider adapters against stubbed SDK clients: no network, no keys."""

from types import SimpleNamespace

import openai
from google.genai import errors, types

from app.llm.base import Completion, Message, TextDelta, ToolCall, ToolSpec
from app.llm.gemini_provider import GeminiChatModel
from app.llm.openai_provider import OpenAIChatModel

TOOL = ToolSpec("tinh_tong", "Tính tổng.", {"type": "object", "properties": {"a": {"type": "integer"}}})


class Item(SimpleNamespace):
    def model_dump(self, exclude_none: bool = False) -> dict:
        return dict(vars(self))


async def collect(model, messages, **kwargs) -> tuple[str, Completion]:
    text, final = "", None
    async for event in model.stream(messages, system="sys", **kwargs):
        if isinstance(event, TextDelta):
            text += event.text
        else:
            final = event
    assert final is not None
    return text, final


def openai_stream(output: list[Item], deltas: list[str] = (), incomplete: str | None = None):
    response = SimpleNamespace(
        output=output,
        model="gpt-test",
        usage=SimpleNamespace(input_tokens=11, output_tokens=7),
        incomplete_details=SimpleNamespace(reason=incomplete) if incomplete else None,
    )

    async def events():
        for delta in deltas:
            yield SimpleNamespace(type="response.output_text.delta", delta=delta)
        yield SimpleNamespace(type="response.incomplete" if incomplete else "response.completed", response=response)

    return events()


async def test_openai_tool_call_and_reasoning_replay() -> None:
    model = OpenAIChatModel("sk-test", "gpt-test", "gpt-small", effort="high")
    sent: list[dict] = []
    reasoning = Item(type="reasoning", id="rs_1", encrypted_content="enc", summary=[])
    call = Item(type="function_call", call_id="call_1", name="tinh_tong", arguments='{"a": 2}')

    async def create(**params):
        sent.append(params)
        return openai_stream([reasoning, call])

    model.client = SimpleNamespace(responses=SimpleNamespace(create=create))
    _, final = await collect(model, [Message(role="user", content="2+?")], tools=[TOOL])
    assert final.stop_reason == "tool_use"
    assert final.message.tool_calls == [ToolCall(id="call_1", name="tinh_tong", arguments={"a": 2})]
    assert sent[0]["reasoning"] == {"effort": "high"} and sent[0]["store"] is False
    assert sent[0]["tools"][0]["strict"] is False

    # Next round: the model's own items (reasoning included) are replayed, then the tool result.
    history = [
        Message(role="user", content="2+?"),
        final.message,
        Message(role="tool", content="4", tool_call_id="call_1"),
    ]
    await collect(model, history, tools=[TOOL], tier="small")
    assert sent[1]["input"][1:] == [
        reasoning.model_dump(),
        call.model_dump(),
        {"type": "function_call_output", "call_id": "call_1", "output": "4"},
    ]
    assert sent[1]["reasoning"] == {"effort": "low"}


async def test_openai_falls_back_without_reasoning_for_models_that_reject_it() -> None:
    model = OpenAIChatModel("sk-test", "gpt-4.1-mini", "gpt-4.1-mini")
    calls: list[dict] = []

    async def create(**params):
        calls.append(params)
        if "reasoning" in params:
            request = SimpleNamespace(method="POST", url="https://api.openai.com/v1/responses")
            raise openai.BadRequestError(
                "Unsupported parameter: 'reasoning.effort'",
                response=SimpleNamespace(status_code=400, headers={}, request=request),
                body=None,
            )
        message = Item(type="message", role="assistant", content=[{"type": "output_text", "text": "Chào"}])
        return openai_stream([message], deltas=["Chào"])

    model.client = SimpleNamespace(responses=SimpleNamespace(create=create))
    text, final = await collect(model, [Message(role="user", content="hi")])
    assert text == "Chào" and final.stop_reason == "end_turn" and final.usage.input_tokens == 11
    await collect(model, [Message(role="user", content="hi")])
    # Rejected once; later calls skip the reasoning parameters straight away.
    assert ["reasoning" in params for params in calls] == [True, False, False]


async def test_gemini_thinking_level_fallback_and_thought_tokens() -> None:
    model = GeminiChatModel("key", "gemini-2.5-flash", "gemini-2.5-flash", effort="high")
    configs: list[types.GenerateContentConfig] = []

    async def generate_content_stream(*, model: str, contents, config):
        configs.append(config)
        if config.thinking_config is not None:
            raise errors.ClientError(400, {"error": {"code": 400, "message": "Thinking level is not supported."}})

        async def chunks():
            yield types.GenerateContentResponse(
                candidates=[
                    types.Candidate(
                        content=types.Content(role="model", parts=[types.Part(text="Xin chào")]),
                        finish_reason=types.FinishReason.STOP,
                    )
                ],
                usage_metadata=types.GenerateContentResponseUsageMetadata(
                    prompt_token_count=5, candidates_token_count=3, thoughts_token_count=20
                ),
            )

        return chunks()

    model.client = SimpleNamespace(
        aio=SimpleNamespace(models=SimpleNamespace(generate_content_stream=generate_content_stream))
    )
    text, final = await collect(model, [Message(role="user", content="hi")])
    assert text == "Xin chào" and final.stop_reason == "end_turn"
    assert final.usage.output_tokens == 23
    assert configs[0].thinking_config.thinking_level == types.ThinkingLevel.HIGH
    assert configs[1].thinking_config is None
