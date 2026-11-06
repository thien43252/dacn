"""Short-lived handles linking an MCP tool call to the platform context the tool guard approved.

The handle is the `ctx` argument of every tool. The LangGraph engine registers one per call; the Dify engine
registers one per turn and passes it to the runner app, whose MCP tools send it back as a Fixed Value the model
never sees (research R6). A handle lives at most `TTL_S` seconds and is released when its turn ends.
"""

import secrets
import time
from typing import TYPE_CHECKING

from mcp.server.mcpserver.exceptions import ToolError

if TYPE_CHECKING:
    from app.tools.registry import ToolContext

TTL_S = 600
INVALID = "Ngữ cảnh gọi công cụ không hợp lệ hoặc đã hết hạn."

# handle -> (context, expiry on the monotonic clock)
_live: dict[str, tuple["ToolContext", float]] = {}


def now() -> float:
    """Monotonic clock; tests move it forward to expire handles."""
    return time.monotonic()


def sweep() -> int:
    """Drops expired handles nobody looked up again, e.g. of a turn that was cut off. Returns how many."""
    current = now()
    expired = [handle for handle, (_, expires_at) in _live.items() if current >= expires_at]
    for handle in expired:
        _live.pop(handle, None)
    return len(expired)


def register(context: "ToolContext", ttl_s: float = TTL_S) -> str:
    sweep()
    handle = secrets.token_urlsafe(16)  # 128 bits
    _live[handle] = (context, now() + ttl_s)
    return handle


def release(handle: str) -> None:
    _live.pop(handle, None)


def lookup(handle: str) -> "ToolContext | None":
    entry = _live.get(handle)
    if entry is None:
        return None
    context, expires_at = entry
    if now() >= expires_at:
        _live.pop(handle, None)
        return None
    return context


def resolve(handle: str) -> "ToolContext":
    context = lookup(handle)
    if context is None:
        raise ToolError(INVALID)
    return context
