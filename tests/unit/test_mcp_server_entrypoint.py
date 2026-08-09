"""Unit and integration tests for the MCP resource-server entrypoint."""

from collections.abc import AsyncIterator

import httpx
import pytest
from mcp.server.auth.middleware.auth_context import auth_context_var
from mcp.server.auth.middleware.bearer_auth import AuthenticatedUser
from mcp.server.auth.provider import AccessToken
from pydantic import AnyHttpUrl
from starlette.applications import Starlette

from mcp_server_auth_template.adapters.entra_token_verifier import EntraTokenVerifier
from mcp_server_auth_template.adapters.generic_oidc_token_verifier import GenericOidcTokenVerifier
from mcp_server_auth_template.adapters.oauth_client_credentials_extension import (
    OAUTH_CLIENT_CREDENTIALS_EXTENSION_ID,
)
from mcp_server_auth_template.entrypoints.mcp_server import (
    _build_token_verifier,
    _health,
    _resolve_issuer_url,
    _whoami,
    build_server,
    create_app,
)
from mcp_server_auth_template.entrypoints.settings import Settings

_API_CLIENT_ID = "33333333-3333-3333-3333-333333333333"
_APPLICATION_ID_URI = f"api://{_API_CLIENT_ID}"

_ENTRA_ENV = {
    "MCP_SERVER_RESOURCE_SERVER_URL": "https://mcp.example.invalid",
    "MCP_SERVER_REQUIRED_SCOPES": '["mcp:tools:call"]',
    "MCP_SERVER_AUTH_PROVIDER": "entra",
    "MCP_SERVER_ENTRA_TENANT_ID": "11111111-1111-1111-1111-111111111111",
    "MCP_SERVER_ENTRA_AUDIENCE": _API_CLIENT_ID,
    "MCP_SERVER_ENTRA_APPLICATION_ID_URI": _APPLICATION_ID_URI,
}

_GENERIC_ENV = {
    "MCP_SERVER_RESOURCE_SERVER_URL": "https://mcp.example.invalid",
    "MCP_SERVER_AUTH_PROVIDER": "generic",
    "MCP_SERVER_GENERIC_ISSUER_URL": "https://as.example.invalid",
    "MCP_SERVER_GENERIC_AUDIENCE": "https://mcp.example.invalid",
}


@pytest.fixture
async def http_client() -> AsyncIterator[httpx.AsyncClient]:
    async with httpx.AsyncClient() as client:
        yield client


def _set_env(monkeypatch: pytest.MonkeyPatch, env: dict[str, str]) -> None:
    for key, value in env.items():
        monkeypatch.setenv(key, value)


async def test_builds_an_entra_verifier_for_entra_settings(http_client: httpx.AsyncClient) -> None:
    settings = Settings(
        auth_provider="entra",
        resource_server_url="https://mcp.example.invalid",
        entra_tenant_id="11111111-1111-1111-1111-111111111111",
        entra_audience=_API_CLIENT_ID,
        entra_application_id_uri=_APPLICATION_ID_URI,
    )

    verifier = _build_token_verifier(settings, http_client=http_client)

    assert isinstance(verifier, EntraTokenVerifier)


async def test_builds_a_generic_verifier_for_generic_settings(
    http_client: httpx.AsyncClient,
) -> None:
    settings = Settings(
        auth_provider="generic",
        resource_server_url="https://mcp.example.invalid",
        generic_issuer_url="https://as.example.invalid",
        generic_audience="https://mcp.example.invalid",
    )

    verifier = _build_token_verifier(settings, http_client=http_client)

    assert isinstance(verifier, GenericOidcTokenVerifier)


async def test_build_token_verifier_rejects_entra_settings_missing_required_fields(
    http_client: httpx.AsyncClient,
) -> None:
    # Settings.model_validator already blocks this at construction time; model_construct
    # bypasses it to exercise _build_token_verifier's own defensive check (see its docstring).
    settings = Settings.model_construct(
        auth_provider="entra",
        resource_server_url=AnyHttpUrl("https://mcp.example.invalid"),
        service_name="mcp-server-auth-template",
        required_scopes=[],
        entra_tenant_id=None,
        entra_audience=None,
        entra_application_id_uri=None,
        generic_issuer_url=None,
        generic_audience=None,
    )

    with pytest.raises(RuntimeError, match="auth_provider=entra requires"):
        _build_token_verifier(settings, http_client=http_client)


async def test_build_token_verifier_rejects_generic_settings_missing_required_fields(
    http_client: httpx.AsyncClient,
) -> None:
    settings = Settings.model_construct(
        auth_provider="generic",
        resource_server_url=AnyHttpUrl("https://mcp.example.invalid"),
        service_name="mcp-server-auth-template",
        required_scopes=[],
        entra_tenant_id=None,
        entra_audience=None,
        entra_application_id_uri=None,
        generic_issuer_url=None,
        generic_audience=None,
    )

    with pytest.raises(RuntimeError, match="auth_provider=generic requires"):
        _build_token_verifier(settings, http_client=http_client)


def test_resolve_issuer_url_templates_the_entra_tenant() -> None:
    settings = Settings(
        auth_provider="entra",
        resource_server_url="https://mcp.example.invalid",
        entra_tenant_id="11111111-1111-1111-1111-111111111111",
        entra_audience=_API_CLIENT_ID,
        entra_application_id_uri=_APPLICATION_ID_URI,
    )

    assert (
        _resolve_issuer_url(settings)
        == "https://login.microsoftonline.com/11111111-1111-1111-1111-111111111111/v2.0"
    )


def test_resolve_issuer_url_passes_through_the_generic_issuer() -> None:
    settings = Settings(
        auth_provider="generic",
        resource_server_url="https://mcp.example.invalid",
        generic_issuer_url="https://as.example.invalid",
        generic_audience="https://mcp.example.invalid",
    )

    assert _resolve_issuer_url(settings) == "https://as.example.invalid"


def test_resolve_issuer_url_raises_when_generic_issuer_is_missing() -> None:
    settings = Settings.model_construct(
        auth_provider="generic",
        resource_server_url=AnyHttpUrl("https://mcp.example.invalid"),
        service_name="mcp-server-auth-template",
        required_scopes=[],
        entra_tenant_id=None,
        entra_audience=None,
        entra_application_id_uri=None,
        generic_issuer_url=None,
        generic_audience=None,
    )

    with pytest.raises(RuntimeError, match="could not resolve issuer_url"):
        _resolve_issuer_url(settings)


def test_whoami_reports_unauthenticated_with_no_access_token() -> None:
    assert _whoami() == {"authenticated": False}


def test_whoami_reports_the_caller_identity_from_the_access_token() -> None:
    access_token = AccessToken(
        token="opaque-token-value",
        client_id="client-123",
        scopes=["mcp:tools:call"],
        expires_at=None,
        subject="user-456",
    )
    reset_token = auth_context_var.set(AuthenticatedUser(access_token))
    try:
        assert _whoami() == {
            "authenticated": True,
            "client_id": "client-123",
            "subject": "user-456",
            "scopes": ["mcp:tools:call"],
        }
    finally:
        auth_context_var.reset(reset_token)


def test_health_reports_ok() -> None:
    assert _health() == {"status": "ok"}


@pytest.mark.integration
def test_build_server_wires_an_entra_resource_server(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_env(monkeypatch, _ENTRA_ENV)

    server = build_server()

    assert server.name == "mcp-server-auth-template"
    assert server.settings.auth is not None
    assert str(server.settings.auth.issuer_url) == (
        "https://login.microsoftonline.com/11111111-1111-1111-1111-111111111111/v2.0"
    )
    assert str(server.settings.auth.resource_server_url) == "https://mcp.example.invalid/"
    assert server.settings.auth.required_scopes == [f"{_APPLICATION_ID_URI}/mcp:tools:call"]


@pytest.mark.integration
def test_build_server_wires_a_generic_resource_server(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_env(monkeypatch, _GENERIC_ENV)

    server = build_server()

    assert server.name == "mcp-server-auth-template"
    assert server.settings.auth is not None
    assert str(server.settings.auth.issuer_url) == "https://as.example.invalid"
    assert server._lowlevel_server.extensions == {OAUTH_CLIENT_CREDENTIALS_EXTENSION_ID: {}}


@pytest.mark.integration
async def test_build_server_registers_the_example_tools(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_env(monkeypatch, _GENERIC_ENV)

    server = build_server()

    tool_names = {tool.name for tool in await server.list_tools()}
    assert tool_names == {"whoami", "health"}


@pytest.mark.integration
def test_create_app_returns_a_starlette_asgi_app(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_env(monkeypatch, _GENERIC_ENV)

    assert isinstance(create_app(), Starlette)
