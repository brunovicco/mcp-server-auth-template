"""Resolve JWT signing keys from a bounded, trusted and cached JWKS document.

Network I/O is intentionally performed through the shared ``httpx`` client
instead of ``PyJWKClient``. This keeps DNS pinning, redirects, timeouts and
response-size limits under this template's OIDC trust boundary. A ``kid`` miss
refreshes the JWKS exactly once so normal key rotation remains available.
"""

import asyncio
from time import monotonic
from typing import Any, cast

import httpx
import jwt
from cachetools import TTLCache
from jwt import PyJWK
from jwt.exceptions import InvalidKeyError, PyJWKError

from mcp_server_auth_template.adapters.oidc_http_security import (
    OidcNetworkSecurityError,
    OidcNetworkSecurityPolicy,
)
from mcp_server_auth_template.adapters.oidc_json import OidcDocumentError, parse_json_object
from mcp_server_auth_template.domain.auth_errors import SigningKeyError

_DEFAULT_JWKS_LIFESPAN_SECONDS = 300
_DEFAULT_CACHE_SIZE = 8
_DEFAULT_MAX_KEYS = 64
_DEFAULT_REFRESH_COOLDOWN_SECONDS = 30.0
_MAX_KID_LENGTH = 256
_ACCEPTED_ALGORITHMS = frozenset({"RS256", "ES256"})
_JSON_MEDIA_TYPES = {"application/json", "application/jwk-set+json"}


class JwksKeyResolver:
    """Resolve a token ``kid`` from trusted JWKS with bounded rotation-aware caching."""

    def __init__(
        self,
        *,
        http_client: httpx.AsyncClient,
        policy: OidcNetworkSecurityPolicy,
        lifespan_seconds: int = _DEFAULT_JWKS_LIFESPAN_SECONDS,
        cache_size: int = _DEFAULT_CACHE_SIZE,
        max_keys: int = _DEFAULT_MAX_KEYS,
        refresh_cooldown_seconds: float = _DEFAULT_REFRESH_COOLDOWN_SECONDS,
    ) -> None:
        """Build a resolver; the shared HTTP client is owned by the entrypoint."""
        if lifespan_seconds <= 0 or cache_size <= 0 or max_keys <= 0:
            raise ValueError("JWKS cache TTL, cache size and max_keys must be positive")
        if refresh_cooldown_seconds <= 0:
            raise ValueError("JWKS refresh cooldown must be positive")
        self._http_client = http_client
        self._policy = policy
        self._max_keys = max_keys
        self._refresh_cooldown_seconds = refresh_cooldown_seconds
        self._last_forced_refresh: dict[str, float] = {}
        self._cache: TTLCache[str, dict[str, dict[str, object]]] = TTLCache(
            maxsize=cache_size,
            ttl=lifespan_seconds,
            timer=monotonic,
        )
        self._fetch_lock = asyncio.Lock()

    async def resolve(self, *, jwks_uri: str, token: str) -> PyJWK:
        """Return a key whose ``kid`` and algorithm are bound to the JWT header.

        Raises:
            SigningKeyError: The token header is invalid, the JWKS cannot be trusted,
                or no compatible signing key exists after one refresh.
        """
        try:
            header = jwt.get_unverified_header(token)
        except jwt.exceptions.InvalidTokenError as exc:
            raise SigningKeyError("JWT header could not be decoded") from exc

        kid = header.get("kid")
        algorithm = header.get("alg")
        if not isinstance(kid, str) or not kid or len(kid) > _MAX_KID_LENGTH:
            raise SigningKeyError("JWT header must contain a bounded non-empty kid")
        if not isinstance(algorithm, str) or algorithm not in _ACCEPTED_ALGORITHMS:
            raise SigningKeyError("JWT signing algorithm is not accepted")

        try:
            self._policy.assert_jwks_uri_trusted(jwks_uri)
        except OidcNetworkSecurityError as exc:
            raise SigningKeyError("JWKS URI is outside the configured trust boundary") from exc
        keys = await self._keys_for(jwks_uri)
        resolved = self._compatible_key(keys, kid=kid, algorithm=algorithm)
        if resolved is not None:
            return resolved

        keys = await self._keys_for(jwks_uri, force_refresh=True)
        resolved = self._compatible_key(keys, kid=kid, algorithm=algorithm)
        if resolved is not None:
            return resolved
        raise SigningKeyError("no matching trusted JWKS signing key")

    async def _keys_for(
        self,
        jwks_uri: str,
        *,
        force_refresh: bool = False,
    ) -> dict[str, dict[str, object]]:
        if not force_refresh:
            cached = self._cache.get(jwks_uri)
            if cached is not None:
                return cached

        async with self._fetch_lock:
            cached = self._cache.get(jwks_uri)
            if not force_refresh and cached is not None:
                return cached
            if force_refresh and cached is not None:
                last_refresh = self._last_forced_refresh.get(jwks_uri)
                now = monotonic()
                if last_refresh is not None and now - last_refresh < self._refresh_cooldown_seconds:
                    return cached
                self._last_forced_refresh[jwks_uri] = now
            keys = await self._fetch_keys(jwks_uri)
            self._cache[jwks_uri] = keys
            return keys

    async def _fetch_keys(self, jwks_uri: str) -> dict[str, dict[str, object]]:
        try:
            self._policy.assert_jwks_uri_trusted(jwks_uri)
            response = await self._http_client.get(jwks_uri)
            response.raise_for_status()
            media_type = response.headers.get("Content-Type", "").split(";", maxsplit=1)[0].lower()
            if media_type not in _JSON_MEDIA_TYPES:
                raise OidcDocumentError("JWKS response has an unsupported media type")
            document = parse_json_object(response.content, max_bytes=self._policy.jwks_max_bytes)
            raw_keys = document.get("keys")
            if not isinstance(raw_keys, list):
                raise OidcDocumentError("JWKS keys member must be an array")
            if len(raw_keys) > self._max_keys:
                raise OidcDocumentError("JWKS contains too many keys")
            return self._index_keys(raw_keys)
        except (httpx.HTTPError, OidcDocumentError, OidcNetworkSecurityError) as exc:
            raise SigningKeyError("could not resolve trusted JWKS") from exc

    def _index_keys(self, raw_keys: list[object]) -> dict[str, dict[str, object]]:
        indexed: dict[str, dict[str, object]] = {}
        seen_kids: set[str] = set()
        for raw in raw_keys:
            if not isinstance(raw, dict):
                continue
            key = cast(dict[str, object], raw)
            kid = key.get("kid")
            if not isinstance(kid, str) or not kid or len(kid) > _MAX_KID_LENGTH:
                continue
            if kid in seen_kids:
                raise OidcDocumentError("JWKS contains duplicate kid values")
            seen_kids.add(kid)

            use = key.get("use")
            if use is not None and use != "sig":
                continue
            key_ops = key.get("key_ops")
            if key_ops is not None and (not isinstance(key_ops, list) or "verify" not in key_ops):
                continue
            indexed[kid] = key
        return indexed

    @staticmethod
    def _compatible_key(
        keys: dict[str, dict[str, object]],
        *,
        kid: str,
        algorithm: str,
    ) -> PyJWK | None:
        raw = keys.get(kid)
        if raw is None:
            return None
        advertised_algorithm = raw.get("alg")
        if advertised_algorithm is not None and advertised_algorithm != algorithm:
            return None

        expected_key_type = "RSA" if algorithm == "RS256" else "EC"
        if raw.get("kty") != expected_key_type:
            return None
        if algorithm == "ES256" and raw.get("crv") != "P-256":
            return None

        try:
            return PyJWK.from_dict(cast(dict[str, Any], raw), algorithm=algorithm)
        except (InvalidKeyError, PyJWKError, KeyError, ValueError):
            return None
