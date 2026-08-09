# ADR-0011: Fail-fast production configuration preflight

## Status

Accepted.

## Context

P1.2a made the process observable to an orchestrator and P1.2b added a hardened deployment
baseline. A workload can still fail late if a copied example value, development-only loopback
escape hatch, or insecure production URL reaches runtime. Late failure is particularly undesirable
when it occurs only after the first authenticated MCP request triggers OIDC work.

A startup check must not solve this by calling the authorization server: coupling process startup to
OIDC/JWKS availability would turn a dependency incident into a rollout/restart incident. Diagnostic
output must also avoid becoming a second secret or identity log.

## Decision

1. Reuse the existing `APP_ENV` setting and treat `production` as an explicit hardening profile.
2. Revalidate the complete `Settings` model in the production launcher before Uvicorn binds.
3. Provide `python -m mcp_server_auth_template.entrypoints.preflight` for CI and operator use.
4. Keep preflight network-silent: no DNS resolution, discovery, JWKS, token verification, or
   downstream dependency calls.
5. In production, reject HTTP resource URLs, the insecure OIDC loopback escape hatch, reserved
   placeholder hostnames, non-HTTPS browser Origins, non-HTTPS generic issuers/JWKS origins, and
   checked-in all-zero Entra identifiers.
6. Emit only allowlisted operational metadata on success. On failure, expose only validation
   location/type metadata and never Pydantic input/context values.
7. Set `APP_ENV=production` in the Kubernetes baseline so copied `.invalid` placeholders fail before
   the workload becomes ready.

## Consequences

- Example configuration remains convenient in development but cannot silently become production
  configuration.
- A production container exits before listening when local configuration violates the production
  profile.
- OIDC outages do not block process startup or trigger rollout loops; request-time authentication
  continues to fail closed independently.
- Preflight output is suitable for CI artifacts and operator terminals without disclosing issuer,
  audience, tenant, scope, or credential material.
- Platform-specific reachability, TLS-chain, DNS, ingress, and NetworkPolicy checks remain outside
  this application-level preflight.

## Alternatives rejected

- **Perform OIDC discovery during startup:** rejected because it couples rollout health to an
  external identity dependency.
- **Only document that placeholders must be replaced:** rejected because documentation does not
  fail closed.
- **Print the full Pydantic validation error:** rejected because validation errors can include input
  values and context that should not become logs.
- **Make production restrictions unconditional:** rejected because explicit loopback HTTP remains
  useful for controlled local integration tests.
