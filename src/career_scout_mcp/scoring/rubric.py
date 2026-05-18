"""Rubric loader: reads versioned scoring text from disk.

The rubric is the prompt template the scoring client sends to the LLM
along with each posting. It carries a version stamp so scores can be
traced back to the exact rubric that produced them — which matters for:

- The tune_rubric prompt's "compare recent mismatches against current
  rubric" workflow.
- Auditing scoring drift across rubric revisions via the
  scores.rubric_version column populated by insert_score().

Version extraction:

- The first non-empty line is scanned for a "vN.M" pattern (one or more
  digits, optionally with dot-separated minor segments). If found, that
  becomes the version string ("v1.0", "v2.3.1", etc.).
- If the first non-empty line has no such pattern, version falls back
  to "unversioned". This is a soft fail: scoring still works, but the
  audit trail loses lineage. A warning belongs in operator dashboards,
  not in this module.

The file is re-read on every load_current_rubric() call. The OS file
cache makes this cheap; no in-memory caching to avoid stale-state bugs
during development where the rubric may be edited live.
"""

from __future__ import annotations

import re
from pathlib import Path

from pydantic import BaseModel

from career_scout_mcp.config import settings


_VERSION_PATTERN = re.compile(r"v(\d+(?:\.\d+)*)")


class Rubric(BaseModel):
    """Loaded rubric content with extracted version + source path."""

    version: str
    text: str
    path: str


def _extract_version(text: str) -> str:
    """Parse a vX.Y stamp from the rubric's first non-empty line."""
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        match = _VERSION_PATTERN.search(stripped)
        if match:
            return f"v{match.group(1)}"
        # First non-empty line found but no version pattern — done.
        break
    return "unversioned"


def load_current_rubric() -> Rubric:
    """Load the current rubric from settings.rubric_path.

    Raises FileNotFoundError if the file is missing — server startup
    should surface this as a deployment misconfiguration rather than
    silently substitute a stub rubric.
    """
    path = Path(settings.rubric_path)
    text = path.read_text(encoding="utf-8")
    return Rubric(
        version=_extract_version(text),
        text=text,
        path=str(path),
    )
