"""OpenAI Chat Completions adapter (streaming, function tools) and embeddings.

Also serves OpenAI-compatible gateways (OPENAI_BASE_URL). Some gateways reject the newer `max_completion_tokens`
and `stream_options` parameters; on such a 400 the call is retried once with the classic `max_tokens`."""

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


def _detail(error: openai.APIStatusError) -> str:
    body = error.body if isinstance(error.body, dict) else {}
    message = (body.get("error") or {}).get("message") if isinstance(body.get("error"), dict) else body.get("message")
    return str(message or error.message)[:200]


class OpenAIChatModel:
    provider = "openai"

    def __init__(self, api_key: str, main_model: str, small_model: str, base_url: str = "") -> None:
        if not main_model or not small_model:
            raise LLMError("Cần đặt LLM_MAIN_MODEL và LLM_SMALL_MODEL khi dùng OpenAI.")
        if not api_key:
            raise LLMError("Chưa đặt OPENAI_API_KEY trong .env.")
        self.client = openai.AsyncOpenAI(api_key=api_key, base_url=base_url or None)
        self.models = {"main": main_model, "small": small_model}
        # Switched off after a gateway rejects the newer parameters, for the rest of the process.
        self.modern_params = True

    def model_for(self, tier: Tier) -> str:
        return self.models[tier]

    async def _create(self, params: dict[str, Any], max_tokens: int):
        if self.modern_params:
            try:
                return await self.client.chat.completions.create(
                    **params, max_completion_tokens=max_tokens, stream_options={"include_usage": True}
                )
            except openai.BadRequestError as error:
                if not any(
                    word in str(error)
                    for word in ("max_completion_tokens", "stream_options", "unsupported", "Unrecognized", "unknown")
                ):
                    raise
                self.modern_params = False
        return await self.client.chat.completions.create(**params, max_tokens=max_tokens)

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
            "stream": True,
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
            response = await self._create(params, max_tokens)
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
            raise LLMError(f"Lỗi từ máy chủ mô hình ({error.status_code}): {_detail(error)}") from error
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
        if not usage.output_tokens:
            # Gateways without usage in the stream: a rough count so the ledger is not empty.
            usage.input_tokens = sum(len(m.content) for m in messages) // 4 + len(system) // 4
            usage.output_tokens = max(1, len("".join(text_parts)) // 4)
        stop = {"stop": "end_turn", "tool_calls": "tool_use", "length": "max_tokens", "content_filter": "refusal"}
        yield Completion(
            message=Message(role="assistant", content="".join(text_parts), tool_calls=calls),
            usage=usage,
            stop_reason=stop.get(finish, finish),
        )


class OpenAIEmbedder:
    provider = "openai"

    def __init__(self, api_key: str, model: str, dimensions: int, base_url: str = "") -> None:
        self.client = openai.AsyncOpenAI(api_key=api_key or None, base_url=base_url or None)
        self.model = model or "text-embedding-3-small"
        self.dimensions = dimensions

    async def embed(self, texts: list[str]) -> list[list[float]]:
        try:
            response = await self.client.embeddings.create(input=texts, model=self.model, dimensions=self.dimensions)
        except openai.OpenAIError as error:
            raise LLMError("Không tạo được embedding với OpenAI.") from error
        return [item.embedding for item in sorted(response.data, key=lambda item: item.index)]
