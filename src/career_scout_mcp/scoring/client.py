"""LLM scoring client wrapping LiteLLM SDK.

Default model is ollama/qwen2.5:3b (self-hosted, CPU-only). Provider swap
is one env-var change with no code change: anthropic/claude-3-5-sonnet,
openai/gpt-4o, deepseek/deepseek-reasoner, etc.

Design choices defended:

- LiteLLM SDK, not LiteLLM Proxy. Single-user MCP server doesn't need the
  Proxy's token-pool / rate-limit / model-routing surface. The SDK gives
  provider-agnostic acompletion() with env-driven swap — exactly the
  abstraction value claim, without running another service.

- JSON extraction is forgiving. The rubric asks for strict JSON, but
  small open-weight models (Qwen 2.5 3B) occasionally wrap output in
  markdown fences or emit preamble. We isolate the first {...} block
  before parsing. The structured pydantic validation downstream is the
  real correctness gate, not the model's prompt-following discipline.

- Timeout 300s. CPU-only Qwen on i7-9700K runs ~10-18 tok/s; a typical
  1-2K-token generation lands at 60-200s. 300s gives margin for cold
  model loads and longer rationales without false timeouts.

- temperature=0.0. Scoring should be reproducible; runs with the same
  posting + rubric should yield the same score (modulo model rounding).
  Determinism matters for both testing and audit.

- All failures collapse to ScoringError. Callers (tools.py) don't need
  to understand LiteLLM's exception hierarchy or JSON parsing modes.
"""

from __future__ import annotations

import json
from typing import Literal

import litellm
from loguru import logger
from pydantic import BaseModel, Field, ValidationError

from career_scout_mcp.config import settings
from career_scout_mcp.scoring.rubric import Rubric
from career_scout_mcp.storage.queries import Posting


class ScoringError(Exception):
    """Raised when scoring fails — network, parsing, schema, or validation."""


class ScoreResult(BaseModel):
    """LLM-produced scoring result. Distinct from the DB Score row."""

    score: int = Field(ge=0, le=100)
    score_band: Literal["high", "mid", "low"]
    rationale: str
    model: str
    rubric_version: str


def _format_posting_for_prompt(p: Posting) -> str:
    """Render a posting into a clean text block for the LLM user-message."""
    lines = [
        f"Title: {p.title}",
        f"Company: {p.company}",
        f"Location: {p.location or 'not specified'}",
        f"Posted: {p.posted_date}",
        f"Role anchor: {p.role_anchor}",
        "",
        "Description:",
        p.description,
    ]
    return "\n".join(lines)


def _extract_json_block(text: str) -> str:
    """Locate the first {...} JSON object in a possibly-noisy LLM response.

    Small models sometimes wrap output in markdown fences or add a preamble
    despite the rubric's strict-JSON instruction. We isolate the first
    top-level object by scanning for outer braces rather than relying on
    model discipline.
    """
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise ScoringError(f"no JSON object in model response: {text!r}")
    return text[start : end + 1]


async def score_posting(
    posting: Posting,
    rubric: Rubric,
    model: str | None = None,
) -> ScoreResult:
    """Score one posting against the rubric via LiteLLM.

    Returns a structured ScoreResult. Raises ScoringError on any failure
    (network unreachable, malformed model output, schema mismatch).
    Callers decide retry vs surface.
    """
    chosen_model = model or settings.litellm_model
    log = logger.bind(
        posting_id=posting.id,
        model=chosen_model,
        rubric_version=rubric.version,
    )

    messages = [
        {"role": "system", "content": rubric.text},
        {"role": "user", "content": _format_posting_for_prompt(posting)},
    ]

    # Explicit api_base for ollama/ models. LiteLLM can auto-detect from
    # OLLAMA_HOST env, but passing it directly removes a layer of magic
    # and makes the routing obvious in the call site.
    api_base: str | None = (
        settings.ollama_host if chosen_model.startswith("ollama/") else None
    )

    log.info("scoring start")
    try:
        response = await litellm.acompletion(
            model=chosen_model,
            messages=messages,
            api_base=api_base,
            timeout=300,
            temperature=0.0,
        )
    except Exception as e:
        log.bind(error=str(e)).error("litellm call failed")
        raise ScoringError(f"LLM call failed: {e}") from e

    # Extract content from the OpenAI-compatible response shape LiteLLM
    # normalizes to. Defensive against any LiteLLM API drift.
    try:
        raw_text = response.choices[0].message.content
        if not isinstance(raw_text, str):
            raise ScoringError(f"response content not str: {type(raw_text).__name__}")
    except (AttributeError, IndexError, KeyError) as e:
        raise ScoringError(f"unexpected response shape: {e}") from e

    # Parse + schema-validate
    json_block = _extract_json_block(raw_text)
    try:
        parsed = json.loads(json_block)
    except json.JSONDecodeError as e:
        log.bind(raw=raw_text[:500]).error("JSON parse failed")
        raise ScoringError(f"invalid JSON in response: {e}") from e

    if not isinstance(parsed, dict):
        raise ScoringError(f"JSON root not object: {type(parsed).__name__}")

    try:
        result = ScoreResult(
            score=parsed["score"],
            score_band=parsed["score_band"],
            rationale=parsed["rationale"],
            model=chosen_model,
            rubric_version=rubric.version,
        )
    except (KeyError, ValidationError) as e:
        log.bind(parsed=parsed).error("schema validation failed")
        raise ScoringError(f"response schema mismatch: {e}") from e

    log.bind(score=result.score, score_band=result.score_band).info("scoring complete")
    return result
