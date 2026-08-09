# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

## [0.3.0] - 2026-08-09

### Added

- MCP OAuth Client Credentials extension advertisement for non-interactive generic OIDC clients.
- Executable modern request-envelope validation for MCP `2026-07-28`.
- Sessionless Streamable HTTP interoperability and protocol-version negotiation evidence.
- Runtime scope step-up for protected MCP tools.
- Client ID Metadata Document-first interoperability evidence.
- ADRs covering CIMD, modern request envelopes, runtime scope step-up, and Client Credentials.

### Changed

- Public package version is now `0.3.0`.
- The cross-repository contract now covers interactive and machine-to-machine authentication.
- Compatibility documentation now distinguishes generic client credentials from Microsoft Entra
  application identities.
- Dynamic Client Registration remains only as backwards-compatible interoperability evidence.

### Security

- Extension negotiation never grants authorization by itself.
- The server remains an OAuth resource server and does not issue tokens or persist client secrets.
- Machine identities remain subject to verified issuer, audience, expiry, and scope validation.
- Generic client identities are not promoted to Microsoft Entra application principals.
- Invalid credentials, scope failures, protocol mismatches, and envelope mismatches fail closed.

## [0.2.0] - 2026-08-09

### Added

- OAuth 2.1 resource-server authentication for MCP `2026-07-28`, including RFC 9728 Protected
  Resource Metadata and standards-shaped bearer challenges.
- Microsoft Entra ID and generic OIDC token-verifier paths with exact issuer/audience validation,
  JWKS resolution, caching, and algorithm/key checks.
- Request-scoped `Principal` propagation, delegated/application identity classification, and
  per-tool scope authorization with `403 insufficient_scope` step-up challenges.
- Security audit events for authentication, authorization, transport rejection, scope step-up,
  and outbound credential blocking.
- Operational `GET /livez` and `GET /readyz` probes, production launcher, startup configuration
  preflight, hardened container runtime guidance, and Kubernetes deployment baseline.
- Executable compatibility matrices for Python 3.13/3.14, MCP SDK `2.0.0`/latest compatible 2.x,
  Entra/generic OIDC, production HTTPS, and IPv4/IPv6 loopback development profiles.
- A versioned cross-repository compatibility contract shared with `mcp-client-auth-template`.

### Changed

- Public package version is now `0.2.0`.
- Supported Python range is `>=3.13,<3.15`; the CI matrix exercises Python 3.13 and 3.14.
- Supported MCP Python SDK range is `>=2.0,<3`, with `2.0.0` as the tested support floor.
- Streamable HTTP is configured for the stateless/sessionless MCP `2026-07-28` execution model.
- Production configuration is fail-closed for insecure transport, placeholder identifiers, and
  unsafe OIDC settings.

### Security

- OIDC discovery/JWKS networking rejects unsafe schemes, redirects, compression, oversized
  responses, private/reserved destinations, mixed DNS answers, and bearer credential forwarding.
- HTTP transport admission enforces Host/Origin, request framing, body/header, concurrency, and
  method bounds.
- Raw bearer tokens and full identity-provider claims are excluded from the application principal
  and security audit surface.

[Unreleased]: https://github.com/brunovicco/mcp-server-auth-template/compare/v0.3.0...HEAD
[0.3.0]: https://github.com/brunovicco/mcp-server-auth-template/releases/tag/v0.3.0
[0.2.0]: https://github.com/brunovicco/mcp-server-auth-template/releases/tag/v0.2.0
