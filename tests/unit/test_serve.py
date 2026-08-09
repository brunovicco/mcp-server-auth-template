"""Tests for the production Uvicorn launcher."""

import pytest
import uvicorn

import mcp_server_auth_template.entrypoints.serve as serve_entrypoint
from mcp_server_auth_template.entrypoints.serve import serve
from mcp_server_auth_template.entrypoints.settings import Settings


def test_serve_uses_explicit_bounded_runtime_configuration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    def fake_run(app: str, **kwargs: object) -> None:
        captured["app"] = app
        captured.update(kwargs)

    monkeypatch.setattr(uvicorn, "run", fake_run)
    settings = Settings(
        auth_provider="generic",
        resource_server_url="https://mcp.example.invalid",
        generic_issuer_url="https://as.example.invalid",
        generic_audience="https://mcp.example.invalid",
        runtime_host="127.0.0.1",
        runtime_port=9000,
        runtime_workers=2,
        runtime_backlog=512,
        runtime_keep_alive_seconds=7,
        runtime_graceful_shutdown_seconds=45,
    )

    serve(settings)

    assert captured == {
        "app": "mcp_server_auth_template.entrypoints.mcp_server:create_app",
        "factory": True,
        "host": "127.0.0.1",
        "port": 9000,
        "workers": 2,
        "backlog": 512,
        "lifespan": "on",
        "ws": "none",
        "proxy_headers": False,
        "server_header": False,
        "timeout_keep_alive": 7,
        "timeout_graceful_shutdown": 45,
    }


def test_serve_runs_preflight_before_binding(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[str] = []
    settings = Settings(
        auth_provider="generic",
        resource_server_url="https://mcp.example.invalid",
        generic_issuer_url="https://as.example.invalid",
        generic_audience="https://mcp.example.invalid",
    )

    def fake_preflight(candidate: Settings) -> Settings:
        events.append("preflight")
        return candidate

    def fake_run(app: str, **kwargs: object) -> None:
        del app, kwargs
        events.append("uvicorn")

    monkeypatch.setattr(serve_entrypoint, "validate_preflight_settings", fake_preflight)
    monkeypatch.setattr(uvicorn, "run", fake_run)

    serve(settings)

    assert events == ["preflight", "uvicorn"]
