# ADR-0002: MCP server as an OAuth 2.1 resource server only

- Status: Accepted
- Date: 2026-08-07

## Context

The MCP 2026-07-28 authorization specification models every remote MCP server as an
OAuth 2.1 **resource server** (RFC 9728, Protected Resource Metadata) that verifies
bearer tokens minted by a separate authorization server, never as the authorization
server itself. Two authorization-server shapes need to be supported by this template:

- **Microsoft Entra ID**, which supports neither Dynamic Client Registration nor
  Client ID Metadata Documents - only pre-registration of known clients - and uses
  Entra-specific claims (`scp` for delegated permissions, `roles` for application
  permissions, `tid` for tenant) instead of a plain `scope` string.
- **Any standards-compliant OIDC authorization server** (Auth0, Keycloak, WorkOS
  AuthKit, ...), which publishes ordinary OIDC discovery and JWKS endpoints.

DCR itself was formally deprecated in the 2026-07-28 revision in favor of CIMD
(Client ID Metadata Documents); since this repository never acts as an authorization
server, client registration is out of its scope either way - that concern belongs to
`mcp-client-auth-template`, the companion client repository.

## Decision

- Depend on the official `mcp` Python SDK v2 (`mcp>=2.0,<3`), which speaks the
  2026-07-28 specification natively. `mcp.server.mcpserver.MCPServer` already
  implements Protected Resource Metadata, the `401` + `WWW-Authenticate` challenge,
  and per-request `required_scopes` enforcement once constructed with `auth=` and
  `token_verifier=` - this repository does not reimplement any of that.
- The only code this template owns is the `TokenVerifier` implementation: signature
  verification against a cached JWKS, issuer/audience/expiry checks, and scope-claim
  normalization. Two adapters share that logic through composition:
  `GenericOidcTokenVerifier` for any OIDC-compliant AS, and `EntraTokenVerifier`,
  which wraps it with Entra's tenant-scoped issuer URL and an additional `tid`
  binding check.
- The server never requests, stores, or forwards a token on the caller's behalf; it
  only verifies tokens a client already obtained. An on-behalf-of flow for calling
  downstream APIs (e.g. Microsoft Graph) is intentionally out of scope for this
  template - add it as a separate adapter only when a concrete downstream call is
  needed, so the added trust boundary is deliberate rather than default.
- The ASGI app is exposed as a factory (`create_app()`), not a module-level `app =
  ...`, so importing this module never requires real environment variables and stays
  safe for tooling (tests, docs generators) that only need to import it.

## Consequences

- Adding a third authorization-server shape means adding one more `TokenVerifier`
  implementation, not touching `entrypoints/mcp_server.py` beyond the provider
  branch in `_build_token_verifier`.
- Because scope enforcement and PRM are the SDK's responsibility, this template
  cannot silently drift from the specification's transport-level requirements; it
  can only get the adapter-level claim validation wrong, which is exactly what
  `tests/unit/test_generic_oidc_token_verifier.py` and
  `tests/unit/test_entra_token_verifier.py` exist to catch.
- If Entra later adds CIMD or DCR support, `EntraTokenVerifier` does not need to
  change - only the companion client repository's registration logic would.
