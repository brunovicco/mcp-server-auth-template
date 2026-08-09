# ADR-0018: Advertise and prove the OAuth Client Credentials extension

- Status: Accepted
- Date: 2026-08-09

## Context

The server already validates bearer tokens independently of how an authorization server issued
them. It also models Entra application principals and application roles separately from delegated
scopes. What remained missing was discoverable and cross-repository evidence for an unattended MCP
client using the draft `io.modelcontextprotocol/oauth-client-credentials` extension.

Generic OIDC scope tokens and Entra app-only tokens are not interchangeable. The generic verifier
does not have a portable claim that proves application identity, while Entra client credentials
request `{resource}/.default` and carry assigned application permissions in `roles`.

## Decision

- Advertise `io.modelcontextprotocol/oauth-client-credentials` in server capabilities.
- Reuse the existing verifier and authorization middleware; do not add a token endpoint or trust a
  client capability declaration as authentication evidence.
- Exercise a generic-OIDC pre-registered client in the companion-owned E2E, including discovery,
  resource binding, bearer validation, machine client ID/subject, and scope step-up.
- Keep generic OAuth scopes and Entra `PrincipalKind.APPLICATION`/application roles separate. Do
  not claim live Entra client credentials interoperability in this increment.

## Consequences

- Non-interactive support becomes discoverable without changing the resource-server trust
  boundary: only a valid issuer/audience-bound token authorizes a request.
- The same pre-dispatch scope challenge works for the generic machine client and remains bounded by
  the SDK authorization replay.
- Entra deployments can continue using explicit app-role tool policies, but need provider-specific
  client acquisition and live IdP validation before advertising an end-to-end compatibility claim.
- Merge this server change before the companion client change because client-owned E2E checks the
  advertised capability and shared contract.
