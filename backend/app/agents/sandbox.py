"""Builder sandbox: talk to a draft agent outside any class, as the role it is made for."""

from collections.abc import AsyncIterator
from typing import TYPE_CHECKING

from app.agents.service import ResolvedAgent
from app.chat.router import ChatIn, run_turn

if TYPE_CHECKING:
    from app.agents.router import TryIn


def run_sandbox(user_id: str, agent: ResolvedAgent, payload: "TryIn") -> AsyncIterator[str]:
    chat = ChatIn(message=payload.message, conversation_id=payload.conversation_id, agent=agent.slug)
    return run_turn(user_id, None, payload.as_role, chat, agents_override=[agent], kind="sandbox")
