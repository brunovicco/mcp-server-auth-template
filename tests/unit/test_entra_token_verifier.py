"""Unit tests for :class:`EntraTokenVerifier`.

Covers the Entra-specific behavior layered on top of
:class:`GenericOidcTokenVerifier`: tenant binding through ``tid`` and
qualification of the short ``scp``/``roles`` permission values with the
configured Application ID URI.
"""

from dataclasses import dataclass

import pytest
from jwt import PyJWK

from mcp_server_auth_template.adapters.entra_token_verifier import EntraTokenVerifier
from mcp_server_auth_template.domain.oidc_metadata import OidcMetadata
from tests.unit.auth_testing import SigningKeyPair, generate_test_keypair, sign_test_token

_TENANT_ID = "11111111-1111-1111-1111-111111111111"
_OTHER_TENANT_ID = "22222222-2222-2222-2222-222222222222"
_ISSUER = f"https://login.microsoftonline.com/{_TENANT_ID}/v2.0"
_API_CLIENT_ID = "33333333-3333-3333-3333-333333333333"
_AUDIENCE = _API_CLIENT_ID
_APPLICATION_ID_URI = f"api://{_API_CLIENT_ID}"


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
        application_id_uri=_APPLICATION_ID_URI,
        discovery=_FakeDiscovery(metadata),
        key_resolver=_FakeKeyResolver(keypair.signing_key),
    )


async def test_accepts_and_qualifies_a_delegated_scope_from_the_configured_tenant(
    keypair: SigningKeyPair,
) -> None:
    token = sign_test_token(
        keypair,
        issuer=_ISSUER,
        audience=_AUDIENCE,
        scopes=None,
        extra_claims={"tid": _TENANT_ID, "scp": "mcp:tools:call"},
    )

    access_token = await _verifier(keypair).verify_token(token)

    assert access_token is not None
    assert access_token.scopes == [f"{_APPLICATION_ID_URI}/mcp:tools:call"]


async def test_accepts_and_qualifies_an_application_role(keypair: SigningKeyPair) -> None:
    token = sign_test_token(
        keypair,
        issuer=_ISSUER,
        audience=_AUDIENCE,
        scopes=None,
        extra_claims={"tid": _TENANT_ID, "roles": ["Data.Read"]},
    )

    access_token = await _verifier(keypair).verify_token(token)

    assert access_token is not None
    assert access_token.scopes == [f"{_APPLICATION_ID_URI}/Data.Read"]


async def test_does_not_rewrite_an_already_qualified_permission(keypair: SigningKeyPair) -> None:
    qualified = "api://other-resource/Data.Read"
    token = sign_test_token(
        keypair,
        issuer=_ISSUER,
        audience=_AUDIENCE,
        scopes=None,
        extra_claims={"tid": _TENANT_ID, "roles": [qualified]},
    )

    access_token = await _verifier(keypair).verify_token(token)

    assert access_token is not None
    assert access_token.scopes == [qualified]


async def test_rejects_a_token_from_a_different_tenant(keypair: SigningKeyPair) -> None:
    token = sign_test_token(
        keypair, issuer=_ISSUER, audience=_AUDIENCE, extra_claims={"tid": _OTHER_TENANT_ID}
    )

    assert await _verifier(keypair).verify_token(token) is None


async def test_rejects_a_token_with_no_tid_claim(keypair: SigningKeyPair) -> None:
    token = sign_test_token(keypair, issuer=_ISSUER, audience=_AUDIENCE)

    assert await _verifier(keypair).verify_token(token) is None
