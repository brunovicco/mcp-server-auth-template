"""Production-oriented Uvicorn launcher for the MCP ASGI application."""

import uvicorn

from mcp_server_auth_template.entrypoints.preflight import validate_preflight_settings
from mcp_server_auth_template.entrypoints.settings import Settings

_APP_FACTORY = "mcp_server_auth_template.entrypoints.mcp_server:create_app"


def serve(settings: Settings | None = None) -> None:
    """Run the configured ASGI factory with explicit production lifecycle settings."""
    settings = validate_preflight_settings(settings or Settings())
    uvicorn.run(
        _APP_FACTORY,
        factory=True,
        host=settings.runtime_host,
        port=settings.runtime_port,
        workers=settings.runtime_workers,
        backlog=settings.runtime_backlog,
        lifespan="on",
        ws="none",
        proxy_headers=False,
        server_header=False,
        timeout_keep_alive=settings.runtime_keep_alive_seconds,
        timeout_graceful_shutdown=settings.runtime_graceful_shutdown_seconds,
    )


def main() -> None:
    """Run the production-oriented HTTP entrypoint."""
    serve()


if __name__ == "__main__":
    main()
