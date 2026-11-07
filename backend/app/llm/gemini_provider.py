"""Google Gemini adapter via the google-genai SDK (streaming, function declarations)."""

import uuid
from collections.abc import AsyncIterator
from typing import Any

from google import genai
from google.genai import errors, types

from app.llm.base import Completion, LLMError, Message, StreamEvent, TextDelta, Tier, ToolCall, ToolSpec, Usage


def _to_contents(messages: list[Message]) -> list[types.Content]:
    names: dict[str, str] = {}
    contents: list[types.Content] = []
    for message in messages:
        if message.role == "assistant":
            for call in message.tool_calls:
                names[call.id] = call.name
            if message.raw_provider == "gemini" and message.raw:
                # Replays thought signatures, which multi-turn function calling requires.
                contents.append(types.Content.model_validate(message.raw))
                continue
            parts = [types.Part(text=message.content)] if message.content else []
            parts += [
                types.Part(function_call=types.FunctionCall(name=c.name, args=c.arguments)) for c in message.tool_calls
            ]
            contents.append(types.Content(role="model", parts=parts or [types.Part(text="…")]))
        elif message.role == "tool":
            part = types.Part(
                function_response=types.FunctionResponse(
                    name=names.get(message.tool_call_id or "", "tool"),
                    response={"error" if message.is_error else "result": message.content},
                )
            )
            if (
                contents
                and contents[-1].role == "user"
                and contents[-1].parts
                and contents[-1].parts[0].function_response
            ):
                contents[-1].parts.append(part)
            else:
                contents.append(types.Content(role="user", parts=[part]))
        else:
            contents.append(types.Content(role="user", parts=[types.Part(text=message.content)]))
    return contents


THINKING_LEVELS = {"low": "LOW", "medium": "MEDIUM", "high": "HIGH", "xhigh": "HIGH", "max": "HIGH"}


class GeminiChatModel:
    provider = "gemini"

    def __init__(self, api_key: str, main_model: str, small_model: str, effort: str = "medium") -> None:
        if not main_model or not small_model:
            raise LLMError("Cần đặt LLM_MAIN_MODEL và LLM_SMALL_MODEL khi dùng Gemini.")
        self.client = genai.Client(api_key=api_key or None)
        self.models = {"main": main_model, "small": small_model}
        self.effort = effort
        # Models without thinking levels (Gemini 2.x) reject the parameter; after one 400 it is left out for them.
        self.no_thinking_level: set[str] = set()

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
        config: dict[str, Any] = {"system_instruction": system, "max_output_tokens": max_tokens}
        if tools:
            config["tools"] = [
                types.Tool(
                    function_declarations=[
                        types.FunctionDeclaration(
                            name=t.name, description=t.description, parameters_json_schema=t.parameters
                        )
                        for t in tools
                    ]
                )
            ]
        text_parts: list[str] = []
        calls: list[ToolCall] = []
        model_parts: list[types.Part] = []
        usage = Usage(provider=self.provider, model=model)
        finish = "STOP"
        if model not in self.no_thinking_level:
            # Guards and the router want speed; agents get the configured depth.
            level = "LOW" if tier == "small" else THINKING_LEVELS.get(self.effort, "MEDIUM")
            config["thinking_config"] = types.ThinkingConfig(thinking_level=level)
        try:
            try:
                stream = await self.client.aio.models.generate_content_stream(
                    model=model, contents=_to_contents(messages), config=types.GenerateContentConfig(**config)
                )
            except errors.ClientError as error:
                if "thinking" not in str(error).lower() or "thinking_config" not in config:
                    raise
                self.no_thinking_level.add(model)
                del config["thinking_config"]
                stream = await self.client.aio.models.generate_content_stream(
                    model=model, contents=_to_contents(messages), config=types.GenerateContentConfig(**config)
                )
            async for chunk in stream:
                if chunk.usage_metadata:
                    meta = chunk.usage_metadata
                    usage.input_tokens = meta.prompt_token_count or 0
                    # Thinking tokens are billed as output.
                    usage.output_tokens = (meta.candidates_token_count or 0) + (meta.thoughts_token_count or 0)
                for candidate in chunk.candidates or []:
                    if candidate.finish_reason:
                        finish = str(
                            candidate.finish_reason.value
                            if hasattr(candidate.finish_reason, "value")
                            else candidate.finish_reason
                        )
                    for part in (candidate.content.parts if candidate.content else None) or []:
                        model_parts.append(part)
                        if part.text and not part.thought:
                            text_parts.append(part.text)
                            yield TextDelta(part.text)
                        if part.function_call:
                            call = part.function_call
                            calls.append(
                                ToolCall(
                                    id=call.id or f"call_{uuid.uuid4().hex[:8]}",
                                    name=call.name or "",
                                    arguments=dict(call.args or {}),
                                )
                            )
        except errors.APIError as error:
            if getattr(error, "code", None) in (401, 403):
                raise LLMError("Khoá API Gemini không hợp lệ hoặc chưa được cấp quyền.") from error
            if getattr(error, "code", None) == 429:
                raise LLMError("Đã vượt giới hạn gọi mô hình hoặc hết hạn mức. Thử lại sau ít phút.") from error
            detail = str(getattr(error, "message", "") or error)[:200]
            raise LLMError(f"Lỗi từ Gemini ({getattr(error, 'code', '?')}): {detail}") from error

        raw = types.Content(role="model", parts=model_parts).model_dump(exclude_none=True)
        stop = (
            "tool_use"
            if calls
            else {"STOP": "end_turn", "MAX_TOKENS": "max_tokens", "SAFETY": "refusal"}.get(finish, finish)
        )
        yield Completion(
            message=Message(
                role="assistant", content="".join(text_parts), tool_calls=calls, raw=raw, raw_provider=self.provider
            ),
            usage=usage,
            stop_reason=stop,
        )
