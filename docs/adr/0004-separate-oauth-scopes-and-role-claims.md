# ADR-0004: Keep OAuth scopes and role claims in separate authorization namespaces

- Status: Accepted
- Date: 2026-08-08

## Context

The MCP Python SDK's resource-server scope gate evaluates
`AccessToken.scopes`. The template previously populated that list by merging
three JWT claims: standard OAuth `scope`, Microsoft Entra `scp`, and Entra
`roles`.

That merge loses an authorization boundary. Microsoft Entra documents `scp` as
the delegated scopes granted to a client acting for a signed-in user. In an
app-only/client-credentials token, application permissions are carried in
`roles` instead. A delegated user token may also contain `roles` for roles
assigned to that user, so the mere presence of `roles` does not prove that the
token represents an application identity.

If a delegated scope and an application role share the same string value, a
merged list allows the role to satisfy the SDK's scope-only middleware. A
policy intended to require delegated user consent can therefore be bypassed by
an app-only token that has a same-named role.

## Decision

`AccessToken.scopes` contains OAuth scope values only:

- standard `scope` values for generic OAuth/OIDC providers;
- Microsoft Entra `scp` values for delegated permissions.

The `roles` claim is never promoted into `AccessToken.scopes`. It remains in
the already-validated `AccessToken.claims` mapping and can be extracted through
`roles_from_claims()` by an explicit role-aware authorization policy.

This ADR deliberately does **not** infer `authentication_mode` from the
presence of `roles`. Entra can emit `roles` on delegated user tokens as well as
app-only tokens. ADR-0005 builds on this boundary with a provider-aware
principal model and explicit per-tool delegated-vs-application policies.

## Consequences

- An application role can no longer satisfy `AuthSettings.required_scopes`.
- Existing deployments that relied on a `roles` value being treated as an
  OAuth scope will fail closed and must move to an explicit role policy.
- Application roles are not discarded: the validated raw claim remains
  available for future authorization decisions and audit events.
- Delegated scope behavior, Entra Application ID URI qualification, audience
  validation, tenant binding, and generic OAuth `scope` handling remain
  unchanged.
- This is intentionally a small security boundary fix. Per-tool authorization
  and a first-class principal model are separate P1.1 work so their semantics
  can be reviewed and tested without broadening this change.
