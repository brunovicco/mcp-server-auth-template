# ADR-0009: Emit minimal security audit events and forbid token passthrough

- Status: Accepted
- Date: 2026-08-08

## Context

The MCP 2026-07-28 authorization specification requires an MCP resource server to accept only
access tokens intended for that resource and forbids accepting or transiting other tokens. The
security guidance calls forwarding the inbound MCP bearer token to a downstream API "token
passthrough" and identifies confused-deputy, accountability, and audit-trail risks.

Authentication and authorization failures are also security-relevant operational evidence, but
logging raw bearer values, refresh tokens, full claims, request bodies, or authorization headers
would turn the audit trail itself into a credential-exfiltration surface.

## Decision

1. Emit one structured `security_audit` event for authentication rejection, denied tool calls,
   progressive OAuth scope challenges, transport admission rejection, and blocked outbound
   credentials.
2. Audit records are allowlisted and minimized: action, outcome, reason, status, tool name,
   principal kind/client ID, scope count, and target kind where relevant. Raw tokens, raw claims,
   scope values, subjects, request bodies, and authorization headers are excluded.
3. The logging pipeline performs defense-in-depth redaction for credential-shaped keys, bearer
   strings, and common OAuth query parameters before JSON/console rendering.
4. The OIDC discovery/JWKS transport rejects any outbound `Authorization` header. Those requests
   never require the caller's bearer token.
5. `Principal` remains the application authorization boundary. It deliberately contains normalized
   identity/permission facts and no raw token or full claims mapping.
6. This template currently has no downstream business API client. A future downstream integration
   MUST obtain a separate credential issued for that API and MUST NOT reuse the MCP inbound bearer.

## Consequences

- Security denials become queryable without creating a second secret store in logs.
- A coding mistake that adds an Authorization header to the server's current outbound OIDC path
  fails closed before network I/O.
- The raw MCP bearer remains confined to the SDK authentication layer and validated `AccessToken`;
  application authorization consumes `Principal` instead.
- Audit sinks still need normal access control, retention, integrity, and privacy governance.
