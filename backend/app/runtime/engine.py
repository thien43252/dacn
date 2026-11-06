"""Picks the agent runtime for a chat turn: the in-process LangGraph graph or Dify (`runtime_engine`).

Chat, the builder's sandbox and certification all go through here, so the eval scripts can compare both engines on
the same data (FR-024, FR-025).
"""

from collections.abc import AsyncIterator
from typing import TYPE_CHECKING

from app.config import get_settings

if TYPE_CHECKING:
    from app.agents.service import ResolvedAgent
    from app.chat.router import ChatIn


def current_engine() -> str:
    return get_settings().runtime_engine


def run_turn(
    user_id: str,
    class_id: str | None,
    role: str,
    payload: "ChatIn",
    *,
    agents_override: "list[ResolvedAgent] | None" = None,
    kind: str = "chat",
) -> AsyncIterator[str]:
    """Returns the SSE stream of one turn. Engine modules are imported lazily: they import app.chat.router."""
    if current_engine() == "dify":
        from app.runtime.dify_turn import run_dify_turn

        return run_dify_turn(user_id, class_id, role, payload, agents_override=agents_override, kind=kind)
    from app.runtime.langgraph_turn import run_langgraph_turn

    return run_langgraph_turn(user_id, class_id, role, payload, agents_override=agents_override, kind=kind)
