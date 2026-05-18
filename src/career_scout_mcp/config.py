"""Application configuration.

All settings load from environment variables, with .env file support for local
development. Settings are validated on startup; misconfigured deploys fail fast
rather than at first request.

Security invariants enforced here:
- MCP_HTTP_BIND must bind to a loopback address; never 0.0.0.0. The MCP server
  is never publicly exposed. Cloudflare Tunnel ingress points exclusively at
  the static docs nginx vhost, never this process.
- MCP_AUTH_TOKEN is required when MCP_TRANSPORT=http. stdio transport is
  unauthenticated by design (transport security delegates to the spawning
  client).
- Empty-string env values are coerced to None for optional secrets, so a
  blank line in .env doesn't masquerade as a real credential.
"""

from __future__ import annotations

import ipaddress
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # LLM routing. LiteLLM resolves provider+protocol from the model string
    # (e.g., "ollama/<name>", "anthropic/<name>", "openai/<name>"). Default is
    # the self-hosted Ollama path; no external API key needed.
    litellm_model: str = Field(default="ollama/qwen2.5:3b")
    ollama_host: str = Field(default="http://127.0.0.1:11434")

    # Optional provider keys. Default Ollama path needs none of these; they
    # exist so a single env-var swap reroutes scoring without code changes.
    anthropic_api_key: str | None = None
    openai_api_key: str | None = None
    deepseek_api_key: str | None = None

    # MCP transport. stdio is the default and only mode that runs as a
    # daemonless subprocess of an MCP client (Claude Desktop, Claude Code,
    # OpenCode). HTTP transport exists for environments that need it but
    # carries its own auth + bind constraints (see validators below).
    mcp_transport: Literal["stdio", "http"] = "stdio"
    mcp_auth_token: str | None = None
    mcp_http_bind: str = Field(default="127.0.0.1:8765")

    # Storage paths. The directory creation is handled in storage/db.py, not
    # here — config is read-only, side-effect-free.
    scout_data_path: Path = Field(default=Path("/var/lib/career-scout-mcp/data"))
    tagged_mismatches_db: Path = Field(
        default=Path("/var/lib/career-scout-mcp/tagged_mismatches.db")
    )
    rubric_path: Path = Field(default=Path("/opt/career-scout-mcp/rubric/current.txt"))
    digest_output_path: Path = Field(default=Path("/var/lib/career-scout-mcp/digests"))

    # Logging. Patterns are matched as substrings against every log line
    # before emission (see logging.py). Comma-separated in env, list here.
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    log_redact_patterns: list[str] = Field(
        default_factory=lambda: [
            "sk-",
            "AKIA",
            "ghp_",
            "xoxb-",
            "xoxp-",
            "glpat-",
            "cf_",
            "eyJ",
        ]
    )

    @field_validator(
        "mcp_auth_token",
        "anthropic_api_key",
        "openai_api_key",
        "deepseek_api_key",
        mode="before",
    )
    @classmethod
    def _empty_str_to_none(cls, v: object) -> object:
        # An empty value in .env (e.g. `OPENAI_API_KEY=`) should be treated as
        # absent, not as the literal empty string. Without this, the http
        # validator below would accept "" as a valid auth token.
        if isinstance(v, str) and not v.strip():
            return None
        return v

    @field_validator("log_redact_patterns", mode="before")
    @classmethod
    def _split_redact_patterns(cls, v: object) -> object:
        # Allow .env comma-separated form ("sk-,AKIA,..."). Lists pass through.
        if isinstance(v, str):
            return [p.strip() for p in v.split(",") if p.strip()]
        return v

    @field_validator("mcp_http_bind")
    @classmethod
    def _bind_must_be_loopback(cls, v: str) -> str:
        # Hard security guardrail: the MCP HTTP transport may only ever
        # listen on a loopback interface. Cloudflare Tunnel ingress in this
        # deployment targets nginx:80 for static docs, never this server.
        # If anyone later "improves" the deploy by exposing this on
        # 0.0.0.0, validation here fails closed at startup.
        host, _, port = v.rpartition(":")
        host = host.strip("[]")  # strip IPv6 brackets if present
        if not host or not port:
            raise ValueError(f"MCP_HTTP_BIND must be host:port, got {v!r}")
        try:
            addr = ipaddress.ip_address(host)
        except ValueError as e:
            raise ValueError(f"MCP_HTTP_BIND host must be an IP literal: {e}") from e
        if not addr.is_loopback:
            raise ValueError(
                f"MCP_HTTP_BIND must be loopback (127.x.x.x or ::1); got {host}. "
                "The MCP server is never publicly bound."
            )
        return v

    @model_validator(mode="after")
    def _http_requires_auth_token(self) -> Settings:
        # Fail fast on misconfigured http deploys rather than serving
        # unauthenticated traffic on first request.
        if self.mcp_transport == "http" and not self.mcp_auth_token:
            raise ValueError("MCP_AUTH_TOKEN is required when MCP_TRANSPORT=http")
        return self


# Module-level singleton. Importing this module triggers validation; a
# misconfigured deploy raises ValidationError at import time, before any
# server work begins. Tests construct Settings(_env_file=None, ...) directly.
settings = Settings()
