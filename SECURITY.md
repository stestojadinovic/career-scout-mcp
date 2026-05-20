# Security Policy

## Supported Versions

This is a portfolio / demonstration project. Only the latest release
receives security fixes.

| Version | Supported |
| ------- | --------- |
| 0.1.x   | ✓         |
| < 0.1   | ✗         |

## Reporting a Vulnerability

Please report security issues **privately** by emailing
**security@stojadinovic.at** rather than opening a public issue.

Include:

- Type of issue (e.g., injection, authentication bypass, info disclosure)
- File / line affected, or the affected primitive (tool, resource, prompt)
- Reproduction steps or proof-of-concept
- Impact assessment

You should receive an acknowledgment within 48 hours. Confirmed issues
will be fixed and credit given (unless you prefer anonymity).

## Security Model

The Career Scout MCP server is designed around the following invariants.

### Transport Boundaries

- **stdio (default)** — process-local; no network surface.
- **HTTP (opt-in)** — bound to loopback (`127.0.0.1`) only; Bearer-token
  authenticated via custom Starlette middleware. Public exposure
  requires an external reverse proxy under the operator's control.

The loopback restriction is enforced by the config layer at server
startup (`mcp_http_bind` validator); the Bearer middleware enforces it
in-flight. Two independent layers because operational misconfiguration
happens.

### Input Validation

- All SQL is parameterized; no string interpolation in queries.
- Allowlist enforcement for `sort_column` and `sort_direction` — the
  only fields that cannot be parameterized (column/keyword identifiers).
- Numeric range validation on `limit`, `score`, and `min_score` at the
  query boundary.
- Non-empty enforcement on operator-provided rationale / reason strings.

Adversarial input tests live in `tests/test_security.py`.

### Secret Handling

- No secrets in source. `.env` is `.gitignore`d.
- Production environment file (`/etc/career-scout-mcp/env`) mode `0640`,
  owner `root:mcp`. Application user (`mcp`) reads only.
- Logging redacts known token shapes before serialization:
  `sk-`, `AKIA`, `ghp_`, `xoxb-`, `xoxp-`, `glpat-`, `cf_`, `eyJ`.

### Threat Model

A full threat model with trust boundaries diagram lives in the project
documentation at
<https://career-scout-mcp.stojadinovic.at/architecture.html#threat-model>.

## Known issues

### CVE-2025-45768 — PyJWT weak key length enforcement

pip-audit flags `pyjwt 2.12.1` with PYSEC-2025-183 (CVE-2025-45768): the library does not enforce minimum key length on HMAC/RSA JWS operations. Upstream PyJWT disputes the CVE as application-level responsibility; no fix is planned.

**Our exposure: none.** PyJWT is a transitive dependency pulled in by `mcp` (the official Python MCP SDK). career-scout-mcp does not exercise JWT code paths:
- stdio transport has no auth headers
- HTTP transport (loopback-only when enabled) uses static-secret Bearer middleware via `hmac.compare_digest`, not JWT
- PyJWT's `decode`/`encode` is never called by our code

We accept this transitive risk and document it here for any reviewer running `pip-audit` against the repo.
