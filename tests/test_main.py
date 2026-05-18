"""Tests for __main__.py CLI argument handling."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent


class TestCLI:
    def test_help_exits_clean(self) -> None:
        env = os.environ.copy()
        env["RUBRIC_PATH"] = str(REPO_ROOT / "src/career_scout_mcp/rubric/current.txt")
        result = subprocess.run(
            [sys.executable, "-m", "career_scout_mcp", "--help"],
            env=env,
            capture_output=True,
            text=True,
            timeout=10,
            cwd=str(REPO_ROOT),
        )
        assert result.returncode == 0
        assert "--transport" in result.stdout
        assert "--auth-token" in result.stdout

    def test_http_without_token_errors(self) -> None:
        env = os.environ.copy()
        env["RUBRIC_PATH"] = str(REPO_ROOT / "src/career_scout_mcp/rubric/current.txt")
        env["MCP_AUTH_TOKEN"] = ""
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "career_scout_mcp",
                "--transport",
                "http",
                "--auth-token",
                "",
            ],
            env=env,
            capture_output=True,
            text=True,
            timeout=15,
            cwd=str(REPO_ROOT),
        )
        assert result.returncode != 0
        combined = (result.stderr + result.stdout).lower()
        assert "auth" in combined or "token" in combined


class TestMainDispatch:
    """In-process tests for main()'s argparse dispatch.

    Subprocess tests above prove the CLI works end-to-end but don't
    contribute to coverage. These in-process tests monkeypatch the
    transport entry points to no-ops and call main() directly, so
    argparse logic in __main__.py is fully covered.
    """

    def test_stdio_dispatch(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import career_scout_mcp.__main__ as m

        calls: list[str] = []
        monkeypatch.setattr(m, "run_stdio", lambda: calls.append("stdio"))
        monkeypatch.setattr(m, "run_http", lambda *a, **kw: calls.append("http"))
        monkeypatch.setattr(sys, "argv", ["career_scout_mcp", "--transport", "stdio"])
        m.main()
        assert calls == ["stdio"]

    def test_http_dispatch_with_token(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import career_scout_mcp.__main__ as m

        captured: list[tuple[str, int, str]] = []

        def _fake_http(host: str, port: int, token: str) -> None:
            captured.append((host, port, token))

        monkeypatch.setattr(m, "run_stdio", lambda: None)
        monkeypatch.setattr(m, "run_http", _fake_http)
        monkeypatch.setattr(
            sys,
            "argv",
            [
                "career_scout_mcp",
                "--transport",
                "http",
                "--auth-token",
                "secret-test-token",
            ],
        )
        m.main()
        assert len(captured) == 1
        assert captured[0][2] == "secret-test-token"

    def test_http_without_token_exits(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import career_scout_mcp.__main__ as m

        monkeypatch.setattr(m, "run_stdio", lambda: None)
        monkeypatch.setattr(m, "run_http", lambda *a, **kw: None)
        monkeypatch.setattr(
            sys,
            "argv",
            [
                "career_scout_mcp",
                "--transport",
                "http",
                "--auth-token",
                "",
            ],
        )
        with pytest.raises(SystemExit):
            m.main()
