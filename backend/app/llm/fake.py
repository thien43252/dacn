"""Deterministic offline provider for tests and key-less demos.

Behaviour, in order:
1. A scripted reply queued with `script()` (tests use this to drive tool calls, guard verdicts, judge scores).
2. A JSON prompt (system mentions JSON) gets `{}` so callers fall back to their own defaults.
3. A last user message containing `[[tool:NAME {json}]]` calls that tool once, if it is offered.
4. Otherwise a short Vietnamese echo, streamed word by word.
"""

import json
import re
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field

from app.llm.base import Completion, Message, StreamEvent, TextDelta, Tier, ToolCall, ToolSpec, Usage

TOOL_PATTERN = re.compile(r"\[\[tool:([a-z_]+)\s*(\{.*?\})?\]\]", re.S)


@dataclass
class Scripted:
    text: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    stop_reason: str | None = None


Responder = Callable[[list[Message], str, list[ToolSpec] | None, Tier], Scripted | None]


class FakeChatModel:
    provider = "fake"

    def __init__(self) -> None:
        self.queue: list[Scripted] = []
        self.responders: list[Responder] = []
        self.calls: list[dict] = []

    def model_for(self, tier: Tier) -> str:
        return f"fake-{tier}"

    def script(self, *items: Scripted | str) -> None:
        self.queue.extend(Scripted(text=item) if isinstance(item, str) else item for item in items)

    def respond_with(self, responder: Responder) -> None:
        """Registers a function that may answer based on the request (returns None to pass)."""
        self.responders.append(responder)

    def _reply(self, messages: list[Message], system: str, tools: list[ToolSpec] | None, tier: Tier) -> Scripted:
        for responder in self.responders:
            reply = responder(messages, system, tools, tier)
            if reply is not None:
                return reply
        if self.queue:
            return self.queue.pop(0)
        if "JSON" in system:
            return Scripted(text="{}")
        last = messages[-1] if messages else Message(role="user")
        if last.role == "user":
            match = TOOL_PATTERN.search(last.content)
            offered = {tool.name for tool in tools or []}
            if match and match.group(1) in offered:
                arguments = json.loads(match.group(2) or "{}")
                return Scripted(
                    tool_calls=[ToolCall(id=f"call_{len(self.calls)}", name=match.group(1), arguments=arguments)]
                )
            return Scripted(
                text=f"(Chế độ thử nghiệm, chưa nối mô hình thật) Mình đã nhận câu hỏi: “{last.content[:200]}”."
            )
        if last.role == "tool":
            return Scripted(text=f"Kết quả công cụ: {last.content[:400]}")
        return Scripted(text="Mình sẵn sàng hỗ trợ.")

    async def stream(
        self,
        messages: list[Message],
        *,
        system: str,
        tools: list[ToolSpec] | None = None,
        tier: Tier = "main",
        max_tokens: int = 4096,
    ) -> AsyncIterator[StreamEvent]:
        self.calls.append({"messages": list(messages), "system": system, "tools": tools, "tier": tier})
        reply = self._reply(messages, system, tools, tier)
        for index, word in enumerate(reply.text.split(" ")):
            if word or index == 0:
                yield TextDelta(word if index == 0 else f" {word}")
        stop = reply.stop_reason or ("tool_use" if reply.tool_calls else "end_turn")
        prompt_tokens = sum(len(message.content) for message in messages) // 4 + len(system) // 4
        yield Completion(
            message=Message(role="assistant", content=reply.text, tool_calls=list(reply.tool_calls)),
            usage=Usage(self.provider, self.model_for(tier), prompt_tokens, max(1, len(reply.text) // 4)),
            stop_reason=stop,
        )


class FakeEmbedder:
    """Hashed bag of words: similar wording gives similar vectors, so RAG tests run offline."""

    provider = "fake"
    model = "fake-hash"

    def __init__(self, dimensions: int = 768) -> None:
        self.dimensions = dimensions

    async def embed(self, texts: list[str]) -> list[list[float]]:
        import hashlib
        import math

        vectors = []
        for text in texts:
            vector = [0.0] * self.dimensions
            for token in re.findall(r"\w+", text.lower()):
                bucket = int(hashlib.md5(token.encode()).hexdigest(), 16) % self.dimensions
                vector[bucket] += 1.0
            norm = math.sqrt(sum(value * value for value in vector)) or 1.0
            vectors.append([value / norm for value in vector])
        return vectors
