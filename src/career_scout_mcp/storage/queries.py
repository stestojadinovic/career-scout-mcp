"""Data-access functions over scout.db and tagged_mismatches.db.

Hard security rule: every query in this module uses sqlite3 parameter
substitution. No f-strings interpolating user input. No string
concatenation of user input into SQL.

The only places we assemble SQL strings dynamically are:

1. ORDER BY column and direction. SQLite does not permit parameterizing
   identifiers or keywords. We validate caller-supplied sort columns and
   directions against hardcoded allowlists before substituting; an
   invalid value raises ValueError. The allowlists are inline constants
   below — adding a new sortable column is a deliberate code change
   visible in PR diff.

2. Optional WHERE-clause fragments. The fragments are static strings
   ("AND p.role_anchor = ?"), chosen by Python control flow based on
   whether a filter parameter is provided. The fragment strings contain
   no user input; the actual filter VALUES still flow through ?
   placeholders alongside the assembled SQL.

Anything that touches user input — posting_id, role_anchor, date_after,
limit, offset, score, score_band, expected_band, reason — passes through
? placeholders. This docstring exists so any contributor reading the
diff understands the policy is non-negotiable, not stylistic.

Application-level validation (range checks, non-empty checks) is layered
on top of parameterization, not in place of it. Defense in depth.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field

from career_scout_mcp.storage.db import (
    scout_connection,
    tagged_mismatches_connection,
)


# Allowlists for query_postings ordering. Updating either is a deliberate
# code change visible in PR review; the security guarantee depends on these
# being closed sets known at compile time.
_POSTING_SORT_COLUMNS = frozenset({"posted_date", "title", "company", "score"})
_SORT_DIRECTIONS = frozenset({"ASC", "DESC"})


def _validated_sort(column: str, direction: str) -> tuple[str, str]:
    """Return (column, direction_upper) only if both pass allowlist checks."""
    if column not in _POSTING_SORT_COLUMNS:
        raise ValueError(
            f"invalid sort column: {column!r}; allowed: {sorted(_POSTING_SORT_COLUMNS)}"
        )
    direction_upper = direction.upper()
    if direction_upper not in _SORT_DIRECTIONS:
        raise ValueError(f"invalid sort direction: {direction!r}; allowed: ASC, DESC")
    return column, direction_upper


# ---------- Pydantic models for return types ----------


class Posting(BaseModel):
    """A job posting row, matching the postings table 1:1."""

    id: str
    title: str
    company: str
    location: str | None
    posted_date: str
    description: str
    raw_url: str | None
    role_anchor: str


class Score(BaseModel):
    """A score row, matching the scores table 1:1."""

    id: int
    posting_id: str
    score: int = Field(ge=0, le=100)
    score_band: str
    rationale: str | None
    model: str
    rubric_version: str
    scored_at: str


class PostingWithScore(BaseModel):
    """A posting joined with its latest score (None if never scored)."""

    posting: Posting
    latest_score: Score | None


class TaggedMismatch(BaseModel):
    """A user-tagged mismatch row, matching the table 1:1."""

    id: int
    posting_id: str
    expected_band: str
    reason: str
    created_at: str


# ---------- Read functions ----------


async def get_posting(posting_id: str) -> Posting | None:
    """Fetch a posting by id, or None if not found."""
    async with scout_connection() as conn:
        cur = await conn.execute(
            "SELECT id, title, company, location, posted_date, description, "
            "raw_url, role_anchor FROM postings WHERE id = ?",
            (posting_id,),
        )
        row = await cur.fetchone()
    if row is None:
        return None
    return Posting(**dict(row))


async def get_latest_score(posting_id: str) -> Score | None:
    """Fetch the most recent score for a posting, or None."""
    async with scout_connection() as conn:
        cur = await conn.execute(
            "SELECT id, posting_id, score, score_band, rationale, model, "
            "rubric_version, scored_at FROM scores WHERE posting_id = ? "
            "ORDER BY scored_at DESC LIMIT 1",
            (posting_id,),
        )
        row = await cur.fetchone()
    if row is None:
        return None
    return Score(**dict(row))


async def query_postings_filtered(
    min_score: int = 0,
    role_anchor: str | None = None,
    date_after: str | None = None,
    limit: int = 20,
    sort_column: str = "posted_date",
    sort_direction: str = "DESC",
) -> list[PostingWithScore]:
    """Filtered query of postings joined with their latest score.

    Returns postings whose latest score meets min_score, optionally
    filtered by role_anchor and minimum posted_date. Postings with no
    scores are excluded by the JOIN. Empty result is valid output.
    """
    if not 1 <= limit <= 1000:
        raise ValueError(f"limit must be 1..1000, got {limit}")
    if not 0 <= min_score <= 100:
        raise ValueError(f"min_score must be 0..100, got {min_score}")

    sort_col, sort_dir = _validated_sort(sort_column, sort_direction)

    # Build SQL from validated static fragments. The only dynamic insertions
    # are sort_col and sort_dir, both checked above against frozenset
    # allowlists. All VALUES flow through ? placeholders below.
    fragments: list[str] = [
        "SELECT",
        "  p.id, p.title, p.company, p.location, p.posted_date,",
        "  p.description, p.raw_url, p.role_anchor,",
        "  s.id AS score_id, s.score, s.score_band, s.rationale,",
        "  s.model, s.rubric_version, s.scored_at",
        "FROM postings p",
        "JOIN scores s ON s.posting_id = p.id",
        "WHERE s.scored_at = (",
        "  SELECT MAX(scored_at) FROM scores WHERE posting_id = p.id",
        ")",
        "AND s.score >= ?",
    ]
    params: list[Any] = [min_score]

    if role_anchor is not None:
        fragments.append("AND p.role_anchor = ?")
        params.append(role_anchor)
    if date_after is not None:
        fragments.append("AND p.posted_date >= ?")
        params.append(date_after)

    fragments.append(f"ORDER BY {sort_col} {sort_dir}")
    fragments.append("LIMIT ?")
    params.append(limit)

    sql = "\n".join(fragments)

    async with scout_connection() as conn:
        cur = await conn.execute(sql, params)
        rows = await cur.fetchall()

    results: list[PostingWithScore] = []
    for row in rows:
        d = dict(row)
        posting = Posting(
            id=d["id"],
            title=d["title"],
            company=d["company"],
            location=d["location"],
            posted_date=d["posted_date"],
            description=d["description"],
            raw_url=d["raw_url"],
            role_anchor=d["role_anchor"],
        )
        score = Score(
            id=d["score_id"],
            posting_id=d["id"],
            score=d["score"],
            score_band=d["score_band"],
            rationale=d["rationale"],
            model=d["model"],
            rubric_version=d["rubric_version"],
            scored_at=d["scored_at"],
        )
        results.append(PostingWithScore(posting=posting, latest_score=score))
    return results


async def get_scores_history(limit: int = 100, offset: int = 0) -> list[Score]:
    """Paginated scoring history, newest first."""
    if not 1 <= limit <= 1000:
        raise ValueError(f"limit must be 1..1000, got {limit}")
    if offset < 0:
        raise ValueError(f"offset must be >= 0, got {offset}")

    async with scout_connection() as conn:
        cur = await conn.execute(
            "SELECT id, posting_id, score, score_band, rationale, model, "
            "rubric_version, scored_at FROM scores "
            "ORDER BY scored_at DESC LIMIT ? OFFSET ?",
            (limit, offset),
        )
        rows = await cur.fetchall()
    return [Score(**dict(r)) for r in rows]


async def get_top_postings_for_digest(limit: int = 20) -> list[PostingWithScore]:
    """Top-scoring postings for the digest, ordered by score DESC."""
    return await query_postings_filtered(
        min_score=0, limit=limit, sort_column="score", sort_direction="DESC"
    )


async def list_tagged_mismatches(limit: int = 50) -> list[TaggedMismatch]:
    """Recent tagged mismatches, newest first. Used by the tune_rubric prompt."""
    if not 1 <= limit <= 1000:
        raise ValueError(f"limit must be 1..1000, got {limit}")
    async with tagged_mismatches_connection() as conn:
        cur = await conn.execute(
            "SELECT id, posting_id, expected_band, reason, created_at "
            "FROM tagged_mismatches ORDER BY created_at DESC LIMIT ?",
            (limit,),
        )
        rows = await cur.fetchall()
    return [TaggedMismatch(**dict(r)) for r in rows]


async def get_stats_summary() -> dict[str, Any]:
    """Aggregate stats for the scout://stats/summary resource."""
    stats: dict[str, Any] = {}

    async with scout_connection() as conn:
        cur = await conn.execute("SELECT COUNT(*) AS n FROM postings")
        row = await cur.fetchone()
        stats["postings_total"] = row["n"] if row else 0

        cur = await conn.execute("SELECT COUNT(*) AS n FROM scores")
        row = await cur.fetchone()
        stats["scores_total"] = row["n"] if row else 0

        cur = await conn.execute("SELECT AVG(score) AS avg_score FROM scores")
        row = await cur.fetchone()
        avg = row["avg_score"] if row else None
        stats["scores_avg"] = round(float(avg), 2) if avg is not None else None

        cur = await conn.execute(
            "SELECT score_band, COUNT(*) AS n FROM scores GROUP BY score_band"
        )
        rows = await cur.fetchall()
        stats["scores_by_band"] = {r["score_band"]: r["n"] for r in rows}

    async with tagged_mismatches_connection() as conn:
        cur = await conn.execute("SELECT COUNT(*) AS n FROM tagged_mismatches")
        row = await cur.fetchone()
        stats["tagged_mismatches_total"] = row["n"] if row else 0

    return stats


# ---------- Write functions ----------


async def insert_score(
    posting_id: str,
    score: int,
    score_band: str,
    rationale: str | None,
    model: str,
    rubric_version: str,
) -> int:
    """Insert a new score row. Returns the new score id."""
    if not posting_id.strip():
        raise ValueError("posting_id must be non-empty")
    if not 0 <= score <= 100:
        raise ValueError(f"score must be 0..100, got {score}")
    if not score_band.strip():
        raise ValueError("score_band must be non-empty")
    if not model.strip():
        raise ValueError("model must be non-empty")
    if not rubric_version.strip():
        raise ValueError("rubric_version must be non-empty")

    now = datetime.now(timezone.utc).isoformat()
    async with scout_connection() as conn:
        cur = await conn.execute(
            "INSERT INTO scores "
            "(posting_id, score, score_band, rationale, model, "
            "rubric_version, scored_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (posting_id, score, score_band, rationale, model, rubric_version, now),
        )
        await conn.commit()
        new_id = cur.lastrowid
    if new_id is None:
        raise RuntimeError("INSERT returned no lastrowid")
    return new_id


async def insert_tagged_mismatch(
    posting_id: str, expected_band: str, reason: str
) -> int:
    """Insert a tagged-mismatch row. Returns the new row id."""
    if not posting_id.strip():
        raise ValueError("posting_id must be non-empty")
    if not expected_band.strip():
        raise ValueError("expected_band must be non-empty")
    if not reason.strip():
        raise ValueError("reason must be non-empty")

    now = datetime.now(timezone.utc).isoformat()
    async with tagged_mismatches_connection() as conn:
        cur = await conn.execute(
            "INSERT INTO tagged_mismatches "
            "(posting_id, expected_band, reason, created_at) "
            "VALUES (?, ?, ?, ?)",
            (posting_id, expected_band, reason, now),
        )
        await conn.commit()
        new_id = cur.lastrowid
    if new_id is None:
        raise RuntimeError("INSERT returned no lastrowid")
    return new_id
