"""Strict OpenID Connect discovery cached only after trust validation."""

import asyncio
from time import monotonic

import httpx
from cachetools import TTLCache

from mcp_server_auth_template.adapters.oidc_http_security import (
    OidcNetworkSecurityError,
    OidcNetworkSecurityPolicy,
)
from mcp_server_auth_template.adapters.oidc_json import OidcDocumentError, parse_json_object
from mcp_server_auth_template.domain.auth_errors import DiscoveryError
from mcp_server_auth_template.domain.oidc_metadata import OidcMetadata

_DEFAULT_CACHE_TTL_SECONDS = 3600
_DEFAULT_CACHE_SIZE = 8
_JSON_MEDIA_TYPES = {"application/json"}


class OidcDiscoveryClient:
    """Resolve one configured issuer's discovery document through a secure HTTP boundary."""

    def __init__(
        self,
        *,
        http_client: httpx.AsyncClient,
        policy: OidcNetworkSecurityPolicy,
        cache_ttl_seconds: int = _DEFAULT_CACHE_TTL_SECONDS,
        cache_size: int = _DEFAULT_CACHE_SIZE,
    ) -> None:
        """Build a discovery client; the shared HTTP client is owned by the entrypoint."""
        if cache_ttl_seconds <= 0 or cache_size <= 0:
            raise ValueError("discovery cache TTL and size must be positive")
        self._http_client = http_client
        self._policy = policy
        self._cache: TTLCache[str, OidcMetadata] = TTLCache(
            maxsize=cache_size, ttl=cache_ttl_seconds, timer=monotonic
        )
        self._fetch_lock = asyncio.Lock()

    async def resolve(self, issuer_base_url: str) -> OidcMetadata:
        """Return trusted metadata for the exact issuer configured in ``policy``."""
        if issuer_base_url != self._policy.issuer_url:
            raise DiscoveryError("OIDC discovery requested for an untrusted issuer")
        cached = self._cache.get(issuer_base_url)
        if cached is not None:
            return cached

        async with self._fetch_lock:
            cached = self._cache.get(issuer_base_url)
            if cached is not None:
                return cached
            metadata = await self._fetch()
            self._cache[issuer_base_url] = metadata
            return metadata

    async def _fetch(self) -> OidcMetadata:
        url = self._policy.discovery_url
        try:
            response = await self._http_client.get(url)
            response.raise_for_status()
            media_type = response.headers.get("Content-Type", "").split(";", maxsplit=1)[0].lower()
            if media_type not in _JSON_MEDIA_TYPES:
                raise OidcDocumentError("OIDC discovery response must be application/json")
            document = parse_json_object(
                response.content,
                max_bytes=self._policy.discovery_max_bytes,
            )
            issuer = document.get("issuer")
            jwks_uri = document.get("jwks_uri")
            if not isinstance(issuer, str) or not issuer:
                raise OidcDocumentError("OIDC discovery issuer must be a non-empty string")
            if not isinstance(jwks_uri, str) or not jwks_uri:
                raise OidcDocumentError("OIDC discovery jwks_uri must be a non-empty string")
            self._policy.assert_metadata_trusted(issuer=issuer, jwks_uri=jwks_uri)
            return OidcMetadata(issuer=issuer, jwks_uri=jwks_uri)
        except (httpx.HTTPError, OidcDocumentError, OidcNetworkSecurityError) as exc:
            raise DiscoveryError("could not resolve trusted OIDC metadata") from exc
