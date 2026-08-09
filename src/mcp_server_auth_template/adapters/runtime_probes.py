"""Unauthenticated operational probes outside the MCP authentication path."""

from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp, Receive, Scope, Send

from mcp_server_auth_template.application.runtime_status import RuntimeStatus

_LIVE_PATH = "/livez"
_READY_PATH = "/readyz"
_PROBE_HEADERS = {
    "Cache-Control": "no-store",
    "X-Content-Type-Options": "nosniff",
}


class OperationalProbeMiddleware:
    """Answer liveness/readiness probes without invoking OAuth or MCP handlers."""

    def __init__(self, app: ASGIApp, *, runtime_status: RuntimeStatus) -> None:
        """Wrap an ASGI app with process-local operational probes."""
        self._app = app
        self._runtime_status = runtime_status

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Intercept exact probe paths and delegate every other ASGI scope."""
        if scope["type"] != "http" or scope["path"] not in {_LIVE_PATH, _READY_PATH}:
            await self._app(scope, receive, send)
            return

        if scope["method"] != "GET":
            response = Response(
                status_code=405,
                headers={**_PROBE_HEADERS, "Allow": "GET"},
            )
            await response(scope, receive, send)
            return

        if scope["path"] == _LIVE_PATH:
            response = JSONResponse({"status": "ok"}, headers=_PROBE_HEADERS)
        elif self._runtime_status.is_ready():
            response = JSONResponse({"status": "ready"}, headers=_PROBE_HEADERS)
        else:
            response = JSONResponse(
                {"status": "not_ready"},
                status_code=503,
                headers=_PROBE_HEADERS,
            )
        await response(scope, receive, send)
