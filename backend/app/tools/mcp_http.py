"""The MCP server over streamable HTTP, mounted at /mcp for Dify (contracts/mcp-tools.md).

Stateless JSON responses: each request stands alone, which suits Dify's tool calls and needs no session affinity.
Only `Authorization: Bearer <MCP_TOKEN>` is accepted (no cookies); with no token configured the endpoint refuses
everything. DNS-rebinding protection stays on: the Host header must be a local name or the host of MCP_PUBLIC_URL
(host.docker.internal by default, how Dify's containers reach the backend), and browser origins are refused since
only Dify, server to server, calls this endpoint.
"""

import hmac
import json
from urllib.parse import urlsplit

from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from mcp.server.transport_security import TransportSecuritySettings
from starlette.types import Receive, Scope, Send

from app.config import get_settings
from app.tools.server import server

LOCAL_HOSTS = ("127.0.0.1", "localhost", "[::1]")


def allowed_hosts() -> list[str]:
    """Host header values accepted at /mcp, each with or without a port."""
    names = list(LOCAL_HOSTS)
    public = urlsplit(get_settings().mcp_public_url).hostname
    if public and public not in names:
        names.append(public)
    return [variant for name in names for variant in (name, f"{name}:*")]


def create_session_manager() -> StreamableHTTPSessionManager:
    """A fresh session manager per app instance (its `run()` may only be entered once)."""
    server.streamable_http_app(
        stateless_http=True,
        json_response=True,
        transport_security=TransportSecuritySettings(
            enable_dns_rebinding_protection=True, allowed_hosts=allowed_hosts(), allowed_origins=[]
        ),
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
