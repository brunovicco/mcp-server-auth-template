import pytest

from mcp_server_auth_template.adapters.http_transport_security import (
    HttpTransportAdmissionMiddleware,
)
from mcp_server_auth_template.adapters.progressive_auth_http import (
    ProgressiveAuthorizationMiddleware,
)
from mcp_server_auth_template.adapters.runtime_probes import OperationalProbeMiddleware
from mcp_server_auth_template.application.tool_authorization import ToolPolicy
from mcp_server_auth_template.domain.principal import Principal, PrincipalKind
from mcp_server_auth_template.entrypoints.mcp_server import (
    _build_tool_authorizer,
    create_app,
)
from mcp_server_auth_template.entrypoints.settings import Settings

_API_CLIENT_ID = "33333333-3333-3333-3333-333333333333"
_APPLICATION_ID_URI = f"api://{_API_CLIENT_ID}"
_HEALTH_SCOPE = "mcp:tools:health"


def _principal(kind: PrincipalKind, *scopes: str) -> Principal:
    return Principal(
        client_id="client-123",
        subject="subject-456",
        issuer="https://as.example.invalid",
        kind=kind,
        scopes=frozenset(scopes),
        roles=frozenset(),
    )


def test_generic_default_health_policy_requires_incremental_oauth_scope() -> None:
    settings = Settings(
        auth_provider="generic",
        resource_server_url="https://mcp.example.invalid",
        generic_issuer_url="https://as.example.invalid",
        generic_audience="https://mcp.example.invalid",
    )

    authorizer = _build_tool_authorizer(settings)

    assert authorizer.authorize("whoami", _principal(PrincipalKind.UNKNOWN)).allowed is True
    health = authorizer.authorize("health", _principal(PrincipalKind.UNKNOWN, "mcp:tools:call"))
    assert health.allowed is False
    assert health.required_scopes == (_HEALTH_SCOPE,)


def test_entra_default_health_policy_requires_delegated_qualified_scope() -> None:
    settings = Settings(
        auth_provider="entra",
        resource_server_url="https://mcp.example.invalid",
        entra_tenant_id="11111111-1111-1111-1111-111111111111",
        entra_audience=_API_CLIENT_ID,
        entra_application_id_uri=_APPLICATION_ID_URI,
    )

    authorizer = _build_tool_authorizer(settings)
    required_scope = f"{_APPLICATION_ID_URI}/{_HEALTH_SCOPE}"

    assert authorizer.authorize(
        "health", _principal(PrincipalKind.DELEGATED, required_scope)
    ).allowed
    assert not authorizer.authorize("health", _principal(PrincipalKind.APPLICATION)).allowed
    assert authorizer.required_scopes_for("health") == (required_scope,)


def test_entra_tool_authorizer_qualifies_short_scope_policies() -> None:
    settings = Settings(
        auth_provider="entra",
        resource_server_url="https://mcp.example.invalid",
        entra_tenant_id="11111111-1111-1111-1111-111111111111",
        entra_audience=_API_CLIENT_ID,
        entra_application_id_uri=_APPLICATION_ID_URI,
    )

    authorizer = _build_tool_authorizer(
        settings,
        {"customer": ToolPolicy.delegated_scopes("customer.read")},
    )

    assert authorizer.required_scopes_for("customer") == (f"{_APPLICATION_ID_URI}/customer.read",)


@pytest.mark.integration
def test_create_app_orders_transport_admission_before_progressive_authorization(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MCP_SERVER_RESOURCE_SERVER_URL", "https://mcp.example.invalid")
    monkeypatch.setenv("MCP_SERVER_AUTH_PROVIDER", "generic")
    monkeypatch.setenv("MCP_SERVER_GENERIC_ISSUER_URL", "https://as.example.invalid")
    monkeypatch.setenv("MCP_SERVER_GENERIC_AUDIENCE", "https://mcp.example.invalid")

    app = create_app()

    middleware_names = [getattr(item.cls, "__name__", None) for item in app.user_middleware[:3]]
    assert middleware_names == [
        HttpTransportAdmissionMiddleware.__name__,
        OperationalProbeMiddleware.__name__,
        ProgressiveAuthorizationMiddleware.__name__,
    ]
    assert app.user_middleware[2].kwargs["resource_metadata_url"] == (
        "https://mcp.example.invalid/.well-known/oauth-protected-resource"
    )
