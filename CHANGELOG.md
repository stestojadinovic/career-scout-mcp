# Changelog

All notable changes to this project will be documented here. Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.0] — 2026-05-18

### Added
- Initial release.
- MCP server with 4 tools (rescore_posting, tag_mismatched_score, query_postings, regenerate_digest).
- 5 resources (digest/current, scores/history, rubric/current, config/scrapers, stats/summary).
- 2 user-invoked prompts (tune_rubric, analyze_digest_trends).
- LiteLLM SDK routing with Ollama/Qwen 2.5 3B default; provider-swappable via `LITELLM_MODEL` env.
- Structured JSON logging with regex-based secret redaction.
- Health endpoint reporting version, git SHA, uptime, Ollama + sqlite reachability.
- Synthetic dataset (30-50 fictional postings) committed for portability.
- Documentation page at career-scout-mcp.stojadinovic.at, fronted by Cloudflare Tunnel + edge TLS.
- Full CI: ruff, mypy --strict, pytest with >85% coverage, pip-audit, gitleaks, CodeQL.

[Unreleased]: https://github.com/stestojadinovic/career-scout-mcp/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/stestojadinovic/career-scout-mcp/releases/tag/v0.1.0
