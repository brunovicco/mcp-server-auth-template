# Development guide

## Setup

```bash
uv sync --frozen --all-groups
```

`a2a-otel-kit[mcp]` is a core dependency because the ASGI entrypoint always composes its
metadata-only tracing middleware. Export remains network-silent unless `A2A_OTEL_ENABLED=true` and a
complete OTLP endpoint are configured. Tests use disabled or in-memory telemetry and do not require
a real collector.

## Run checks

```bash
uv run python scripts/quality_gate.py
```

For focused feedback:

```bash
uv run python scripts/quality_gate.py --list
uv run python scripts/quality_gate.py --check tests
```

The complete gate remains the definition of done.

## Container

```bash
docker build -t mcp-server-auth-template .
docker run --rm \
  --env-file .env \
  -p 8000:8000 \
  mcp-server-auth-template
```

`Dockerfile` is a multi-stage uv-based build. The builder installs the locked environment and the
runtime executes as a non-root user. Provider configuration is supplied at runtime via environment
variables and is never baked into the image.

The container command expects a local `.env` with safe development values. If a development OIDC
provider runs on the Docker host, do not configure it as container-local `localhost`; use a
deliberate host address such as `host.docker.internal` where supported, or place both services on
the same Docker network.

## Local configuration

Copy `.env.example` to `.env` and replace only the provider/profile values required for local
development. Never commit `.env`, signing keys, bearer tokens or real credentials.

## Cross-repository verification

With the companion client cloned beside this repository:

```bash
cd ../mcp-client-auth-template
./scripts/run_reference_demo.sh \
  --server-root ../mcp-server-auth-template
```

See `docs/VERIFICATION.md` for source-level and observable evidence.

## Local tooling

Personal editor, coding-agent and automation configuration belongs in local user/project state and
is intentionally excluded from version control. The public repository contains only durable
project-owned runtime, tests, CI, policy and documentation.
