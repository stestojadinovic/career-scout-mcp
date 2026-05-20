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

## Prerequisites

- Python 3.13 (uv manages this automatically)
- [uv](https://docs.astral.sh/uv/) — dependency and environment management
- [Ollama](https://ollama.com/) — default local LLM provider for `qwen2.5:3b`

### Debian 13

    curl -LsSf https://astral.sh/uv/install.sh | sh
    curl -fsSL https://ollama.com/install.sh | sh
    ollama pull qwen2.5:3b

### macOS

    brew install uv ollama
    ollama serve &
    ollama pull qwen2.5:3b

### Windows

[uv installer](https://docs.astral.sh/uv/getting-started/installation/) · [Ollama installer](https://ollama.com/download/windows), then `ollama pull qwen2.5:3b`.

## Quick start (local stdio)

```bash
uv sync
uv run python -m career_scout_mcp
```

The server exposes 4 tools, 5 resources (6 URIs), and 2 prompts via stdio. Connect from Claude Desktop, Claude Code, or OpenCode by pointing them at this binary.

### Try it out

The fastest way to exercise the server is via [MCP Inspector](https://github.com/modelcontextprotocol/inspector):

    npx @modelcontextprotocol/inspector uv run python -m career_scout_mcp

Opens a browser UI at `localhost:6274` where you can list resources, render prompts, and invoke tools end-to-end against your local Ollama.

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
- Docs deploy via manual `scripts/deploy_docs.sh`. MCP server is never publicly exposed — stdio default; HTTP transport loopback-only behind Bearer auth (`hmac.compare_digest`).

## License

MIT — see [LICENSE](LICENSE).

---

Built by Stefan Stojadinovic, Vienna. Contact: stefan@stojadinovic.at
