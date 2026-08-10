# Verification guide

This repository owns the MCP **resource-server** boundary. The companion
[`mcp-client-auth-template`](https://github.com/brunovicco/mcp-client-auth-template) owns the
cross-repository executable reference harness so the pair has one source of truth for OAuth
orchestration.

## Source-level proof

Clone both repositories as siblings:

```text
Projects/
├── mcp-client-auth-template/
└── mcp-server-auth-template/
```

From the client repository:

```bash
./scripts/run_reference_demo.sh \
  --server-root ../mcp-server-auth-template
```

This path starts the server from the current source checkout and a deterministic local OIDC
provider. A successful run proves:

- real server startup and readiness;
- Protected Resource Metadata discovery;
- CIMD-first Authorization Code + PKCE on the client side;
- resource-bound bearer authentication;
- authenticated `whoami`;
- pre-dispatch `403 insufficient_scope`;
- bounded elevated retry for `health`;
- wrong-audience `401`;
- no `Mcp-Session-Id`.

No production credentials or external identity provider are required.

## Observable published-image proof

The observable reference stack is intentionally owned by the companion client:

```bash
./scripts/run_observability_demo.sh --keep
```

A passing run must end with:

```text
P1.7c OBSERVABILITY DEMO PASSED
Collector: positive OTLP receipt
Context:   MCP client/server share one trace_id
Tempo:     trace query succeeded
Grafana:   Tempo datasource provisioned
Privacy:   OAuth/MCP sensitive values absent
```

The proof covers the published server image by immutable digest and verifies:

- a positive OTLP receipt;
- one distributed trace across the client and server;
- `service.name=mcp-server-auth-template` in server spans;
- successful Tempo retrieval;
- Grafana Tempo datasource provisioning;
- absence of OAuth tokens, scopes/resource values and other protected MCP data from telemetry.

Stop the retained stack with the companion client's stop command after inspection.

## Visual evidence

The root README uses three committed assets:

```text
docs/assets/server-reference-demo.gif
docs/assets/server-observability-trace.png
docs/assets/server-observability-trace-detail.png
```

They must come from successful executions of the paths above. Do not use mocked screenshots,
manually edited pass banners or synthetic trace data.

The GIF should show the source-level reference command and its deterministic pass result. Trace
screenshots should make the `mcp-server-auth-template` service/spans visible and, when practical,
show the client/server relationship in the same trace.

Never capture bearer tokens, JWTs, authorization codes, cookies, client secrets, signing material,
full MCP arguments/results, personal data or local machine secrets.

## Boundary

The companion harness is evidence infrastructure, not a runtime dependency of this server. A
production deployment still owns its IdP registration, TLS termination, network policy, secrets,
capacity, telemetry backend, retention and operational controls.
