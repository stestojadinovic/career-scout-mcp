"""Tests for primitives/prompts.py."""

from __future__ import annotations

from typing import Any


class TestTuneRubric:
    async def test_with_mismatches(self, seeded_db: Any) -> None:
        from career_scout_mcp.primitives import prompts

        result = await prompts.tune_rubric()
        assert "Rubric Refinement Task" in result
        assert "p-001" in result
        assert "salary lower than band warrants" in result
        assert "v1.0" in result

    async def test_no_mismatches_returns_guidance(self, initialized_db: Any) -> None:
        from career_scout_mcp.primitives import prompts

        result = await prompts.tune_rubric()
        assert "No tagged mismatches recorded" in result

    async def test_respects_limit(self, seeded_db: Any) -> None:
        from career_scout_mcp.primitives import prompts
        from career_scout_mcp.storage import queries

        for i in range(5):
            await queries.insert_tagged_mismatch(
                posting_id="p-001",
                expected_band="low",
                reason=f"distinct reason {i}",
            )
        result = await prompts.tune_rubric(limit=3)
        # Each mismatch starts with "- Posting p-001:"
        count = result.count("- Posting p-001:")
        assert count == 3


class TestAnalyzeDigestTrends:
    async def test_with_scores(self, seeded_db: Any) -> None:
        from career_scout_mcp.primitives import prompts

        result = await prompts.analyze_digest_trends()
        assert "Digest Trend Analysis Task" in result
        assert "p-001" in result
        assert "score=75" in result

    async def test_no_scores_returns_guidance(self, initialized_db: Any) -> None:
        from career_scout_mcp.primitives import prompts

        result = await prompts.analyze_digest_trends()
        assert "No scoring history available" in result
