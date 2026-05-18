"""End-to-end tests: spawn server subprocess, exchange MCP protocol.

These tests do NOT hit Ollama — they exercise the protocol layer only.
Real-Ollama tests live in the smoke suite (Phase 5 verified).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent


def _build_env() -> dict[str, str]:
    env = os.environ.copy()
    env["RUBRIC_PATH"] = str(REPO_ROOT / "src/career_scout_mcp/rubric/current.txt")
    return env


class TestE2EStdio:
    async def test_initialize_and_list_tools(self) -> None:
        from mcp import ClientSession
        from mcp.client.stdio import StdioServerParameters, stdio_client

        params = StdioServerParameters(
            command=sys.executable,
            args=["-m", "career_scout_mcp", "--transport", "stdio"],
            env=_build_env(),
            cwd=str(REPO_ROOT),
        )
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                tools_response = await session.list_tools()
                names = [t.name for t in tools_response.tools]
                assert "rescore_posting" in names
                assert "tag_mismatched_score" in names
                assert "query_postings" in names
                assert "regenerate_digest" in names

    async def test_list_resources_and_prompts(self) -> None:
        from mcp import ClientSession
        from mcp.client.stdio import StdioServerParameters, stdio_client

        params = StdioServerParameters(
            command=sys.executable,
            args=["-m", "career_scout_mcp", "--transport", "stdio"],
            env=_build_env(),
            cwd=str(REPO_ROOT),
        )
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()

                resources_resp = await session.list_resources()
                uris = [str(r.uri) for r in resources_resp.resources]
                assert any("digest/current" in u for u in uris)
                assert any("stats/summary" in u for u in uris)

                prompts_resp = await session.list_prompts()
                names = [p.name for p in prompts_resp.prompts]
                assert "tune_rubric" in names
