# ADR-0019: Adopt `a2a-otel-kit` at the MCP ASGI boundary

- Status: Accepted
- Date: 2026-08-09

## Context

The repository contained a hand-rolled OpenTelemetry `TelemetryLifecycle`, safe tracer/span
wrappers, and propagation helpers behind an optional `observability` extra. That stack was tested
in isolation but never composed into `create_app()`, so production MCP requests had no inbound
trace-context continuation. The companion client already uses `a2a-otel-kit`, and version 0.6.0
adds native MCP SDK 2.x/HTTPX2 support while preserving its metadata-only ASGI boundary.

Keeping both implementations would create two environment-variable contracts, sanitization
policies, providers, and lifecycle owners without adding runtime evidence.

## Decision

- Depend on `a2a-otel-kit[mcp]>=0.6,<0.7` as a core runtime dependency.
- Configure one `Observability` facade in `create_app()` with the server's fixed identity.
- Insert `TracingASGIMiddleware` inside `HttpTransportAdmissionMiddleware` and outside operational
  probes, authentication, authorization, and tool dispatch.
- Shut the facade down from the MCP server lifespan after readiness is cleared and the OIDC HTTP
  client is closed; also shut it down if application construction fails.
- Remove the unused local OpenTelemetry lifecycle and its optional install extra.
- Retain the separate Langfuse `LlmCallObserver` and `tracing` extra; it serves a different,
  explicitly content-governed use case.

## Consequences

- Server and client spans share one supported W3C propagation contract across the companion pair.
- Observability remains network-silent by default and requires explicit `A2A_OTEL_*` configuration.
- Hardened transport admission remains the outer request boundary.
- Spans use fixed low-cardinality names and never record credentials, MCP arguments/results,
  request or response bodies, arbitrary headers, URLs, baggage, or exception text.
