# mcp-server-auth-template

[![quality](https://github.com/brunovicco/mcp-server-auth-template/actions/workflows/quality.yml/badge.svg)](https://github.com/brunovicco/mcp-server-auth-template/actions/workflows/quality.yml)
[![compatibility](https://github.com/brunovicco/mcp-server-auth-template/actions/workflows/compatibility.yml/badge.svg)](https://github.com/brunovicco/mcp-server-auth-template/actions/workflows/compatibility.yml)
[![release](https://img.shields.io/github/v/release/brunovicco/mcp-server-auth-template)](https://github.com/brunovicco/mcp-server-auth-template/releases)
![python](https://img.shields.io/badge/python-3.13%20%7C%203.14-blue.svg)
[![license](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

*[Leia em português](README.pt-BR.md)*

A reusable template for an MCP server that acts as an OAuth 2.1 **resource server** - never an
authorization server - against either Microsoft Entra ID or any standards-compliant OIDC
authorization server (Auth0, Keycloak, WorkOS AuthKit, ...). Targets the MCP **2026-07-28**
specification.

The MCP 2026-07-28 authorization model keeps a remote MCP server at the OAuth resource-server
boundary: it publishes Protected Resource Metadata and validates access tokens issued by an
external authorization server. This template implements that boundary for Entra ID and generic
OIDC, including issuer/audience checks, hardened JWKS retrieval, scope enforcement, and Entra's
split delegated/application claim shapes. Entra deployments use pre-registered client
applications; client registration itself remains an authorization-server concern. See
`docs/adr/0002-oauth21-resource-server.md` for the full reasoning, and the companion repository,
[`mcp-client-auth-template`](https://github.com/brunovicco/mcp-client-auth-template), for the
client-side half of this pattern.

## Compatibility

Release `v0.2.0` supports Python **3.13 and 3.14**, MCP Python SDK **2.x**
(`>=2.0,<3`), and the MCP **2026-07-28** reference profile. CI continuously exercises the SDK
support floor (`2.0.0`) and the latest compatible 2.x, both auth providers, production HTTPS,
explicit IPv4/IPv6 loopback development profiles, and the versioned client/server pair contract.

See [`docs/COMPATIBILITY.md`](docs/COMPATIBILITY.md) for the executable support policy and its
scope. Provider-specific live IdP interoperability is intentionally not claimed by the local
deterministic matrix.

## Auth quick start

1. Copy `.env.example` to `.env` and fill in one of the two provider blocks
   (Entra ID or a generic OIDC authorization server).
2. Run the server:

   ```bash
   uv run uvicorn mcp_server_auth_template.entrypoints.mcp_server:create_app --factory --reload
   ```

   For production-style execution, use the repository launcher instead:

   ```bash
   uv run python -m mcp_server_auth_template.entrypoints.serve
   ```

   See `docs/OPERATIONS.md` for probes, shutdown, container, and Kubernetes guidance.

3. Protected Resource Metadata is served automatically at
   `/.well-known/oauth-protected-resource` - point an MCP client at
   `http://localhost:8000/mcp` and it will discover the configured authorization
   server from there:

   ```json
   {
     "resource": "https://mcp.example.invalid/",
     "authorization_servers": ["https://as.example.invalid"],
     "bearer_methods_supported": ["header"]
   }
   ```

   A request with no (or an invalid) bearer token gets a `401` with a `WWW-Authenticate` header
   pointing back at that same metadata document, exactly as the spec requires - the server never
   issues its own login page:

   ```text
   HTTP/1.1 401 Unauthorized
   www-authenticate: Bearer error="invalid_token", error_description="Authentication required",
     resource_metadata="https://mcp.example.invalid/.well-known/oauth-protected-resource"
   ```

4. Two example tools are registered: `whoami` returns the identity carried by the
   caller's token (client ID, subject, scopes), and `health` is an authenticated
   application-level diagnostic for MCP callers.

Operational liveness/readiness are exposed separately as unauthenticated `GET /livez` and
`GET /readyz`; see `docs/OPERATIONS.md` for their deployment contract.

Swap `MCP_SERVER_AUTH_PROVIDER` between `entra` and `generic` to switch adapters -
no other code changes. See `src/mcp_server_auth_template/adapters/` for the two
`TokenVerifier` implementations and `tests/unit/test_*_token_verifier.py` for how
each is tested offline with a locally-signed JWT (no network, no real IdP needed).

## Authentication flow

`docs/ARCHITECTURE.md` has a sequence diagram of the full bearer-token round trip - the 401
challenge, Protected Resource Metadata discovery, token acquisition on the authorization server
(out of scope for this repo), and signature/issuer/audience verification on every subsequent call.
See [Diagrams](docs/ARCHITECTURE.md#diagrams).

## Development

```bash
uv lock --check
uv sync --frozen --all-groups --extra observability
uv run pytest
uv run python scripts/quality_gate.py
```

List or select gate checks with `--list` and `--check NAME`. See `AGENTS.md` for build, lint,
format, typecheck, test, security, architecture, MCP, and completion requirements, and
`docs/DEVELOPMENT.md` for the container build and local setup.

Codex loads the checked-in `.codex/config.toml`, `.codex/hooks.json`, and `.agents/skills/` only
within the appropriate project/trust context. Review lifecycle hooks with `/hooks` before use.

## License

[MIT](LICENSE)
