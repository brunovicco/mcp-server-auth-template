import pytest

from mcp_server_auth_template.adapters.http_transport_security import (
    HttpTransportAdmissionMiddleware,
)
from mcp_server_auth_template.adapters.progressive_auth_http import (
    ProgressiveAuthorizationMiddleware,
)
from mcp_server_auth_template.adapters.runtime_probes import OperationalProbeMiddleware
from mcp_server_auth_template.application.tool_authorization import ToolPolicy
from mcp_server_auth_template.entrypoints.mcp_server import (
    _build_tool_authorizer,
    create_app,
)
from mcp_server_auth_template.entrypoints.settings import Settings

_API_CLIENT_ID = "33333333-3333-3333-3333-333333333333"
_APPLICATION_ID_URI = f"api://{_API_CLIENT_ID}"


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
