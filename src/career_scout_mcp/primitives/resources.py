"""MCP resources — read-only URI-addressable data over the scoring pipeline.

Six FastMCP registrations covering the five v5 resource specs:

- scout://digest/current          — latest digest HTML
- scout://scores/history          — recent scoring records, default limit
- scout://scores/history/{limit}  — recent scoring records, custom limit
- scout://rubric/current          — current scoring rubric text + version
- scout://config/scrapers         — synthetic scraper configs (demo)
- scout://stats/summary           — aggregate stats

Design choices defended:

- Resources are read-only. None of these accept write operations.
  Read/write split mirrors MCP semantics: tools are model-controlled
  actions; resources are app-controlled fetches.

- Path traversal prevention. The only parameterized resource takes an
  integer limit; FastMCP coerces the URI segment to int via the type
  hint, and integers carry no path-traversal payload. All filesystem
  paths read here resolve from settings (operator-controlled, validated
  at config load), never from user input. If a future resource accepts
  a string path parameter, it must validate against an allowlist or
  normalize via Path.resolve() against a known root — documented here
  so a reviewer catches any drift from the invariant.

- Synthetic scraper config is exactly that. The standalone build runs
  no scrapers; this resource exposes the shape so MCP clients can see
  the pattern without leaking the real Career Scout pipeline's source
  list. The _note field tells any reader explicitly.

- Resources decoupled from the FastMCP instance via register_resources()
  helper, same as tools.py. Unit-testable as plain async functions.
"""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from career_scout_mcp.config import settings
from career_scout_mcp.scoring.rubric import load_current_rubric
from career_scout_mcp.storage import queries


# Synthetic scraper config — demonstrates the pattern; no actual scrapers
# run in this CT. The real Career Scout pipeline (private, separate CT)
# maintains its own inventory. This resource exists so MCP clients can
# see the config shape without exposing the source list.
_SYNTHETIC_SCRAPERS: dict[str, Any] = {
    "scrapers": [
        {
            "id": "synthetic_board_a",
            "name": "Synthetic Job Board (Demo)",
            "url_pattern": "https://example.test/jobs?q={query}",
            "queries": [
                "AI engineer Vienna",
                "platform engineer EU remote",
                "MCP developer",
            ],
            "refresh_minutes": 1440,
            "enabled": False,
        },
    ],
    "_note": (
        "Synthetic demonstration of the scraper config shape. No "
        "scrapers run in the career-scout-mcp container. The real "
        "Career Scout pipeline lives in a private CT and maintains its "
        "own scraper inventory there."
    ),
}


async def digest_current() -> str:
    """Return the most recent digest HTML, or a placeholder if none exists."""
    output_file = settings.digest_output_path / "current.html"
    if not output_file.exists():
        return (
            "<!DOCTYPE html><html><body>"
            "<h1>No digest generated yet</h1>"
            "<p>Invoke the regenerate_digest tool to produce one.</p>"
            "</body></html>"
        )
    return output_file.read_text(encoding="utf-8")


async def scores_history_default() -> list[dict[str, Any]]:
    """Return the most recent 50 scoring records."""
    scores = await queries.get_scores_history(limit=50)
    return [s.model_dump() for s in scores]


async def scores_history(limit: int) -> list[dict[str, Any]]:
    """Return the most recent N scoring records.

    Caller-supplied limit is bounded in storage/queries (1..1000); out
    of range raises ValueError. Integer-only parameter, no path
    traversal vector.
    """
    scores = await queries.get_scores_history(limit=limit)
    return [s.model_dump() for s in scores]


async def rubric_current() -> dict[str, Any]:
    """Return the current rubric text + version + source path."""
    rubric = load_current_rubric()
    return rubric.model_dump()


async def config_scrapers() -> dict[str, Any]:
    """Return the synthetic scraper config (demonstration only)."""
    return _SYNTHETIC_SCRAPERS


async def stats_summary() -> dict[str, Any]:
    """Return aggregate stats for dashboard / overview consumption."""
    return await queries.get_stats_summary()


def register_resources(mcp: FastMCP) -> None:
    """Register all resources on the given FastMCP instance.

    Called from server.py at startup. Keeps resource implementations
    decoupled from the FastMCP instance for unit-testability.
    """
    mcp.resource("scout://digest/current")(digest_current)
    mcp.resource("scout://scores/history")(scores_history_default)
    mcp.resource("scout://scores/history/{limit}")(scores_history)
    mcp.resource("scout://rubric/current")(rubric_current)
    mcp.resource("scout://config/scrapers")(config_scrapers)
    mcp.resource("scout://stats/summary")(stats_summary)
