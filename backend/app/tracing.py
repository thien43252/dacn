"""Langfuse tracing. Off unless LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY are set; every helper is then a no-op.

One chat turn (or one certification case) is one trace:

    chat ─┬─ triage                 eduagent-triage (safety + routing) in Dify
          ├─ run_agent ── <tool>    the eduagent-runner stream; MCP tool calls, with the model calls a tool makes
          └─ review                 eduagent-review, for students and parents

The steps inside each Dify app are traced by Dify itself (infra/dify/README.md, "Tracing"); the trace keeps the Dify
message and conversation ids to find them. Backend model calls outside a turn (reports, judges, eval scripts) become
traces of their own. Every string sent to Langfuse goes
through the same PII redaction as the input guard, and users are identified by id only.
"""

import logging
from collections.abc import AsyncIterator, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from functools import lru_cache
from typing import TYPE_CHECKING, Any

from app.config import get_settings
from app.llm.base import ChatModel, Completion, Message, StreamEvent, TextDelta, Tier, ToolSpec

if TYPE_CHECKING:
    from langfuse import Langfuse

log = logging.getLogger("eduagent")


def _mask(*, data: Any, **_: Any) -> Any:
    from app.guard.rules import redact

    if isinstance(data, str):
        return redact(data)[0]
    if isinstance(data, dict):
        return {key: _mask(data=value) for key, value in data.items()}
    if isinstance(data, list | tuple):
        return [_mask(data=value) for value in data]
    return data


@lru_cache
def get_langfuse() -> "Langfuse | None":
    settings = get_settings()
    if not (settings.langfuse_public_key and settings.langfuse_secret_key):
        return None
    from langfuse import Langfuse

    log.info("tracing to Langfuse at %s", settings.langfuse_base_url or "https://cloud.langfuse.com")
    return Langfuse(
        public_key=settings.langfuse_public_key,
        secret_key=settings.langfuse_secret_key,
        base_url=settings.langfuse_base_url or None,
        environment=settings.app_env,
        sample_rate=settings.langfuse_sample_rate,
        mask=_mask,
    )


def flush() -> None:
    client = get_langfuse()
    if client is not None:
        client.flush()


@dataclass
class Trace:
    """The root observation of a turn. Nodes open their spans under it explicitly, so the trace never depends on
    OpenTelemetry context surviving across the yields of the SSE generator."""

    root: Any
    # Re-applied by every node span so user, session and tags reach all observations (Langfuse filters on them).
    attributes: dict[str, Any]

    def update(self, **fields: Any) -> None:
        self.root.update(**fields)

    def score(self, name: str, value: float | str, comment: str | None = None) -> None:
        data_type = "CATEGORICAL" if isinstance(value, str) else "NUMERIC"
        self.root.score_trace(name=name, value=value, data_type=data_type, comment=comment)


@contextmanager
def start_trace(
    name: str,
    *,
    user_id: str,
    session_id: str | None = None,
    tags: list[str] | None = None,
    metadata: dict[str, str | None] | None = None,
    input: Any = None,
) -> Iterator[Trace | None]:
    client = get_langfuse()
    if client is None:
        yield None
        return
    from langfuse import propagate_attributes

    attributes: dict[str, Any] = {"user_id": user_id, "trace_name": name}
    if session_id:
        attributes["session_id"] = session_id
    if tags:
        attributes["tags"] = tags
    # Propagated metadata values must be short strings; None values are dropped.
    if metadata:
        attributes["metadata"] = {key: value for key, value in metadata.items() if value is not None}
    with propagate_attributes(**attributes):
        root = client.start_observation(name=name, as_type="chain", input=input)
    try:
        yield Trace(root, attributes)
    finally:
        root.end()


@contextmanager
def node(trace: Trace | None, name: str, *, as_type: str = "span", input: Any = None) -> Iterator[Any]:
    """A child of the trace root, current for the block: model calls and tools inside it nest under it."""
    if trace is None:
        yield None
        return
    from langfuse import propagate_attributes

    with (
        propagate_attributes(**trace.attributes),
        trace.root.start_as_current_observation(name=name, as_type=as_type, input=input) as observation,
    ):
        yield observation


@contextmanager
def observe(name: str, *, as_type: str = "span", input: Any = None) -> Iterator[Any]:
    """A child of the current observation (e.g. a tool call inside run_agent)."""
    client = get_langfuse()
    if client is None:
        yield None
        return
    with client.start_as_current_observation(name=name, as_type=as_type, input=input) as observation:
        yield observation


def _message(message: Message) -> dict[str, Any]:
    shown: dict[str, Any] = {"role": message.role, "content": message.content}
    if message.tool_calls:
        shown["tool_calls"] = [{"name": call.name, "arguments": call.arguments} for call in message.tool_calls]
    if message.tool_call_id:
        shown["tool_call_id"] = message.tool_call_id
    return shown


class TracedChatModel:
    """Records every model call as a Langfuse generation. Wraps the provider; behaviour is unchanged."""

    def __init__(self, inner: ChatModel) -> None:
        self.inner = inner
        self.provider = inner.provider

    def __getattr__(self, name: str) -> Any:
        return getattr(self.inner, name)

    def model_for(self, tier: Tier) -> str:
        return self.inner.model_for(tier)

    async def stream(
        self,
        messages: list[Message],
        *,
        system: str,
        tools: list[ToolSpec] | None = None,
        tier: Tier = "main",
        max_tokens: int = 4096,
    ) -> AsyncIterator[StreamEvent]:
        events = self.inner.stream(messages, system=system, tools=tools, tier=tier, max_tokens=max_tokens)
        client = get_langfuse()
        if client is None:
            async for event in events:
                yield event
            return
        from app.llm.registry import cost_usd

        # Not made current: the observation would otherwise stay attached across the generator's yields.
        generation = client.start_observation(
            name=f"llm.{tier}",
            as_type="generation",
            model=self.model_for(tier),
            model_parameters={"max_tokens": max_tokens},
            input=[{"role": "system", "content": system}, *(_message(m) for m in messages)],
            metadata={"provider": self.provider, "tools": [spec.name for spec in tools or []]},
        )
        first_token = False
        try:
            async for event in events:
                if isinstance(event, TextDelta) and not first_token:
                    first_token = True
                    generation.update(completion_start_time=datetime.now(UTC))
                elif isinstance(event, Completion):
                    usage = event.usage
                    cost = cost_usd(usage.model, usage.input_tokens, usage.output_tokens)
                    generation.update(
                        output=_message(event.message),
                        model=usage.model,
                        usage_details={"input": usage.input_tokens, "output": usage.output_tokens},
                        cost_details={"total": cost} if cost is not None else None,
                        level="WARNING" if event.stop_reason in ("refusal", "max_tokens") else None,
                        status_message=event.stop_reason,
                    )
                yield event
        except Exception as error:
            generation.update(level="ERROR", status_message=f"{type(error).__name__}: {error}"[:500])
            raise
        finally:
            generation.end()
