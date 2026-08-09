# ADR-0010: Runtime operability and unauthenticated probes

## Status

Accepted.

## Context

P1.1 hardened authentication, authorization, OIDC egress, and Streamable HTTP admission. A secure
resource server still needs an explicit process contract for orchestration: deterministic startup
and shutdown, liveness/readiness signals, non-root container execution, and a CI check that the
production image actually starts under restrictive runtime settings.

Using the authenticated MCP `health` tool as an orchestrator probe is inappropriate because it
couples process health to bearer authentication and can trigger token/JWKS work. Requiring the public
resource Host header on probes is also awkward for container and Kubernetes health checks, which
normally address the workload directly.

## Decision

1. Keep the authenticated MCP `health` tool as an MCP example, but do not use it for orchestration.
2. Add exact HTTP operational paths `/livez` and `/readyz` outside bearer authentication.
3. Keep header-count/header-size and duplicate-security-header checks in front of probes.
4. Skip public Host/Origin validation and the MCP request-concurrency limiter for probe paths.
5. Make readiness process-local and tied to the MCP server lifespan. It becomes ready only after the
   lifespan enters and becomes not-ready before shared runtime resources are closed.
6. Do not call OIDC/JWKS or external business dependencies from liveness/readiness probes.
7. Run Uvicorn through a project launcher with explicit workers, backlog, keep-alive, graceful
   shutdown, lifespan-on, WebSocket-disabled, proxy-header-disabled, and server-header-disabled
   settings.
8. Run the container as non-root and verify in CI that it starts with a read-only root filesystem,
   all capabilities dropped, and `no-new-privileges`.

## Rationale

Liveness should answer whether the process itself can make progress; tying it to an authorization
server can cause cascading restarts during an external outage. Readiness is narrower: it signals
that the MCP worker has completed its own startup lifecycle and can accept traffic.

The MCP 2026-07-28 stateless HTTP path does not require sticky sessions, so multiple Uvicorn workers
or replicas can be used without sharing MCP session identity. Per-worker OIDC caches remain local by
design.

Explicit Uvicorn settings make shutdown and protocol surface predictable. The reverse proxy remains
the TLS boundary and must preserve the intended Host header for `/mcp`; forwarded proxy headers are
not trusted by default.

## Consequences

- Probes reveal only `ok`, `ready`, or `not_ready`; no identity or dependency details are exposed.
- A healthy process may remain ready while an authorization server is temporarily unavailable. MCP
  authentication will fail closed independently, without causing a liveness restart loop.
- Operators should set termination grace periods longer than the configured Uvicorn graceful
  shutdown timeout.
- Deployment platforms still own ingress/TLS, network policy, autoscaling, resource limits, and
  secret injection.

## Alternatives rejected

- **Use the MCP `health` tool for probes:** rejected because it requires bearer authentication.
- **Probe OIDC/JWKS from `/readyz`:** rejected because it amplifies dependency incidents and can
  create probe-driven load on the authorization server.
- **Expose probes through the normal Host/Origin gate:** rejected because workload-local probes do
  not naturally carry the public resource authority.
- **Rely on Uvicorn defaults:** rejected because production lifecycle behavior should be explicit
  and reviewable in the repository.
