"""Tests for scoring/rubric.py."""

from __future__ import annotations

from pathlib import Path

import pytest

from career_scout_mcp.scoring.rubric import (
    Rubric,
    _extract_version,
    load_current_rubric,
)


class TestExtractVersion:
    def test_standard_version(self) -> None:
        assert _extract_version("# Career Scout Rubric v1.0\nbody") == "v1.0"

    def test_multi_dot_version(self) -> None:
        assert _extract_version("# Rubric v2.3.1") == "v2.3.1"

    def test_leading_blanks_skipped(self) -> None:
        assert _extract_version("\n\n# Title v5\n") == "v5"

    def test_first_line_no_version(self) -> None:
        """Pattern lookup stops at first non-empty line."""
        result = _extract_version("# No version here\nv0.1 in body")
        assert result == "unversioned"

    def test_empty_text(self) -> None:
        assert _extract_version("") == "unversioned"

    def test_text_with_no_version(self) -> None:
        assert _extract_version("just text, no version") == "unversioned"


class TestLoadCurrentRubric:
    def test_loads_real_rubric(self, test_env: None) -> None:
        rubric = load_current_rubric()
        assert isinstance(rubric, Rubric)
        assert rubric.version == "v1.0"
        assert "Career Scout Rubric" in rubric.text

    def test_raises_on_missing_file(self, test_env: None, tmp_path: Path) -> None:
        from career_scout_mcp.config import settings

        # Local save/restore — test_env fixture doesn't manage rubric_path.
        saved = settings.rubric_path
        try:
            settings.rubric_path = tmp_path / "nonexistent.txt"
            with pytest.raises(FileNotFoundError):
                load_current_rubric()
        finally:
            settings.rubric_path = saved
