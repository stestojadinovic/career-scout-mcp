"""Tests for primitives/tools.py with LiteLLM mocked."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest


def _mock_response(content: str) -> MagicMock:
    r = MagicMock()
    r.choices = [MagicMock()]
    r.choices[0].message = MagicMock()
    r.choices[0].message.content = content
    return r


class TestRescorePosting:
    async def test_rescore_existing_persists(
        self, seeded_db: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from career_scout_mcp.primitives import tools
        from career_scout_mcp.storage import queries

        mock = AsyncMock(
            return_value=_mock_response(
                '{"score": 88, "score_band": "high", "rationale": "fit"}'
            )
        )
        monkeypatch.setattr("litellm.acompletion", mock)
        result = await tools.rescore_posting("p-001")
        assert result.score == 88
        latest = await queries.get_latest_score("p-001")
        assert latest is not None
        assert latest.score == 88

    async def test_rescore_missing_raises(self, initialized_db: Any) -> None:
        from career_scout_mcp.primitives import tools

        with pytest.raises(ValueError, match="not found"):
            await tools.rescore_posting("does-not-exist")


class TestTagMismatchedScore:
    async def test_tag_returns_ack(self, seeded_db: Any) -> None:
        from career_scout_mcp.primitives import tools

        result = await tools.tag_mismatched_score(
            posting_id="p-001",
            expected_band="mid",
            reason="real reason here",
        )
        assert result.ok is True
        assert result.id > 0
        assert "p-001" in result.message


class TestQueryPostings:
    async def test_returns_summaries(self, seeded_db: Any) -> None:
        from career_scout_mcp.primitives import tools

        results = await tools.query_postings(min_score=70)
        assert len(results) == 1
        assert results[0].id == "p-001"
        assert results[0].latest_score == 75
        assert results[0].latest_score_band == "high"

    async def test_filter_excludes_unscored(self, seeded_db: Any) -> None:
        from career_scout_mcp.primitives import tools

        async with seeded_db.scout_connection() as conn:
            await conn.execute(
                "INSERT INTO postings (id, title, company, location, "
                "posted_date, description, raw_url, role_anchor) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                ("p-X", "T", "Co", "V", "2026-05-15", "d", "url", "a"),
            )
            await conn.commit()
        results = await tools.query_postings()
        ids = [r.id for r in results]
        assert "p-001" in ids
        assert "p-X" not in ids


class TestRegenerateDigest:
    async def test_writes_html_file(self, seeded_db: Any) -> None:
        from career_scout_mcp.primitives import tools

        result = await tools.regenerate_digest()
        assert result.postings_included >= 1
        assert result.bytes_written > 0
        assert Path(result.path).exists()
        html = Path(result.path).read_text(encoding="utf-8")
        assert "Career Scout Digest" in html
        assert "Senior AI Engineer" in html

    async def test_band_class_applied(self, seeded_db: Any) -> None:
        from career_scout_mcp.primitives import tools

        await tools.regenerate_digest()
        # Re-fetch via the result path
        result = await tools.regenerate_digest()
        html = Path(result.path).read_text(encoding="utf-8")
        assert "band-high" in html
