"""Unit tests for :class:`GenericOidcTokenVerifier`.

All network I/O is faked through :class:`DiscoveryPort`/:class:`KeyResolverPort`
implementations backed by an in-memory RSA key, so these tests run offline and
deterministically.
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest
from jwt import PyJWK

from mcp_server_auth_template.adapters.generic_oidc_token_verifier import GenericOidcTokenVerifier
from mcp_server_auth_template.domain.oidc_metadata import OidcMetadata
from tests.unit.auth_testing import SigningKeyPair, generate_test_keypair, sign_test_token

_ISSUER = "https://as.example.invalid"
_AUDIENCE = "https://mcp.example.invalid"


@dataclass
class _FakeDiscovery:
    metadata: OidcMetadata

    async def resolve(self, issuer_base_url: str) -> OidcMetadata:
        assert issuer_base_url == _ISSUER
        return self.metadata


@dataclass
class _FakeKeyResolver:
    signing_key: PyJWK

    async def resolve(self, *, jwks_uri: str, token: str) -> PyJWK:
        return self.signing_key


@pytest.fixture
def keypair() -> SigningKeyPair:
    return generate_test_keypair()


def _verifier(keypair: SigningKeyPair) -> GenericOidcTokenVerifier:
    metadata = OidcMetadata(issuer=_ISSUER, jwks_uri="https://as.example.invalid/jwks")
    return GenericOidcTokenVerifier(
        issuer_url=_ISSUER,
        audience=_AUDIENCE,
        discovery=_FakeDiscovery(metadata),
        key_resolver=_FakeKeyResolver(keypair.signing_key),
    )


async def test_accepts_a_valid_token(keypair: SigningKeyPair) -> None:
    token = sign_test_token(
        keypair, issuer=_ISSUER, audience=_AUDIENCE, scopes="mcp:tools:call mcp:tools:list"
    )

    access_token = await _verifier(keypair).verify_token(token)

    assert access_token is not None
    assert access_token.subject == "user-123"
    assert access_token.scopes == ["mcp:tools:call", "mcp:tools:list"]
    assert access_token.resource == _AUDIENCE


async def test_rejects_an_expired_token(keypair: SigningKeyPair) -> None:
    token = sign_test_token(keypair, issuer=_ISSUER, audience=_AUDIENCE, expires_in_seconds=-120)

    assert await _verifier(keypair).verify_token(token) is None


async def test_rejects_the_wrong_audience(keypair: SigningKeyPair) -> None:
    token = sign_test_token(
        keypair, issuer=_ISSUER, audience="https://someone-else.example.invalid"
    )

    assert await _verifier(keypair).verify_token(token) is None


async def test_rejects_the_wrong_issuer(keypair: SigningKeyPair) -> None:
    token = sign_test_token(
        keypair, issuer="https://not-the-configured-issuer.invalid", audience=_AUDIENCE
    )

    assert await _verifier(keypair).verify_token(token) is None


async def test_rejects_a_token_signed_by_a_different_key() -> None:
    signing_keypair = generate_test_keypair()
    other_keypair = generate_test_keypair()
    token = sign_test_token(signing_keypair, issuer=_ISSUER, audience=_AUDIENCE)

    assert await _verifier(other_keypair).verify_token(token) is None
