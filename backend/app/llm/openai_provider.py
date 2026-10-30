"""OpenAI via the Responses API (streaming, function tools with reasoning) and embeddings.

Requests are stateless (`store=False`): nothing is kept on OpenAI's side, so the reasoning items of a tool loop come
back encrypted and are replayed with the next request (Message.raw). Models without reasoning (e.g. gpt-4.1) reject
the reasoning parameters; on that 400 the call is retried once without them.
"""

import json
from collections.abc import AsyncIterator
from typing import Any

import openai

from app.llm.base import Completion, LLMError, Message, StreamEvent, TextDelta, Tier, ToolCall, ToolSpec, Usage


def _to_input(messages: list[Message]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for message in messages:
        if message.role == "tool":
            items.append({"type": "function_call_output", "call_id": message.tool_call_id, "output": message.content})
        elif message.role == "assistant":
            if message.raw_provider == "openai" and message.raw:
                # Output items of this model's own turn: reasoning, text and function calls, unchanged.
                items.extend(message.raw)
                continue
            if message.content:
                items.append({"role": "assistant", "content": message.content})
            items += [
                {
                    "type": "function_call",
                    "call_id": call.id,
                    "name": call.name,
                    "arguments": json.dumps(call.arguments, ensure_ascii=False),
                }
                for call in message.tool_calls
            ]
        else:
            items.append({"role": "user", "content": message.content})
    return items


def _tool_param(tool: ToolSpec) -> dict[str, Any]:
    # Not strict: strict mode needs every property required and additionalProperties false, which the tool schemas
    # do not promise. The runtime validates arguments before running any tool.
    return {
        "type": "function",
        "name": tool.name,
        "description": tool.description,
        "parameters": tool.parameters,
        "strict": False,
    }


def _detail(error: openai.APIStatusError) -> str:
    body = error.body if isinstance(error.body, dict) else {}
    message = (body.get("error") or {}).get("message") if isinstance(body.get("error"), dict) else body.get("message")
    return str(message or error.message)[:200]


class OpenAIChatModel:
    provider = "openai"

    def __init__(
        self, api_key: str, main_model: str, small_model: str, base_url: str = "", effort: str = "medium"
    ) -> None:
        if not main_model or not small_model:
            raise LLMError("Cần đặt LLM_MAIN_MODEL và LLM_SMALL_MODEL khi dùng OpenAI.")
        if not api_key:
            raise LLMError("Chưa đặt OPENAI_API_KEY trong .env.")
        self.client = openai.AsyncOpenAI(api_key=api_key, base_url=base_url or None)
        self.models = {"main": main_model, "small": small_model}
        self.effort = effort
        # Switched off per model after it rejects the reasoning parameters, for the rest of the process.
        self.no_reasoning: set[str] = set()

    def model_for(self, tier: Tier) -> str:
        return self.models[tier]

    async def _create(self, params: dict[str, Any], effort: str):
        model = params["model"]
        if model not in self.no_reasoning:
            try:
                return await self.client.responses.create(
                    **params, reasoning={"effort": effort}, include=["reasoning.encrypted_content"]
                )
            except openai.BadRequestError as error:
                if "reasoning" not in str(error):
                    raise
                self.no_reasoning.add(model)
        return await self.client.responses.create(**params)

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
            "instructions": system,
            "input": _to_input(messages),
            "max_output_tokens": max_tokens,
            "store": False,
            "stream": True,
        }
        if tools:
            params["tools"] = [_tool_param(tool) for tool in tools]
        text_parts: list[str] = []
        refused = False
        final = None
        try:
            # Guards and the router want speed; agents get the configured depth.
            response = await self._create(params, "low" if tier == "small" else self.effort)
            async for event in response:
                if event.type == "response.output_text.delta":
                    text_parts.append(event.delta)
                    yield TextDelta(event.delta)
                elif event.type == "response.refusal.delta":
                    refused = True
                elif event.type in ("response.completed", "response.incomplete"):
                    final = event.response
                elif event.type == "response.failed":
                    error = event.response.error
                    raise LLMError(f"Lỗi từ máy chủ mô hình: {error.message if error else 'không rõ'}"[:300])
                elif event.type == "error":
                    raise LLMError(f"Lỗi từ máy chủ mô hình: {event.message}"[:300])
        except openai.AuthenticationError as error:
            raise LLMError("Khoá API OpenAI không hợp lệ.") from error
        except openai.RateLimitError as error:
            raise LLMError("Đã vượt giới hạn gọi mô hình hoặc hết hạn mức. Thử lại sau ít phút.") from error
        except openai.APIStatusError as error:
            raise LLMError(f"Lỗi từ máy chủ mô hình ({error.status_code}): {_detail(error)}") from error
        except openai.APIConnectionError as error:
            raise LLMError("Không kết nối được tới OpenAI.") from error
        if final is None:
            raise LLMError("Mô hình không trả về kết quả.")

        incomplete = final.incomplete_details.reason if final.incomplete_details else None
        output = [item.model_dump(exclude_none=True) for item in final.output]
        calls = []
        for item in output:
            if item.get("type") != "function_call":
                continue
            try:
                arguments = json.loads(item.get("arguments") or "{}")
            except json.JSONDecodeError:
                arguments = None
            calls.append(
                ToolCall(
                    id=item["call_id"],
                    name=item["name"],
                    arguments=arguments if isinstance(arguments, dict) else {},
                    invalid=not isinstance(arguments, dict) or incomplete == "max_output_tokens",
                )
            )
        if refused or incomplete == "content_filter":
            stop = "refusal"
        elif calls:
            stop = "tool_use"
        elif incomplete == "max_output_tokens":
            stop = "max_tokens"
        else:
            stop = incomplete or "end_turn"
        usage = final.usage
        yield Completion(
            message=Message(
                role="assistant", content="".join(text_parts), tool_calls=calls, raw=output, raw_provider=self.provider
            ),
            usage=Usage(
                provider=self.provider,
                model=final.model or model,
                input_tokens=usage.input_tokens if usage else 0,
                output_tokens=usage.output_tokens if usage else 0,
            ),
            stop_reason=stop,
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
