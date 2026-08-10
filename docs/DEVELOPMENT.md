# Development guide

## Setup

```bash
uv sync --frozen --all-groups
```

`a2a-otel-kit[mcp]` is a core dependency because the ASGI entrypoint always composes its
metadata-only tracing middleware. Export remains network-silent unless `A2A_OTEL_ENABLED=true`
and an OTLP endpoint are configured. Tests use disabled or in-memory telemetry and never require a
real collector.

## Run checks

```bash
uv run python scripts/quality_gate.py
```

## Container

```bash
docker build -t mcp-server-auth-template .
docker run --rm \
  --env-file .env \
  -p 8000:8000 \
  mcp-server-auth-template
```

`Dockerfile` is a multi-stage, uv-based build: a `builder` stage installs the locked
dependencies and builds the package, then only the resulting virtualenv and source are copied
into a slim, non-root runtime image. The shipped `CMD` runs the real ASGI entrypoint
(`uvicorn mcp_server_auth_template.entrypoints.mcp_server:create_app --factory --host 0.0.0.0
--port 8000`); provider configuration (`MCP_SERVER_*` variables, see `.env.example`) is supplied
at container-run time via the environment, never baked into the image. Adjust `.dockerignore` if
new top-level files or directories need to be excluded from the build context.

The container command above expects a local `.env` with safe development values. If a development
OIDC provider runs on the Docker host, do not configure it as container-local `localhost`; expose it
through a deliberate host address such as `host.docker.internal` where supported, or place both
services on the same Docker network.

## Local configuration

Copy `.env.example` to `.env` for local development and replace only the provider/profile values
you need. Docker's `--env-file` passes the same variable names into the container. Never commit
`.env` or real credentials.

## Codex

- Run `/status` to inspect the active project and configuration.
- Run `/hooks` to inspect configured hooks.
- Run `codex --version` from the shell for an installation check.
- Use `$plan-change` before complex work.
- Use `$quality-gate` before completion.
- Use `$prepare-pr` to produce a reviewable PR description.

Codex discovers durable project guidance in `AGENTS.md`, workflows in `.agents/skills/`, and
trusted project configuration and hooks under `.codex/`. Skills do not silently delegate work;
the active agent follows their checked-in workflow and the user's requested scope.
