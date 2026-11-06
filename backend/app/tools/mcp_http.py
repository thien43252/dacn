"""The MCP server over streamable HTTP, mounted at /mcp for Dify (contracts/mcp-tools.md).

Stateless JSON responses: each request stands alone, which suits Dify's tool calls and needs no session affinity.
Only `Authorization: Bearer <MCP_TOKEN>` is accepted (no cookies); with no token configured the endpoint refuses
everything. DNS-rebinding protection is off because Dify reaches the backend as host.docker.internal and the
bearer token already authenticates every request.
"""

import hmac
import json

from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from mcp.server.transport_security import TransportSecuritySettings
from starlette.types import Receive, Scope, Send

from app.config import get_settings
from app.tools.server import server


def create_session_manager() -> StreamableHTTPSessionManager:
    """A fresh session manager per app instance (its `run()` may only be entered once)."""
    server.streamable_http_app(
        stateless_http=True,
        json_response=True,
        transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
    )
    return server.session_manager


def authorized(scope: Scope) -> bool:
    token = get_settings().mcp_token
    if not token:
        return False
    headers = dict(scope.get("headers") or [])
    supplied = headers.get(b"authorization", b"").decode("latin-1")
    return hmac.compare_digest(supplied.encode(), f"Bearer {token}".encode())


class MCPEndpoint:
    """ASGI app for /mcp: bearer check, then the MCP session manager."""

    def __init__(self, manager: StreamableHTTPSessionManager) -> None:
        self.manager = manager

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            return
        if not authorized(scope):
            body = json.dumps({"detail": "Thiếu hoặc sai mã truy cập MCP."}, ensure_ascii=False).encode()
            await send(
                {
                    "type": "http.response.start",
                    "status": 401,
                    "headers": [
                        (b"content-type", b"application/json; charset=utf-8"),
                        (b"www-authenticate", b"Bearer"),
                    ],
                }
            )
            await send({"type": "http.response.body", "body": body})
            return
        await self.manager.handle_request(scope, receive, send)
