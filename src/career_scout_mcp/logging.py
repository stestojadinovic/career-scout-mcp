"""Structured JSON logging with regex-based secret redaction.

Every log line is serialized to JSON and passed through a redaction filter
before emission. The patterns to redact load from settings.log_redact_patterns
at module import; updates require a process restart (correct for systemd
deployment).

Security and correctness choices defended here:

- diagnose=False. Loguru's "better tracebacks" feature (diagnose=True) renders
  local variable values inside exception stack frames. Developer convenience
  becomes a credential-leak vector in production: any function holding a
  secret as a local at exception time would leak it via the traceback.
  Forbidden.

- Output to stderr, not stdout. MCP stdio transport reserves stdout for
  JSON-RPC protocol bytes; any non-protocol byte on stdout corrupts the
  stream and breaks the client. systemd captures stdout and stderr into the
  same journal, so operational visibility is preserved.

- Synchronous emission (enqueue=False). MCP traffic is low-volume
  request-response; an async log queue's overhead exceeds its benefit and
  complicates clean shutdown semantics.

- Redaction is substring-based with non-whitespace continuation. For
  credential-shaped tokens (sk-..., eyJ..., AKIA...) this catches the full
  token at minimal regex cost. False positives on prefix collisions are
  tolerated; the threat model favors over-redacting over leaking.

- Redaction runs on the fully serialized JSON, not just the message field.
  This covers logger.bind() extras, exception strings, and any nested
  payload, anywhere a caller might inadvertently route a secret.
"""

from __future__ import annotations

import json
import re
import sys
from typing import Any

from loguru import logger

from career_scout_mcp.config import settings


def _compile_redact_regexes(
    patterns: list[str],
) -> list[tuple[re.Pattern[str], str]]:
    """Compile each prefix pattern into a regex matching prefix + token tail.

    The tail character class matches characters that appear in JWTs, API
    keys, base64, and URL-safe credentials. Whitespace and JSON quotes are
    deliberately excluded so the redaction stops at field boundaries.
    """
    return [
        (
            re.compile(rf"({re.escape(p)})[A-Za-z0-9_\-./+=:]*"),
            r"\1<REDACTED>",
        )
        for p in patterns
    ]


# Compiled once at import time; the pattern list is static for the process
# lifetime by design (config.Settings is read-only).
_REDACT_REGEXES = _compile_redact_regexes(settings.log_redact_patterns)


def _redact(text: str) -> str:
    """Apply all configured redaction regexes to a string."""
    for regex, replacement in _REDACT_REGEXES:
        text = regex.sub(replacement, text)
    return text


def _serialize(record: dict[str, Any]) -> str:
    """Serialize a loguru record to a single redacted JSON line."""
    payload: dict[str, Any] = {
        "ts": record["time"].isoformat(),
        "level": record["level"].name,
        "logger": record["name"],
        "function": record["function"],
        "line": record["line"],
        "message": record["message"],
    }
    if record["extra"]:
        payload["extra"] = record["extra"]
    if record["exception"] is not None:
        # str(exception) gives "ExceptionClass: message"; we deliberately
        # avoid reaching into traceback frame objects, which can hold local
        # variable references that escape our redaction surface.
        payload["exception"] = str(record["exception"])
    raw = json.dumps(payload, default=str, ensure_ascii=False)
    return _redact(raw)


def _sink(message: Any) -> None:
    """Loguru sink: emit serialized + redacted JSON line to stderr."""
    sys.stderr.write(_serialize(message.record) + "\n")
    sys.stderr.flush()


def configure_logging() -> None:
    """Configure loguru for production. Safe to call multiple times.

    Removes loguru's default human-readable handler and installs the
    redacting JSON sink. Idempotent.
    """
    logger.remove()
    logger.add(
        _sink,
        level=settings.log_level,
        backtrace=True,
        diagnose=False,  # NEVER True — leaks local variable values via tracebacks
        enqueue=False,
        catch=True,
    )
