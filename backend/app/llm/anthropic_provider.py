"""Claude via the official Anthropic Python SDK (streaming Messages API with client tools)."""

from collections.abc import AsyncIterator
from typing import Any

import anthropic

from app.llm.base import Completion, LLMError, Message, StreamEvent, TextDelta, Tier, ToolCall, ToolSpec, Usage

DEFAULT_MODELS: dict[Tier, str] = {"main": "claude-opus-5-5", "small": "claude-haiku-5-5"}
# Server-side refusal fallback (routes by refusal category). Claude Haiku 5.5 has no server-side fallback.
FALLBACK_MODELS = {"claude-opus-5-5", "claude-opus-5", "claude-fable-5-1", "claude-sonnet-5-5"}
FALLBACK_BETA = "server-side-fallback-2026-07-01"


def _tool_param(tool: ToolSpec) -> dict[str, Any]:
    return {
        "name": tool.name,
        "description": tool.description,
        "input_schema": tool.parameters,
        # Stream tool inputs as generated; the runtime validates arguments before running any tool.
        "eager_input_streaming": True,
    }


def _block_dict(block: Any) -> dict[str, Any]:
    return block.model_dump(exclude_none=True) if hasattr(block, "model_dump") else dict(block)


def _replayable(blocks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Assistant content to send back. After a mid-output fallback, model-internal blocks before the last
    `fallback` marker are dropped; text blocks and everything after the marker are echoed unchanged."""
    boundary = max((index for index, block in enumerate(blocks) if block.get("type") == "fallback"), default=-1)
    out = []
    for index, block in enumerate(blocks):
        kind = block.get("type")
        if kind == "fallback":
            continue
        if index < boundary and kind not in ("text",):
            continue
        out.append(block)
    return out


def _to_anthropic(messages: list[Message]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for message in messages:
        if message.role == "tool":
            result = {
                "type": "tool_result",
                "tool_use_id": message.tool_call_id,
                "content": message.content,
                "is_error": message.is_error,
            }
            # All results of one assistant turn go back in a single user message.
            if out and out[-1]["role"] == "user" and isinstance(out[-1]["content"], list):
                out[-1]["content"].append(result)
            else:
                out.append({"role": "user", "content": [result]})
        elif message.role == "assistant":
            if message.raw_provider == "anthropic" and message.raw:
                out.append({"role": "assistant", "content": _replayable(message.raw)})
                continue
            content: list[dict[str, Any]] = []
            if message.content:
                content.append({"type": "text", "text": message.content})
            for call in message.tool_calls:
                content.append({"type": "tool_use", "id": call.id, "name": call.name, "input": call.arguments})
            out.append({"role": "assistant", "content": content or [{"type": "text", "text": "…"}]})
        else:
            out.append({"role": "user", "content": message.content})
    return out


class AnthropicChatModel:
    provider = "anthropic"

    def __init__(self, api_key: str, main_model: str = "", small_model: str = "", effort: str = "medium") -> None:
        # An empty key lets the SDK resolve credentials itself (env var or `ant auth login` profile).
        self.client = anthropic.AsyncAnthropic(api_key=api_key) if api_key else anthropic.AsyncAnthropic()
        self.models = {"main": main_model or DEFAULT_MODELS["main"], "small": small_model or DEFAULT_MODELS["small"]}
        self.effort = effort

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
            "max_tokens": max_tokens,
            "system": system,
            "messages": _to_anthropic(messages),
            # Guards and the router want speed; agents get the configured depth.
            "output_config": {"effort": "low" if tier == "small" else self.effort},
        }
        if tools:
            params["tools"] = [_tool_param(tool) for tool in tools]
        if model in FALLBACK_MODELS:
            params["betas"] = [FALLBACK_BETA]
            params["fallbacks"] = "default"
        try:
            async with self.client.beta.messages.stream(**params) as stream:
                async for event in stream:
                    if event.type == "text":
                        yield TextDelta(event.text)
                final = await stream.get_final_message()
        except ValueError as error:
            # Tool input JSON the SDK could not parse at all; the runtime re-issues the turn.
            raise LLMError(f"Mô hình trả về tham số công cụ không đọc được: {error}") from error
        except anthropic.AuthenticationError as error:
            raise LLMError("Khoá API Anthropic không hợp lệ.") from error
        except anthropic.RateLimitError as error:
            raise LLMError("Đã vượt giới hạn gọi mô hình. Thử lại sau ít phút.") from error
        except anthropic.APIStatusError as error:
            raise LLMError(f"Lỗi từ Anthropic ({error.status_code}).") from error
        except anthropic.APIConnectionError as error:
            raise LLMError("Không kết nối được tới Anthropic.") from error

        blocks = [_block_dict(block) for block in final.content]
        boundary = max((i for i, block in enumerate(blocks) if block.get("type") == "fallback"), default=-1)
        text = "".join(block.get("text", "") for block in blocks if block.get("type") == "text")
        calls = []
        if final.stop_reason != "refusal":
            for block in blocks[boundary + 1 :]:
                if block.get("type") == "tool_use":
                    arguments = block.get("input")
                    calls.append(
                        ToolCall(
                            id=block["id"],
                            name=block["name"],
                            arguments=arguments if isinstance(arguments, dict) else {},
                            invalid=not isinstance(arguments, dict) or final.stop_reason == "max_tokens",
                        )
                    )
        yield Completion(
            message=Message(role="assistant", content=text, tool_calls=calls, raw=blocks, raw_provider=self.provider),
            usage=Usage(
                provider=self.provider,
                model=final.model or model,
                input_tokens=(final.usage.input_tokens or 0)
                + (getattr(final.usage, "cache_read_input_tokens", 0) or 0)
                + (getattr(final.usage, "cache_creation_input_tokens", 0) or 0),
                output_tokens=final.usage.output_tokens or 0,
            ),
            stop_reason=final.stop_reason or "end_turn",
        )
