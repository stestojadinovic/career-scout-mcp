"""Security-focused tests.

Covers:
- SQL injection attempts via parameterized fields. Parameterization
  means payloads are treated as data, not code; tests verify this in
  practice.
- Allowlist enforcement for sort_column / sort_direction (queries
  string-interpolates these, so an allowlist is the only defense).
- Range validation: limit, score, min_score boundaries.
- Empty/whitespace-only string rejection where non-empty is required.
- Config-level negatives (subprocess-isolated): non-loopback bind,
  http transport without auth token. These must run in subprocesses
  because career_scout_mcp.config validates at module import — a bad
  env in the test process would crash collection.

Each test is a single negative assertion. No tests share state with
each other; each gets a fresh tmp DB via the seeded_db / initialized_db
fixtures.
"""

from __future__ import annotations

import os
import subprocess
import sys
import textwrap
from pathlib import Path
from typing import Any

import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent


# ---------- SQL injection: parameterization holds under attack ----------


class TestSqlInjection:
    async def test_get_posting_with_sql_payload(self, seeded_db: Any) -> None:
        """Posting IDs are parameterized; SQL payloads return None safely."""
        from career_scout_mcp.storage import queries

        result = await queries.get_posting("' OR 1=1; --")
        assert result is None

    async def test_query_postings_role_anchor_payload(self, seeded_db: Any) -> None:
        """role_anchor with SQL payload returns empty; tables intact after."""
        from career_scout_mcp.storage import queries

        result = await queries.query_postings_filtered(
            role_anchor="' OR 1=1; DROP TABLE postings; --",
        )
        assert result == []
        # Verify the postings table still exists after the attempt
        check = await queries.get_posting("p-001")
        assert check is not None

    async def test_sort_column_allowlist_blocks_payload(self, seeded_db: Any) -> None:
        """Non-allowlisted sort columns raise ValueError before any SQL."""
        from career_scout_mcp.storage import queries

        with pytest.raises(ValueError):
            await queries.query_postings_filtered(
                sort_column="id; DROP TABLE postings; --",
            )

    async def test_sort_direction_validation(self, seeded_db: Any) -> None:
        """sort_direction outside {ASC,DESC} raises ValueError."""
        from career_scout_mcp.storage import queries

        with pytest.raises(ValueError):
            await queries.query_postings_filtered(
                sort_direction="ASC; DELETE FROM postings",
            )


# ---------- Range validation: numeric bounds ----------


class TestRangeValidation:
    async def test_limit_too_small(self, initialized_db: Any) -> None:
        from career_scout_mcp.storage import queries

        with pytest.raises(ValueError):
            await queries.get_scores_history(limit=0)

    async def test_limit_too_large(self, initialized_db: Any) -> None:
        from career_scout_mcp.storage import queries

        with pytest.raises(ValueError):
            await queries.get_scores_history(limit=99999)

    async def test_score_below_range(self, initialized_db: Any) -> None:
        from career_scout_mcp.storage import queries

        with pytest.raises(ValueError):
            await queries.insert_score(
                posting_id="p-001",
                score=-1,
                score_band="low",
                rationale="x",
                model="m",
                rubric_version="v1",
            )

    async def test_score_above_range(self, initialized_db: Any) -> None:
        from career_scout_mcp.storage import queries

        with pytest.raises(ValueError):
            await queries.insert_score(
                posting_id="p-001",
                score=101,
                score_band="high",
                rationale="x",
                model="m",
                rubric_version="v1",
            )

    async def test_min_score_out_of_range(self, initialized_db: Any) -> None:
        from career_scout_mcp.storage import queries

        with pytest.raises(ValueError):
            await queries.query_postings_filtered(min_score=150)


# ---------- Empty/whitespace rejection ----------


class TestEmptyInputRejection:
    async def test_tag_with_empty_reason(self, seeded_db: Any) -> None:
        from career_scout_mcp.storage import queries

        with pytest.raises(ValueError):
            await queries.insert_tagged_mismatch(
                posting_id="p-001",
                expected_band="mid",
                reason="",
            )

    async def test_tag_with_whitespace_reason(self, seeded_db: Any) -> None:
        from career_scout_mcp.storage import queries

        with pytest.raises(ValueError):
            await queries.insert_tagged_mismatch(
                posting_id="p-001",
                expected_band="mid",
                reason="   \t\n  ",
            )


# ---------- Config-level: subprocess-isolated ----------


@pytest.mark.subprocess
class TestConfigSecurity:
    """Config validates at module import — bad env crashes import.

    These tests verify that critical misconfigurations FAIL at startup
    rather than being silently accepted. Each test spawns a fresh
    Python process with the bad env so the import-time validator runs
    in isolation from this test process.
    """

    def _run_with_env(
        self, env: dict[str, str], code: str
    ) -> subprocess.CompletedProcess[str]:
        full_env = os.environ.copy()
        # Strip the test defaults so the negative case isn't masked
        for key in (
            "SCOUT_DATA_PATH",
            "TAGGED_MISMATCHES_DB",
            "DIGEST_OUTPUT_PATH",
        ):
            full_env.pop(key, None)
        full_env.update(env)
        return subprocess.run(
            [sys.executable, "-c", textwrap.dedent(code)],
            env=full_env,
            capture_output=True,
            text=True,
            timeout=15,
        )

    def test_http_transport_without_auth_token(self) -> None:
        """MCP_TRANSPORT=http with empty MCP_AUTH_TOKEN must reject."""
        result = self._run_with_env(
            env={
                "MCP_TRANSPORT": "http",
                "MCP_AUTH_TOKEN": "",
                "RUBRIC_PATH": str(
                    REPO_ROOT / "src/career_scout_mcp/rubric/current.txt"
                ),
            },
            code="""
                from career_scout_mcp.config import settings
                print("unexpected success:", settings.mcp_transport)
            """,
        )
        combined = result.stderr + result.stdout
        assert result.returncode != 0, f"expected failure; got success: {combined}"
        assert "auth" in combined.lower() or "token" in combined.lower(), (
            f"error did not mention auth/token: {combined}"
        )

    def test_http_bind_not_loopback(self) -> None:
        """MCP_HTTP_BIND set to non-loopback address must reject."""
        result = self._run_with_env(
            env={
                "MCP_HTTP_BIND": "0.0.0.0:8765",
                "RUBRIC_PATH": str(
                    REPO_ROOT / "src/career_scout_mcp/rubric/current.txt"
                ),
            },
            code="""
                from career_scout_mcp.config import settings
                print("unexpected success:", settings.mcp_http_bind)
            """,
        )
        combined = result.stderr + result.stdout
        assert result.returncode != 0
        assert "loopback" in combined.lower() or "127.0.0.1" in combined.lower(), (
            f"error did not mention loopback restriction: {combined}"
        )
