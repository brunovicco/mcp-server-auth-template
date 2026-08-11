# MCP Authorization Implementer Report

**Report date:** 2026-08-11
**MCP authorization profile:** `2026-07-28`
**Audience:** MCP Authorization Interest Group and Tool Scopes Working Group
**Status:** implementation experience report; not a conformance certification

## Purpose

This report documents how the paired `mcp-server-auth-template` and
`mcp-client-auth-template` implement and exercise the MCP `2026-07-28`
HTTP authorization profile.

The report is evidence-first. It distinguishes project-owned behavior from behavior delegated to
the official MCP Python SDK, and it records important requirements that are not independently
exercised by the deterministic reference pair. A status in this report therefore means exactly what
the cited evidence proves; it is not a claim of exhaustive OAuth or MCP certification.

The Authorization Interest Group explicitly accepts deployment experience and implementer reports,
including client registration, enterprise IdP integration, audience confusion, scope granularity
and step-up authorization. The active Tool Scopes Working Group is directly relevant to the
per-tool scope and client scope-accumulation behavior exercised here.

## Reproducible snapshot

| Component | Public baseline | Commit |
| --- | --- | --- |
| MCP server | `v0.6.2` | `d5cde4530567c8aec5ca275eec711eb55b33fbce` |
| MCP client | `v0.6.0` | `fba0870e5bcbe961c0a56c483ebedfcede46db45` |
| MCP specification | `2026-07-28` | `modelcontextprotocol/modelcontextprotocol@b25c0874bf0ba699a58e21ef06f659d839659de3` |

The server's later `main` commit
`3410e14cdcf2833a431f487a2ed06ef3271edff4` adds secure Official MCP Registry publication
automation only; it does not change the authorization runtime represented by `v0.6.2`.

The server is published in the Official MCP Registry as
`io.github.brunovicco/mcp-server-auth-template@0.6.2`.

## Status vocabulary

| Status | Meaning |
| --- | --- |
| **PAIR-E2E** | Exercised through the real client + real server with a deterministic local authorization server |
| **UNIT** | Explicit project-owned unit/contract evidence exists |
| **SDK+E2E** | Core behavior is delegated to the official MCP Python SDK and exercised through the pair |
| **SUPPORTED / NOT LIVE-VERIFIED** | Implementation path exists, but no live external IdP is part of this deterministic report |
| **NOT INDEPENDENTLY EXERCISED** | Behavior may be provided by the SDK or protocol stack, but this report has no focused proof for the full normative condition |
| **OUT OF SCOPE** | Requirement applies to another role or deployment boundary |

## Executive summary

The strongest verified path is the generic-OIDC interactive flow:

```text
unauthenticated MCP request
→ RFC 9728 Protected Resource Metadata
→ authorization-server metadata discovery
→ CIMD-first or DCR fallback client identity
→ Authorization Code + PKCE S256
→ RFC 8707 resource on authorization request
→ RFC 9207 issuer-bound authorization response
→ resource-bound token exchange
→ bearer-authenticated MCP request
→ per-tool 403 insufficient_scope when needed
→ reauthorization with prior + challenged scope union
→ one bounded retry of the undispatched operation
```

The same resource-server boundary also rejects wrong issuer, wrong audience and expired bearer
tokens before MCP dispatch. The server explicitly prevents inbound MCP bearer tokens from being sent
on its outbound OIDC control-plane requests.

Microsoft Entra ID is implemented as a separate pre-registered public-client/resource-server
profile. The source and unit suite cover tenant/issuer/resource boundaries, while live Entra
authorization remains outside this deterministic report.

## Normative implementation matrix

### Protected Resource Metadata and authorization-server discovery

| Requirement | Role | Status | Evidence / notes |
| --- | --- | --- | --- |
| MCP server implements RFC 9728 Protected Resource Metadata | Server MUST | **SDK+E2E** | `MCPServer(..., auth=AuthSettings(...))`; pair E2E completes PRM-driven discovery |
| PRM contains authorization-server location | Server MUST | **SDK+E2E** | MCP Python SDK owns PRM generation; server supplies exact `issuer_url` and `resource_server_url` |
| Client uses PRM for authorization-server discovery | Client MUST | **SDK+E2E** | Cross-repository auth flow starts from protected MCP request and reaches discovered AS |
| Client parses `WWW-Authenticate` / `resource_metadata` | Client MUST | **SDK+E2E** | Positive protected-resource challenge path exercised |
| Client falls back to both RFC 9728 well-known locations when challenge metadata is absent | Client MUST | **NOT INDEPENDENTLY EXERCISED** | No focused pair scenario removes `resource_metadata` and proves both fallback probes |
| Client supports RFC 8414 and OIDC discovery | Client MUST | **SDK+E2E / NOT EXHAUSTIVE** | Fake AS publishes both endpoints; deterministic flow succeeds, but every path-order variant is not independently asserted |
| Discovered issuer must exactly match expected issuer | Client MUST | **PAIR-E2E + UNIT** | Changed-AS registration is discarded; RFC 9207 and outbound trust boundaries are separately tested |
| Multiple authorization servers keep separate credential/token state | Client MUST | **PARTIAL** | Issuer-bound stored registration is discarded when AS changes; active multi-AS selection is not exercised |

### Client registration

| Requirement | Role | Status | Evidence / notes |
| --- | --- | --- | --- |
| Client obtains a client ID before authorization | Client MUST | **PAIR-E2E** | CIMD and DCR paths both reach authenticated `whoami` |
| Pre-registration support | Client SHOULD | **SUPPORTED / NOT LIVE-VERIFIED** | Entra public client is explicitly pre-registered and secret-free |
| Client ID Metadata Documents | Client/AS SHOULD | **PAIR-E2E, CLIENT-SELECTION ONLY** | AS advertises `client_id_metadata_document_supported=true`; HTTPS metadata URL becomes `client_id`; DCR count remains zero |
| Hosted CIMD document is fetched and validated by an external AS | Deployment / AS | **NOT INDEPENDENTLY EXERCISED** | Fake AS treats the configured CIMD URL as pre-validated fixture data |
| DCR fallback | Client MAY | **PAIR-E2E** | Generic flow registers once when CIMD is unavailable and then completes authorization/token exchange |
| DCR `application_type` interoperability | Client MUST when DCR is used | **NOT INDEPENDENTLY ASSERTED** | Fake AS returns a native registration; this report does not assert the exact outbound DCR request field |
| DCR/pre-registered credentials bound to issuer | Client MUST | **PAIR-E2E** | Stale registration for another issuer is discarded and replaced before use |

### Authorization Code, PKCE and mix-up protection

| Requirement | Role | Status | Evidence / notes |
| --- | --- | --- | --- |
| PKCE support checked from AS metadata | Client MUST | **SDK+E2E** | Fake AS advertises `code_challenge_methods_supported=["S256"]`; full flow succeeds |
| PKCE uses S256 | Client MUST | **PAIR-E2E** | Fake AS rejects non-S256 authorization requests and recomputes S256 from `code_verifier` at token exchange |
| Authorization response expected issuer is recorded with flow state | Client MUST | **SDK+E2E** | Stored client/flow issuer is used by the SDK; mismatch test proves issuer validation precedes token exchange |
| RFC 9207 `iss` present and equal | Client MUST validate | **PAIR-E2E** | Normal flow emits `iss`; negative mismatch raises `OAuthFlowError` |
| RFC 9207 mismatch is rejected before token endpoint | Client MUST | **PAIR-E2E** | Negative test observes one authorization and zero token exchanges |
| Missing-`iss` matrix for every metadata-advertisement combination | Client MUST | **NOT INDEPENDENTLY EXERCISED** | Focused test covers mismatch, not all four normative combinations |
| `state` is used in the authorization flow | Client SHOULD | **SDK+E2E** | Pair carries state through the loopback callback |
| Explicit state-mismatch rejection | Client SHOULD | **NOT INDEPENDENTLY EXERCISED** | No focused negative pair case in this report |

### Resource indicators and token audience

| Requirement | Role | Status | Evidence / notes |
| --- | --- | --- | --- |
| `resource` included in authorization request | Client MUST | **PAIR-E2E** | Fake AS records authorization-request resource |
| `resource` included in token request | Client MUST | **PAIR-E2E** | Fake AS requires token-request resource and requires it to equal authorization-request resource |
| Token is specifically bound to MCP resource | Client/Server MUST | **PAIR-E2E** | Fake AS mints JWT `aud` from resource; server requires exact configured audience |
| Wrong resource/audience rejected | Server MUST | **PAIR-E2E** | Deliberately wrong-audience token returns `401` |
| Wrong issuer rejected | Server MUST | **PAIR-E2E** | Deliberately wrong-issuer token returns `401` |
| Expired token rejected | Server MUST | **PAIR-E2E** | Deliberately expired token returns `401` |
| Signature, issuer, audience and expiry validated | Server MUST | **UNIT + PAIR-E2E** | Generic verifier requires `exp`, `iat`, `iss`, `aud`, `sub` and validates signature/issuer/audience |
| Inbound bearer token is never passed through to upstream APIs | Server MUST NOT | **UNIT** | OIDC outbound transport rejects any `Authorization` header before network I/O |

### Bearer-token transport and token storage

| Requirement | Role | Status | Evidence / notes |
| --- | --- | --- | --- |
| Bearer access token uses HTTP `Authorization` header | Client MUST | **SDK+E2E** | Every authenticated MCP request in the pair reaches server token verification through bearer middleware |
| Token must not be sent in URI query string | Client MUST NOT | **NOT INDEPENDENTLY NEGATIVE-TESTED** | Positive SDK path uses header; no dedicated query-token rejection scenario is claimed |
| Client stores OAuth state/tokens securely | Client MUST | **UNIT / REFERENCE PROFILE** | In-memory storage and fail-closed POSIX file storage (`0700` directory, `0600` regular file, no symlink/hard-link traversal, atomic replacement) |
| File storage is suitable for multi-user services | Deployment | **OUT OF SCOPE** | Adapter explicitly targets one local POSIX user; use keyring/secret manager for other deployments |

### Communication and discovery egress hardening

| Requirement | Role | Status | Evidence / notes |
| --- | --- | --- | --- |
| Production authorization endpoints use HTTPS | Client/Server MUST | **UNIT** | Client and server outbound OAuth/OIDC policies reject non-loopback HTTP |
| Local HTTP is limited to explicit loopback development profile | Reference profile | **UNIT + PAIR-E2E** | Deterministic E2E uses explicit loopback opt-in; private LAN/non-loopback targets remain rejected |
| Redirect URI is loopback or HTTPS | Client MUST | **UNIT / CONFIG CONTRACT** | Reference CLI uses IP-literal loopback redirect; production rules remain strict |
| OAuth discovery egress resists SSRF/DNS rebinding | Security hardening | **UNIT** | Client pins validated DNS result, preserves Host/SNI, rejects private/mixed answers and validates redirects hop-by-hop |
| OIDC discovery/JWKS egress never carries caller bearer | Server MUST NOT passthrough | **UNIT** | Explicit no-token-passthrough test |

### Scopes, per-tool authorization and step-up

| Requirement | Role | Status | Evidence / notes |
| --- | --- | --- | --- |
| Server provides scope guidance in `WWW-Authenticate` | Server SHOULD | **UNIT + PAIR-E2E** | Under-scoped request returns `403`, `error="insufficient_scope"`, `scope=...`, and `resource_metadata=...` |
| Challenge scope is authoritative for current operation | Client MUST | **PAIR-E2E** | `health` challenge drives reauthorization for `mcp:tools:health` |
| Client preserves prior grant during step-up | Client SHOULD | **PAIR-E2E** | Second authorization requests `mcp:tools:call mcp:tools:health` |
| Under-scoped operation is not dispatched before upgrade | Server | **PAIR-E2E + UNIT** | Verifier returns no access token for current request; outer middleware replaces SDK 401 with 403 before MCP dispatch |
| Retry is bounded | Reference profile | **PAIR-E2E** | SDK retries the undispatched operation once after successful reauthorization |
| Per-tool OAuth scope advertisement before invocation | Emerging Tool Scopes topic | **NOT PROVIDED AS A PROACTIVE CATALOG CONTRACT** | Current pair is challenge-driven; this is a primary feedback item for the Tool Scopes WG |
| Semantic scope hierarchy / broader-scope implication | Emerging Tool Scopes topic | **NOT CLAIMED** | Current reference policy uses explicit scope strings and exact set membership |

## Optional extension profile: OAuth client credentials

The pair also exercises the optional
`io.modelcontextprotocol/oauth-client-credentials` extension as a separate generic-OIDC profile.

Evidence proves:

- pre-registered machine client ID;
- `client_secret_basic` at the token endpoint;
- no browser authorization;
- no CIMD or DCR;
- RFC 8707 resource-bound token acquisition;
- authenticated `whoami`;
- non-interactive scope step-up from `mcp:tools:call` to
  `mcp:tools:call mcp:tools:health`;
- invalid machine credentials fail closed without the secret appearing in the raised error.

This is not a claim of Entra client-credentials interoperability. Entra app-only authorization uses
provider-specific `{resource}/.default`, `idtyp=app` and app-role policy and remains a separate
deployment-validation concern.

## Project-owned behavior vs SDK-delegated behavior

The report intentionally does not attribute SDK behavior to project code.

**Official MCP Python SDK owns:**

- Protected Resource Metadata route generation;
- base OAuth client orchestration;
- bearer authentication middleware;
- core CIMD/DCR selection machinery;
- PKCE/resource mechanics used by `OAuthClientProvider`;
- the HTTP MCP client/server protocol machinery.

**These repositories add or tighten:**

- exact generic-OIDC and Entra issuer/audience token validation adapters;
- Entra tenant pinning and pre-registered public-client profile;
- SSRF-resistant, DNS-pinned OAuth/OIDC control-plane transports;
- fail-closed local token storage;
- per-tool authorization policy;
- `403 insufficient_scope` translation before dispatch;
- bounded progressive scope behavior exercised across the pair;
- explicit no-token-passthrough boundary;
- deterministic cross-repository positive and negative evidence.

## Reproduce the deterministic pair

Clone both repositories as siblings and use the public baselines above.

```bash
git clone https://github.com/brunovicco/mcp-server-auth-template.git
git clone https://github.com/brunovicco/mcp-client-auth-template.git

git -C mcp-server-auth-template checkout v0.6.2
git -C mcp-client-auth-template checkout v0.6.0

cd mcp-client-auth-template
uv sync --frozen --all-groups
uv pip install --python .venv/bin/python -e ../mcp-server-auth-template

.venv/bin/python scripts/cross_repository_contract.py \
  --peer-root ../mcp-server-auth-template

MCP_E2E_SERVER_ROOT="$PWD/../mcp-server-auth-template" \
  .venv/bin/python -m pytest \
  -m e2e tests/e2e/test_companion_auth_flow.py --no-cov
```

The deterministic authorization server uses only synthetic identities and local signing keys. No
production IdP credential is required.

## Deliberately unclaimed / open evidence

This report does **not** claim that the pair has independently proven:

1. every RFC 9728 fallback probe when `resource_metadata` is absent from the 401 challenge;
2. every RFC 8414/OIDC discovery URL ordering variant, including every issuer-path shape;
3. active selection among multiple simultaneous authorization servers;
4. an authorization server fetching a hosted CIMD document over the public Internet;
5. every RFC 9207 present/absent `iss` combination;
6. a negative `state` mismatch scenario;
7. URI-query bearer-token rejection as a focused client test;
8. semantic scope hierarchies or alternative/superset permission models;
9. live Entra ID, Okta, Ping, Keycloak or other external IdP interoperability;
10. secure multi-user or non-POSIX token persistence;
11. authorization behavior for non-HTTP MCP transports.

These are evidence boundaries, not silent assumptions.

## Feedback topics for the Authorization IG / Tool Scopes WG

### 1. Proactive per-tool scope discovery

The current pair can decide the required scope before dispatch and return a precise
`403 insufficient_scope` challenge. It does not proactively advertise per-tool OAuth requirements
in the tool catalog.

**Question:** what protocol-level representation should clients use to understand likely tool scopes
before the first denied invocation without making the tool catalog itself an authorization oracle?

### 2. Scope accumulation and bounded replay

The current client preserves the prior grant, unions the challenged scope, reauthorizes, and retries
the undispatched operation once.

**Question:** should the union + bounded-replay behavior become a stronger cross-SDK interoperability
contract, and how should clients handle alternative scope sets rather than simple additive scopes?

### 3. Scope semantics beyond exact strings

The reference pair deliberately treats scopes as explicit strings and does not infer hierarchy.

**Question:** should broader/narrower scope relationships remain authorization-server policy, be
advertised by MCP metadata, or move to the Fine-Grained Authorization work rather than Tool Scopes?

### 4. Pre-dispatch scope decision

MCP `2026-07-28` routing metadata lets this server determine the requested tool before dispatch.
The SDK still validates the mirrored routing data against the JSON-RPC request, so the early scope
decision is not the final authorization decision.

**Question:** is this two-stage pattern the intended interoperability boundary for progressive
authorization, or should the SDK expose a first-class pre-dispatch authorization hook?

### 5. Enterprise registration reality

Generic OIDC can use CIMD-first with DCR fallback. Entra uses a pre-registered public client pinned
to one tenant because CIMD/DCR are not the practical enterprise path for that profile.

**Question:** which enterprise registration/deployment constraints should be captured as
implementation guidance versus extension work?

## Evidence index

### MCP specification

- `docs/specification/2026-07-28/basic/authorization/index.mdx`
- `docs/specification/2026-07-28/basic/authorization/authorization-server-discovery.mdx`
- `docs/specification/2026-07-28/basic/authorization/client-registration.mdx`
- `docs/specification/2026-07-28/basic/authorization/security-considerations.mdx`
- `docs/community/interest-groups/auth.mdx`

Specification snapshot:
`modelcontextprotocol/modelcontextprotocol@b25c0874bf0ba699a58e21ef06f659d839659de3`.

### Server evidence

- `src/mcp_server_auth_template/entrypoints/mcp_server.py`
- `src/mcp_server_auth_template/adapters/generic_oidc_token_verifier.py`
- `src/mcp_server_auth_template/adapters/entra_token_verifier.py`
- `src/mcp_server_auth_template/adapters/progressive_token_verifier.py`
- `src/mcp_server_auth_template/adapters/progressive_auth_http.py`
- `tests/unit/test_progressive_auth_http.py`
- `tests/unit/test_oidc_no_token_passthrough.py`
- `tests/unit/test_generic_oidc_token_verifier.py`
- `tests/unit/test_entra_token_verifier.py`

### Client / pair evidence

- `src/mcp_client_auth_template/adapters/generic_oidc_client_auth.py`
- `src/mcp_client_auth_template/adapters/entra_client_auth.py`
- `src/mcp_client_auth_template/adapters/oauth_discovery_security.py`
- `src/mcp_client_auth_template/adapters/token_storage.py`
- `scripts/e2e_fake_oidc_as.py`
- `tests/e2e/test_companion_auth_flow.py`
- `.github/workflows/e2e.yml`
- `docs/COMPATIBILITY.md`

## Interpretation

The useful claim from this report is not “fully compliant.”

The useful claim is narrower and reproducible:

> The paired templates implement and continuously exercise a substantial MCP `2026-07-28`
> authorization reference profile, including resource metadata discovery, Authorization Code +
> PKCE, RFC 8707 resource binding, RFC 9207 mix-up protection, exact resource-server token
> validation, challenge-driven per-tool scope step-up, issuer-bound client registration state and
> explicit no-token-passthrough behavior; the report also names the normative and deployment cases
> that are not independently exercised.

That distinction is intentional and should make external review easier.
