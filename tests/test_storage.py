"""Unit tests for storage layer — happy paths, ordering, pagination.

Complements test_security.py (which covers SQL injection, range
validation, empty input). This file exercises positive behavior:
data shapes, JOIN semantics, ordering, pagination, idempotency.
"""

from __future__ import annotations

from typing import Any


class TestSchemaInit:
    async def test_init_schemas_idempotent(self, initialized_db: Any) -> None:
        """Running init_schemas a second time is a no-op."""
        await initialized_db.init_schemas()
        from career_scout_mcp.storage import queries

        result = await queries.get_posting("nonexistent")
        assert result is None


class TestHealthcheck:
    async def test_healthcheck_ok_state(self, initialized_db: Any) -> None:
        """Both databases reachable, schemas present."""
        result = await initialized_db.healthcheck()
        # db.healthcheck() reports per-database flags, not a unified "ok".
        assert result["scout_ok"] is True
        assert result["tagged_ok"] is True


class TestQueryReads:
    async def test_get_posting_returns_row(self, seeded_db: Any) -> None:
        from career_scout_mcp.storage import queries

        posting = await queries.get_posting("p-001")
        assert posting is not None
        assert posting.title == "Senior AI Engineer"
        assert posting.role_anchor == "ai_engineer"

    async def test_get_posting_returns_none_for_missing(self, seeded_db: Any) -> None:
        from career_scout_mcp.storage import queries

        result = await queries.get_posting("does-not-exist")
        assert result is None

    async def test_get_latest_score_returns_most_recent(self, seeded_db: Any) -> None:
        from career_scout_mcp.storage import queries

        await queries.insert_score(
            posting_id="p-001",
            score=85,
            score_band="high",
            rationale="newer score",
            model="ollama/qwen2.5:3b",
            rubric_version="v1.0",
        )
        latest = await queries.get_latest_score("p-001")
        assert latest is not None
        assert latest.score == 85
        assert latest.rationale == "newer score"

    async def test_get_latest_score_none_for_unscored(
        self, initialized_db: Any
    ) -> None:
        from career_scout_mcp.storage import queries

        result = await queries.get_latest_score("nonexistent")
        assert result is None


class TestQueryFiltered:
    async def test_filter_by_min_score_excludes_below(self, seeded_db: Any) -> None:
        from career_scout_mcp.storage import queries

        results = await queries.query_postings_filtered(min_score=80)
        assert results == []

    async def test_filter_by_min_score_includes_at_or_above(
        self, seeded_db: Any
    ) -> None:
        from career_scout_mcp.storage import queries

        results = await queries.query_postings_filtered(min_score=70)
        assert len(results) == 1
        assert results[0].posting.id == "p-001"

    async def test_filter_by_role_anchor(self, seeded_db: Any) -> None:
        from career_scout_mcp.storage import queries

        results = await queries.query_postings_filtered(role_anchor="ai_engineer")
        assert len(results) == 1
        results = await queries.query_postings_filtered(role_anchor="other_role")
        assert results == []

    async def test_filter_by_date_after(self, seeded_db: Any) -> None:
        from career_scout_mcp.storage import queries

        # Seeded posting has posted_date=2026-05-15
        results = await queries.query_postings_filtered(date_after="2026-05-10")
        assert len(results) == 1
        results = await queries.query_postings_filtered(date_after="2026-05-20")
        assert results == []

    async def test_filter_limit_caps_results(self, seeded_db: Any) -> None:
        from career_scout_mcp.storage import queries

        async with seeded_db.scout_connection() as conn:
            for i in range(2, 7):
                await conn.execute(
                    "INSERT INTO postings (id, title, company, location, "
                    "posted_date, description, raw_url, role_anchor) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        f"p-{i:03d}",
                        f"Title {i}",
                        "Co",
                        "Vienna",
                        "2026-05-15",
                        f"desc {i}",
                        f"https://x.test/{i}",
                        "ai_engineer",
                    ),
                )
                await conn.execute(
                    "INSERT INTO scores (posting_id, score, score_band, "
                    "rationale, model, rubric_version, scored_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (
                        f"p-{i:03d}",
                        70 + i,
                        "high",
                        "fit",
                        "m",
                        "v1",
                        f"2026-05-18T10:0{i}:00Z",
                    ),
                )
            await conn.commit()
        results = await queries.query_postings_filtered(limit=3)
        assert len(results) == 3

    async def test_filter_sort_by_score_desc(self, seeded_db: Any) -> None:
        from career_scout_mcp.storage import queries

        async with seeded_db.scout_connection() as conn:
            await conn.execute(
                "INSERT INTO postings (id, title, company, location, "
                "posted_date, description, raw_url, role_anchor) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    "p-002",
                    "T2",
                    "Co",
                    "V",
                    "2026-05-15",
                    "d",
                    "url",
                    "a",
                ),
            )
            await conn.execute(
                "INSERT INTO scores (posting_id, score, score_band, "
                "rationale, model, rubric_version, scored_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    "p-002",
                    92,
                    "high",
                    "r",
                    "m",
                    "v1",
                    "2026-05-18T11:00:00Z",
                ),
            )
            await conn.commit()
        results = await queries.query_postings_filtered(
            sort_column="score", sort_direction="DESC"
        )
        assert results[0].latest_score is not None
        assert results[0].latest_score.score == 92
        assert results[1].latest_score is not None
        assert results[1].latest_score.score == 75


class TestDigestQueries:
    async def test_get_top_postings_excludes_unscored(self, seeded_db: Any) -> None:
        from career_scout_mcp.storage import queries

        async with seeded_db.scout_connection() as conn:
            await conn.execute(
                "INSERT INTO postings (id, title, company, location, "
                "posted_date, description, raw_url, role_anchor) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                ("p-X", "T", "Co", "V", "2026-05-15", "d", "url", "a"),
            )
            await conn.commit()
        top = await queries.get_top_postings_for_digest(limit=20)
        ids = [r.posting.id for r in top]
        assert "p-001" in ids
        assert "p-X" not in ids


class TestStatsSummary:
    async def test_stats_summary_counts(self, seeded_db: Any) -> None:
        from career_scout_mcp.storage import queries

        stats = await queries.get_stats_summary()
        assert stats["postings_total"] == 1
        assert stats["scores_total"] == 1
        assert stats["tagged_mismatches_total"] == 1
        # get_stats_summary() returns the band breakdown under
        # "scores_by_band" (verified Phase 5.4 contract).
        assert "scores_by_band" in stats
        assert stats["scores_by_band"].get("high", 0) == 1


class TestScoresHistory:
    async def test_history_ordered_newest_first(self, seeded_db: Any) -> None:
        from career_scout_mcp.storage import queries

        async with seeded_db.scout_connection() as conn:
            await conn.execute(
                "INSERT INTO scores (posting_id, score, score_band, "
                "rationale, model, rubric_version, scored_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    "p-001",
                    50,
                    "mid",
                    "old",
                    "m",
                    "v0",
                    "2026-01-01T00:00:00Z",
                ),
            )
            await conn.commit()
        history = await queries.get_scores_history(limit=10)
        assert history[0].score == 75
        assert history[1].score == 50


class TestTaggedMismatches:
    async def test_list_tagged_mismatches(self, seeded_db: Any) -> None:
        from career_scout_mcp.storage import queries

        results = await queries.list_tagged_mismatches(limit=10)
        assert len(results) == 1
        assert results[0].posting_id == "p-001"
        assert results[0].expected_band == "mid"

    async def test_insert_tagged_mismatch_returns_id(self, seeded_db: Any) -> None:
        from career_scout_mcp.storage import queries

        new_id = await queries.insert_tagged_mismatch(
            posting_id="p-001",
            expected_band="low",
            reason="actually a bad fit on second look",
        )
        assert new_id > 0
        all_mismatches = await queries.list_tagged_mismatches(limit=10)
        assert len(all_mismatches) == 2
