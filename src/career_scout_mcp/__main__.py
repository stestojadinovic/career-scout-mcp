"""CLI entry point: python -m career_scout_mcp."""

from __future__ import annotations

import argparse

from career_scout_mcp.config import settings
from career_scout_mcp.server import run_http, run_stdio


def main() -> None:
    # config.py models the HTTP bind as a single loopback-validated
    # "host:port" string (settings.mcp_http_bind). Split it the same way
    # config.py's loopback validator does so the CLI defaults stay
    # consistent with the validated config; there is intentionally no
    # separate mcp_http_port field.
    _host, _, _port = settings.mcp_http_bind.rpartition(":")

    parser = argparse.ArgumentParser(
        prog="career_scout_mcp",
        description="Career Scout MCP server",
    )
    parser.add_argument(
        "--transport",
        choices=["stdio", "http"],
        default=settings.mcp_transport,
        help="MCP transport (default from MCP_TRANSPORT env)",
    )
    parser.add_argument(
        "--host",
        default=_host,
        help="HTTP bind address (loopback enforced by config)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(_port),
        help="HTTP bind port",
    )
    parser.add_argument(
        "--auth-token",
        default=settings.mcp_auth_token,
        help="Bearer token for HTTP auth (required for HTTP transport)",
    )
    args = parser.parse_args()

    if args.transport == "stdio":
        run_stdio()
    else:
        if not args.auth_token:
            parser.error(
                "--auth-token is required for HTTP transport "
                "(or set MCP_AUTH_TOKEN env)"
            )
        run_http(args.host, args.port, args.auth_token)


if __name__ == "__main__":
    main()
