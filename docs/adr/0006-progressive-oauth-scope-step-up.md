# ADR-0006: Bridge per-tool scope policy to HTTP 403 step-up challenges

- Status: Accepted
- Date: 2026-08-08

## Context

ADR-0005 introduced request-scoped principals and default-deny authorization
for `tools/list` and `tools/call`. That closes the authorization boundary, but
an MCP client cannot automatically request additional delegated permissions
from an in-band `CallToolResult(is_error=True)` response.

The MCP authorization specification requires runtime insufficient-scope errors
to use HTTP `403 Forbidden` with a `WWW-Authenticate: Bearer` challenge carrying
`error="insufficient_scope"`, the minimum scopes for the operation, and the
Protected Resource Metadata URL. MCP 2026-07-28 also requires `Mcp-Method` and
`Mcp-Name` headers on HTTP requests, allowing a resource server or gateway to
identify a `tools/call` operation before parsing its JSON-RPC body.

The server must not solve this by decoding the bearer token twice or by trusting
header routing metadata as the final authorization decision. It must also keep
legacy clients functional.

## Decision

Use two cooperating public extension seams:

1. An outer Starlette/ASGI middleware reads only MCP 2026-07-28 routing headers
   and stores the request target in a request-local `ContextVar`. It does not
   parse the JSON-RPC body or verify the token.
2. A `TokenVerifier` decorator delegates cryptographic/token validation exactly
   once to the configured Entra or generic OIDC verifier. For a modern
   `tools/call`, it evaluates the already-validated token against the same
   `ToolAuthorizationService` used by MCP message middleware.

When the principal kind is correct but one or more OAuth scopes are missing,
the verifier decorator records the minimum required scopes and returns `None`.
The same decorator also checks the server-wide `required_scopes` baseline. If
both a global scope and a tool-specific scope are missing, they are combined in
one challenge so a conforming client can perform a single step-up round trip.
The SDK then stops before MCP dispatch and emits its normal unauthenticated
response. The outer middleware replaces that response with:

```http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer error="insufficient_scope", scope="...", resource_metadata="..."
Cache-Control: no-store
```

The original `ToolAuthorizationMiddleware` remains authoritative for the parsed
MCP message. It still checks the real `tools/call.params.name`, hides
unauthorized tools from `tools/list`, and denies legacy requests in-band. Thus a
forged or mismatched `Mcp-Name` header cannot authorize a different tool; the
SDK's 2026-07-28 header/body validation and the message-level policy both remain
in force.

Only `MISSING_PERMISSION` decisions with OAuth scopes become a progressive HTTP
challenge. Wrong principal kind, application-role failures, missing tool
policies, and other denials remain ordinary authorization failures. Re-running
interactive OAuth cannot turn an application token into a delegated user token
or manufacture an application role, so challenging those cases would create
misleading or looping step-up behavior.

For Entra, short delegated scope names in the template policy registry are
qualified with the configured Application ID URI before matching and before
being advertised in `WWW-Authenticate`. This keeps the token namespace, policy
namespace, and scope requested by the OAuth client identical.

Scope-policy constructors validate RFC 6749 `scope-token` syntax before startup.
This prevents spaces, quotes, backslashes, controls, or non-ASCII data from being
injected into an HTTP authentication challenge.

## Consequences

- Python SDK clients can perform the MCP runtime scope step-up flow from a real
  HTTP 403 instead of receiving only an MCP tool error.
- The bearer token is cryptographically verified once per request.
- The bridge does not depend on private MCP SDK route objects or duplicated JSON
  parsing.
- Modern header metadata is used only as a pre-dispatch optimization; the
  parsed MCP request remains the final authorization source of truth.
- Legacy protocol requests keep the P1.1b1 in-band per-tool default-deny
  behavior rather than trusting headers that legacy revisions do not require.
  Server-wide OAuth scope failures can still use the transport-level 403 because
  they do not depend on `Mcp-Name`.
- Application-role authorization intentionally has no OAuth scope challenge.
