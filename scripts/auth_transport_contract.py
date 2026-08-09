"""Validate the server auth-provider and transport compatibility matrix."""

import argparse
import json
from ipaddress import ip_address
from typing import Literal
from urllib.parse import urlsplit

from mcp_server_auth_template.entrypoints.settings import Settings

Provider = Literal["entra", "generic"]
TransportProfile = Literal["production-https", "loopback-ipv4", "loopback-ipv6"]

_ENTRA_TENANT_ID = "11111111-1111-1111-1111-111111111111"
_ENTRA_AUDIENCE = "api://22222222-2222-2222-2222-222222222222"
_ENTRA_APP_ID_URI = "api://22222222-2222-2222-2222-222222222222"


class AuthTransportContractError(RuntimeError):
    """Raised when a provider/transport profile violates the compatibility contract."""


def _provider_settings(provider: Provider, transport: TransportProfile) -> dict[str, object]:
    """Return provider settings for one network-silent compatibility profile."""
    if provider == "entra":
        return {
            "entra_tenant_id": _ENTRA_TENANT_ID,
            "entra_audience": _ENTRA_AUDIENCE,
            "entra_application_id_uri": _ENTRA_APP_ID_URI,
        }

    if transport == "loopback-ipv4":
        issuer = "http://127.0.0.1:9000"
        insecure_loopback = True
    elif transport == "loopback-ipv6":
        issuer = "http://[::1]:9000"
        insecure_loopback = True
    else:
        issuer = "https://identity.acme.corp"
        insecure_loopback = False

    return {
        "generic_issuer_url": issuer,
        "generic_audience": "mcp-production-audience",
        "oidc_allow_insecure_loopback": insecure_loopback,
    }


def build_profile_settings(provider: Provider, transport: TransportProfile) -> Settings:
    """Build one supported provider/transport profile without network I/O."""
    values: dict[str, object] = {
        "auth_provider": provider,
        **_provider_settings(provider, transport),
    }

    if transport == "production-https":
        values.update(
            app_env="production",
            resource_server_url="https://mcp.acme.corp/mcp",
            transport_allowed_hosts=["mcp.acme.corp"],
            transport_allowed_origins=["https://app.acme.corp"],
        )
    elif transport == "loopback-ipv4":
        values.update(
            app_env="test",
            resource_server_url="http://127.0.0.1:8000/mcp",
            transport_allowed_hosts=["127.0.0.1:8000"],
            transport_allowed_origins=["http://127.0.0.1:3000"],
        )
    elif transport == "loopback-ipv6":
        values.update(
            app_env="test",
            resource_server_url="http://[::1]:8000/mcp",
            transport_allowed_hosts=["[::1]:8000"],
            transport_allowed_origins=["http://[::1]:3000"],
        )
    else:
        raise AuthTransportContractError("unsupported transport profile")
    return Settings.model_validate(values)


def validate_profile(provider: Provider, transport: TransportProfile) -> dict[str, object]:
    """Validate one supported profile and return only non-sensitive evidence."""
    settings = build_profile_settings(provider, transport)
    parsed = urlsplit(str(settings.resource_server_url))

    if transport == "production-https":
        if settings.app_env != "production" or parsed.scheme != "https":
            raise AuthTransportContractError("production transport must use HTTPS")
        if settings.oidc_allow_insecure_loopback:
            raise AuthTransportContractError("production must reject insecure OIDC loopback")
        family = "n/a"
    else:
        if parsed.scheme != "http" or parsed.hostname is None:
            raise AuthTransportContractError("local transport must use HTTP on a loopback IP")
        address = ip_address(parsed.hostname)
        if not address.is_loopback:
            raise AuthTransportContractError("local transport escaped the loopback boundary")
        family = f"ipv{address.version}"
        if provider == "generic" and not settings.oidc_allow_insecure_loopback:
            raise AuthTransportContractError("local generic OIDC requires explicit loopback opt-in")

    return {
        "status": "ok",
        "provider": provider,
        "transport": transport,
        "resource_scheme": parsed.scheme,
        "address_family": family,
    }


def main() -> None:
    """Validate one CI matrix cell."""
    parser = argparse.ArgumentParser(description="Validate server auth/transport compatibility")
    parser.add_argument("--provider", choices=("entra", "generic"), required=True)
    parser.add_argument(
        "--transport",
        choices=("production-https", "loopback-ipv4", "loopback-ipv6"),
        required=True,
    )
    args = parser.parse_args()
    payload = validate_profile(args.provider, args.transport)
    print(json.dumps(payload, sort_keys=True))


if __name__ == "__main__":
    main()
