# ADR-0005: Use request-scoped principals and default-deny per-tool authorization

- Status: Accepted
- Date: 2026-08-08

## Context

ADR-0004 separated OAuth scopes from Microsoft Entra `roles`, but a resource
server still needs to decide which authenticated identity may discover and call
each MCP tool. A single `AuthSettings.required_scopes` list is only a global
baseline. It cannot express that one tool needs a delegated scope, another
needs an app-only permission, and a third only needs authentication.

The distinction is security-sensitive. Microsoft documents `scp` as a user /
delegated-token signal and notes that `roles` can also be present on delegated
tokens for roles assigned to the user. Therefore `roles` alone is not proof
that the caller is an application identity.

MCP Python SDK v2.0.0 exposes public `ServerMiddleware` that receives a
per-message `ServerRequestContext`, including the original HTTP request. The
SDK's bearer middleware stores the validated `AccessToken` on that request's
`AuthenticatedUser`. This is a safer authorization seam than consulting a
connection- or context-local identity that could be stale across legacy
stateful requests.

## Decision

Introduce a provider-neutral `Principal` with separate `scopes` and `roles`
namespaces and an explicit identity kind:

- Entra with a non-empty `scp` -> `delegated`, unless the token also claims
  `idtyp=app`, in which case the contradictory shape becomes `unknown`;
- Entra with no `scp` and `idtyp=app` -> `application`;
- all other Entra shapes -> `unknown`;
- generic OAuth/OIDC -> `unknown` identity kind while retaining validated
  OAuth scopes.

Application-role policies require `PrincipalKind.APPLICATION`. This means
Entra deployments that want app-only tool authorization must configure the
`idtyp` optional claim and receive `idtyp=app`. The stricter requirement is
intentional: a role-bearing delegated token must never be mistaken for an
application principal.

Per-tool policies are explicit and default-deny. Supported policy forms are:

- `ToolPolicy.authenticated()`;
- `ToolPolicy.delegated_scopes(...)`;
- `ToolPolicy.application_roles(...)`;
- `ToolPolicy.oauth_scopes(...)` for generic providers where the grant type
  cannot be inferred safely from standard scope claims alone.

A public MCP `ServerMiddleware` enforces the policy on `tools/call` before the
tool handler runs and filters `tools/list` so the caller does not see tools it
cannot invoke. A newly registered tool without a policy is hidden and denied.

The example `health` and `whoami` tools remain authenticated-only so this
security substep does not silently change their existing contract. Templates
can replace either policy with delegated scopes or application roles.

## Progressive authorization boundary

An in-band `CallToolResult(is_error=True)` remains the fail-closed fallback for
denials that cannot be repaired by requesting more OAuth scopes. ADR-0006 adds
the HTTP bridge for repairable scope failures: MCP 2026-07-28 routing headers
select the candidate tool before dispatch, the already-validated principal is
checked against this same policy service, and a missing OAuth scope becomes a
standards-compliant HTTP 403 `insufficient_scope` challenge. The parsed MCP
message is still re-authorized by this middleware, so routing headers never
become the final authorization source of truth.

## Consequences

- Delegated scope rules and application-role rules cannot satisfy each other.
- Tool discovery is authorization-aware.
- Missing policies fail closed, reducing accidental exposure when a new tool is
  registered.
- Raw bearer tokens and the full JWT claims mapping do not enter the domain
  principal.
- Generic OIDC remains conservative: scope authorization is supported, but the
  template does not invent delegated/application identity semantics a generic
  provider did not prove.
- `AuthSettings.required_scopes` remains a global baseline. Deployments mixing
  app-only role tools and delegated-scope tools should leave that baseline
  empty and rely on per-tool policies; transport-level progressive scope
  challenges are the remaining piece for automatic step-up.
