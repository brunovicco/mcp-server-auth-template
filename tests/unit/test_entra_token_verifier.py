"""Unit tests for :class:`EntraTokenVerifier`.

Covers the two things this adapter adds on top of
:class:`GenericOidcTokenVerifier`: Entra's tenant-scoped issuer URL and the
``tid`` claim binding that rejects a token from a different tenant even when
every other check passes.
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest
from jwt import PyJWK

from mcp_server_auth_template.adapters.entra_token_verifier import EntraTokenVerifier
from mcp_server_auth_template.domain.oidc_metadata import OidcMetadata
from tests.unit.auth_testing import SigningKeyPair, generate_test_keypair, sign_test_token

_TENANT_ID = "11111111-1111-1111-1111-111111111111"
_OTHER_TENANT_ID = "22222222-2222-2222-2222-222222222222"
_ISSUER = f"https://login.microsoftonline.com/{_TENANT_ID}/v2.0"
_AUDIENCE = "api://00000000-0000-0000-0000-000000000000"


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


def _verifier(keypair: SigningKeyPair) -> EntraTokenVerifier:
    metadata = OidcMetadata(issuer=_ISSUER, jwks_uri=f"{_ISSUER}/discovery/v2.0/keys")
    return EntraTokenVerifier(
        tenant_id=_TENANT_ID,
        audience=_AUDIENCE,
        discovery=_FakeDiscovery(metadata),
        key_resolver=_FakeKeyResolver(keypair.signing_key),
    )


async def test_accepts_a_token_from_the_configured_tenant(keypair: SigningKeyPair) -> None:
    token = sign_test_token(
        keypair,
        issuer=_ISSUER,
        audience=_AUDIENCE,
        scopes=None,
        extra_claims={"tid": _TENANT_ID, "roles": ["Data.Read"]},
    )

    access_token = await _verifier(keypair).verify_token(token)

    assert access_token is not None
    assert access_token.scopes == ["Data.Read"]


async def test_rejects_a_token_from_a_different_tenant(keypair: SigningKeyPair) -> None:
    token = sign_test_token(
        keypair, issuer=_ISSUER, audience=_AUDIENCE, extra_claims={"tid": _OTHER_TENANT_ID}
    )

    assert await _verifier(keypair).verify_token(token) is None


async def test_rejects_a_token_with_no_tid_claim(keypair: SigningKeyPair) -> None:
    token = sign_test_token(keypair, issuer=_ISSUER, audience=_AUDIENCE)

    assert await _verifier(keypair).verify_token(token) is None
