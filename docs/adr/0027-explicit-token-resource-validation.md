# ADR 0027: Explicit token-resource validation policy

- Status: Accepted
- Date: 2026-09-22

## Context

MCP Python SDK 2.2 adds `AuthSettings.validate_token_resource`. When it is `True`, the SDK bearer
middleware refuses any token whose `AccessToken.resource` is not equal to
`AuthSettings.resource_server_url`. Leaving it unset while `resource_server_url` is configured emits
`MCPDeprecationWarning` and currently behaves as `False`. MCP SDK 3.0 changes that default to `True`.

If this repository relied on the default, a future SDK upgrade could change authorization semantics
with no decision recorded here. It could also break real providers:

- **Microsoft Entra ID** access tokens carry the API application's client ID (a GUID) in `aud`,
  never the public MCP URL.
- **Generic OIDC** authorization servers often use an API identifier such as `api://...`, or an
  audience that differs from the MCP URL in path or trailing slash.

Exact string equality between the provider audience and the MCP HTTP URL is therefore the wrong
rule. It would reject valid tokens while adding nothing that the verifiers do not already enforce.

The template already enforces the audience at the trust boundary it owns.
`GenericOidcTokenVerifier` calls `jwt.decode(..., audience=<configured audience>, issuer=...)` with
`exp`, `iat`, `iss`, `aud` and `sub` required, and reports the configured audience as
`AccessToken.resource`. `EntraTokenVerifier` delegates signature, issuer, audience and expiry
validation to it and adds tenant (`tid`) binding.

## Decision

Resource-server settings are built by one helper, `_build_auth_settings`, which always passes
`validate_token_resource=False`.

Audience enforcement stays in the provider-specific token verifier. This does not disable resource
validation. The invariant for every accepted bearer token is:

```text
accepted token
    =>
valid signature (JWKS from the pinned issuer)
AND expected issuer
AND unexpired
AND provider audience == configured audience
AND (Entra) configured tenant
```

Pytest promotes `mcp.MCPDeprecationWarning` to an error, so leaving the setting implicit cannot
pass CI.

## Evidence

`tests/unit/test_token_resource_contract.py` proves:

- both providers build `AuthSettings` with `validate_token_resource` explicitly set to `False`;
- a token whose audience is the provider API identifier (not the MCP URL) is accepted end to end;
- tokens minted for another API, for the bare MCP URL, or for a sibling path get `401` end to end;
- the counterfactual: enabling SDK string equality rejects that same valid provider token.

`tests/unit/test_generic_oidc_token_verifier.py` covers wrong, multi-valued and missing audiences.
`tests/unit/test_entra_token_verifier.py` covers Graph, other-API and MCP-URL audiences.
`tests/unit/test_mcp_deprecation_gate.py` proves an implicit policy fails the suite.

## Consequences

The authorization semantics no longer depend on an SDK default, and MCP 3's default flip is a
no-op for this repository.

Deployments whose authorization server does bind `aud` to the RFC 8707 `resource` exactly as the
MCP URL could enable SDK checking as defense in depth. That would make the generic profile
provider-specific and is out of scope here.

Revisit this decision if the SDK gains provider-aware resource matching (for example, a
configurable accepted-audience set), or if the MCP authorization specification requires the
resource server to compare `aud` to its canonical URL.
