"""Shared pytest fixtures for career-scout-mcp.

Sets canonical test env vars at IMPORT time, before any
career_scout_mcp module loads. This is necessary because
career_scout_mcp.config validates env at module import — a test that
imports anything from the package without env set first would crash
during collection.

Per-test fixtures (test_env, initialized_db, seeded_db) further isolate
state by pointing settings at a fresh tmpdir per test.
"""

from __future__ import annotations

# IMPORTANT: set defaults BEFORE importing career_scout_mcp.
import os
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

_DEFAULT_TMP = tempfile.mkdtemp(prefix="scout_test_default_")
os.environ.setdefault("SCOUT_DATA_PATH", _DEFAULT_TMP + "/data")
os.environ.setdefault("TAGGED_MISMATCHES_DB", _DEFAULT_TMP + "/tagged.db")
os.environ.setdefault("DIGEST_OUTPUT_PATH", _DEFAULT_TMP + "/digests")
os.environ.setdefault(
    "RUBRIC_PATH",
    str(REPO_ROOT / "src/career_scout_mcp/rubric/current.txt"),
)

# Safe to import the rest now. These imports are intentionally below the
# os.environ setup above (career_scout_mcp.config validates env at import
# time), so E402 is suppressed per-line for this required ordering.
import shutil  # noqa: E402
from collections.abc import AsyncIterator, Iterator  # noqa: E402
from typing import Any  # noqa: E402

import pytest  # noqa: E402
import pytest_asyncio  # noqa: E402


@pytest.fixture
def tmp_data_dir() -> Iterator[Path]:
    """Fresh tmp directory per test; cleaned up after."""
    tmpdir = tempfile.mkdtemp(prefix="scout_test_")
    yield Path(tmpdir)
    shutil.rmtree(tmpdir, ignore_errors=True)


@pytest.fixture
def test_env(tmp_data_dir: Path) -> Iterator[None]:
    """Point settings at a fresh tmp dir for this test, restore after.

    Mutates the settings singleton directly because pydantic-settings
    caches values at module import; env-var monkeypatching alone would
    not propagate to already-imported callers.
    """
    from career_scout_mcp.config import settings

    saved = {
        "scout_data_path": settings.scout_data_path,
        "tagged_mismatches_db": settings.tagged_mismatches_db,
        "digest_output_path": settings.digest_output_path,
    }
    settings.scout_data_path = tmp_data_dir / "data"
    settings.tagged_mismatches_db = tmp_data_dir / "tagged.db"
    settings.digest_output_path = tmp_data_dir / "digests"
    yield
    for key, value in saved.items():
        setattr(settings, key, value)


@pytest_asyncio.fixture
async def initialized_db(test_env: None) -> AsyncIterator[Any]:
    """db module with both schemas initialized on a fresh tmp dir."""
    from career_scout_mcp.storage import db

    await db.init_schemas()
    yield db


@pytest_asyncio.fixture
async def seeded_db(initialized_db: Any) -> AsyncIterator[Any]:
    """db with one posting + one score + one tagged mismatch."""
    db = initialized_db
    async with db.scout_connection() as conn:
        await conn.execute(
            "INSERT INTO postings (id, title, company, location, "
            "posted_date, description, raw_url, role_anchor) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "p-001",
                "Senior AI Engineer",
                "Acme AI",
                "Vienna",
                "2026-05-15",
                "AI platform work",
                "https://x.test/1",
                "ai_engineer",
            ),
        )
        await conn.execute(
            "INSERT INTO scores (posting_id, score, score_band, "
            "rationale, model, rubric_version, scored_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                "p-001",
                75,
                "high",
                "good fit",
                "ollama/qwen2.5:3b",
                "v1.0",
                "2026-05-18T10:00:00Z",
            ),
        )
        await conn.commit()
    async with db.tagged_mismatches_connection() as conn:
        await conn.execute(
            "INSERT INTO tagged_mismatches (posting_id, expected_band, "
            "reason, created_at) VALUES (?, ?, ?, ?)",
            (
                "p-001",
                "mid",
                "salary lower than band warrants",
                "2026-05-18T11:00:00Z",
            ),
        )
        await conn.commit()
    yield db
