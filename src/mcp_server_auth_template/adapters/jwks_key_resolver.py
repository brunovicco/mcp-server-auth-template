"""Resolves the RSA/EC signing key for a JWT's ``kid`` from a JWKS endpoint.

``PyJWKClient`` does its own network I/O and key caching, but that I/O is
synchronous, so every call is pushed to a worker thread with
:func:`asyncio.to_thread` to keep the event loop free for other requests.
One client is cached per ``jwks_uri`` so repeated calls reuse its internal
key cache instead of re-fetching the JWKS document per request.
"""

from __future__ import annotations

import asyncio

import jwt
from jwt import PyJWK, PyJWKClient
from jwt.exceptions import PyJWKClientError

from mcp_server_auth_template.domain.auth_errors import SigningKeyError

_DEFAULT_KEY_CACHE_KEYS = True
_DEFAULT_JWKS_LIFESPAN_SECONDS = 3600


class JwksKeyResolver:
    """Caches one :class:`PyJWKClient` per JWKS URI for the process lifetime."""

    def __init__(self, *, lifespan_seconds: int = _DEFAULT_JWKS_LIFESPAN_SECONDS) -> None:
        """Build a resolver; ``lifespan_seconds`` controls each client's own key-cache TTL."""
        self._lifespan_seconds = lifespan_seconds
        self._clients: dict[str, PyJWKClient] = {}

    def _client_for(self, jwks_uri: str) -> PyJWKClient:
        client = self._clients.get(jwks_uri)
        if client is None:
            client = PyJWKClient(
                jwks_uri,
                cache_keys=_DEFAULT_KEY_CACHE_KEYS,
                lifespan=self._lifespan_seconds,
            )
            self._clients[jwks_uri] = client
        return client

    async def resolve(self, *, jwks_uri: str, token: str) -> PyJWK:
        """Return the signing key that matches ``token``'s ``kid`` header.

        Raises:
            SigningKeyError: No matching key could be resolved.
        """
        client = self._client_for(jwks_uri)
        try:
            return await asyncio.to_thread(client.get_signing_key_from_jwt, token)
        except (PyJWKClientError, jwt.exceptions.DecodeError) as exc:
            raise SigningKeyError(f"no matching signing key in {jwks_uri}") from exc
