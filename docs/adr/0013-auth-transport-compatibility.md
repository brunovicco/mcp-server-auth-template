# ADR-0013: Auth-provider and transport compatibility matrix

- Status: Accepted
- Date: 2026-08-09

## Context

Python and MCP SDK compatibility do not prove that the supported authorization modes remain
compatible with the project's production and local-development transport policies. Security
hardening deliberately treats production HTTPS and explicit loopback HTTP differently, and both
IPv4 and IPv6 loopback forms need regression coverage.

A compatibility claim that exercises only successful configuration is also incomplete: the
fail-closed combinations are part of the contract.

## Decision

CI exposes six network-silent compatibility cells:

- Microsoft Entra ID × production HTTPS;
- Microsoft Entra ID × loopback IPv4 HTTP;
- Microsoft Entra ID × loopback IPv6 HTTP;
- Generic OIDC × production HTTPS;
- Generic OIDC × loopback IPv4 HTTP;
- Generic OIDC × loopback IPv6 HTTP.

`scripts/auth_transport_contract.py` constructs each supported profile from public Settings APIs
and emits only non-sensitive evidence. Unit tests exercise the rejected combinations.

For the server, production continues to require HTTPS. Local HTTP is accepted only for
IP-literal loopback resource URLs. Generic OIDC loopback profiles require the existing explicit
OIDC loopback escape, while production forbids that escape. Exact Host/Origin allowlists remain
part of the transport boundary.

The matrix is intentionally configuration-only and performs no DNS, HTTP, token, browser, or
identity-provider I/O.

## Consequences

- Entra and generic OIDC stay visible as independently tested support commitments.
- IPv4 and IPv6 loopback behavior can no longer regress silently.
- Production HTTP and insecure OIDC loopback remain fail-closed.
- Wildcard transport allowlists remain outside the supported contract.
- Cross-repository OAuth/MCP interoperability is still validated separately in P1.3c.
