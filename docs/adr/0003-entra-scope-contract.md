# ADR-0003: Normalize Microsoft Entra scope identifiers at the resource-server boundary

- Status: Accepted
- Date: 2026-08-08

## Context

Microsoft Entra represents the same delegated API permission differently at the
OAuth request boundary and inside an access token.

A client requests a custom API permission with the API's Application ID URI,
for example:

```text
api://33333333-3333-3333-3333-333333333333/mcp:tools:call
```

For a v2 access token, Entra normally emits the API's Application (client) ID
GUID in `aud`, while the delegated permission is emitted in `scp` using only
the short value:

```json
{
  "aud": "33333333-3333-3333-3333-333333333333",
  "scp": "mcp:tools:call"
}
```

MCP scope discovery and step-up authorization use the scope strings published
by the resource server in Protected Resource Metadata and
`WWW-Authenticate`. Publishing the short `mcp:tools:call` value is not enough
for an Entra client to request a custom API permission, but publishing the full
Application ID URI form without normalizing the token claim makes server-side
scope enforcement fail.

## Decision

Keep three concepts explicit in configuration:

- `MCP_SERVER_ENTRA_AUDIENCE`: the access-token audience. For Entra v2 access
  tokens this is normally the API's Application (client) ID GUID.
- `MCP_SERVER_ENTRA_APPLICATION_ID_URI`: the resource identifier configured in
  **Expose an API**, commonly `api://<api-client-id>`.
- `MCP_SERVER_REQUIRED_SCOPES`: logical permission names, such as
  `mcp:tools:call`.

In Entra mode, the server qualifies logical required scopes with the
Application ID URI before passing them to the MCP SDK's `AuthSettings`.
Therefore PRM and `WWW-Authenticate` expose the requestable OAuth scope:

```text
api://33333333-3333-3333-3333-333333333333/mcp:tools:call
```

After signature, issuer, audience, expiry, and tenant validation, the Entra
token adapter qualifies the short permissions extracted from `scp`/`roles`
with the same Application ID URI. The MCP SDK therefore compares identical
canonical strings when enforcing required scopes.

Already URI-qualified permission values are preserved rather than rewritten.
A permission qualified for another resource consequently remains different and
cannot accidentally satisfy this server's required scope.

The generic OIDC adapter is unchanged: its scope values continue to pass
through exactly as issued by its authorization server.

## Consequences

- The companion MCP client does not need an Entra-specific hard-coded scope.
  The MCP SDK follows the specification's challenge-first scope-selection
  strategy and requests the full scope advertised by this resource server.
- Deployments using Entra must add `MCP_SERVER_ENTRA_APPLICATION_ID_URI`.
- Existing Entra deployments should verify `MCP_SERVER_ENTRA_AUDIENCE`.
  For v2 access tokens this should normally be the API's Application (client)
  ID GUID, not the `api://...` Application ID URI.
- The same short logical `MCP_SERVER_REQUIRED_SCOPES` configuration remains
  usable for both providers, while provider-specific wire representation stays
  inside the Entra adapter.
