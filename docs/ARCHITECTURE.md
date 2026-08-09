# Architecture

## Context

This service is a reusable template for an MCP server that acts as an OAuth 2.1 **resource
server** (RFC 9728) - it never issues tokens itself. Its one job is verifying bearer tokens a
client already obtained and translating their claims into the identity the server's tools see. See
`docs/adr/0002-oauth21-resource-server.md` for why token issuance is out of scope.

- **Upstream dependency**: exactly one authorization server per deployment - either Microsoft
  Entra ID or any standards-compliant OIDC authorization server (Auth0, Keycloak, WorkOS AuthKit,
  ...), selected by `MCP_SERVER_AUTH_PROVIDER`. This service reads the AS's OIDC discovery document
  and JWKS to verify signatures; it never calls the AS's token endpoint.
- **Downstream dependency**: MCP clients (2026-07-28 spec) that discover this server's Protected
  Resource Metadata at `/.well-known/oauth-protected-resource`, obtain a token from the configured
  AS, and call the registered tools (`whoami`, `health`) with that token as a bearer credential.
  The server advertises the draft OAuth Client Credentials extension for non-interactive clients.
- **Companion repository**: [`mcp-client-auth-template`](https://github.com/brunovicco/mcp-client-auth-template)
  owns the client-side half of this pattern (token acquisition, client registration).

## Layers

```text
src/mcp_server_auth_template/
├── domain/
├── application/
├── adapters/
└── entrypoints/
```

### Domain

Pure business concepts, invariants, Value Objects, domain services, events, and domain errors.

### Application

Use cases, commands, queries, ports, authorization decisions, and transaction coordination.

### Adapters

Implementations of application ports for databases, messaging, HTTP, cache, storage, identity, and external SDKs.

### Entrypoints

HTTP, CLI, jobs, events, and serverless handlers. Entrypoints validate and translate transport data but do not own business rules.

## Dependency rule

```text
entrypoints -> application -> domain
adapters    -> application/domain
domain      -> no outer layer
```

## Cross-cutting decisions

- Configuration: environment variables validated at startup.
- Logging: structured events to stdout/stderr.
- Tracing: `a2a-otel-kit` wraps the MCP Streamable HTTP ASGI boundary inside transport admission
  and outside auth/tool dispatch. It exports metadata-only traces over OTLP HTTP/protobuf only
  when `A2A_OTEL_ENABLED=true`, propagates W3C Trace Context but not baggage, and is shut down by
  the MCP server lifespan. The separate Langfuse LLM observer remains opt-in.
- Errors: infrastructure errors translated at adapters; external errors mapped at entrypoints.
- Time: UTC internally with timezone-aware values.
- Money: `Decimal` wrapped in a domain Value Object.
- Idempotency: required for externally visible side effects.
- Packaging: containerized via the repo `Dockerfile` (multi-stage, uv-based); the runtime `CMD` is defined per project.

## Diagrams

Resource-server bearer-token flow (the only critical flow this service owns; token issuance
happens entirely on the authorization server and is out of scope):

```mermaid
sequenceDiagram
    participant Client as MCP client
    participant Server as This resource server
    participant AS as Authorization server<br/>(Entra ID / generic OIDC)

    Client->>Server: Call a tool, no bearer token
    Server-->>Client: 401 + WWW-Authenticate
    Client->>Server: GET /.well-known/oauth-protected-resource
    Server-->>Client: Protected Resource Metadata (points at AS)
    Client->>AS: Obtain a token (out of scope for this repo)
    AS-->>Client: Access token
    Client->>Server: Call a tool, Authorization: Bearer <token>
    Server->>AS: Fetch OIDC discovery + JWKS (cached)
    Server->>Server: Verify signature, issuer, audience, expiry
    alt Tool needs an additional scope
        Server-->>Client: 403 insufficient_scope before dispatch
        Client->>AS: Reauthorize with prior + challenged scopes
        AS-->>Client: Elevated access token
        Client->>Server: Retry the undispatched request once
    end
    Server-->>Client: Tool result
```

For the generic-OIDC client-credentials profile, token acquisition uses a pre-registered
confidential client instead of browser authorization, CIMD, or DCR. Resource-server validation is
unchanged: signature, issuer, audience, expiry, and OAuth scopes remain mandatory. Generic claims
are not promoted to Entra application identity. Entra app-only authorization continues to require
the explicit `idtyp=app` classification and `ToolPolicy.application_roles(...)`.
