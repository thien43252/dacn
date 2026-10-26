"""OpenAI Chat Completions adapter (streaming, function tools) and embeddings."""

import json
from collections.abc import AsyncIterator
from typing import Any

import openai

from app.llm.base import Completion, LLMError, Message, StreamEvent, TextDelta, Tier, ToolCall, ToolSpec, Usage


def _to_openai(system: str, messages: list[Message]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = [{"role": "system", "content": system}]
    for message in messages:
        if message.role == "tool":
            out.append({"role": "tool", "tool_call_id": message.tool_call_id, "content": message.content})
        elif message.role == "assistant":
            entry: dict[str, Any] = {"role": "assistant", "content": message.content or None}
            if message.tool_calls:
                entry["tool_calls"] = [
                    {
                        "id": call.id,
                        "type": "function",
                        "function": {"name": call.name, "arguments": json.dumps(call.arguments, ensure_ascii=False)},
                    }
                    for call in message.tool_calls
                ]
            out.append(entry)
        else:
            out.append({"role": "user", "content": message.content})
    return out


class OpenAIChatModel:
    provider = "openai"

    def __init__(self, api_key: str, main_model: str, small_model: str) -> None:
        if not main_model or not small_model:
            raise LLMError("Cần đặt LLM_MAIN_MODEL và LLM_SMALL_MODEL khi dùng OpenAI.")
        self.client = openai.AsyncOpenAI(api_key=api_key or None)
        self.models = {"main": main_model, "small": small_model}

    def model_for(self, tier: Tier) -> str:
        return self.models[tier]

    async def stream(
        self,
        messages: list[Message],
        *,
        system: str,
        tools: list[ToolSpec] | None = None,
        tier: Tier = "main",
        max_tokens: int = 4096,
    ) -> AsyncIterator[StreamEvent]:
        model = self.model_for(tier)
        params: dict[str, Any] = {
            "model": model,
            "messages": _to_openai(system, messages),
            "max_completion_tokens": max_tokens,
            "stream": True,
            "stream_options": {"include_usage": True},
        }
        if tools:
            params["tools"] = [
                {
                    "type": "function",
                    "function": {"name": t.name, "description": t.description, "parameters": t.parameters},
                }
                for t in tools
            ]
        text_parts: list[str] = []
        pending: dict[int, dict[str, str]] = {}
        finish = "stop"
        usage = Usage(provider=self.provider, model=model)
        try:
            response = await self.client.chat.completions.create(**params)
            async for chunk in response:
                if chunk.usage:
                    usage.input_tokens = chunk.usage.prompt_tokens or 0
                    usage.output_tokens = chunk.usage.completion_tokens or 0
                for choice in chunk.choices:
                    delta = choice.delta
                    if delta and delta.content:
                        text_parts.append(delta.content)
                        yield TextDelta(delta.content)
                    for call in (delta.tool_calls or []) if delta else []:
                        slot = pending.setdefault(call.index, {"id": "", "name": "", "arguments": ""})
                        slot["id"] = call.id or slot["id"]
                        if call.function:
                            slot["name"] += call.function.name or ""
                            slot["arguments"] += call.function.arguments or ""
                    if choice.finish_reason:
                        finish = choice.finish_reason
        except openai.AuthenticationError as error:
            raise LLMError("Khoá API OpenAI không hợp lệ.") from error
        except openai.RateLimitError as error:
            raise LLMError("Đã vượt giới hạn gọi mô hình. Thử lại sau ít phút.") from error
        except openai.APIStatusError as error:
            raise LLMError(f"Lỗi từ OpenAI ({error.status_code}).") from error
        except openai.APIConnectionError as error:
            raise LLMError("Không kết nối được tới OpenAI.") from error

        calls = []
        for index in sorted(pending):
            slot = pending[index]
            try:
                arguments = json.loads(slot["arguments"] or "{}")
            except json.JSONDecodeError:
                arguments = None
            calls.append(
                ToolCall(
                    id=slot["id"] or f"call_{index}",
                    name=slot["name"],
                    arguments=arguments if isinstance(arguments, dict) else {},
                    invalid=not isinstance(arguments, dict) or finish == "length",
                )
            )
        stop = {"stop": "end_turn", "tool_calls": "tool_use", "length": "max_tokens", "content_filter": "refusal"}
        yield Completion(
            message=Message(role="assistant", content="".join(text_parts), tool_calls=calls),
            usage=usage,
            stop_reason=stop.get(finish, finish),
        )


class OpenAIEmbedder:
    provider = "openai"

    def __init__(self, api_key: str, model: str, dimensions: int) -> None:
        self.client = openai.AsyncOpenAI(api_key=api_key or None)
        self.model = model or "text-embedding-3-small"
        self.dimensions = dimensions

    async def embed(self, texts: list[str]) -> list[list[float]]:
        try:
            response = await self.client.embeddings.create(input=texts, model=self.model, dimensions=self.dimensions)
        except openai.OpenAIError as error:
            raise LLMError("Không tạo được embedding với OpenAI.") from error
        return [item.embedding for item in sorted(response.data, key=lambda item: item.index)]
