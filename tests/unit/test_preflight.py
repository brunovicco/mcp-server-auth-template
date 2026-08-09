"""Tests for fail-fast, secret-safe deployment preflight."""

import json
from pathlib import Path

import pytest
from pydantic import AnyHttpUrl, ValidationError

from mcp_server_auth_template.entrypoints.preflight import (
    build_preflight_report,
    main,
    validate_preflight_settings,
)
from mcp_server_auth_template.entrypoints.settings import Settings


def _production_settings() -> Settings:
    return Settings(
        app_env="production",
        auth_provider="generic",
        resource_server_url="https://mcp.acme.corp",
        generic_issuer_url="https://identity.acme.corp/oidc",
        generic_audience="sensitive-audience-value",
        generic_jwks_allowed_origins=["https://keys.acme.corp"],
    )


def test_preflight_report_is_allowlisted_and_does_not_expose_identifiers() -> None:
    report = build_preflight_report(_production_settings())

    assert report["status"] == "ok"
    assert report["environment"] == "production"
    assert report["auth_provider"] == "generic"
    serialized = json.dumps(report, sort_keys=True)
    assert "mcp.acme.corp" not in serialized
    assert "identity.acme.corp" not in serialized
    assert "keys.acme.corp" not in serialized
    assert "sensitive-audience-value" not in serialized


def test_preflight_revalidates_settings_constructed_without_validation() -> None:
    settings = Settings.model_construct(
        app_env="production",
        auth_provider="generic",
        resource_server_url=AnyHttpUrl("http://127.0.0.1:8000"),
        generic_issuer_url="https://identity.acme.corp",
        generic_audience="https://mcp.acme.corp",
    )

    with pytest.raises(ValidationError, match="HTTPS resource_server_url"):
        validate_preflight_settings(settings)


def test_json_failure_does_not_echo_invalid_environment_input(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("MCP_SERVER_RESOURCE_SERVER_URL", "https://mcp.acme.corp")
    monkeypatch.setenv("MCP_SERVER_AUTH_PROVIDER", "generic")
    monkeypatch.setenv("MCP_SERVER_GENERIC_ISSUER_URL", "https://identity.acme.corp")
    monkeypatch.setenv("MCP_SERVER_GENERIC_AUDIENCE", "https://mcp.acme.corp")
    monkeypatch.setenv("MCP_SERVER_RUNTIME_HOST", " secret-runtime-host")

    exit_code = main(["--json"])

    captured = capsys.readouterr()
    assert exit_code == 2
    assert "secret-runtime-host" not in captured.out
    payload = json.loads(captured.out)
    assert payload["status"] == "error"
    assert payload["error"] == "configuration_invalid"
    assert payload["issues"]


def test_json_success_reports_only_operational_metadata(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("MCP_SERVER_RESOURCE_SERVER_URL", "https://mcp.acme.corp")
    monkeypatch.setenv("MCP_SERVER_AUTH_PROVIDER", "generic")
    monkeypatch.setenv("MCP_SERVER_GENERIC_ISSUER_URL", "https://identity.acme.corp")
    monkeypatch.setenv("MCP_SERVER_GENERIC_AUDIENCE", "sensitive-audience-value")

    exit_code = main(["--json"])

    captured = capsys.readouterr()
    assert exit_code == 0
    payload = json.loads(captured.out)
    assert payload["status"] == "ok"
    assert payload["environment"] == "production"
    assert payload["auth_provider"] == "generic"
    assert "identity.acme.corp" not in captured.out
    assert "sensitive-audience-value" not in captured.out
