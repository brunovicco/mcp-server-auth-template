# ADR-0007: Harden the OIDC discovery and JWKS trust chain

- Status: Accepted
- Date: 2026-08-08

## Context

This resource server validates bearer-token signatures using metadata and keys obtained from the
configured authorization server. Before this decision, discovery used a shared `httpx` client while
JWKS retrieval was delegated to `PyJWKClient`. That split left several trust-boundary gaps:

- the `issuer` returned by discovery was not required to equal the configured issuer;
- an advertised `jwks_uri` could redirect or point at an unexpected/private network destination;
- `PyJWKClient` owned its network path, so this service could not apply one SSRF policy to DNS,
  redirects, timeouts, proxies or response sizes;
- DNS validation followed by a normal hostname connection would still permit rebinding between the
  validation and connect operations;
- an attacker could force repeated JWKS refreshes with arbitrary unknown `kid` values;
- key selection did not make the expected JWT algorithm/key-type relationship explicit at the
  resolver boundary.

The configured issuer is operator-controlled configuration and is therefore the only appropriate
root of trust. Metadata returned over the network must not be allowed to expand that boundary by
default.

## Decision

Use one outbound OIDC security boundary for both discovery and JWKS retrieval.

### Issuer and endpoint trust

- The configured issuer is preserved exactly and discovery accepts metadata only when its `issuer`
  is byte-for-byte identical.
- Production issuer URLs require HTTPS. HTTP is available only behind the explicit
  `MCP_SERVER_OIDC_ALLOW_INSECURE_LOOPBACK=true` development switch, and the resolved addresses
  must all be loopback.
- `jwks_uri` is same-origin with the issuer by default. Generic providers that legitimately host
  keys elsewhere must explicitly list exact additional origins with
  `MCP_SERVER_GENERIC_JWKS_ALLOWED_ORIGINS`.
- Entra tenant IDs must be tenant-specific UUIDs; aliases such as `common`, `organizations` and
  path-like values are rejected before the issuer URL is constructed.

### SSRF and transport boundary

- Resolve every hostname before connecting and reject any non-global answer in production,
  including private, loopback, link-local, multicast, unspecified and reserved addresses.
- Connect to the validated IP address while preserving the original `Host` header and TLS SNI name,
  preventing a second DNS lookup from reopening a rebinding window.
- Do not follow redirects.
- Do not use environment proxy configuration for this dedicated control-plane client.
- Accept only GET operations, request identity encoding, reject compressed responses, and impose
  short network timeouts plus raw response-size ceilings (64 KiB discovery, 512 KiB JWKS).

### Metadata and JWKS parsing

- Require JSON media types and strict UTF-8 JSON objects.
- Reject duplicate JSON member names rather than allowing parser last-value-wins behavior.
- Bound a JWKS to 64 keys and reject duplicate `kid` values.
- Require a bounded, non-empty JWT `kid` and permit only `RS256` and `ES256`.
- A usable JWK must be a signing/verification key; when `alg` is present it must match the token
  header. `RS256` requires RSA and `ES256` requires EC P-256.
- Construct `PyJWK` with the already-approved token algorithm explicitly.

### Cache and rotation behavior

- Cache discovery metadata for one hour after full validation.
- Cache JWKS documents for five minutes.
- On a `kid` miss, refresh once to support key rotation, then fail closed if no compatible key
  appears.
- Rate-limit forced refreshes with a 30-second per-JWKS cooldown so arbitrary `kid` values cannot
  turn token verification into unbounded outbound traffic.

### Dependency floor

Require `PyJWT>=2.13`. PyJWT 2.13.0 fixes the algorithm allow-list bypass affecting `PyJWK` /
`PyJWKClient` verification in versions through 2.12.1. The resolver still applies its own explicit
algorithm/key binding; the dependency floor is defense in depth, not a substitute for that policy.

## Consequences

- OIDC discovery/JWKS failures remain indistinguishable to callers: token verification returns an
  authentication failure rather than exposing network or parsing detail.
- Generic providers with cross-origin JWKS endpoints require explicit configuration.
- Local E2E environments using an HTTP loopback issuer must opt in explicitly.
- A newly rotated key can be rejected for at most the forced-refresh cooldown after another
  unknown-key refresh. This availability trade-off is intentional to bound attacker-triggered IdP
  traffic.
- The resource server no longer depends on `PyJWKClient` network behavior; all identity-provider
  network access is visible at one adapter boundary and can be tested deterministically.
