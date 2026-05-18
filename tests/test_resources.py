"""Tests for primitives/resources.py."""

from __future__ import annotations

from typing import Any


class TestDigestCurrent:
    async def test_placeholder_when_missing(self, initialized_db: Any) -> None:
        from career_scout_mcp.primitives import resources

        result = await resources.digest_current()
        assert "No digest generated yet" in result

    async def test_returns_generated_html(self, seeded_db: Any) -> None:
        from career_scout_mcp.primitives import resources, tools

        await tools.regenerate_digest()
        result = await resources.digest_current()
        assert "Career Scout Digest" in result
        assert "Senior AI Engineer" in result


class TestScoresHistory:
    async def test_default_returns_list(self, seeded_db: Any) -> None:
        from career_scout_mcp.primitives import resources

        result = await resources.scores_history_default()
        assert isinstance(result, list)
        assert len(result) == 1
        assert result[0]["score"] == 75

    async def test_with_limit(self, seeded_db: Any) -> None:
        from career_scout_mcp.primitives import resources

        result = await resources.scores_history(limit=5)
        assert len(result) == 1


class TestRubricCurrent:
    async def test_returns_rubric_dict(self, test_env: None) -> None:
        from career_scout_mcp.primitives import resources

        result = await resources.rubric_current()
        assert result["version"] == "v1.0"
        assert "Career Scout Rubric" in result["text"]


class TestConfigScrapers:
    async def test_returns_synthetic(self) -> None:
        from career_scout_mcp.primitives import resources

        result = await resources.config_scrapers()
        assert "scrapers" in result
        assert "_note" in result
        assert "synthetic" in result["_note"].lower()


class TestStatsSummary:
    async def test_returns_counts(self, seeded_db: Any) -> None:
        from career_scout_mcp.primitives import resources

        result = await resources.stats_summary()
        assert result["postings_total"] == 1
        assert result["scores_total"] == 1
        assert result["tagged_mismatches_total"] == 1
