# Production operations

This document describes the runtime contract for the HTTP deployment of
`mcp-server-auth-template`.

## Process model

Use the production launcher:

```bash
python -m mcp_server_auth_template.entrypoints.serve
```

The launcher keeps Uvicorn configuration explicit instead of relying on
environment-dependent defaults. The MCP transport remains stateless and uses JSON responses, so
workers and replicas do not require sticky sessions for MCP 2026-07-28 traffic.

Runtime settings use the `MCP_SERVER_` prefix:

| Variable | Default | Purpose |
| --- | ---: | --- |
| `MCP_SERVER_RUNTIME_HOST` | `0.0.0.0` | Bind host |
| `MCP_SERVER_RUNTIME_PORT` | `8000` | HTTP port |
| `MCP_SERVER_RUNTIME_WORKERS` | `1` | Uvicorn worker processes |
| `MCP_SERVER_RUNTIME_BACKLOG` | `2048` | Socket accept backlog |
| `MCP_SERVER_RUNTIME_KEEP_ALIVE_SECONDS` | `5` | HTTP keep-alive timeout |
| `MCP_SERVER_RUNTIME_GRACEFUL_SHUTDOWN_SECONDS` | `30` | Graceful shutdown deadline |

WebSockets are disabled because this template exposes MCP Streamable HTTP only. Proxy-derived
client/scheme headers are not trusted by the launcher; configure the reverse proxy to preserve the
public `Host` header and terminate TLS at the intended trust boundary.

## Startup preflight

The production launcher revalidates the complete settings model before Uvicorn binds its socket.
The same check can run independently in CI, a deployment pipeline, or a container shell:

```bash
python -m mcp_server_auth_template.entrypoints.preflight
python -m mcp_server_auth_template.entrypoints.preflight --json
```

The preflight is intentionally network-silent: it does not resolve DNS, fetch OIDC metadata, or
refresh JWKS. Its job is to reject unsafe local configuration without making process startup depend
on authorization-server availability.

`APP_ENV=production` enables additional fail-fast invariants:

- the public MCP resource URL must use HTTPS and cannot use reserved placeholder hosts;
- `MCP_SERVER_OIDC_ALLOW_INSECURE_LOOPBACK=true` is forbidden;
- configured browser Origins must use HTTPS and cannot be placeholders;
- generic OIDC issuers and explicit JWKS origins must use HTTPS and cannot be placeholders;
- the checked-in all-zero Entra identifiers are rejected.

The JSON output is allowlisted and deliberately excludes resource URLs, issuer URLs, audiences,
tenant/client identifiers, scopes, headers, tokens, and other credential-shaped values. Validation
failures report only an error category plus Pydantic location/type metadata; invalid input values
are never echoed.

## Operational probes

Two probe endpoints are intentionally outside MCP bearer authentication:

- `GET /livez` returns `200` when the ASGI worker can serve the request.
- `GET /readyz` returns `200` only after the MCP lifespan has entered; otherwise it returns `503`.

Neither probe performs OIDC discovery, JWKS refresh, token verification, or business dependency
calls. This prevents authorization-server incidents or bearer-auth load from turning into false
liveness failures and restart storms.

The probe middleware intercepts these exact paths before OAuth, while the outer admission boundary
still enforces request-header count/size and duplicate security-header rules. Host/Origin checks and
the MCP in-process concurrency limit are skipped for the two probe paths so orchestrators can probe
the Pod/container address directly.

Responses are non-cacheable and contain no build, environment, dependency, or identity details.

## Graceful termination

The image uses `SIGTERM`. Uvicorn stops accepting new work, waits for active responses/tasks, and
then runs the ASGI lifespan teardown. The MCP lifespan marks the worker not-ready before closing the
shared OIDC HTTP client.

Set the orchestrator termination grace period longer than
`MCP_SERVER_RUNTIME_GRACEFUL_SHUTDOWN_SECONDS`. With the default 30-second Uvicorn deadline, a
40-second Pod grace period is a reasonable starting point.

## Container contract

The image:

- uses a multi-stage build from the committed lock file;
- runs as the non-root `app` user;
- supports a read-only root filesystem;
- requires no Linux capabilities for the default HTTP runtime;
- exposes port `8000` by convention;
- includes a Docker health check against `/livez` using Python's standard library and no proxy.

The CI smoke job runs the image with a read-only root filesystem, a small `/tmp` tmpfs, all Linux
capabilities dropped, and `no-new-privileges` enabled.

## Kubernetes baseline

Example probe/security settings:

```yaml
spec:
  terminationGracePeriodSeconds: 40
  containers:
    - name: mcp-server
      ports:
        - name: http
          containerPort: 8000
      startupProbe:
        httpGet:
          path: /readyz
          port: http
        periodSeconds: 2
        failureThreshold: 30
      readinessProbe:
        httpGet:
          path: /readyz
          port: http
        periodSeconds: 5
        failureThreshold: 3
      livenessProbe:
        httpGet:
          path: /livez
          port: http
        periodSeconds: 10
        failureThreshold: 3
      securityContext:
        allowPrivilegeEscalation: false
        readOnlyRootFilesystem: true
        runAsNonRoot: true
        capabilities:
          drop: ["ALL"]
```

Treat this as a baseline, not a complete platform manifest. NetworkPolicy, ingress/TLS, autoscaling,
resource requests/limits, PodDisruptionBudget, secret delivery, and organization-specific policy
remain deployment concerns.

## Checked-in Kubernetes deployment baseline

`deploy/kubernetes/` turns the probe/security sketch above into concrete reference resources:

- a two-replica `Deployment` with `maxUnavailable: 0` rolling updates;
- `startupProbe`, `readinessProbe`, and `livenessProbe` wired to the P1.2a endpoints;
- explicit CPU/memory requests and limits;
- `RuntimeDefault` seccomp, non-root execution, read-only root filesystem, no privilege escalation,
  and all Linux capabilities dropped;
- service-account token automount and service-link environment injection disabled;
- node-level topology spreading;
- a `ClusterIP` Service;
- a `PodDisruptionBudget` that keeps one replica available during voluntary disruptions and allows
  eviction of unhealthy Pods;
- an in-memory, size-bounded `/tmp` volume for the otherwise read-only filesystem.

The image field is intentionally an all-zero digest placeholder. Replace it with an immutable image
digest before deployment. Provider/resource values also use `.invalid` placeholders and must be
replaced.

The repository intentionally does not ship a generic NetworkPolicy or Ingress. OIDC/JWKS egress
addresses and ingress/TLS controllers are platform/provider-specific; a misleading generic policy
would either block required identity traffic or allow substantially more egress than intended. See
`deploy/kubernetes/README.md` for the deployment checklist.
