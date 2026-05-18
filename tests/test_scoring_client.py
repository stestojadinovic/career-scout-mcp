"""Tests for scoring/client.py with LiteLLM mocked.

Real Ollama calls live in test_integration.py / test_e2e.py. This file
tests parsing, validation, and error-handling paths deterministically
via AsyncMock-patched litellm.acompletion.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from career_scout_mcp.scoring.client import (
    ScoreResult,
    ScoringError,
    _extract_json_block,
    score_posting,
)
from career_scout_mcp.scoring.rubric import Rubric
from career_scout_mcp.storage.queries import Posting


def _make_posting() -> Posting:
    return Posting(
        id="p-test",
        title="Test Role",
        company="TestCo",
        location="Vienna",
        posted_date="2026-05-15",
        description="Test description",
        raw_url="https://x.test/p-test",
        role_anchor="ai_engineer",
    )


def _make_rubric() -> Rubric:
    return Rubric(
        version="v1.0",
        text="Test rubric content",
        path="/tmp/rubric.txt",
    )


def _make_mock_response(content: str) -> MagicMock:
    """Build a MagicMock matching LiteLLM ModelResponse shape."""
    response = MagicMock()
    response.choices = [MagicMock()]
    response.choices[0].message = MagicMock()
    response.choices[0].message.content = content
    return response


class TestExtractJsonBlock:
    def test_plain_json(self) -> None:
        s = '{"score": 80, "score_band": "high", "rationale": "fit"}'
        assert _extract_json_block(s) == s

    def test_markdown_fenced(self) -> None:
        result = _extract_json_block('```json\n{"score": 80}\n```')
        assert result == '{"score": 80}'

    def test_with_preamble_and_postamble(self) -> None:
        result = _extract_json_block('Here is the result:\n{"score": 50}\nThank you.')
        assert result == '{"score": 50}'

    def test_nested_object(self) -> None:
        result = _extract_json_block('prefix {"a":1, "b":{"c":2}} suffix')
        assert result == '{"a":1, "b":{"c":2}}'

    def test_no_json_raises(self) -> None:
        with pytest.raises(ScoringError):
            _extract_json_block("no braces at all")


class TestScorePosting:
    async def test_happy_path(self, monkeypatch: pytest.MonkeyPatch) -> None:
        mock = AsyncMock(
            return_value=_make_mock_response(
                '{"score": 82, "score_band": "high", '
                '"rationale": "strong AI role match"}'
            )
        )
        monkeypatch.setattr("litellm.acompletion", mock)
        result = await score_posting(_make_posting(), _make_rubric())
        assert isinstance(result, ScoreResult)
        assert result.score == 82
        assert result.score_band == "high"
        assert result.rationale == "strong AI role match"
        assert result.model == "ollama/qwen2.5:3b"
        assert result.rubric_version == "v1.0"

    async def test_response_with_markdown_fences(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        mock = AsyncMock(
            return_value=_make_mock_response(
                '```json\n{"score": 70, "score_band": "high", "rationale": "good"}\n```'
            )
        )
        monkeypatch.setattr("litellm.acompletion", mock)
        result = await score_posting(_make_posting(), _make_rubric())
        assert result.score == 70

    async def test_malformed_json_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        mock = AsyncMock(
            return_value=_make_mock_response('{"score": 80, "score_band":}')
        )
        monkeypatch.setattr("litellm.acompletion", mock)
        with pytest.raises(ScoringError, match="invalid JSON"):
            await score_posting(_make_posting(), _make_rubric())

    async def test_no_json_in_response_raises(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        mock = AsyncMock(return_value=_make_mock_response("just plain text, no JSON"))
        monkeypatch.setattr("litellm.acompletion", mock)
        with pytest.raises(ScoringError, match="no JSON object"):
            await score_posting(_make_posting(), _make_rubric())

    async def test_missing_required_field_raises(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        mock = AsyncMock(return_value=_make_mock_response('{"score": 80}'))
        monkeypatch.setattr("litellm.acompletion", mock)
        with pytest.raises(ScoringError, match="schema"):
            await score_posting(_make_posting(), _make_rubric())

    async def test_score_out_of_range_raises(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        mock = AsyncMock(
            return_value=_make_mock_response(
                '{"score": 150, "score_band": "high", "rationale": "x"}'
            )
        )
        monkeypatch.setattr("litellm.acompletion", mock)
        with pytest.raises(ScoringError, match="schema"):
            await score_posting(_make_posting(), _make_rubric())

    async def test_invalid_score_band_raises(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        mock = AsyncMock(
            return_value=_make_mock_response(
                '{"score": 80, "score_band": "exceptional", "rationale": "x"}'
            )
        )
        monkeypatch.setattr("litellm.acompletion", mock)
        with pytest.raises(ScoringError, match="schema"):
            await score_posting(_make_posting(), _make_rubric())

    async def test_litellm_exception_wrapped(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        mock = AsyncMock(side_effect=RuntimeError("connection refused"))
        monkeypatch.setattr("litellm.acompletion", mock)
        with pytest.raises(ScoringError, match="LLM call failed"):
            await score_posting(_make_posting(), _make_rubric())

    async def test_response_content_not_string_raises(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Defensive check: content not str surfaces clean error."""
        response = MagicMock()
        response.choices = [MagicMock()]
        response.choices[0].message = MagicMock()
        response.choices[0].message.content = {"unexpected": "dict"}
        mock = AsyncMock(return_value=response)
        monkeypatch.setattr("litellm.acompletion", mock)
        with pytest.raises(ScoringError):
            await score_posting(_make_posting(), _make_rubric())

    async def test_model_override(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Caller-provided model overrides settings.litellm_model."""
        mock = AsyncMock(
            return_value=_make_mock_response(
                '{"score": 80, "score_band": "high", "rationale": "x"}'
            )
        )
        monkeypatch.setattr("litellm.acompletion", mock)
        result = await score_posting(
            _make_posting(),
            _make_rubric(),
            model="anthropic/claude-3-5-sonnet",
        )
        assert result.model == "anthropic/claude-3-5-sonnet"
        call_kwargs = mock.call_args.kwargs
        assert call_kwargs["model"] == "anthropic/claude-3-5-sonnet"
        # api_base should be None for non-ollama
        assert call_kwargs["api_base"] is None

    async def test_api_base_passed_for_ollama(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """ollama/ models get explicit api_base from settings."""
        mock = AsyncMock(
            return_value=_make_mock_response(
                '{"score": 80, "score_band": "high", "rationale": "x"}'
            )
        )
        monkeypatch.setattr("litellm.acompletion", mock)
        await score_posting(_make_posting(), _make_rubric())
        call_kwargs = mock.call_args.kwargs
        assert call_kwargs["model"] == "ollama/qwen2.5:3b"
        from career_scout_mcp.config import settings

        assert call_kwargs["api_base"] == settings.ollama_host
