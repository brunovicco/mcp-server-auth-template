"""Unit tests for :class:`JwksKeyResolver`.

``PyJWKClient`` itself is stubbed out, so these tests never touch the
network - they only verify that one client is built per JWKS URI (and
reused across calls to the same URI) and that a client-side failure surfaces
as :class:`SigningKeyError`.
"""

from __future__ import annotations

from typing import Any

import pytest
from jwt.exceptions import PyJWKClientError

from mcp_server_auth_template.adapters import jwks_key_resolver as module_under_test
from mcp_server_auth_template.domain.auth_errors import SigningKeyError

_JWKS_URI = "https://as.example.invalid/jwks"
_SENTINEL_KEY = object()


class _FakePyJWKClient:
    instances_created = 0

    def __init__(self, jwks_uri: str, *, cache_keys: bool, lifespan: int) -> None:
        self.jwks_uri = jwks_uri
        _FakePyJWKClient.instances_created += 1

    def get_signing_key_from_jwt(self, token: str) -> Any:
        if token == "bad-token":
            raise PyJWKClientError("no matching key")
        return _SENTINEL_KEY


@pytest.fixture(autouse=True)
def _patch_pyjwkclient(monkeypatch: pytest.MonkeyPatch) -> None:
    _FakePyJWKClient.instances_created = 0
    monkeypatch.setattr(module_under_test, "PyJWKClient", _FakePyJWKClient)


async def test_resolves_the_signing_key() -> None:
    resolver = module_under_test.JwksKeyResolver()

    key = await resolver.resolve(jwks_uri=_JWKS_URI, token="good-token")

    assert key is _SENTINEL_KEY


async def test_reuses_one_client_per_jwks_uri() -> None:
    resolver = module_under_test.JwksKeyResolver()

    await resolver.resolve(jwks_uri=_JWKS_URI, token="good-token")
    await resolver.resolve(jwks_uri=_JWKS_URI, token="good-token")

    assert _FakePyJWKClient.instances_created == 1


async def test_wraps_a_client_error_in_signing_key_error() -> None:
    resolver = module_under_test.JwksKeyResolver()

    with pytest.raises(SigningKeyError):
        await resolver.resolve(jwks_uri=_JWKS_URI, token="bad-token")
