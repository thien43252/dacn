"""Client for the Dify Service API used by the `dify` engine (contracts/dify-apps.md).

Two apps per turn: `eduagent-triage` (workflow, blocking) decides safety and the agent, then `eduagent-runner`
(chatflow, streaming) answers. Stream events are turned into a few internal ones (research R9); everything else Dify
sends (`node_*`, `agent_log`, `ping`) is dropped, since tool events come from the platform's own MCP handler.

The HTTP client is passed in, so tests drive this module with `httpx.MockTransport` and recorded fixtures
(backend/tests/fixtures/dify/).
"""

import json
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any, Literal

import httpx

from app.config import Settings, get_settings
from app.llm.base import Usage


class DifyError(Exception):
    """Dify could not be reached, refused the request or failed while answering."""


class DifyConversationNotFound(DifyError):
    """The runner no longer knows the conversation id we stored (Dify rebuilt or its data deleted)."""


@dataclass
class TriageResult:
    verdict: str
    category: str
    reason: str
    agent: str
    route_reason: str
    usage: Usage | None = None


@dataclass
class RunnerEvent:
    # start: first event with the task id | delta: answer text | replace: moderation replaced the answer
    # end: message_end with usage | error: Dify failed mid-stream (text already sent stays)
    kind: Literal["start", "delta", "replace", "end", "error"]
    text: str = ""
    task_id: str = ""
    conversation_id: str = ""
    message_id: str = ""
    usage: Usage | None = None
    raw: dict[str, Any] = field(default_factory=dict)


def _usage(data: dict[str, Any] | None, purpose_model: str) -> Usage | None:
    if not data:
        return None
    return Usage(
        provider="dify",
        model=purpose_model,
        input_tokens=int(data.get("prompt_tokens") or 0),
        output_tokens=int(data.get("completion_tokens") or 0),
    )


def _error_message(response: httpx.Response) -> str:
    try:
        body = response.json()
    except ValueError:
        return response.text[:300]
    return str(body.get("message") or body.get("code") or body)[:300]


class DifyClient:
    def __init__(self, http: httpx.AsyncClient, settings: Settings | None = None) -> None:
        self.http = http
        self.settings = settings or get_settings()
        self.base = self.settings.dify_base_url.rstrip("/") + "/v1"

    def _headers(self, key: str) -> dict[str, str]:
        return {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}

    def _runner_key(self, raw: bool) -> str:
        return self.settings.dify_runner_raw_key if raw else self.settings.dify_runner_key

    async def run_triage(self, inputs: dict[str, str], user: str) -> TriageResult:
        """Runs the triage workflow. Any failure raises DifyError: the caller then fails the turn closed."""
        try:
            response = await self.http.post(
                f"{self.base}/workflows/run",
                headers=self._headers(self.settings.dify_triage_key),
                json={"inputs": inputs, "response_mode": "blocking", "user": user},
                timeout=self.settings.dify_timeout_s,
            )
        except httpx.HTTPError as error:
            raise DifyError(f"triage: {type(error).__name__}") from error
        if response.status_code != 200:
            raise DifyError(f"triage HTTP {response.status_code}: {_error_message(response)}")
        data = response.json().get("data") or {}
        if data.get("status") != "succeeded":
            raise DifyError(f"triage {data.get('status')}: {data.get('error') or ''}"[:300])
        outputs = data.get("outputs") or {}
        missing = [k for k in ("verdict", "category", "agent") if not outputs.get(k)]
        if missing:
            raise DifyError(f"triage outputs missing {missing}")
        tokens = int(data.get("total_tokens") or 0)
        return TriageResult(
            verdict=str(outputs["verdict"]),
            category=str(outputs["category"]),
            reason=str(outputs.get("reason") or ""),
            agent=str(outputs["agent"]),
            route_reason=str(outputs.get("route_reason") or ""),
            # The workflow reports only a total; it is booked as input tokens.
            usage=Usage(provider="dify", model="dify-triage", input_tokens=tokens) if tokens else None,
        )

    async def stream_runner(
        self,
        query: str,
        inputs: dict[str, str],
        conversation_id: str,
        user: str,
        *,
        raw: bool = False,
    ) -> AsyncIterator[RunnerEvent]:
        """Streams one runner turn as RunnerEvents.

        Raises DifyConversationNotFound or DifyError when the request is refused before streaming; failures after
        the first event arrive as an `error` event so the caller keeps the text already shown.
        """
        body = {
            "inputs": inputs,
            "query": query,
            "response_mode": "streaming",
            "conversation_id": conversation_id,
            "user": user,
        }
        timeout = httpx.Timeout(self.settings.dify_timeout_s, read=max(self.settings.dify_timeout_s, 60.0))
        started = False
        ended = False
        try:
            async with self.http.stream(
                "POST",
                f"{self.base}/chat-messages",
                headers=self._headers(self._runner_key(raw)),
                json=body,
                timeout=timeout,
            ) as response:
                if response.status_code != 200:
                    await response.aread()
                    message = _error_message(response)
                    if response.status_code == 404 and "conversation" in message.lower():
                        raise DifyConversationNotFound(message)
                    raise DifyError(f"runner HTTP {response.status_code}: {message}")
                async for line in response.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    try:
                        event = json.loads(line[5:])
                    except ValueError:
                        continue
                    name = event.get("event")
                    if not started and event.get("task_id"):
                        started = True
                        yield RunnerEvent(
                            "start",
                            task_id=event["task_id"],
                            conversation_id=event.get("conversation_id") or "",
                            message_id=event.get("message_id") or "",
                        )
                    if name in ("message", "agent_message"):
                        if event.get("answer"):
                            yield RunnerEvent("delta", text=event["answer"])
                    elif name == "message_replace":
                        yield RunnerEvent("replace", text=event.get("answer") or "")
                    elif name == "message_end":
                        ended = True
                        yield RunnerEvent(
                            "end",
                            conversation_id=event.get("conversation_id") or "",
                            message_id=event.get("message_id") or event.get("id") or "",
                            usage=_usage((event.get("metadata") or {}).get("usage"), "dify-runner"),
                        )
                    elif name == "error":
                        yield RunnerEvent("error", text=str(event.get("message") or event.get("code") or "error"))
                        return
                    elif name == "workflow_finished":
                        data = event.get("data") or {}
                        # After the runner's input moderation answers, Dify still reports the skipped workflow as
                        # failed; only a run that never produced a message is an error (e.g. an input too long).
                        if not ended and data.get("status") not in (None, "succeeded"):
                            yield RunnerEvent("error", text=str(data.get("error") or data.get("status")))
                            return
        except DifyError:
            raise
        except httpx.HTTPError as error:
            if not started:
                raise DifyError(f"runner: {type(error).__name__}") from error
            yield RunnerEvent("error", text=f"runner: {type(error).__name__}")

    async def stop(self, task_id: str, user: str, *, raw: bool = False) -> None:
        response = await self.http.post(
            f"{self.base}/chat-messages/{task_id}/stop",
            headers=self._headers(self._runner_key(raw)),
            json={"user": user},
            timeout=self.settings.dify_timeout_s,
        )
        if response.status_code != 200:
            raise DifyError(f"stop HTTP {response.status_code}: {_error_message(response)}")

    async def get_suggested(self, message_id: str, user: str) -> list[str]:
        response = await self.http.get(
            f"{self.base}/messages/{message_id}/suggested",
            headers=self._headers(self.settings.dify_runner_key),
            params={"user": user},
            timeout=self.settings.dify_timeout_s,
        )
        if response.status_code != 200:
            raise DifyError(f"suggested HTTP {response.status_code}: {_error_message(response)}")
        return [str(item) for item in (response.json().get("data") or []) if str(item).strip()]
