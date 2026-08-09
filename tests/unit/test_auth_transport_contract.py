"""Tests for the server auth-provider and transport compatibility contract."""

import pytest
from pydantic import ValidationError
from scripts.auth_transport_contract import (
    Provider,
    TransportProfile,
    build_profile_settings,
    validate_profile,
)

from mcp_server_auth_template.entrypoints.settings import Settings

_PROVIDERS: tuple[Provider, ...] = ("entra", "generic")
_TRANSPORTS: tuple[TransportProfile, ...] = (
    "production-https",
    "loopback-ipv4",
    "loopback-ipv6",
)
_ENTRA: dict[str, object] = {
    "auth_provider": "entra",
    "entra_tenant_id": "11111111-1111-1111-1111-111111111111",
    "entra_audience": "api://22222222-2222-2222-2222-222222222222",
    "entra_application_id_uri": "api://22222222-2222-2222-2222-222222222222",
}


@pytest.mark.parametrize("provider", _PROVIDERS)
@pytest.mark.parametrize("transport", _TRANSPORTS)
def test_supported_matrix_cells_validate(
    provider: Provider,
    transport: TransportProfile,
) -> None:
    result = validate_profile(provider, transport)

    assert result["status"] == "ok"
    assert result["provider"] == provider
    assert result["transport"] == transport


def test_ipv6_resource_server_is_supported_for_local_http() -> None:
    settings = build_profile_settings("generic", "loopback-ipv6")

    assert str(settings.resource_server_url).startswith("http://[::1]:8000/")


def test_http_hostname_is_rejected_because_local_http_requires_ip_literal() -> None:
    with pytest.raises(ValidationError, match=r"IP-literal loopback"):
        Settings.model_validate({"resource_server_url": "http://localhost:8000/mcp", **_ENTRA})


def test_http_non_loopback_is_rejected() -> None:
    with pytest.raises(ValidationError, match=r"IP-literal loopback"):
        Settings.model_validate({"resource_server_url": "http://192.0.2.10:8000/mcp", **_ENTRA})


def test_production_rejects_local_http() -> None:
    with pytest.raises(ValidationError, match=r"production requires an HTTPS"):
        Settings.model_validate(
            {
                "app_env": "production",
                "resource_server_url": "http://127.0.0.1:8000/mcp",
                **_ENTRA,
            }
        )


def test_production_rejects_insecure_oidc_loopback_escape() -> None:
    with pytest.raises(ValidationError, match=r"forbids oidc_allow_insecure_loopback=true"):
        Settings.model_validate(
            {
                "app_env": "production",
                "resource_server_url": "https://mcp.acme.corp/mcp",
                "oidc_allow_insecure_loopback": True,
                **_ENTRA,
            }
        )


def test_transport_allowlist_rejects_wildcards() -> None:
    with pytest.raises(ValidationError, match=r"exact visible strings"):
        Settings.model_validate(
            {
                "resource_server_url": "https://mcp.acme.corp/mcp",
                "transport_allowed_hosts": ["*.acme.corp"],
                **_ENTRA,
            }
        )


def test_generic_production_issuer_requires_https() -> None:
    with pytest.raises(ValidationError, match=r"production generic_issuer_url must be"):
        Settings(
            app_env="production",
            auth_provider="generic",
            resource_server_url="https://mcp.acme.corp/mcp",
            generic_issuer_url="http://127.0.0.1:9000",
            generic_audience="mcp-production-audience",
        )
