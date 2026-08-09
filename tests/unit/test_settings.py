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


def test_oidc_network_security_is_fail_closed_by_default() -> None:
    default = Settings.model_fields["oidc_allow_insecure_loopback"].default

    assert default is False


def test_entra_tenant_alias_is_rejected() -> None:
    with pytest.raises(ValueError, match="tenant-specific UUID"):
        Settings(
            auth_provider="entra",
            resource_server_url="https://mcp.example.invalid",
            entra_tenant_id="common",
            entra_audience=_API_CLIENT_ID,
            entra_application_id_uri=_APPLICATION_ID_URI,
        )


def test_generic_cross_origin_jwks_allowlist_is_configurable() -> None:
    settings = Settings(
        auth_provider="generic",
        resource_server_url="https://mcp.example.invalid",
        generic_issuer_url="https://as.example.invalid",
        generic_audience="https://mcp.example.invalid",
        generic_jwks_allowed_origins=["https://keys.example.invalid"],
    )

    assert settings.generic_jwks_allowed_origins == ["https://keys.example.invalid"]


def test_transport_limits_are_bounded_by_default() -> None:
    settings = Settings(
        auth_provider="generic",
        resource_server_url="https://mcp.example.invalid",
        generic_issuer_url="https://as.example.invalid",
        generic_audience="https://mcp.example.invalid",
    )

    assert settings.transport_max_request_body_bytes == 1024 * 1024
    assert settings.transport_max_header_count == 64
    assert settings.transport_max_header_bytes == 32 * 1024
    assert settings.transport_max_concurrent_requests == 64


def test_runtime_process_defaults_are_explicit_and_bounded() -> None:
    settings = Settings(
        auth_provider="generic",
        resource_server_url="https://mcp.example.invalid",
        generic_issuer_url="https://as.example.invalid",
        generic_audience="https://mcp.example.invalid",
    )

    assert settings.runtime_host == "0.0.0.0"  # noqa: S104 - intentional bind-all runtime default
    assert settings.runtime_port == 8000
    assert settings.runtime_workers == 1
    assert settings.runtime_backlog == 2048
    assert settings.runtime_keep_alive_seconds == 5
    assert settings.runtime_graceful_shutdown_seconds == 30


def test_runtime_host_rejects_whitespace() -> None:
    with pytest.raises(ValueError, match="runtime_host"):
        Settings(
            auth_provider="generic",
            resource_server_url="https://mcp.example.invalid",
            generic_issuer_url="https://as.example.invalid",
            generic_audience="https://mcp.example.invalid",
            runtime_host=" 0.0.0.0",
        )


def test_app_env_reads_the_existing_unprefixed_environment_variable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APP_ENV", "staging")
    settings = Settings(
        auth_provider="generic",
        resource_server_url="https://mcp.example.invalid",
        generic_issuer_url="https://as.example.invalid",
        generic_audience="https://mcp.example.invalid",
    )

    assert settings.app_env == "staging"


def test_production_profile_accepts_non_placeholder_https_configuration() -> None:
    settings = Settings(
        app_env="production",
        auth_provider="generic",
        resource_server_url="https://mcp.acme.corp",
        generic_issuer_url="https://identity.acme.corp/oidc",
        generic_audience="https://mcp.acme.corp",
        generic_jwks_allowed_origins=["https://keys.acme.corp"],
        transport_allowed_origins=["https://console.acme.corp"],
    )

    assert settings.app_env == "production"


def test_production_profile_rejects_placeholder_resource_hostname() -> None:
    with pytest.raises(ValueError, match="placeholder hostname"):
        Settings(
            app_env="production",
            auth_provider="generic",
            resource_server_url="https://mcp.example.invalid",
            generic_issuer_url="https://identity.acme.corp",
            generic_audience="https://mcp.acme.corp",
        )


def test_production_profile_rejects_loopback_http_resource_url() -> None:
    with pytest.raises(ValueError, match="HTTPS resource_server_url"):
        Settings(
            app_env="production",
            auth_provider="generic",
            resource_server_url="http://127.0.0.1:8000",
            generic_issuer_url="https://identity.acme.corp",
            generic_audience="https://mcp.acme.corp",
        )


def test_production_profile_rejects_insecure_oidc_escape_hatch() -> None:
    with pytest.raises(ValueError, match="forbids oidc_allow_insecure_loopback"):
        Settings(
            app_env="production",
            auth_provider="generic",
            resource_server_url="https://mcp.acme.corp",
            generic_issuer_url="https://identity.acme.corp",
            generic_audience="https://mcp.acme.corp",
            oidc_allow_insecure_loopback=True,
        )


def test_production_profile_rejects_non_https_generic_issuer() -> None:
    with pytest.raises(ValueError, match="absolute HTTPS issuer"):
        Settings(
            app_env="production",
            auth_provider="generic",
            resource_server_url="https://mcp.acme.corp",
            generic_issuer_url="http://127.0.0.1:9000",
            generic_audience="https://mcp.acme.corp",
        )


def test_production_profile_rejects_all_zero_entra_placeholder() -> None:
    with pytest.raises(ValueError, match="all-zero placeholder"):
        Settings(
            app_env="production",
            auth_provider="entra",
            resource_server_url="https://mcp.acme.corp",
            entra_tenant_id="00000000-0000-0000-0000-000000000000",
            entra_audience=_API_CLIENT_ID,
            entra_application_id_uri=_APPLICATION_ID_URI,
        )


@pytest.mark.parametrize(
    "resource_url",
    ["http://127.0.0.1:8000", "http://[::1]:8000"],
)
def test_loopback_ip_literal_http_resource_url_is_allowed(resource_url: str) -> None:
    settings = Settings(
        auth_provider="generic",
        resource_server_url=resource_url,
        generic_issuer_url="https://as.example.invalid",
        generic_audience="https://mcp.example.invalid",
    )

    assert str(settings.resource_server_url).startswith(resource_url)


@pytest.mark.parametrize(
    "resource_url",
    ["http://10.0.0.10:8000", "http://localhost:8000"],
)
def test_non_loopback_or_hostname_http_resource_url_is_rejected(resource_url: str) -> None:
    with pytest.raises(ValueError, match="IP-literal loopback"):
        Settings(
            auth_provider="generic",
            resource_server_url=resource_url,
            generic_issuer_url="https://as.example.invalid",
            generic_audience="https://mcp.example.invalid",
        )


def test_transport_exact_allowlists_are_configurable() -> None:
    settings = Settings(
        auth_provider="generic",
        resource_server_url="https://mcp.example.invalid",
        generic_issuer_url="https://as.example.invalid",
        generic_audience="https://mcp.example.invalid",
        transport_allowed_hosts=["proxy.example.invalid:8443"],
        transport_allowed_origins=["https://console.example.invalid"],
    )

    assert settings.transport_allowed_hosts == ["proxy.example.invalid:8443"]
    assert settings.transport_allowed_origins == ["https://console.example.invalid"]


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("transport_allowed_hosts", " proxy.example.invalid"),
        ("transport_allowed_hosts", "proxy.example.invalid:*"),
        ("transport_allowed_hosts", "https://proxy.example.invalid"),
        ("transport_allowed_origins", "https://console.example.invalid/"),
        ("transport_allowed_origins", "https://console.example.invalid:*"),
        ("transport_allowed_origins", "console.example.invalid"),
    ],
)
def test_transport_allowlists_reject_non_exact_entries(field_name: str, value: str) -> None:
    values: dict[str, object] = {
        "auth_provider": "generic",
        "resource_server_url": "https://mcp.example.invalid",
        "generic_issuer_url": "https://as.example.invalid",
        "generic_audience": "https://mcp.example.invalid",
        field_name: [value],
    }
    with pytest.raises(ValueError):
        Settings.model_validate(values)
