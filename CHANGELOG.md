# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added

- Added a server-focused verification guide and visual-evidence slots backed by the companion
  executable reference harness.
- Added public-repository hygiene regression coverage preventing local coding-agent state from
  returning to the tracked tree.

### Changed

- Reworked the EN/PT-BR landing pages around resource-server proof, security boundaries,
  source-level verification, observable evidence and explicit demo-vs-production limits.
- Made contributor/development guidance tool-agnostic and removed the Codex-only MCP-config check
  from the project quality gate.
- Removed checked-in coding-agent/Codex scaffolding and development-only MCP consumer configuration
  from the public repository.

## [0.5.0] - 2026-08-09

### Added

- Added an executable supply-chain trust baseline with SHA-pinned GitHub Actions, explicit
  least-privilege workflow permissions, controlled Dependabot updates, and dependency/license
  review.
- Added CycloneDX source and production-image inventories, checksum-verified Syft/Grype tooling,
  complete vulnerability evidence, and a fail-closed policy for actionable findings with narrow,
  expiring exceptions.
- Added allowlisted, byte-reproducible wheel and sdist builds with exact build constraints,
  SHA-256 manifests, and GitHub build-provenance attestations.
- Added tag-gated GitHub Release publication with reproducible Python packages, complete checksum
  coverage, CycloneDX inventories, vulnerability evidence, and a machine-readable release manifest.
- Added GHCR publication for the policy-approved production image, identified by immutable digest
  and accompanied by build-provenance and SBOM attestations.

### Changed

- Public package version is now `0.5.0`.
- Release publication is split across isolated artifact-build, container-publication, and GitHub
  Release jobs; PyPI publication remains out of scope.
- Existing GHCR version and commit tags are never overwritten; a partial publication requires a
  new version rather than reusing a partially published version.

### Fixed

- Made the checksum-corruption regression test deterministic so release-integrity failures are
  exercised reliably.
- Derive runtime logging and OpenTelemetry service version from installed package metadata so
  released telemetry identifies `v0.5.0` correctly.

### Security

- Reject `offline_access` when configured as a required MCP resource scope; refresh-token consent
  belongs to the OAuth client and authorization server.
- GHCR authentication happens only after the vulnerability policy approves the locally built
  production image.
- Attestation, registry, and GitHub Release write authority are isolated into narrowly scoped jobs.
- Release builds fail closed on version/tag mismatch, non-reproducible artifacts, unexpected
  archive contents, unsafe paths, checksum drift, stale or expired vulnerability exceptions, and
  release-bundle inconsistencies.

## [0.4.0] - 2026-08-09

### Changed

- Public package version is now `0.4.0`.
- Replaced the disconnected, hand-rolled OpenTelemetry lifecycle with the released
  `a2a-otel-kit[mcp]>=0.6,<0.7` ASGI integration at the MCP Streamable HTTP boundary.
- Made metadata-only W3C tracing a network-silent core capability and removed the separate
  `observability` install extra.
- Reworked the English and Brazilian Portuguese READMEs around adoption, architecture, security,
  engineering evidence, operations, and explicit production boundaries.

### Security

- Kept hardened HTTP admission outside tracing and preserved the rule that spans never capture
  authorization data, MCP arguments/results, request bodies, arbitrary headers, URLs, or
  exception text.

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

[Unreleased]: https://github.com/brunovicco/mcp-server-auth-template/compare/v0.5.0...HEAD
[0.5.0]: https://github.com/brunovicco/mcp-server-auth-template/compare/v0.4.0...v0.5.0
[0.4.0]: https://github.com/brunovicco/mcp-server-auth-template/compare/v0.3.0...v0.4.0
[0.3.0]: https://github.com/brunovicco/mcp-server-auth-template/releases/tag/v0.3.0
[0.2.0]: https://github.com/brunovicco/mcp-server-auth-template/releases/tag/v0.2.0
