# ADR 0028: MCP cache-hint security policy

- Status: Accepted
- Date: 2026-09-22

## Context

Protocol revision `2026-07-28` (SEP-2549) adds freshness hints to cacheable results: `ttlMs` (how
long a client may treat the result as fresh) and `cacheScope`. A `public` scope means the result may
be shared across authorization contexts; a `private` scope means it may be reused only within the
context that produced it. MCP Python SDK 2.2 exposes these hints as
`MCPServer(cache_hints={method: CacheHint(...)})`. Without hints, results default to `ttlMs=0`,
`cacheScope="private"`.

In this template, the `tools/list` catalog is **principal dependent**. `ToolAuthorizationMiddleware`
hides tools the caller cannot call, so two tokens with different scopes, roles, tenants or providers
see different catalogs. Caching one principal's catalog as `public` would disclose tool names across
users and could steer a client toward calls that will be denied.

While adding hints, full-stack tests showed that the middleware received the SDK's serialized wire
dict, not a `ListToolsResult`, and returned an empty catalog to every caller. That bug was fixed
first, so the filtering these hints depend on is itself covered by an end-to-end test.

## Decision

Hints are declared once, as `_CACHE_HINTS` in `entrypoints/mcp_server.py`:

```text
server/discover: ttlMs=30000, cacheScope=private
tools/list:      ttlMs=30000, cacheScope=private
```

- `private` is the only permitted scope. `public` is forbidden until executable tests prove a result
  cannot vary by principal, scope, tenant, roles, auth mode or runtime policy.
- The TTL is bounded (30 seconds), so a scope grant or a tool-policy change reaches clients quickly
  without per-request rediscovery.
- No other cacheable methods are hinted. The template exposes no resources or prompts.
- The middleware's fail-closed empty catalog is built without server hints and keeps the SDK-safe
  defaults (`ttlMs=0`, `private`), so a degraded response is never cached as fresh.

## Evidence

`tests/unit/test_tool_discovery_entrypoint.py`, through the real `build_server` wiring, proves:

- `server/discover` and `tools/list` carry `ttlMs=30000` and `cacheScope="private"`;
- two principals with different scopes receive different catalogs, both `private`;
- the policy contains only private, bounded hints for discovery methods known to the SDK;
- the fail-closed fallback is immediately stale and private.

## Consequences

Clients may skip redundant discovery round trips within one authorization context for up to 30
seconds. A client that changes tokens must not reuse a `private` result across them; that behavior
is the client's responsibility under SEP-2549.

Any future attempt to mark a discovery result `public`, or to add per-user resources or prompts,
must first extend these tests and amend this ADR.
