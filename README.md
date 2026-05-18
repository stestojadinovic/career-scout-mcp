# career-scout-mcp

[![CI](https://github.com/stestojadinovic/career-scout-mcp/actions/workflows/ci.yml/badge.svg)](https://github.com/stestojadinovic/career-scout-mcp/actions/workflows/ci.yml)
[![CodeQL](https://github.com/stestojadinovic/career-scout-mcp/actions/workflows/codeql.yml/badge.svg)](https://github.com/stestojadinovic/career-scout-mcp/actions/workflows/codeql.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.13](https://img.shields.io/badge/python-3.13-blue.svg)](https://www.python.org/)
[![Debian](https://img.shields.io/badge/Debian-13%20(trixie)-A81D33?logo=debian&logoColor=white)](https://www.debian.org/)

A production-grade Model Context Protocol (MCP) server demonstrating the wrapping pattern for AI-augmented data pipelines. Built as a standalone artifact: one LXC container, one Cloudflare Tunnel, one repo. Self-hosted via Ollama + LiteLLM SDK.

This server demonstrates the pattern I would apply to wrap Career Scout — my private job-search scoring pipeline. Synthetic data committed here for portability and reproducibility.

## Documentation

Full architecture and design decisions: **[career-scout-mcp.stojadinovic.at](https://career-scout-mcp.stojadinovic.at)**

## Stack

- **Python 3.13** (mypy strict)
- **MCP SDK** with decorator-based primitive registration
- **LiteLLM SDK** — provider-agnostic LLM routing, model-swappable via env
- **Ollama + Qwen 2.5 3B** (default) — self-hosted, biomedical-research-portable
- **Pydantic** for config + tool schemas
- **loguru** structured JSON logging with secret redaction
- **Debian 13** LXC, **cloudflared** edge termination, **nginx** static docs

## Quick start (local stdio)

```bash
uv sync
uv run python -m career_scout_mcp
```

The server exposes 4 tools, 5 resources, and 2 prompts via stdio. Connect from Claude Desktop, Claude Code, or OpenCode by pointing them at this binary.

## Development

Dev workflow uses **OpenCode** + standard Python tooling. See [CONTRIBUTING.md](CONTRIBUTING.md).

## Security

See [SECURITY.md](SECURITY.md) for reporting. Key posture:

- All SQL parameterized (never f-string)
- Pydantic input validation on every tool entry
- Path traversal prevention on resource URIs
- systemd hardening (non-root, ProtectSystem=strict, etc.)
- MCP server NEVER publicly exposed (stdio default, HTTP bound 127.0.0.1 only)
- TLS via Cloudflare edge — no local cert management surface
- Self-hosted GHA runner restricted to tag-push events; PR workflows use GitHub-hosted runners

## License

MIT — see [LICENSE](LICENSE).

---

Built by Stefan Stojadinovic, Vienna. Contact: stefan@stojadinovic.at
