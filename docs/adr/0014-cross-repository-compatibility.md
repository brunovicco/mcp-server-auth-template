# ADR-0014: Versioned cross-repository compatibility contract

- Status: Accepted
- Date: 2026-08-09

## Context

Local Python, MCP SDK, authorization-provider, and transport matrices do not prove that the
server remains interoperable with the companion client template. Cross-repository compatibility
needs an explicit protocol/security contract that can be compared before a live OAuth/MCP flow.

## Decision

Both repositories publish the same versioned machine-readable document at
`compatibility/cross-repository.json`. The contract pins MCP `2026-07-28`, Streamable HTTP, the
generic OIDC OAuth 2.1 E2E profile, the required scope, and the positive/negative security
evidence expected from the pair.

`scripts/cross_repository_contract.py` validates the server's local document. The companion
client owns the live interoperability workflow because it initiates OAuth and MCP calls. That
workflow checks out this repository from `main`, compares the two canonical contracts, and then
executes the real cross-repository OAuth/MCP suite.

Dynamic Client Registration remains a tested path of the generic reference E2E authorization
server. It is an interoperability profile, not a statement that DCR is the preferred client
registration mechanism for the 2026-07-28 protocol revision.

## Consequences

- This repository publishes a machine-checkable interoperability commitment.
- Drift in protocol revision, repository identity, or required evidence fails local tests.
- The companion client refuses to run its live E2E suite against a mismatched server contract.
- Server P1.3 must merge before client P1.3 so the client's `server/main` comparison is valid.
- Runtime authentication and transport behavior are unchanged by this decision.
