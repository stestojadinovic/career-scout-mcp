"""Tests for the Settings layer in config.py.

The conftest already sets canonical env defaults at import time. These
tests construct fresh Settings instances directly (bypassing the
module-level singleton) to exercise the validators in isolation. Where a
test needs an env-var that the singleton has already captured, it
patches the relevant key with monkeypatch and reconstructs Settings.
"""

from __future__ import annotations

import pytest

from career_scout_mcp.config import Settings


def test_log_redact_patterns_csv_string_parses_to_list(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """CSV form ("sk-,AKIA,...") becomes a stripped list of patterns."""
    monkeypatch.setenv("LOG_REDACT_PATTERNS", "sk-,AKIA, ghp_ ,xoxb-")
    s = Settings(_env_file=None)  # type: ignore[call-arg]
    assert s.log_redact_patterns == ["sk-", "AKIA", "ghp_", "xoxb-"]


def test_log_redact_patterns_json_string_parses_to_list(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """JSON-encoded list form is delegated to pydantic-settings' decoder."""
    monkeypatch.setenv("LOG_REDACT_PATTERNS", '["sk-","AKIA","ghp_"]')
    s = Settings(_env_file=None)  # type: ignore[call-arg]
    assert s.log_redact_patterns == ["sk-", "AKIA", "ghp_"]


def test_log_redact_patterns_empty_csv_yields_empty_list(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """CSV with only separators yields empty list, not [''] singletons."""
    monkeypatch.setenv("LOG_REDACT_PATTERNS", " , , ")
    s = Settings(_env_file=None)  # type: ignore[call-arg]
    assert s.log_redact_patterns == []


def test_log_redact_patterns_default_when_unset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Unset env var falls through to the default factory list."""
    monkeypatch.delenv("LOG_REDACT_PATTERNS", raising=False)
    s = Settings(_env_file=None)  # type: ignore[call-arg]
    assert "sk-" in s.log_redact_patterns
    assert "eyJ" in s.log_redact_patterns
