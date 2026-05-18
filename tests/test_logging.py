"""Tests for logging.py — JSON output + secret redaction."""

from __future__ import annotations

import json
from typing import Any

import pytest
from loguru import logger


@pytest.fixture(autouse=True)
def _reset_loguru() -> Any:
    """Remove any prior sinks so each test sees clean loguru state."""
    logger.remove()
    yield
    logger.remove()


class TestRedaction:
    def test_sk_keys_redacted(self, capsys: pytest.CaptureFixture[str]) -> None:
        from career_scout_mcp.logging import configure_logging

        configure_logging()
        logger.info("payload contains sk-abc123XYZsecret value")
        captured = capsys.readouterr().err
        assert "sk-abc123XYZsecret" not in captured

    def test_jwt_eyj_redacted(self, capsys: pytest.CaptureFixture[str]) -> None:
        from career_scout_mcp.logging import configure_logging

        configure_logging()
        logger.info("token: eyJhbGciOiJIUzI1NiJ9.test.sig")
        captured = capsys.readouterr().err
        assert "eyJhbGciOiJIUzI1NiJ9" not in captured

    def test_safe_text_passes_through(self, capsys: pytest.CaptureFixture[str]) -> None:
        from career_scout_mcp.logging import configure_logging

        configure_logging()
        logger.info("the sky is blue")
        captured = capsys.readouterr().err
        assert "the sky is blue" in captured


class TestJsonOutput:
    def test_output_is_parseable_json(self, capsys: pytest.CaptureFixture[str]) -> None:
        from career_scout_mcp.logging import configure_logging

        configure_logging()
        logger.info("event_one")
        captured = capsys.readouterr().err
        for line in captured.strip().splitlines():
            if line:
                obj = json.loads(line)  # raises if not JSON
                assert isinstance(obj, dict)
