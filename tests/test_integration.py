"""Integration tests — full stack in-process, LLM mocked.

Real Ollama is exercised only in test_e2e.py. This file tests the
chain DB -> tools -> resources -> prompts and verifies FastMCP wiring.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest


def _mock_response(content: str) -> MagicMock:
    r = MagicMock()
    r.choices = [MagicMock()]
    r.choices[0].message = MagicMock()
    r.choices[0].message.content = content
    return r


class TestChain:
    async def test_rescore_then_query_reflects_new_score(
        self, seeded_db: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from career_scout_mcp.primitives import tools

        mock = AsyncMock(
            return_value=_mock_response(
                '{"score": 95, "score_band": "high", "rationale": "new"}'
            )
        )
        monkeypatch.setattr("litellm.acompletion", mock)
        await tools.rescore_posting("p-001")
        results = await tools.query_postings(min_score=0)
        p001 = [r for r in results if r.id == "p-001"][0]
        assert p001.latest_score == 95

    async def test_tag_then_tune_rubric_includes(self, seeded_db: Any) -> None:
        from career_scout_mcp.primitives import prompts, tools

        await tools.tag_mismatched_score(
            posting_id="p-001",
            expected_band="low",
            reason="actually peripheral on second look",
        )
        result = await prompts.tune_rubric()
        assert "actually peripheral on second look" in result

    async def test_regenerate_then_digest_resource(self, seeded_db: Any) -> None:
        from career_scout_mcp.primitives import resources, tools

        await tools.regenerate_digest()
        digest = await resources.digest_current()
        assert "Career Scout Digest" in digest


class TestServerInstance:
    def test_mcp_singleton(self) -> None:
        from career_scout_mcp.server import mcp

        assert mcp is not None
        assert mcp.name == "career-scout-mcp"

    async def test_all_primitives_registered(self) -> None:
        """FastMCP list_* methods return our primitives."""
        from career_scout_mcp.server import mcp

        tools_list = await mcp.list_tools()
        tool_names = [t.name for t in tools_list]
        assert "rescore_posting" in tool_names
        assert "tag_mismatched_score" in tool_names
        assert "query_postings" in tool_names
        assert "regenerate_digest" in tool_names

        prompts_list = await mcp.list_prompts()
        prompt_names = [p.name for p in prompts_list]
        assert "tune_rubric" in prompt_names
        assert "analyze_digest_trends" in prompt_names
