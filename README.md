# mcp-server-auth-template

[![quality](https://github.com/brunovicco/mcp-server-auth-template/actions/workflows/quality.yml/badge.svg)](https://github.com/brunovicco/mcp-server-auth-template/actions/workflows/quality.yml)
![python](https://img.shields.io/badge/python-3.13-blue.svg)
[![license](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

*[Leia em português](README.pt-BR.md)*

A reusable template for an MCP server that acts as an OAuth 2.1 **resource server** - never an
authorization server - against either Microsoft Entra ID or any standards-compliant OIDC
authorization server (Auth0, Keycloak, WorkOS AuthKit, ...). Targets the MCP **2026-07-28**
specification.

The MCP 2026-07-28 authorization spec models every remote MCP server this way: it verifies bearer
tokens minted elsewhere, it never mints them itself. Entra ID also can't act as a full MCP
authorization server for arbitrary clients (no Dynamic Client Registration, no Client ID Metadata
Documents), so a real integration needs an adapter either way. This template is that adapter,
built once, correctly, so a new MCP server doesn't have to re-derive JWKS caching, issuer/audience
checks, and Entra's split `scp`/`roles` claim shape from scratch. See
`docs/adr/0002-oauth21-resource-server.md` for the full reasoning, and the companion repository,
[`mcp-client-auth-template`](https://github.com/brunovicco/mcp-client-auth-template), for the
client-side half of this pattern.

## Auth quick start

1. Copy `.env.example` to `.env` and fill in one of the two provider blocks
   (Entra ID or a generic OIDC authorization server).
2. Run the server:

   ```bash
   uv run uvicorn mcp_server_auth_template.entrypoints.mcp_server:create_app --factory --reload
   ```

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
   caller's token (client ID, subject, scopes), and `health` is a liveness check
   for an already-authenticated caller.

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
