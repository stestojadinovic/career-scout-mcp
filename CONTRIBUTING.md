# Contributing

Thanks for your interest in Career Scout MCP. This is a personal
portfolio project demonstrating production MCP server patterns, so
contributions are evaluated against the project's narrow scope.

## Development Setup

Requires Python 3.13 and [uv](https://docs.astral.sh/uv/).

```bash
git clone https://github.com/stestojadinovic/career-scout-mcp
cd career-scout-mcp
uv sync
uv run pre-commit install
```

## Running Tests

```bash
uv run pytest tests/ -v --cov=career_scout_mcp
```

Full suite runs in under a minute. Coverage gate: **85%**.

## Code Style

- `ruff format` for formatting (enforced by pre-commit and CI)
- `ruff check` for linting (enforced)
- `mypy --strict` for type checking (enforced in CI)
- Public functions have docstrings explaining **design choices**, not
  just behavior

## Pull Requests

1. Open an issue first for non-trivial changes — saves time on both
   sides.
2. One logical change per PR.
3. Tests for new functionality. New code should not lower coverage
   below 85%.
4. Pre-commit hooks must pass.
5. CI must be green before merge (ruff, mypy, pytest, gitleaks, CodeQL).

## Out of Scope

This is intentionally a single-user, single-purpose MCP server
demonstrating production patterns. The following are explicitly out of
scope:

- Multi-user support, OAuth, RBAC
- Distributed deployment, clustering, replication
- Database backends other than SQLite
- Web UI (the static `docs/` site is the only browser surface)

The real Career Scout pipeline (private) lives elsewhere; see the
project README's note for context.
