# ADR-0016: Make the modern request envelope an executable pair contract

- Status: Accepted
- Date: 2026-08-09

## Context

The MCP 2026-07-28 Streamable HTTP profile makes every request self-describing. The protocol
version appears in both the HTTP header and `params._meta`; `Mcp-Method` mirrors the JSON-RPC
method; and `Mcp-Name` mirrors the named target for calls such as `tools/call`. Modern HTTP is
sessionless and rejects header/envelope disagreement or unsupported versions with structured
JSON-RPC errors.

The template already uses the official MCP Python SDK v2 modern transport, and existing tests
proved request-scoped identity despite a legacy-looking session header. The cross-repository
contract did not yet claim or execute the complete header, envelope, version, and sessionless
boundary.

## Decision

- Keep envelope classification and routing-header validation delegated to the official MCP SDK.
  Do not add a second template-owned parser or validation middleware.
- Add local transport regressions for mismatched `Mcp-Method` and `Mcp-Name`, expecting JSON-RPC
  `-32020`, and for a coherent unsupported version, expecting `-32022` with supported/requested
  version data.
- Retain the existing regression proving that `Mcp-Session-Id` cannot carry identity between
  modern requests and is never returned by the server.
- Add matching positive and negative evidence to the shared pair contract. The companion client
  owns the live E2E against this server.

## Consequences

- The protocol-advanced claim remains tied to SDK behavior at the supported floor and moving 2.x
  edge instead of becoming a parallel implementation maintained by the template.
- Header/body disagreement fails before tool dispatch. A coherent unknown version gets an
  actionable negotiation error rather than an ambiguous transport failure.
- Authentication remains bearer-token-per-request; neither legacy session identifiers nor hidden
  server state participate in authorization.
- Merge this server contract before the client change because the client E2E compares against
  `server/main`.
