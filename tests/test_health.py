"""Tests for health.py — _check_ollama mocked for determinism."""

from __future__ import annotations

from typing import Any

import pytest


class TestGetHealth:
    async def test_ok_when_all_reachable(
        self,
        initialized_db: Any,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from career_scout_mcp import health

        async def _ok() -> dict[str, Any]:
            return {"reachable": True}

        monkeypatch.setattr(health, "_check_ollama", _ok)
        result = await health.get_health()
        assert result["status"] == "ok"
        assert result["checks"]["ollama"]["reachable"] is True
        # checks.sqlite is the raw db.healthcheck() dict (scout_ok/tagged_ok).
        assert result["checks"]["sqlite"]["scout_ok"] is True
        assert result["checks"]["sqlite"]["tagged_ok"] is True

    async def test_degraded_when_ollama_unreachable(
        self,
        initialized_db: Any,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from career_scout_mcp import health

        async def _fail() -> dict[str, Any]:
            return {"reachable": False, "error": "refused"}

        monkeypatch.setattr(health, "_check_ollama", _fail)
        result = await health.get_health()
        assert result["status"] == "degraded"
        assert result["checks"]["ollama"]["reachable"] is False

    async def test_returns_metadata(
        self,
        initialized_db: Any,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from career_scout_mcp import health

        async def _ok() -> dict[str, Any]:
            return {"reachable": True}

        monkeypatch.setattr(health, "_check_ollama", _ok)
        result = await health.get_health()
        assert "version" in result
        assert result["version"]
        assert "uptime_seconds" in result
        assert result["uptime_seconds"] >= 0

    async def test_git_sha_from_env(
        self,
        initialized_db: Any,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from career_scout_mcp import health

        monkeypatch.setenv("CAREER_SCOUT_GIT_SHA", "abc123")

        async def _ok() -> dict[str, Any]:
            return {"reachable": True}

        monkeypatch.setattr(health, "_check_ollama", _ok)
        result = await health.get_health()
        assert result["git_sha"] == "abc123"
