# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [Unreleased]

### Added

- OAuth 2.1 resource-server authentication for MCP servers (RFC 9728 Protected Resource
  Metadata, `401` + `WWW-Authenticate` challenge), targeting the MCP `2026-07-28` specification.
- Two `TokenVerifier` adapters selected by `MCP_SERVER_AUTH_PROVIDER`: a generic OIDC verifier
  (`generic_oidc_token_verifier.py`) for any standards-compliant authorization server (Auth0,
  Keycloak, WorkOS AuthKit, ...), and an Entra ID verifier (`entra_token_verifier.py`) that wraps
  the generic one and adds `tid` tenant-binding.
- OIDC discovery and JWKS resolution behind `DiscoveryPort`/`KeyResolverPort` protocols, so
  verifiers are tested offline against fakes with a locally-signed JWT - no network, no real IdP.
- Scope/role claim normalization (`scope_claims.py`) covering both plain `scope` strings and
  Entra's split `scp`/`roles` claims.
- Entra scope-contract normalization that separates the v2 access-token audience from the
  Application ID URI, advertises requestable `api://.../<scope>` values to MCP clients, and
  qualifies short `scp`/`roles` permissions before SDK scope enforcement.
- Two example tools: `whoami` (identity from the caller's token) and `health` (authenticated
  liveness check).
- Structured logging (`structlog`) and opt-in, vendor-neutral OpenTelemetry tracing
  (`adapters/observability.py`, `adapters/tracing.py`), silent unless an OTLP endpoint is
  configured.
- Clean Architecture layering (`domain` / `application` / `adapters` / `entrypoints`) enforced by
  `scripts/validate_architecture.py` as part of the quality gate.
- Multi-stage, uv-based, non-root Docker build.
