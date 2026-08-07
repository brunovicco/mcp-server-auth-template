"""Shared fixtures for signing test JWTs against an in-memory RSA key.

Nothing here touches the network: the "JWKS" a test needs is built directly
from the same key used to sign the token, and injected through the
``DiscoveryPort``/``KeyResolverPort`` fakes in each test module.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from jwt import PyJWK


@dataclass(frozen=True, slots=True)
class SigningKeyPair:
    """An RSA key pair plus a ``PyJWK`` wrapper, for signing and verifying test tokens."""

    private_key: rsa.RSAPrivateKey
    signing_key: PyJWK
    key_id: str = "test-key-1"


def generate_test_keypair() -> SigningKeyPair:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_jwk = jwt.PyJWK.from_json(jwt.algorithms.RSAAlgorithm.to_jwk(private_key.public_key()))
    return SigningKeyPair(private_key=private_key, signing_key=public_jwk)


def sign_test_token(
    keypair: SigningKeyPair,
    *,
    issuer: str,
    audience: str,
    subject: str = "user-123",
    scopes: str | None = "mcp:tools:call",
    extra_claims: dict[str, object] | None = None,
    expires_in_seconds: int = 300,
) -> str:
    """Return a signed JWT matching what a real authorization server would issue."""
    now = int(time.time())
    payload: dict[str, object] = {
        "iss": issuer,
        "aud": audience,
        "sub": subject,
        "iat": now,
        "exp": now + expires_in_seconds,
        "azp": "test-client",
    }
    if scopes is not None:
        payload["scope"] = scopes
    if extra_claims:
        payload.update(extra_claims)

    return jwt.encode(
        payload,
        keypair.private_key,
        algorithm="RS256",
        headers={"kid": keypair.key_id},
    )
