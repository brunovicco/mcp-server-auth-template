# ADR-0008: Harden the Streamable HTTP transport boundary

- Status: Accepted
- Date: 2026-08-08

## Context

MCP 2026-07-28 removes protocol-level HTTP sessions and the `Mcp-Session-Id`
header. Each modern request is self-contained. The MCP Python SDK v2.0.0 still
supports handshake-era clients, but its Streamable HTTP public API defaults to
stateful HTTP for compatibility and to a 4 MiB body limit.

The template is an authenticated resource server with no requirement for
server-initiated requests, resumability, or hidden transport state. Keeping
stateful sessions or long-lived GET streams would therefore add memory and
routing state without serving a template requirement.

The MCP transport specification also requires Origin validation to prevent DNS
rebinding. In the SDK, Host/Origin validation happens inside the MCP endpoint,
after Starlette's authentication middleware has already run. A hostile request
should not be able to force token verification before basic transport admission.

## Decision

The production template uses the SDK's public Streamable HTTP API with:

- `stateless_http=True`;
- `json_response=True`;
- a 1 MiB request body limit, configurable within a bounded range;
- DNS-rebinding protection always enabled;
- allowed Host values derived from `MCP_SERVER_RESOURCE_SERVER_URL`, with
  explicit additional hosts for reverse-proxy deployments;
- allowed Origin values derived from the resource-server origin, with explicit
  additional origins for browser clients.

An outer `HttpTransportAdmissionMiddleware` runs before authentication and:

- repeats Host/Origin and POST Content-Type validation before JWT work;
- caps request-header count and aggregate header bytes;
- rejects duplicate security-sensitive singleton headers;
- rejects simultaneous `Content-Length` and `Transfer-Encoding` framing;
- admits only POST on `/mcp` because this template does not expose a standalone
  SSE/session channel;
- caps concurrent in-process HTTP requests and returns `503` with `Retry-After`
  when saturated.

The SDK performs its own Host/Origin validation again inside the transport. The
outer check is deliberate defense in depth, not a replacement.

Plain HTTP is accepted for `MCP_SERVER_RESOURCE_SERVER_URL` only when the host
is an IP-literal loopback address. Non-loopback deployments must advertise an
HTTPS resource URL.

## Consequences

- Modern MCP 2026-07-28 traffic is naturally stateless and never mints or trusts
  `Mcp-Session-Id`.
- Reusing a legacy-looking `Mcp-Session-Id` cannot carry a principal from one
  HTTP request to another; authentication remains request-scoped.
- Handshake-era clients can still send POST requests, but this template does not
  preserve legacy transport sessions, GET SSE channels, DELETE session teardown,
  or server-initiated callbacks.
- Large legitimate tool inputs may require increasing
  `MCP_SERVER_TRANSPORT_MAX_REQUEST_BODY_BYTES`; the configured ceiling remains
  bounded to prevent accidental unlimited buffering.
- This process-local concurrency cap is not a distributed rate limiter. A
  production deployment should still enforce connection, rate, timeout, and
  header limits at its ingress proxy/load balancer.
