# syntax=docker/dockerfile:1
#
# Multi-platform Linux image:
#   linux/amd64 -> Windows Docker Desktop/WSL2, Intel Mac, x86_64 Linux
#   linux/arm64 -> Apple Silicon Mac, ARM64 Linux
#
# Buildx selects the target platform through --platform.

ARG PYTHON_IMAGE=python:3.13-slim@sha256:8d9d0b8bcf6506481eae4907c18f5e3e7902e629f5f6d684f9e7c32e85e3ddf0
ARG UV_IMAGE=ghcr.io/astral-sh/uv:0.11.28@sha256:0f36cb9361a3346885ca3677e3767016687b5a170c1a6b88465ec14aefec90aa

FROM ${UV_IMAGE} AS uv

FROM ${PYTHON_IMAGE} AS builder

ARG TARGETPLATFORM
ARG TARGETARCH

COPY --from=uv /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /app

RUN --mount=type=cache,target=/root/.cache/uv,sharing=locked \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    printf 'Building dependencies for %s (%s)\n' "$TARGETPLATFORM" "$TARGETARCH" && \
    uv sync --frozen --no-install-project --no-dev

COPY . /app

RUN --mount=type=cache,target=/root/.cache/uv,sharing=locked \
    uv sync --frozen --no-dev

FROM ${PYTHON_IMAGE} AS runtime

ARG TARGETPLATFORM
ARG TARGETARCH

RUN groupadd --system app && \
    useradd --system --gid app --no-create-home app

WORKDIR /app

COPY --from=builder --chown=app:app /app /app

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

LABEL org.opencontainers.image.source="https://github.com/brunovicco/mcp-server-auth-template" \
      org.opencontainers.image.title="mcp-server-auth-template" \
      io.modelcontextprotocol.server.name="io.github.brunovicco/mcp-server-auth-template"

USER app

EXPOSE 8000
STOPSIGNAL SIGTERM

HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD python -c "import os, urllib.request; port = os.getenv('MCP_SERVER_RUNTIME_PORT', '8000'); opener = urllib.request.build_opener(urllib.request.ProxyHandler({})); opener.open(f'http://127.0.0.1:{port}/livez', timeout=2).read()"

CMD ["python", "-m", "mcp_server_auth_template.entrypoints.serve"]
