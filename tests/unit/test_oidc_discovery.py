"""Unit tests for the hardened :class:`OidcDiscoveryClient`."""

import httpx
import pytest

from mcp_server_auth_template.adapters.oidc_discovery import OidcDiscoveryClient
from mcp_server_auth_template.adapters.oidc_http_security import OidcNetworkSecurityPolicy
from mcp_server_auth_template.domain.auth_errors import DiscoveryError

_ISSUER = "https://as.example.invalid"
_JWKS_URI = f"{_ISSUER}/jwks"


def _policy(*, allowed_origins: list[str] | None = None) -> OidcNetworkSecurityPolicy:
    return OidcNetworkSecurityPolicy(
        issuer_url=_ISSUER,
        jwks_allowed_origins=allowed_origins or (),
    )


def _client(handler: httpx.MockTransport) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=handler, follow_redirects=False)


async def test_resolves_exact_issuer_and_trusted_jwks_uri() -> None:
    def respond(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/.well-known/openid-configuration"
        return httpx.Response(200, json={"issuer": _ISSUER, "jwks_uri": _JWKS_URI})

    async with _client(httpx.MockTransport(respond)) as http_client:
        discovery = OidcDiscoveryClient(http_client=http_client, policy=_policy())
        metadata = await discovery.resolve(_ISSUER)

    assert metadata.issuer == _ISSUER
    assert metadata.jwks_uri == _JWKS_URI


async def test_caches_only_validated_document_across_calls() -> None:
    call_count = 0

    def respond(_request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        return httpx.Response(200, json={"issuer": _ISSUER, "jwks_uri": _JWKS_URI})

    async with _client(httpx.MockTransport(respond)) as http_client:
        discovery = OidcDiscoveryClient(http_client=http_client, policy=_policy())
        first = await discovery.resolve(_ISSUER)
        second = await discovery.resolve(_ISSUER)

    assert first is second
    assert call_count == 1


async def test_rejects_resolution_for_any_issuer_other_than_configured_root() -> None:
    async with _client(httpx.MockTransport(lambda _request: httpx.Response(500))) as http_client:
        discovery = OidcDiscoveryClient(http_client=http_client, policy=_policy())
        with pytest.raises(DiscoveryError, match="untrusted issuer"):
            await discovery.resolve("https://attacker.example.invalid")


@pytest.mark.parametrize(
    "document",
    [
        {"issuer": "https://attacker.example.invalid", "jwks_uri": _JWKS_URI},
        {"issuer": _ISSUER, "jwks_uri": "https://attacker.example.invalid/jwks"},
        {"issuer": _ISSUER},
        {"jwks_uri": _JWKS_URI},
    ],
)
async def test_rejects_untrusted_or_incomplete_metadata(document: dict[str, str]) -> None:
    def respond(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=document)

    async with _client(httpx.MockTransport(respond)) as http_client:
        discovery = OidcDiscoveryClient(http_client=http_client, policy=_policy())
        with pytest.raises(DiscoveryError):
            await discovery.resolve(_ISSUER)


async def test_allows_explicit_cross_origin_jwks_origin() -> None:
    jwks_uri = "https://keys.example.invalid/tenant/jwks"

    def respond(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"issuer": _ISSUER, "jwks_uri": jwks_uri})

    async with _client(httpx.MockTransport(respond)) as http_client:
        discovery = OidcDiscoveryClient(
            http_client=http_client,
            policy=_policy(allowed_origins=["https://keys.example.invalid"]),
        )
        metadata = await discovery.resolve(_ISSUER)

    assert metadata.jwks_uri == jwks_uri


async def test_rejects_duplicate_json_members() -> None:
    body = (
        b'{"issuer":"https://as.example.invalid",'
        b'"issuer":"https://attacker.example.invalid",'
        b'"jwks_uri":"https://as.example.invalid/jwks"}'
    )

    def respond(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, headers={"Content-Type": "application/json"}, content=body)

    async with _client(httpx.MockTransport(respond)) as http_client:
        discovery = OidcDiscoveryClient(http_client=http_client, policy=_policy())
        with pytest.raises(DiscoveryError):
            await discovery.resolve(_ISSUER)


async def test_rejects_non_json_content_type_and_http_error() -> None:
    responses = iter(
        [
            httpx.Response(200, headers={"Content-Type": "text/plain"}, content=b"{}"),
            httpx.Response(503),
        ]
    )

    def respond(_request: httpx.Request) -> httpx.Response:
        return next(responses)

    async with _client(httpx.MockTransport(respond)) as http_client:
        discovery = OidcDiscoveryClient(
            http_client=http_client,
            policy=_policy(),
            cache_ttl_seconds=1,
        )
        with pytest.raises(DiscoveryError):
            await discovery.resolve(_ISSUER)
        with pytest.raises(DiscoveryError):
            await discovery.resolve(_ISSUER)
