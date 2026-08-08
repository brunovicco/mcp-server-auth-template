"""The server's outbound OIDC control plane must never carry caller credentials."""

import ipaddress
from collections.abc import Sequence

import httpx
import pytest

from mcp_server_auth_template.adapters.oidc_http_security import (
    OidcNetworkSecurityError,
    OidcNetworkSecurityPolicy,
    PinnedOidcAsyncTransport,
)

IPAddress = ipaddress.IPv4Address | ipaddress.IPv6Address
_PUBLIC_IP = ipaddress.ip_address("1.1.1.1")


async def _resolver(_host: str, _port: int, _timeout: float) -> Sequence[IPAddress]:
    return (_PUBLIC_IP,)


async def test_authorization_header_is_blocked_before_network_io() -> None:
    called = False

    async def handler(_: httpx.Request) -> httpx.Response:
        nonlocal called
        called = True
        return httpx.Response(200, json={"keys": []})

    policy = OidcNetworkSecurityPolicy(
        issuer_url="https://issuer.example.invalid",
        resolver=_resolver,
    )
    transport = PinnedOidcAsyncTransport(
        policy=policy,
        transport_factory=lambda: httpx.MockTransport(handler),
    )
    request = httpx.Request(
        "GET",
        "https://issuer.example.invalid/jwks",
        headers={"Authorization": "Bearer inbound-mcp-token"},
    )

    with pytest.raises(OidcNetworkSecurityError, match="must not carry authorization"):
        await transport.handle_async_request(request)

    assert called is False
