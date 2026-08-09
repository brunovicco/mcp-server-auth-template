"""Tests for unauthenticated operational runtime probes."""

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import Route
from starlette.testclient import TestClient

from mcp_server_auth_template.adapters.runtime_probes import OperationalProbeMiddleware
from mcp_server_auth_template.application.runtime_status import RuntimeStatus
from mcp_server_auth_template.entrypoints.mcp_server import (
    _build_streamable_http_app,
    build_server,
)
from mcp_server_auth_template.entrypoints.settings import Settings

_RESOURCE_URL = "https://mcp.example.invalid"


def _settings() -> Settings:
    return Settings(
        auth_provider="generic",
        resource_server_url=_RESOURCE_URL,
        generic_issuer_url="https://as.example.invalid",
        generic_audience=_RESOURCE_URL,
    )


def test_probe_middleware_reports_live_and_not_ready_without_calling_inner_app() -> None:
    runtime_status = RuntimeStatus()

    async def unexpected_inner_call(_: Request) -> Response:
        raise AssertionError("probe must not reach the wrapped application")

    inner = Starlette(routes=[Route("/livez", unexpected_inner_call)])
    app = OperationalProbeMiddleware(inner, runtime_status=runtime_status)

    with TestClient(app) as client:
        live = client.get("/livez")
        ready = client.get("/readyz")

    assert live.status_code == 200
    assert live.json() == {"status": "ok"}
    assert live.headers["cache-control"] == "no-store"
    assert ready.status_code == 503
    assert ready.json() == {"status": "not_ready"}


def test_probe_middleware_readiness_tracks_process_state() -> None:
    runtime_status = RuntimeStatus()
    app = OperationalProbeMiddleware(Starlette(), runtime_status=runtime_status)

    with TestClient(app) as client:
        assert client.get("/readyz").status_code == 503
        runtime_status.mark_ready()
        assert client.get("/readyz").json() == {"status": "ready"}
        runtime_status.mark_not_ready()
        assert client.get("/readyz").status_code == 503


def test_probe_middleware_allows_get_only() -> None:
    app = OperationalProbeMiddleware(Starlette(), runtime_status=RuntimeStatus())

    with TestClient(app) as client:
        response = client.post("/livez")

    assert response.status_code == 405
    assert response.headers["allow"] == "GET"


def test_real_app_probes_bypass_public_host_and_bearer_auth_but_track_lifespan() -> None:
    settings = _settings()
    runtime_status = RuntimeStatus()
    server = build_server(settings, runtime_status=runtime_status)
    app = _build_streamable_http_app(
        server,
        settings,
        runtime_status=runtime_status,
    )

    assert runtime_status.is_ready() is False
    with TestClient(app, base_url=_RESOURCE_URL) as client:
        headers = {
            "Host": "10.0.0.10:12345",
            "Authorization": "Bearer intentionally-invalid-probe-token",
        }
        live = client.get("/livez", headers=headers)
        ready = client.get("/readyz", headers=headers)

        assert runtime_status.is_ready() is True
        assert live.status_code == 200
        assert ready.status_code == 200
        assert ready.json() == {"status": "ready"}

    assert runtime_status.is_ready() is False
