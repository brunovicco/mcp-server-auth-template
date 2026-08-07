"""Unit tests for :class:`OidcDiscoveryClient`."""

from __future__ import annotations

import httpx
import pytest

from mcp_server_auth_template.adapters.oidc_discovery import OidcDiscoveryClient
from mcp_server_auth_template.domain.auth_errors import DiscoveryError

_ISSUER = "https://as.example.invalid"


def _client(handler: httpx.MockTransport) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=handler)


async def test_resolves_and_parses_the_discovery_document() -> None:
    def respond(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/.well-known/openid-configuration"
        return httpx.Response(200, json={"issuer": _ISSUER, "jwks_uri": f"{_ISSUER}/jwks"})

    async with _client(httpx.MockTransport(respond)) as http_client:
        discovery = OidcDiscoveryClient(http_client=http_client)
        metadata = await discovery.resolve(_ISSUER)

    assert metadata.issuer == _ISSUER
    assert metadata.jwks_uri == f"{_ISSUER}/jwks"


async def test_caches_the_document_across_calls() -> None:
    call_count = 0

    def respond(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        return httpx.Response(200, json={"issuer": _ISSUER, "jwks_uri": f"{_ISSUER}/jwks"})

    async with _client(httpx.MockTransport(respond)) as http_client:
        discovery = OidcDiscoveryClient(http_client=http_client)
        await discovery.resolve(_ISSUER)
        await discovery.resolve(_ISSUER)

    assert call_count == 1


async def test_raises_discovery_error_on_a_malformed_document() -> None:
    def respond(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"issuer": _ISSUER})  # missing jwks_uri

    async with _client(httpx.MockTransport(respond)) as http_client:
        discovery = OidcDiscoveryClient(http_client=http_client)
        with pytest.raises(DiscoveryError):
            await discovery.resolve(_ISSUER)


async def test_raises_discovery_error_on_an_http_error_status() -> None:
    def respond(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404)

    async with _client(httpx.MockTransport(respond)) as http_client:
        discovery = OidcDiscoveryClient(http_client=http_client)
        with pytest.raises(DiscoveryError):
            await discovery.resolve(_ISSUER)
