# ADR-0001: Adopt Clean Architecture dependency boundaries

- Status: Accepted
- Date: 2026-08-07

## Context

The service requires business rules to remain independent from web frameworks, persistence, messaging, and external SDKs.

## Decision

Use the dependency direction documented in `docs/ARCHITECTURE.md` and enforce it through package structure, review, tests, and import-contract tooling when introduced.

## Consequences

- Domain code remains independently testable.
- Boundary translation is explicit.
- Small CRUD features should not receive unnecessary abstraction.
- More mapping code is accepted where it protects domain semantics.

### Applied to this template

The one concrete decision this boundary forces in this repository is
`application/auth_ports.py`: `DiscoveryPort` and `KeyResolverPort` are declared as `Protocol`s at
the application layer, and `adapters/generic_oidc_token_verifier.py` /
`adapters/entra_token_verifier.py` depend on those protocols rather than importing
`httpx`/`PyJWKClient` directly. That indirection exists for one reason - it lets
`tests/unit/test_*_token_verifier.py` inject fakes and verify signature/issuer/audience/tenant
logic against a locally-signed JWT, with no network call and no real authorization server, ever.
Without the port, verifying rejection logic (expired token, wrong tenant, wrong audience) would
require either live network I/O in tests or mocking a third-party HTTP client's internals - the
protocol boundary is what keeps the test suite fast, offline, and honest about what it's
checking.
