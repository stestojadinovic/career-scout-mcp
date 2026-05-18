"""Health endpoint — version, uptime, dependency reachability.

Returns a dict suitable for monitoring tools (Glances scrapes,
Prometheus targets, manual curl) and for the scout://health MCP
resource.

Checks:
- Service version (from package metadata)
- Git SHA (from CAREER_SCOUT_GIT_SHA env at deploy time, else "unknown")
- Process uptime in seconds
- Ollama reachability (HTTP GET /api/tags, 2s timeout)
- SQLite reachability (db.healthcheck())

Design choices defended:

- Health is never the bottleneck. All checks have short timeouts (2s
  Ollama HTTP, default for local SQLite). A failing check returns the
  failure inline; the endpoint itself doesn't block or retry.

- Returns dict, not pydantic model. Health endpoints conventionally
  return plain JSON the operator can grep/jq without schema awareness.

- Exposed as MCP resource scout://health (stdio clients); server.py
  optionally also mounts GET /health for load-balancer / Glances
  probes via the FastMCP underlying Starlette app.
"""

from __future__ import annotations

import asyncio
import os
import time
from importlib.metadata import PackageNotFoundError, version
from typing import Any

import httpx
from mcp.server.fastmcp import FastMCP

from career_scout_mcp.config import settings
from career_scout_mcp.storage import db


_START_TIME = time.monotonic()


def _get_version() -> str:
    try:
        return version("career-scout-mcp")
    except PackageNotFoundError:
        return "0.0.0-dev"


def _get_git_sha() -> str:
    return os.environ.get("CAREER_SCOUT_GIT_SHA", "unknown")


async def _check_ollama() -> dict[str, Any]:
    """Probe Ollama /api/tags with a 2s timeout."""
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            response = await client.get(f"{settings.ollama_host}/api/tags")
            if response.status_code == 200:
                return {"reachable": True}
            return {"reachable": False, "status": response.status_code}
    except Exception as e:
        return {"reachable": False, "error": str(e)}


async def get_health() -> dict[str, Any]:
    """Aggregate health into a single dict."""
    ollama_status, sqlite_status = await asyncio.gather(
        _check_ollama(),
        db.healthcheck(),
    )
    uptime_s = round(time.monotonic() - _START_TIME, 1)
    # db.healthcheck() reports per-database flags (scout_ok + tagged_ok),
    # not a single unified "ok" key. Treat SQLite as healthy only when
    # both databases are reachable.
    sqlite_ok = (
        sqlite_status.get("scout_ok") is True and sqlite_status.get("tagged_ok") is True
    )
    is_healthy = ollama_status.get("reachable") is True and sqlite_ok
    return {
        "status": "ok" if is_healthy else "degraded",
        "version": _get_version(),
        "git_sha": _get_git_sha(),
        "uptime_seconds": uptime_s,
        "checks": {
            "ollama": ollama_status,
            "sqlite": sqlite_status,
        },
    }


def register_health(mcp: FastMCP) -> None:
    """Register the health resource at scout://health."""
    mcp.resource("scout://health")(get_health)
