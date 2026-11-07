"""The agent runtime for a chat turn: chat, the builder's sandbox and certification all go through here.

Every turn runs on the self-hosted Dify apps (specs/001-dify-core-migration/contracts/dify-apps.md); the engine
name is kept in health and message metadata so runs stay comparable with earlier results.
"""

from collections.abc import AsyncIterator
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.agents.service import ResolvedAgent
    from app.chat.router import ChatIn


def run_turn(
    user_id: str,
    class_id: str | None,
    role: str,
    payload: "ChatIn",
    *,
    agents_override: "list[ResolvedAgent] | None" = None,
    kind: str = "chat",
) -> AsyncIterator[str]:
    """Returns the SSE stream of one turn. Imported lazily: dify_turn imports app.chat.router."""
    from app.runtime.dify_turn import run_dify_turn

    return run_dify_turn(user_id, class_id, role, payload, agents_override=agents_override, kind=kind)
