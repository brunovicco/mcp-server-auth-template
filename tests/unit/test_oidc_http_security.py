"""Security-boundary tests for OIDC discovery/JWKS outbound HTTP."""

import ipaddress
from collections.abc import AsyncIterator, Sequence

import httpx
import pytest

from mcp_server_auth_template.adapters.oidc_http_security import (
    IPAddress,
    OidcNetworkSecurityError,
    OidcNetworkSecurityPolicy,
    PinnedOidcAsyncTransport,
    Resolver,
)

_ISSUER = "https://as.example.com"
_PUBLIC_IP = ipaddress.ip_address("93.184.216.34")
_PRIVATE_IP = ipaddress.ip_address("10.0.0.7")
_LOOPBACK_IP = ipaddress.ip_address("127.0.0.1")


async def _public_resolver(_host: str, _port: int, _timeout: float) -> Sequence[IPAddress]:
    return (_PUBLIC_IP,)


async def _private_resolver(_host: str, _port: int, _timeout: float) -> Sequence[IPAddress]:
    return (_PRIVATE_IP,)


async def _mixed_resolver(_host: str, _port: int, _timeout: float) -> Sequence[IPAddress]:
    return (_PUBLIC_IP, _PRIVATE_IP)


async def _loopback_resolver(_host: str, _port: int, _timeout: float) -> Sequence[IPAddress]:
    return (_LOOPBACK_IP,)


def _policy(
    *,
    resolver: Resolver = _public_resolver,
    jwks_allowed_origins: Sequence[str] = (),
    discovery_max_bytes: int = 65_536,
) -> OidcNetworkSecurityPolicy:
    return OidcNetworkSecurityPolicy(
        issuer_url=_ISSUER,
        resolver=resolver,
        jwks_allowed_origins=jwks_allowed_origins,
        discovery_max_bytes=discovery_max_bytes,
    )


async def test_public_https_discovery_resolves_to_a_pinned_target() -> None:
    policy = _policy()

    target = await policy.resolve(policy.discovery_url)

    assert target.ip == _PUBLIC_IP
    assert target.host == "as.example.com"
    assert target.kind == "discovery"


@pytest.mark.parametrize("resolver", [_private_resolver, _mixed_resolver])
async def test_non_global_or_mixed_dns_answers_fail_closed(resolver: Resolver) -> None:
    policy = _policy(resolver=resolver)

    with pytest.raises(OidcNetworkSecurityError, match="non-global"):
        await policy.resolve(policy.discovery_url)


async def test_http_loopback_requires_explicit_opt_in() -> None:
    issuer = "http://127.0.0.1:9000"
    with pytest.raises(OidcNetworkSecurityError, match="HTTPS"):
        OidcNetworkSecurityPolicy(issuer_url=issuer, resolver=_loopback_resolver)

    allowed = OidcNetworkSecurityPolicy(
        issuer_url=issuer,
        resolver=_loopback_resolver,
        allow_insecure_loopback=True,
    )
    target = await allowed.resolve(allowed.discovery_url)

    assert target.ip == _LOOPBACK_IP


def test_jwks_is_same_origin_by_default() -> None:
    policy = _policy()

    policy.assert_jwks_uri_trusted("https://as.example.com/keys")
    with pytest.raises(OidcNetworkSecurityError, match="origin"):
        policy.assert_jwks_uri_trusted("https://keys.example.com/jwks")


def test_explicit_cross_origin_jwks_allowlist_is_exact_origin_only() -> None:
    policy = _policy(jwks_allowed_origins=["https://keys.example.com"])

    policy.assert_jwks_uri_trusted("https://keys.example.com/path/to/jwks?version=2")
    with pytest.raises(OidcNetworkSecurityError, match="origin"):
        policy.assert_jwks_uri_trusted("https://sub.keys.example.com/jwks")


@pytest.mark.parametrize(
    "issuer",
    [
        "https://user@example.com",
        "https://example.com/issuer?tenant=1",
        "https://example.com/issuer#fragment",
        "file:///tmp/issuer",
    ],
)
def test_ambiguous_or_non_http_issuer_urls_are_rejected(issuer: str) -> None:
    with pytest.raises(OidcNetworkSecurityError):
        OidcNetworkSecurityPolicy(issuer_url=issuer)


async def test_transport_connects_to_validated_ip_and_preserves_host_and_sni() -> None:
    observed: dict[str, object] = {}

    async def respond(request: httpx.Request) -> httpx.Response:
        observed["url"] = str(request.url)
        observed["host"] = request.headers["Host"]
        observed["sni"] = request.extensions.get("sni_hostname")
        return httpx.Response(200, json={"issuer": _ISSUER, "jwks_uri": f"{_ISSUER}/jwks"})

    policy = _policy()
    transport = PinnedOidcAsyncTransport(
        policy=policy,
        transport_factory=lambda: httpx.MockTransport(respond),
    )
    async with httpx.AsyncClient(transport=transport) as client:
        response = await client.get(policy.discovery_url)

    assert response.status_code == 200
    assert str(observed["url"]).startswith("https://93.184.216.34/")
    assert observed["host"] == "as.example.com"
    assert observed["sni"] == "as.example.com"


async def test_transport_rejects_redirects_before_follow_up_request() -> None:
    async def respond(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"Location": "https://as.example.com/elsewhere"})

    policy = _policy()
    transport = PinnedOidcAsyncTransport(
        policy=policy,
        transport_factory=lambda: httpx.MockTransport(respond),
    )
    async with httpx.AsyncClient(transport=transport) as client:
        with pytest.raises(OidcNetworkSecurityError, match="redirects"):
            await client.get(policy.discovery_url)


async def test_transport_enforces_response_size_before_parsing() -> None:
    async def respond(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"0123456789")

    policy = _policy(discovery_max_bytes=8)
    transport = PinnedOidcAsyncTransport(
        policy=policy,
        transport_factory=lambda: httpx.MockTransport(respond),
    )
    async with httpx.AsyncClient(transport=transport) as client:
        with pytest.raises(OidcNetworkSecurityError, match="size limit"):
            await client.get(policy.discovery_url)


async def test_transport_rejects_non_get_requests_before_network() -> None:
    calls = 0

    async def respond(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200)

    policy = _policy()
    transport = PinnedOidcAsyncTransport(
        policy=policy,
        transport_factory=lambda: httpx.MockTransport(respond),
    )
    async with httpx.AsyncClient(transport=transport) as client:
        with pytest.raises(OidcNetworkSecurityError, match="must use GET"):
            await client.post(policy.discovery_url)

    assert calls == 0


async def test_transport_rejects_compressed_control_plane_responses() -> None:
    class CompressedStream(httpx.AsyncByteStream):
        async def __aiter__(self) -> AsyncIterator[bytes]:
            yield b"not-gzip"

    async def respond(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"Content-Encoding": "gzip"},
            stream=CompressedStream(),
        )

    policy = _policy()
    transport = PinnedOidcAsyncTransport(
        policy=policy,
        transport_factory=lambda: httpx.MockTransport(respond),
    )
    async with httpx.AsyncClient(transport=transport) as client:
        with pytest.raises(OidcNetworkSecurityError, match="compressed"):
            await client.get(policy.discovery_url)
