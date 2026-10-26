"""Provider-neutral chat and embedding interfaces.

Every provider adapter translates these shapes to its own SDK, so the runtime, guards and certification code never
import a vendor SDK. Tiers: "main" serves agents; "small" serves guards, the router and judges.
"""

import json
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

Tier = Literal["main", "small"]
Role = Literal["user", "assistant", "tool"]


@dataclass
class ToolSpec:
    name: str
    description: str
    # JSON Schema for the arguments the model may fill. Context the platform injects is never listed here.
    parameters: dict[str, Any]


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]
    # Set when the provider returned arguments that are not a JSON object; the runtime answers with an error.
    invalid: bool = False


@dataclass
class Message:
    role: Role
    content: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    # For role == "tool": which call this answers, and whether it failed.
    tool_call_id: str | None = None
    is_error: bool = False
    # Provider-native assistant content (e.g. Anthropic thinking blocks) to replay unchanged inside one tool loop.
    # Only reused by the adapter that produced it; other adapters fall back to `content` and `tool_calls`.
    raw: Any = None
    raw_provider: str | None = None


@dataclass
class Usage:
    provider: str
    model: str
    input_tokens: int = 0
    output_tokens: int = 0

    def add(self, other: "Usage") -> None:
        self.input_tokens += other.input_tokens
        self.output_tokens += other.output_tokens


@dataclass
class TextDelta:
    text: str


@dataclass
class Completion:
    """Final event of a stream: the assistant message (text and/or tool calls) and what it cost."""

    message: Message
    usage: Usage
    # "end_turn" | "tool_use" | "max_tokens" | "refusal" | provider-specific
    stop_reason: str


StreamEvent = TextDelta | Completion


class ChatModel(Protocol):
    provider: str

    def model_for(self, tier: Tier) -> str: ...

    def stream(
        self,
        messages: list[Message],
        *,
        system: str,
        tools: list[ToolSpec] | None = None,
        tier: Tier = "main",
        max_tokens: int = 4096,
    ) -> AsyncIterator[StreamEvent]: ...


class Embedder(Protocol):
    provider: str
    model: str
    dimensions: int

    async def embed(self, texts: list[str]) -> list[list[float]]: ...


class LLMError(RuntimeError):
    """A provider call failed in a way the user should hear about (missing key, quota, refusal)."""


async def complete(
    model: ChatModel,
    messages: list[Message],
    *,
    system: str,
    tools: list[ToolSpec] | None = None,
    tier: Tier = "main",
    max_tokens: int = 4096,
) -> Completion:
    final: Completion | None = None
    async for event in model.stream(messages, system=system, tools=tools, tier=tier, max_tokens=max_tokens):
        if isinstance(event, Completion):
            final = event
    if final is None:
        raise LLMError("Mô hình không trả về kết quả.")
    return final


def parse_json_object(text: str) -> dict[str, Any] | None:
    """Extracts the first JSON object from a model reply (tolerates ```json fences and prose around it)."""
    start = text.find("{")
    while start != -1:
        depth = 0
        in_string = False
        escaped = False
        for index in range(start, len(text)):
            char = text[index]
            if in_string:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == '"':
                    in_string = False
            elif char == '"':
                in_string = True
            elif char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    try:
                        value = json.loads(text[start : index + 1])
                    except json.JSONDecodeError:
                        break
                    return value if isinstance(value, dict) else None
        start = text.find("{", start + 1)
    return None


async def complete_json(
    model: ChatModel,
    prompt: str,
    *,
    system: str,
    tier: Tier = "small",
    max_tokens: int = 1024,
) -> tuple[dict[str, Any], Usage]:
    """One-shot JSON answer for guards, the router and judges. Retries once when the reply is not a JSON object."""
    messages = [Message(role="user", content=prompt)]
    usage = Usage(provider=model.provider, model=model.model_for(tier))
    for _ in range(2):
        result = await complete(model, messages, system=system, tier=tier, max_tokens=max_tokens)
        usage.add(result.usage)
        parsed = parse_json_object(result.message.content)
        if parsed is not None:
            return parsed, usage
        messages = [
            *messages,
            result.message,
            Message(role="user", content="Chỉ trả lời bằng đúng một JSON object hợp lệ, không thêm chữ nào khác."),
        ]
    raise LLMError("Mô hình không trả về JSON hợp lệ.")
