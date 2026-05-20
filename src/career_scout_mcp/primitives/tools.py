"""MCP tools — model-invocable actions over the scoring pipeline.

Four tools, exposed via FastMCP decorator registration:

- rescore_posting(posting_id)         — re-score against current rubric
- tag_mismatched_score(...)           — record operator disagreement
- query_postings(...)                 — filtered list with latest scores
- regenerate_digest()                 — render top-N digest HTML

Design choices defended:

- Tools are plain async functions; FastMCP wiring happens via the
  register_tools(mcp) helper called from server.py. This decouples tool
  implementations from the FastMCP instance for unit-testability — the
  smoke test below calls these functions directly without an MCP server.

- Input validation lives in storage/queries.py (range checks, non-empty
  checks). Tools are thin wrappers — FastMCP handles JSON-schema-level
  type coercion from the wire; downstream validation enforces bounds.
  Defense in depth without per-function duplication.

- Return types are pydantic models. FastMCP auto-generates the output
  schema from the type annotations, so the wire contract matches the
  Python signature exactly. One source of truth.

- HTML digest renderer is intentionally minimal. The portfolio page
  (docs/architecture.html, Phase 8) gets the design treatment; the
  digest is a functional artifact, not a marketing surface. If digest
  styling becomes a concern, it gets its own module — not crammed in
  here.
"""

from __future__ import annotations

import html

from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel

from career_scout_mcp.config import settings
from career_scout_mcp.scoring.client import ScoreResult, score_posting
from career_scout_mcp.scoring.rubric import load_current_rubric
from career_scout_mcp.storage import queries


# ---------- Tool result models ----------


class AckResult(BaseModel):
    """Acknowledgement returned by write-only tools."""

    ok: bool
    id: int
    message: str


class PostingSummary(BaseModel):
    """Compact view of a posting + its latest score for list responses."""

    id: str
    title: str
    company: str
    location: str | None
    posted_date: str
    role_anchor: str
    latest_score: int | None
    latest_score_band: str | None


class DigestResult(BaseModel):
    """Output of regenerate_digest."""

    path: str
    postings_included: int
    bytes_written: int


# ---------- Tool implementations ----------


async def rescore_posting(posting_id: str) -> ScoreResult:
    """Re-score one posting against the current rubric via the configured LLM.

    Loads the posting, loads the current rubric, scores it via LiteLLM,
    persists the new score row, and returns the structured result.
    Raises ValueError if posting not found; ScoringError on LLM/parse
    failure.
    """
    posting = await queries.get_posting(posting_id)
    if posting is None:
        raise ValueError(f"posting not found: {posting_id!r}")

    rubric = load_current_rubric()
    result = await score_posting(posting, rubric)

    await queries.insert_score(
        posting_id=posting.id,
        score=result.score,
        score_band=result.score_band,
        rationale=result.rationale,
        model=result.model,
        rubric_version=result.rubric_version,
    )
    return result


async def tag_mismatched_score(
    posting_id: str,
    expected_band: str,
    reason: str,
) -> AckResult:
    """Record that a stored score does not match operator judgment.

    Writes to tagged_mismatches.db. The tune_rubric prompt aggregates
    these for rubric refinement workflows. Reason must be non-empty.
    """
    new_id = await queries.insert_tagged_mismatch(
        posting_id=posting_id,
        expected_band=expected_band,
        reason=reason,
    )
    return AckResult(
        ok=True,
        id=new_id,
        message=f"tagged mismatch for {posting_id} (id={new_id})",
    )


async def query_postings(
    min_score: int = 0,
    role_anchor: str | None = None,
    date_after: str | None = None,
    limit: int = 20,
) -> list[PostingSummary]:
    """List postings matching the filter criteria, with their latest score.

    Returns only postings that have at least one score (the JOIN
    excludes never-scored ones). Empty result is valid output.
    """
    rows = await queries.query_postings_filtered(
        min_score=min_score,
        role_anchor=role_anchor,
        date_after=date_after,
        limit=limit,
    )
    return [
        PostingSummary(
            id=r.posting.id,
            title=r.posting.title,
            company=r.posting.company,
            location=r.posting.location,
            posted_date=r.posting.posted_date,
            role_anchor=r.posting.role_anchor,
            latest_score=r.latest_score.score if r.latest_score else None,
            latest_score_band=(r.latest_score.score_band if r.latest_score else None),
        )
        for r in rows
    ]


async def regenerate_digest() -> DigestResult:
    """Render a digest HTML of the current top-20 postings.

    Output path is settings.digest_output_path (operator-controlled, not
    user-input — no path traversal vector). Writes a single
    self-contained HTML file with minimal inline styling.
    """
    top = await queries.get_top_postings_for_digest(limit=20)

    html_parts: list[str] = [
        "<!DOCTYPE html>",
        "<html lang='en'><head>",
        "<meta charset='utf-8'>",
        "<title>Career Scout Digest</title>",
        "<style>",
        "body{font-family:system-ui,sans-serif;max-width:900px;",
        "margin:2rem auto;padding:0 1rem;color:#222;}",
        ".post{border:1px solid #ddd;padding:1rem;margin:1rem 0;",
        "border-radius:6px;background:#fafafa;}",
        ".score{font-weight:bold;padding:0 .4rem;border-radius:3px;}",
        ".band-high{color:#fff;background:#0a7;}",
        ".band-mid{color:#fff;background:#c80;}",
        ".band-low{color:#fff;background:#a00;}",
        "h1{border-bottom:2px solid #0a7;padding-bottom:.5rem;}",
        ".meta{color:#666;font-size:.9rem;}",
        "</style>",
        "</head><body>",
        "<h1>Career Scout Digest</h1>",
        f"<p>Top {len(top)} postings by latest score.</p>",
    ]
    for r in top:
        score = r.latest_score
        if score is None:
            continue
        # score.score_band is a Literal["high","mid","low"] (see Score in
        # storage/queries.py), so band-{score.score_band} is safe to embed
        # without escaping. Every other interpolation is user/LLM-supplied
        # text and must be html.escape()d.
        html_parts.append(
            f"<div class='post'>"
            f"<h2>{html.escape(r.posting.title)} "
            f"<span class='score band-{score.score_band}'>{score.score}</span>"
            f"</h2>"
            f"<p class='meta'><strong>{html.escape(r.posting.company)}</strong> &middot; "
            f"{html.escape(r.posting.location or 'remote')} &middot; "
            f"{html.escape(r.posting.posted_date)} &middot; "
            f"{html.escape(r.posting.role_anchor)}</p>"
            f"<p><em>{html.escape(score.rationale or '')}</em></p>"
            f"</div>"
        )
    html_parts.append("</body></html>")
    html_doc = "\n".join(html_parts)

    output_dir = settings.digest_output_path
    output_dir.mkdir(parents=True, exist_ok=True)
    output_file = output_dir / "current.html"
    bytes_written = output_file.write_text(html_doc, encoding="utf-8")

    return DigestResult(
        path=str(output_file),
        postings_included=sum(1 for r in top if r.latest_score is not None),
        bytes_written=bytes_written,
    )


# ---------- Registration ----------


def register_tools(mcp: FastMCP) -> None:
    """Register all tools on the given FastMCP instance.

    Called from server.py at startup. Keeps tool implementations
    decoupled from the FastMCP instance so unit tests can exercise them
    as plain async functions.
    """
    mcp.tool()(rescore_posting)
    mcp.tool()(tag_mismatched_score)
    mcp.tool()(query_postings)
    mcp.tool()(regenerate_digest)
