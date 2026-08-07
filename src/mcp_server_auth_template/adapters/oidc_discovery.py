"""OpenID Connect discovery, cached per issuer.

Both the Entra ID adapter and the generic OAuth 2.1 adapter resolve their
signing keys through the same ``.well-known/openid-configuration`` shape, so
the discovery call and its cache live here once instead of twice.
"""

from time import monotonic

import httpx
from cachetools import TTLCache

from mcp_server_auth_template.domain.auth_errors import DiscoveryError
from mcp_server_auth_template.domain.oidc_metadata import OidcMetadata

_DISCOVERY_SUFFIX = "/.well-known/openid-configuration"
_DEFAULT_CACHE_TTL_SECONDS = 3600
_DEFAULT_CACHE_SIZE = 32


class OidcDiscoveryClient:
    """Fetches and caches OIDC discovery documents.

    One instance should be shared for the process lifetime (constructed once
    in ``entrypoints/mcp_server.py`` and injected into whichever token
    verifier needs it) so the TTL cache is actually shared across requests.
    """

    def __init__(
        self,
        *,
        http_client: httpx.AsyncClient,
        cache_ttl_seconds: int = _DEFAULT_CACHE_TTL_SECONDS,
        cache_size: int = _DEFAULT_CACHE_SIZE,
    ) -> None:
        """Build a discovery client; ``http_client`` is shared, not owned, by this instance."""
        self._http_client = http_client
        self._cache: TTLCache[str, OidcMetadata] = TTLCache(
            maxsize=cache_size, ttl=cache_ttl_seconds, timer=monotonic
        )

    async def resolve(self, issuer_base_url: str) -> OidcMetadata:
        """Return the cached or freshly-fetched metadata for ``issuer_base_url``.

        Args:
            issuer_base_url: The issuer URL with no trailing slash and no
                ``/.well-known/...`` suffix, e.g.
                ``https://login.microsoftonline.com/<tenant-id>/v2.0``.

        Raises:
            DiscoveryError: The document could not be fetched or parsed.
        """
        cached = self._cache.get(issuer_base_url)
        if cached is not None:
            return cached

        metadata = await self._fetch(issuer_base_url)
        self._cache[issuer_base_url] = metadata
        return metadata

    async def _fetch(self, issuer_base_url: str) -> OidcMetadata:
        url = issuer_base_url.rstrip("/") + _DISCOVERY_SUFFIX
        try:
            response = await self._http_client.get(url)
            response.raise_for_status()
            document = response.json()
            return OidcMetadata(issuer=document["issuer"], jwks_uri=document["jwks_uri"])
        except (httpx.HTTPError, KeyError, ValueError) as exc:
            raise DiscoveryError(f"could not resolve OIDC metadata from {url}") from exc
