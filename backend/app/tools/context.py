"""Short-lived handles linking an MCP tool call to the platform context the tool guard approved."""

import secrets
from typing import TYPE_CHECKING

from mcp.server.mcpserver.exceptions import ToolError

if TYPE_CHECKING:
    from app.tools.registry import ToolContext

_live: dict[str, "ToolContext"] = {}


def register(context: "ToolContext") -> str:
    handle = secrets.token_urlsafe(16)
    _live[handle] = context
    return handle


def release(handle: str) -> None:
    _live.pop(handle, None)


def resolve(handle: str) -> "ToolContext":
    context = _live.get(handle)
    if context is None:
        raise ToolError("Ngữ cảnh gọi công cụ không hợp lệ hoặc đã hết hạn.")
    return context
