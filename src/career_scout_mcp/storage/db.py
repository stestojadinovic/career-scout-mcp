"""Storage layer: SQLite connection helpers and schema management.

Two databases serve this MCP server:

- scout.db (under SCOUT_DATA_PATH/) — the source dataset: postings + scores.
  In production this would wrap an existing read-mostly Career Scout DB;
  in this standalone demo it is seeded from synthetic fixtures.

- tagged_mismatches.db (at TAGGED_MISMATCHES_DB) — user-generated tagging
  via the tag_mismatched_score tool. Kept separate from scout.db so the
  source dataset stays clean and can be rotated independently of tagging
  history. (Design decision: "Why separate tagged_mismatches.db" in the
  docs page.)

Design notes:

- WAL mode enabled per-connection. Single-writer pattern (this MCP server
  process), but WAL allows concurrent reads during a write — important
  for regenerate_digest while a rescore is in flight.

- Per-call connections via async context manager. SQLite manages its own
  internal locking; we don't need a separate connection pool. Tests
  benefit from the clean-slate-per-call pattern.

- Schema migration is idempotent CREATE TABLE IF NOT EXISTS at startup.
  For v0.1.0, this beats Alembic-style migration tooling on operational
  complexity; the schema is stable enough that the trade favors simplicity.

- foreign_keys=ON enforced per-connection. SQLite defaults to OFF for
  legacy compat; we want enforcement at the storage layer so application
  code can rely on referential integrity.

- busy_timeout=5000ms. With WAL + concurrent reads, a brief writer-wait
  is preferable to immediate SQLITE_BUSY errors.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import aiosqlite

from career_scout_mcp.config import settings


SCOUT_SCHEMA = """
CREATE TABLE IF NOT EXISTS postings (
    id            TEXT PRIMARY KEY,
    title         TEXT NOT NULL,
    company       TEXT NOT NULL,
    location      TEXT,
    posted_date   TEXT NOT NULL,
    description   TEXT NOT NULL,
    raw_url       TEXT,
    role_anchor   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS scores (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    posting_id      TEXT NOT NULL,
    score           INTEGER NOT NULL CHECK (score >= 0 AND score <= 100),
    score_band      TEXT NOT NULL,
    rationale       TEXT,
    model           TEXT NOT NULL,
    rubric_version  TEXT NOT NULL,
    scored_at       TEXT NOT NULL,
    FOREIGN KEY (posting_id) REFERENCES postings(id)
);

CREATE INDEX IF NOT EXISTS idx_scores_posting_id ON scores(posting_id);
CREATE INDEX IF NOT EXISTS idx_scores_scored_at ON scores(scored_at);
CREATE INDEX IF NOT EXISTS idx_postings_role_anchor ON postings(role_anchor);
CREATE INDEX IF NOT EXISTS idx_postings_posted_date ON postings(posted_date);
"""


TAGGED_MISMATCHES_SCHEMA = """
CREATE TABLE IF NOT EXISTS tagged_mismatches (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    posting_id      TEXT NOT NULL,
    expected_band   TEXT NOT NULL,
    reason          TEXT NOT NULL,
    created_at      TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_tagged_mismatches_posting_id
    ON tagged_mismatches(posting_id);
CREATE INDEX IF NOT EXISTS idx_tagged_mismatches_created_at
    ON tagged_mismatches(created_at);
"""


def scout_db_path() -> Path:
    """Resolved path to the scout dataset SQLite file."""
    return settings.scout_data_path / "scout.db"


def tagged_mismatches_path() -> Path:
    """Resolved path to the tagged-mismatches SQLite file."""
    return settings.tagged_mismatches_db


async def _configure_connection(conn: aiosqlite.Connection) -> None:
    """Apply per-connection PRAGMAs: WAL, foreign keys, row factory."""
    await conn.execute("PRAGMA journal_mode = WAL")
    await conn.execute("PRAGMA foreign_keys = ON")
    await conn.execute("PRAGMA synchronous = NORMAL")
    await conn.execute("PRAGMA busy_timeout = 5000")
    conn.row_factory = aiosqlite.Row  # rows behave like both tuples and dicts


@asynccontextmanager
async def scout_connection() -> AsyncIterator[aiosqlite.Connection]:
    """Open an async connection to the scout dataset DB."""
    async with aiosqlite.connect(scout_db_path()) as conn:
        await _configure_connection(conn)
        yield conn


@asynccontextmanager
async def tagged_mismatches_connection() -> AsyncIterator[aiosqlite.Connection]:
    """Open an async connection to the tagged-mismatches DB."""
    async with aiosqlite.connect(tagged_mismatches_path()) as conn:
        await _configure_connection(conn)
        yield conn


async def init_schemas() -> None:
    """Ensure both databases exist with up-to-date schemas. Idempotent.

    Called at server startup. Creates parent directories if missing,
    applies the schema scripts (CREATE TABLE IF NOT EXISTS, so safe to
    re-run on every boot).
    """
    # systemd's StateDirectory creates /var/lib/career-scout-mcp; the
    # data subdirectory beneath it is application-managed.
    scout_db_path().parent.mkdir(parents=True, exist_ok=True)
    tagged_mismatches_path().parent.mkdir(parents=True, exist_ok=True)

    async with scout_connection() as conn:
        await conn.executescript(SCOUT_SCHEMA)
        await conn.commit()

    async with tagged_mismatches_connection() as conn:
        await conn.executescript(TAGGED_MISMATCHES_SCHEMA)
        await conn.commit()


async def healthcheck() -> dict[str, Any]:
    """Lightweight reachability check used by the /health endpoint.

    Returns a dict with paths and per-DB OK/error indicators. Does not
    raise; the health endpoint reports the failure rather than crashing.
    """
    result: dict[str, Any] = {
        "scout_db_path": str(scout_db_path()),
        "tagged_mismatches_path": str(tagged_mismatches_path()),
    }
    try:
        async with scout_connection() as conn:
            cur = await conn.execute("SELECT COUNT(*) FROM postings")
            row = await cur.fetchone()
            result["scout_postings_count"] = row[0] if row else 0
            result["scout_ok"] = True
    except Exception as e:
        result["scout_ok"] = False
        result["scout_error"] = str(e)

    try:
        async with tagged_mismatches_connection() as conn:
            cur = await conn.execute("SELECT COUNT(*) FROM tagged_mismatches")
            row = await cur.fetchone()
            result["tagged_mismatches_count"] = row[0] if row else 0
            result["tagged_ok"] = True
    except Exception as e:
        result["tagged_ok"] = False
        result["tagged_error"] = str(e)

    return result
