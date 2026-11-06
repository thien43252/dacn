"""The Dify engine: one chat turn through the eduagent-triage and eduagent-runner apps.

Contract: specs/001-dify-core-migration/contracts/dify-apps.md. Not built yet: it waits for the Dify spike (task
T006), whose recorded responses the offline tests replay.
"""

from collections.abc import AsyncIterator
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.agents.service import ResolvedAgent
    from app.chat.router import ChatIn


def run_dify_turn(
    user_id: str,
    class_id: str | None,
    role: str,
    payload: "ChatIn",
    *,
    agents_override: "list[ResolvedAgent] | None" = None,
    kind: str = "chat",
) -> AsyncIterator[str]:
    raise NotImplementedError("runtime_engine 'dify' is not available yet; use RUNTIME_ENGINE=langgraph")
