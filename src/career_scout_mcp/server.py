"""FastMCP server instance — wires all primitives + transports.

Creates the singleton FastMCP instance, registers tools, resources,
prompts, and health, then exposes:

- mcp           — FastMCP singleton (importable for tests)
- run_stdio()   — stdio transport entry point
- run_http()    — HTTP transport entry point with Bearer auth

Design choices defended:

- Singleton FastMCP instance at module level. Tests import `mcp`
  directly and inspect registered primitives without standing up a
  transport.

- HTTP transport defense-in-depth: config.py enforces loopback bind +
  required auth_token at startup; BearerAuthMiddleware here rejects
  unauthenticated requests in-flight. Two layers because operational
  mistakes happen.

- HTTP binding stays loopback-only by default. Public exposure is the
  CF Tunnel + nginx reverse proxy, never a direct 0.0.0.0 bind from
  the application.

- Runtime init (logging, schema) runs once before either transport
  starts. Schema is idempotent; running it on every boot guarantees a
  clean container state without a separate migration step.
"""

from __future__ import annotations

import asyncio
from typing import Any, Awaitable, Callable

from mcp.server.fastmcp import FastMCP
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from career_scout_mcp.health import register_health
from career_scout_mcp.logging import configure_logging
from career_scout_mcp.primitives.prompts import register_prompts
from career_scout_mcp.primitives.resources import register_resources
from career_scout_mcp.primitives.tools import register_tools
from career_scout_mcp.storage import db


# Singleton FastMCP instance, wired at import time.
mcp = FastMCP("career-scout-mcp")

register_tools(mcp)
register_resources(mcp)
register_prompts(mcp)
register_health(mcp)


class BearerAuthMiddleware(BaseHTTPMiddleware):
    """Reject HTTP requests lacking a matching Bearer token."""

    def __init__(self, app: Any, expected_token: str) -> None:
        super().__init__(app)
        self._expected = expected_token

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        auth = request.headers.get("authorization", "")
        if not auth.startswith("Bearer "):
            return JSONResponse({"error": "missing bearer token"}, status_code=401)
        if auth.removeprefix("Bearer ") != self._expected:
            return JSONResponse({"error": "invalid bearer token"}, status_code=401)
        return await call_next(request)


async def _init_runtime() -> None:
    """One-time startup tasks before either transport begins serving."""
    configure_logging()
    await db.init_schemas()


def run_stdio() -> None:  # pragma: no cover
    """Start the MCP server on stdio transport.

    Excluded from coverage: mcp.run() blocks indefinitely on the stdio
    transport, so a test that calls this never returns to observe.
    Argparse dispatch into this function is tested in tests/test_main.py
    via monkeypatched no-op replacement.
    """
    asyncio.run(_init_runtime())
    mcp.run(transport="stdio")


def run_http(  # pragma: no cover
    host: str, port: int, auth_token: str
) -> None:
    """Start the MCP server on HTTP transport, gated by Bearer auth.

    Excluded from coverage: uvicorn.run() blocks indefinitely on the
    serving loop, so a test that calls this never returns. Argparse
    dispatch into this function is tested in tests/test_main.py via
    monkeypatched no-op replacement.

    Uses FastMCP's underlying Starlette app, layered with our auth
    middleware. The exact app-factory method name may differ across
    FastMCP versions; if `streamable_http_app` is unavailable, the
    fallback is `sse_app` or direct `mcp.run(transport="streamable-http")`
    with a separate Starlette mount.
    """
    asyncio.run(_init_runtime())
    app = mcp.streamable_http_app()
    app.add_middleware(BearerAuthMiddleware, expected_token=auth_token)

    import uvicorn

    uvicorn.run(app, host=host, port=port)
