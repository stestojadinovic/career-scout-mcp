# syntax=docker/dockerfile:1.7
# Career Scout MCP — production container image
# Default: stdio transport (MCP-native usage pattern).
# For HTTP transport, override CMD with --transport http and pass an auth token.

FROM python:3.13-slim-bookworm

LABEL org.opencontainers.image.source="https://github.com/stestojadinovic/career-scout-mcp"
LABEL org.opencontainers.image.description="Production-grade MCP server demonstrating LLM scoring with provider abstraction"
LABEL org.opencontainers.image.licenses="MIT"

# Install uv from official image
COPY --from=ghcr.io/astral-sh/uv:0.5.0 /uv /usr/local/bin/uv

WORKDIR /opt/career-scout-mcp

# Dependency layer (changes rarely)
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# Source layer (changes more often)
COPY src/ ./src/
RUN uv sync --frozen --no-dev

# Non-root user
RUN groupadd -r -g 1100 mcp \
 && useradd -r -u 1100 -g mcp -s /usr/sbin/nologin -d /nonexistent mcp

# Runtime data dir (mountable)
RUN mkdir -p /var/lib/career-scout-mcp \
 && chown -R mcp:mcp /var/lib/career-scout-mcp /opt/career-scout-mcp

VOLUME ["/var/lib/career-scout-mcp"]

USER mcp

ENV PYTHONUNBUFFERED=1 \
    SCOUT_DATA_PATH=/var/lib/career-scout-mcp/scout-data \
    TAGGED_MISMATCHES_DB=/var/lib/career-scout-mcp/tagged.db \
    DIGEST_OUTPUT_PATH=/var/lib/career-scout-mcp/digests \
    RUBRIC_PATH=/opt/career-scout-mcp/src/career_scout_mcp/rubric/current.txt

CMD ["/opt/career-scout-mcp/.venv/bin/python", "-m", "career_scout_mcp", "--transport", "stdio"]
