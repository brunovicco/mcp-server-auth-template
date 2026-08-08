"""SSRF-resistant HTTP boundary for OIDC discovery and JWKS retrieval.

The configured issuer is the root of trust. Discovery may contact only the
issuer's exact OpenID configuration URL, and JWKS retrieval is same-origin by
default unless an operator explicitly allowlists an additional HTTPS origin.
Every hostname is resolved before connect; production rejects any non-global
answer, and the transport connects to the validated IP while preserving the
original Host header and TLS SNI name. This closes the DNS validation/connect
TOCTOU window instead of merely checking an address and resolving it again.
"""

import asyncio
import ipaddress
import socket
from collections.abc import AsyncIterator, Awaitable, Callable, Sequence
from dataclasses import dataclass
from typing import Literal, cast
from urllib.parse import urlsplit

import httpx

from mcp_server_auth_template.adapters.security_audit import (
    SecurityAuditAction,
    SecurityAuditOutcome,
    emit_security_audit,
)

IPAddress = ipaddress.IPv4Address | ipaddress.IPv6Address
Resolver = Callable[[str, int, float], Awaitable[Sequence[IPAddress]]]
TransportFactory = Callable[[], httpx.AsyncBaseTransport]
RequestKind = Literal["discovery", "jwks"]

_DISCOVERY_SUFFIX = "/.well-known/openid-configuration"
_DEFAULT_DNS_TIMEOUT_SECONDS = 2.0
_DEFAULT_HTTP_TIMEOUT_SECONDS = 5.0
_DEFAULT_DISCOVERY_MAX_BYTES = 65_536
_DEFAULT_JWKS_MAX_BYTES = 524_288
_DEFAULT_MAX_HOSTS = 8


class OidcNetworkSecurityError(RuntimeError):
    """Raised when an outbound OIDC request violates the network trust policy."""


@dataclass(frozen=True, slots=True)
class ResolvedTarget:
    """One validated OIDC target and the exact address to connect to."""

    scheme: str
    host: str
    port: int
    ip: IPAddress
    kind: RequestKind


def _default_port(scheme: str) -> int:
    if scheme == "https":
        return 443
    if scheme == "http":
        return 80
    raise OidcNetworkSecurityError("OIDC URLs must use HTTP or HTTPS")


def _effective_address(address: IPAddress) -> IPAddress:
    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped is not None:
        return address.ipv4_mapped
    return address


def _normalize_host(host: str) -> str:
    if "%" in host:
        raise OidcNetworkSecurityError("IPv6 zone identifiers are not permitted in OIDC URLs")
    try:
        return host.encode("idna").decode("ascii").lower().rstrip(".")
    except UnicodeError as exc:
        raise OidcNetworkSecurityError("OIDC URL contains an invalid hostname") from exc


def _origin(scheme: str, host: str, port: int) -> tuple[str, str, int]:
    return scheme, _normalize_host(host), port


def _parse_url(url: str) -> tuple[str, str, int]:
    if "\\" in url or any(ord(character) < 0x20 for character in url):
        raise OidcNetworkSecurityError("OIDC URL contains invalid characters")
    try:
        parsed = urlsplit(url)
        scheme = parsed.scheme.lower()
        port = parsed.port or _default_port(scheme)
    except ValueError as exc:
        raise OidcNetworkSecurityError("OIDC URL is malformed") from exc
    if scheme not in {"http", "https"}:
        raise OidcNetworkSecurityError("OIDC URLs must use HTTP or HTTPS")
    if not parsed.hostname:
        raise OidcNetworkSecurityError("OIDC URL must contain a hostname")
    if parsed.username is not None or parsed.password is not None:
        raise OidcNetworkSecurityError("userinfo is not permitted in OIDC URLs")
    if parsed.fragment:
        raise OidcNetworkSecurityError("fragments are not permitted in OIDC URLs")
    return scheme, _normalize_host(parsed.hostname), port


def _render_host_header(host: str, port: int, scheme: str) -> str:
    try:
        literal = ipaddress.ip_address(host)
    except ValueError:
        literal = None
    rendered = f"[{host}]" if isinstance(literal, ipaddress.IPv6Address) else host
    if port != _default_port(scheme):
        rendered = f"{rendered}:{port}"
    return rendered


async def _system_resolver(host: str, port: int, timeout_seconds: float) -> Sequence[IPAddress]:
    try:
        literal = ipaddress.ip_address(host)
    except ValueError:
        literal = None
    if literal is not None:
        return (literal,)

    loop = asyncio.get_running_loop()
    try:
        infos = await asyncio.wait_for(
            loop.getaddrinfo(host, port, type=socket.SOCK_STREAM),
            timeout=timeout_seconds,
        )
    except TimeoutError as exc:
        raise OidcNetworkSecurityError("OIDC DNS resolution timed out") from exc
    except socket.gaierror as exc:
        raise OidcNetworkSecurityError("OIDC DNS resolution failed") from exc

    addresses: list[IPAddress] = []
    seen: set[IPAddress] = set()
    for _family, _socktype, _proto, _canonname, sockaddr in infos:
        raw = str(sockaddr[0]).split("%", maxsplit=1)[0]
        try:
            address = ipaddress.ip_address(raw)
        except ValueError as exc:  # pragma: no cover - operating-system contract violation
            raise OidcNetworkSecurityError("resolver returned an invalid IP address") from exc
        if address not in seen:
            addresses.append(address)
            seen.add(address)
    if not addresses:
        raise OidcNetworkSecurityError("OIDC DNS resolution returned no usable addresses")
    return tuple(addresses)


class OidcNetworkSecurityPolicy:
    """Anchor discovery/JWKS traffic to one configured issuer trust boundary."""

    def __init__(
        self,
        *,
        issuer_url: str,
        allow_insecure_loopback: bool = False,
        jwks_allowed_origins: Sequence[str] = (),
        dns_timeout_seconds: float = _DEFAULT_DNS_TIMEOUT_SECONDS,
        http_timeout_seconds: float = _DEFAULT_HTTP_TIMEOUT_SECONDS,
        discovery_max_bytes: int = _DEFAULT_DISCOVERY_MAX_BYTES,
        jwks_max_bytes: int = _DEFAULT_JWKS_MAX_BYTES,
        resolver: Resolver | None = None,
    ) -> None:
        """Create a policy rooted at the exact configured issuer identifier."""
        if dns_timeout_seconds <= 0 or http_timeout_seconds <= 0:
            raise ValueError("OIDC DNS and HTTP timeouts must be positive")
        if discovery_max_bytes <= 0 or jwks_max_bytes <= 0:
            raise ValueError("OIDC response-size limits must be positive")

        issuer_scheme, issuer_host, issuer_port = _parse_url(issuer_url)
        if issuer_scheme != "https" and not allow_insecure_loopback:
            raise OidcNetworkSecurityError("OIDC issuer must use HTTPS")
        parsed_issuer = urlsplit(issuer_url)
        if parsed_issuer.query:
            raise OidcNetworkSecurityError("OIDC issuer URL must not contain a query")
        self._issuer_url = issuer_url
        self._issuer_origin = _origin(issuer_scheme, issuer_host, issuer_port)
        self._discovery_url = issuer_url.rstrip("/") + _DISCOVERY_SUFFIX
        self._allow_insecure_loopback = allow_insecure_loopback
        self._dns_timeout_seconds = dns_timeout_seconds
        self._http_timeout_seconds = http_timeout_seconds
        self._discovery_max_bytes = discovery_max_bytes
        self._jwks_max_bytes = jwks_max_bytes
        self._resolver = resolver or _system_resolver

        trusted = {self._issuer_origin}
        for raw_origin in jwks_allowed_origins:
            scheme, host, port = _parse_url(raw_origin)
            parsed = urlsplit(raw_origin)
            if parsed.path not in {"", "/"} or parsed.query:
                raise OidcNetworkSecurityError(
                    "JWKS allowlist entries must be origins without path or query"
                )
            if scheme != "https" and not allow_insecure_loopback:
                raise OidcNetworkSecurityError("JWKS allowlist origins must use HTTPS")
            trusted.add(_origin(scheme, host, port))
        self._trusted_jwks_origins = frozenset(trusted)

    @property
    def issuer_url(self) -> str:
        """Return the exact configured issuer identifier."""
        return self._issuer_url

    @property
    def discovery_url(self) -> str:
        """Return the only discovery URL this policy permits."""
        return self._discovery_url

    @property
    def http_timeout_seconds(self) -> float:
        """Return the per-operation OIDC network timeout."""
        return self._http_timeout_seconds

    @property
    def discovery_max_bytes(self) -> int:
        """Return the maximum accepted discovery-document size."""
        return self._discovery_max_bytes

    @property
    def jwks_max_bytes(self) -> int:
        """Return the maximum accepted JWKS-document size."""
        return self._jwks_max_bytes

    def assert_metadata_trusted(self, *, issuer: str, jwks_uri: str) -> None:
        """Bind returned metadata to the configured issuer and approved JWKS origins."""
        if issuer != self._issuer_url:
            raise OidcNetworkSecurityError("OIDC discovery issuer does not match configuration")
        self.assert_jwks_uri_trusted(jwks_uri)

    def assert_jwks_uri_trusted(self, jwks_uri: str) -> None:
        """Reject JWKS URLs whose origin is outside the issuer trust boundary."""
        scheme, host, port = _parse_url(jwks_uri)
        if _origin(scheme, host, port) not in self._trusted_jwks_origins:
            raise OidcNetworkSecurityError("OIDC JWKS origin is not trusted")

    def request_kind(self, url: str) -> RequestKind:
        """Classify an outbound URL or reject it before network access."""
        if url == self._discovery_url:
            return "discovery"
        self.assert_jwks_uri_trusted(url)
        return "jwks"

    def response_limit_for(self, url: str) -> int:
        """Return the raw-byte ceiling for the request's response."""
        if self.request_kind(url) == "discovery":
            return self._discovery_max_bytes
        return self._jwks_max_bytes

    async def resolve(self, url: str) -> ResolvedTarget:
        """Validate trust, resolve all answers, and choose one pinned connect address."""
        kind = self.request_kind(url)
        scheme, host, port = _parse_url(url)
        try:
            literal = ipaddress.ip_address(host)
        except ValueError:
            literal = None
        addresses = (
            (literal,)
            if literal is not None
            else tuple(await self._resolver(host, port, self._dns_timeout_seconds))
        )
        if not addresses:
            raise OidcNetworkSecurityError("OIDC DNS resolution returned no usable addresses")

        effective = tuple(_effective_address(address) for address in addresses)
        all_loopback = all(address.is_loopback for address in effective)
        if all_loopback and self._allow_insecure_loopback:
            return ResolvedTarget(scheme=scheme, host=host, port=port, ip=addresses[0], kind=kind)

        if scheme != "https":
            raise OidcNetworkSecurityError("HTTPS is required for OIDC discovery and JWKS")
        if any(not address.is_global for address in effective):
            raise OidcNetworkSecurityError(
                "OIDC DNS resolution included a private, loopback, link-local, reserved, "
                "or otherwise non-global address"
            )
        return ResolvedTarget(scheme=scheme, host=host, port=port, ip=addresses[0], kind=kind)


class _BoundedAsyncByteStream(httpx.AsyncByteStream):
    def __init__(self, stream: httpx.AsyncByteStream, *, limit: int) -> None:
        self._stream = stream
        self._limit = limit

    async def __aiter__(self) -> AsyncIterator[bytes]:
        total = 0
        async for chunk in self._stream:
            total += len(chunk)
            if total > self._limit:
                await self._stream.aclose()
                raise OidcNetworkSecurityError("OIDC response exceeded the configured size limit")
            yield chunk

    async def aclose(self) -> None:
        await self._stream.aclose()


class PinnedOidcAsyncTransport(httpx.AsyncBaseTransport):
    """DNS-pin every discovery/JWKS request and enforce bounded no-redirect responses."""

    def __init__(
        self,
        *,
        policy: OidcNetworkSecurityPolicy,
        transport_factory: TransportFactory,
        max_hosts: int = _DEFAULT_MAX_HOSTS,
    ) -> None:
        """Create the transport with isolated bounded pools per original origin."""
        if max_hosts <= 0:
            raise ValueError("max_hosts must be positive")
        self._policy = policy
        self._transport_factory = transport_factory
        self._max_hosts = max_hosts
        self._transports: dict[tuple[str, str, int], httpx.AsyncBaseTransport] = {}
        self._lock = asyncio.Lock()

    async def _transport_for(self, target: ResolvedTarget) -> httpx.AsyncBaseTransport:
        key = _origin(target.scheme, target.host, target.port)
        existing = self._transports.get(key)
        if existing is not None:
            return existing
        async with self._lock:
            existing = self._transports.get(key)
            if existing is not None:
                return existing
            if len(self._transports) >= self._max_hosts:
                raise OidcNetworkSecurityError("OIDC outbound host budget exhausted")
            child = self._transport_factory()
            self._transports[key] = child
            return child

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        """Connect to the validated IP while preserving Host and certificate identity."""
        if request.method != "GET":
            raise OidcNetworkSecurityError("OIDC control-plane requests must use GET")
        credential_header = next(
            (name for name in ("Authorization", "Proxy-Authorization") if name in request.headers),
            None,
        )
        if credential_header is not None:
            emit_security_audit(
                SecurityAuditAction.OUTBOUND_CREDENTIAL_BLOCKED,
                SecurityAuditOutcome.DENIED,
                reason="credential_header_on_oidc_control_plane",
                target_kind="oidc_control_plane",
            )
            raise OidcNetworkSecurityError(
                "OIDC control-plane requests must not carry authorization credentials"
            )
        original_url = str(request.url)
        target = await self._policy.resolve(original_url)
        child = await self._transport_for(target)

        headers = httpx.Headers(request.headers)
        headers["Host"] = _render_host_header(target.host, target.port, target.scheme)
        headers["Accept-Encoding"] = "identity"
        extensions = dict(request.extensions)
        timeout = self._policy.http_timeout_seconds
        extensions["timeout"] = {
            "connect": timeout,
            "read": timeout,
            "write": timeout,
            "pool": timeout,
        }
        if target.scheme == "https":
            extensions["sni_hostname"] = target.host

        network_request = httpx.Request(
            request.method,
            request.url.copy_with(host=target.ip.compressed),
            headers=headers,
            stream=request.stream,
            extensions=extensions,
        )
        response = await child.handle_async_request(network_request)
        if 300 <= response.status_code < 400:
            await response.aclose()
            raise OidcNetworkSecurityError("OIDC redirects are not permitted")

        content_encoding = response.headers.get("Content-Encoding", "identity").lower().strip()
        if content_encoding not in {"", "identity"}:
            await response.aclose()
            raise OidcNetworkSecurityError("compressed OIDC responses are not accepted")

        limit = self._policy.response_limit_for(original_url)
        content_length = response.headers.get("Content-Length")
        if content_length is not None:
            try:
                length = int(content_length)
            except ValueError:
                await response.aclose()
                raise OidcNetworkSecurityError("OIDC response has invalid Content-Length") from None
            if length < 0 or length > limit:
                await response.aclose()
                raise OidcNetworkSecurityError("OIDC response exceeded the configured size limit")

        return httpx.Response(
            response.status_code,
            headers=response.headers,
            stream=_BoundedAsyncByteStream(
                cast(httpx.AsyncByteStream, response.stream),
                limit=limit,
            ),
            extensions=response.extensions,
            request=request,
        )

    async def aclose(self) -> None:
        """Close all per-origin child connection pools."""
        transports = list(self._transports.values())
        self._transports.clear()
        for transport in transports:
            await transport.aclose()
