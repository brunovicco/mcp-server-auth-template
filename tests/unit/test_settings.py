"""Unit tests for :class:`Settings`."""

import pytest

from mcp_server_auth_template.entrypoints.settings import Settings

_API_CLIENT_ID = "33333333-3333-3333-3333-333333333333"
_APPLICATION_ID_URI = f"api://{_API_CLIENT_ID}"


def test_entra_mode_accepts_matching_fields() -> None:
    settings = Settings(
        auth_provider="entra",
        resource_server_url="https://mcp.example.invalid",
        entra_tenant_id="11111111-1111-1111-1111-111111111111",
        entra_audience=_API_CLIENT_ID,
        entra_application_id_uri=_APPLICATION_ID_URI,
    )

    assert settings.auth_provider == "entra"


def test_entra_mode_rejects_missing_fields() -> None:
    with pytest.raises(ValueError, match="entra_tenant_id"):
        Settings(auth_provider="entra", resource_server_url="https://mcp.example.invalid")


def test_entra_mode_requires_the_application_id_uri() -> None:
    with pytest.raises(ValueError, match="entra_application_id_uri"):
        Settings(
            auth_provider="entra",
            resource_server_url="https://mcp.example.invalid",
            entra_tenant_id="11111111-1111-1111-1111-111111111111",
            entra_audience=_API_CLIENT_ID,
        )


def test_entra_required_scopes_are_qualified_for_mcp_discovery_and_enforcement() -> None:
    settings = Settings(
        auth_provider="entra",
        resource_server_url="https://mcp.example.invalid",
        required_scopes=["mcp:tools:call"],
        entra_tenant_id="11111111-1111-1111-1111-111111111111",
        entra_audience=_API_CLIENT_ID,
        entra_application_id_uri=_APPLICATION_ID_URI,
    )

    assert settings.effective_required_scopes == [f"{_APPLICATION_ID_URI}/mcp:tools:call"]


def test_entra_already_qualified_scope_is_not_double_prefixed() -> None:
    full_scope = f"{_APPLICATION_ID_URI}/mcp:tools:call"
    settings = Settings(
        auth_provider="entra",
        resource_server_url="https://mcp.example.invalid",
        required_scopes=[full_scope],
        entra_tenant_id="11111111-1111-1111-1111-111111111111",
        entra_audience=_API_CLIENT_ID,
        entra_application_id_uri=_APPLICATION_ID_URI,
    )

    assert settings.effective_required_scopes == [full_scope]


def test_generic_mode_accepts_matching_fields() -> None:
    settings = Settings(
        auth_provider="generic",
        resource_server_url="https://mcp.example.invalid",
        generic_issuer_url="https://as.example.invalid",
        generic_audience="https://mcp.example.invalid",
    )

    assert settings.auth_provider == "generic"


def test_generic_required_scopes_pass_through_unchanged() -> None:
    settings = Settings(
        auth_provider="generic",
        resource_server_url="https://mcp.example.invalid",
        required_scopes=["mcp:tools:call"],
        generic_issuer_url="https://as.example.invalid",
        generic_audience="https://mcp.example.invalid",
    )

    assert settings.effective_required_scopes == ["mcp:tools:call"]


def test_generic_mode_rejects_missing_fields() -> None:
    with pytest.raises(ValueError, match="generic_issuer_url"):
        Settings(auth_provider="generic", resource_server_url="https://mcp.example.invalid")
