"""Unit tests for the bounded, rotation-aware JWKS resolver."""

import base64
import json
from typing import Any

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec, rsa
from jwt.algorithms import ECAlgorithm, RSAAlgorithm

from mcp_server_auth_template.adapters.jwks_key_resolver import JwksKeyResolver
from mcp_server_auth_template.adapters.oidc_http_security import OidcNetworkSecurityPolicy
from mcp_server_auth_template.domain.auth_errors import SigningKeyError

_ISSUER = "https://as.example.invalid"
_JWKS_URI = f"{_ISSUER}/jwks"


def _policy() -> OidcNetworkSecurityPolicy:
    return OidcNetworkSecurityPolicy(issuer_url=_ISSUER)


def _rsa_material(kid: str) -> tuple[Any, dict[str, object]]:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    raw = RSAAlgorithm.to_jwk(private_key.public_key(), as_dict=True)
    assert isinstance(raw, dict)
    jwk: dict[str, object] = dict(raw)
    jwk.update({"kid": kid, "alg": "RS256", "use": "sig", "key_ops": ["verify"]})
    return private_key, jwk


def _ec_material(kid: str) -> tuple[Any, dict[str, object]]:
    private_key = ec.generate_private_key(ec.SECP256R1())
    raw = ECAlgorithm.to_jwk(private_key.public_key(), as_dict=True)
    assert isinstance(raw, dict)
    jwk: dict[str, object] = dict(raw)
    jwk.update({"kid": kid, "alg": "ES256", "use": "sig", "key_ops": ["verify"]})
    return private_key, jwk


def _token(private_key: Any, *, kid: str, algorithm: str) -> str:
    return jwt.encode(
        {"sub": "subject"},
        private_key,
        algorithm=algorithm,
        headers={"kid": kid},
    )


def _raw_token_header(header: dict[str, object]) -> str:
    encoded = base64.urlsafe_b64encode(json.dumps(header).encode()).rstrip(b"=").decode()
    payload = base64.urlsafe_b64encode(b"{}").rstrip(b"=").decode()
    return f"{encoded}.{payload}.signature"


async def test_resolves_rs256_signing_key_from_trusted_jwks() -> None:
    private_key, jwk = _rsa_material("rsa-key")

    def respond(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"keys": [jwk]})

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as http_client:
        resolver = JwksKeyResolver(http_client=http_client, policy=_policy())
        key = await resolver.resolve(
            jwks_uri=_JWKS_URI,
            token=_token(private_key, kid="rsa-key", algorithm="RS256"),
        )

    assert key.key_type == "RSA"
    assert key.algorithm_name == "RS256"


async def test_resolves_es256_only_with_p256_ec_key() -> None:
    private_key, jwk = _ec_material("ec-key")

    def respond(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"keys": [jwk]})

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as http_client:
        resolver = JwksKeyResolver(http_client=http_client, policy=_policy())
        key = await resolver.resolve(
            jwks_uri=_JWKS_URI,
            token=_token(private_key, kid="ec-key", algorithm="ES256"),
        )

    assert key.key_type == "EC"
    assert key.algorithm_name == "ES256"


async def test_reuses_cached_jwks_for_matching_kid() -> None:
    private_key, jwk = _rsa_material("rsa-key")
    calls = 0

    def respond(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json={"keys": [jwk]})

    token = _token(private_key, kid="rsa-key", algorithm="RS256")
    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as http_client:
        resolver = JwksKeyResolver(http_client=http_client, policy=_policy())
        await resolver.resolve(jwks_uri=_JWKS_URI, token=token)
        await resolver.resolve(jwks_uri=_JWKS_URI, token=token)

    assert calls == 1


async def test_kid_miss_refreshes_once_and_accepts_rotated_key() -> None:
    old_private, old_jwk = _rsa_material("old")
    new_private, new_jwk = _rsa_material("new")
    del old_private
    calls = 0

    def respond(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        keys = [old_jwk] if calls == 1 else [old_jwk, new_jwk]
        return httpx.Response(200, json={"keys": keys})

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as http_client:
        resolver = JwksKeyResolver(http_client=http_client, policy=_policy())
        key = await resolver.resolve(
            jwks_uri=_JWKS_URI,
            token=_token(new_private, kid="new", algorithm="RS256"),
        )

    assert key.algorithm_name == "RS256"
    assert calls == 2


async def test_repeated_unknown_kids_do_not_bypass_refresh_cooldown() -> None:
    _private_key, jwk = _rsa_material("known")
    attacker_one, _ = _rsa_material("unknown-1")
    attacker_two, _ = _rsa_material("unknown-2")
    calls = 0

    def respond(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json={"keys": [jwk]})

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as http_client:
        resolver = JwksKeyResolver(
            http_client=http_client,
            policy=_policy(),
            refresh_cooldown_seconds=60,
        )
        with pytest.raises(SigningKeyError):
            await resolver.resolve(
                jwks_uri=_JWKS_URI,
                token=_token(attacker_one, kid="unknown-1", algorithm="RS256"),
            )
        with pytest.raises(SigningKeyError):
            await resolver.resolve(
                jwks_uri=_JWKS_URI,
                token=_token(attacker_two, kid="unknown-2", algorithm="RS256"),
            )

    assert calls == 2


@pytest.mark.parametrize(
    "header",
    [
        {"alg": "HS256", "kid": "key"},
        {"alg": ["RS256"], "kid": "key"},
        {"alg": "RS256"},
        {"alg": "RS256", "kid": ""},
    ],
)
async def test_invalid_or_disallowed_headers_fail_before_network(header: dict[str, object]) -> None:
    calls = 0

    def respond(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(500)

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as http_client:
        resolver = JwksKeyResolver(http_client=http_client, policy=_policy())
        with pytest.raises(SigningKeyError):
            await resolver.resolve(jwks_uri=_JWKS_URI, token=_raw_token_header(header))

    assert calls == 0


async def test_duplicate_kid_document_fails_closed() -> None:
    private_key, jwk = _rsa_material("duplicate")

    def respond(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"keys": [jwk, dict(jwk)]})

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as http_client:
        resolver = JwksKeyResolver(http_client=http_client, policy=_policy())
        with pytest.raises(SigningKeyError):
            await resolver.resolve(
                jwks_uri=_JWKS_URI,
                token=_token(private_key, kid="duplicate", algorithm="RS256"),
            )


@pytest.mark.parametrize(
    ("mutation", "algorithm"),
    [
        ({"alg": "ES256"}, "RS256"),
        ({"kty": "EC"}, "RS256"),
        ({"use": "enc"}, "RS256"),
        ({"key_ops": ["sign"]}, "RS256"),
    ],
)
async def test_incompatible_jwk_cannot_satisfy_token_algorithm(
    mutation: dict[str, object], algorithm: str
) -> None:
    private_key, jwk = _rsa_material("key")
    jwk.update(mutation)

    def respond(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"keys": [jwk]})

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as http_client:
        resolver = JwksKeyResolver(http_client=http_client, policy=_policy())
        with pytest.raises(SigningKeyError):
            await resolver.resolve(
                jwks_uri=_JWKS_URI,
                token=_token(private_key, kid="key", algorithm=algorithm),
            )


async def test_untrusted_jwks_origin_is_rejected_before_network() -> None:
    private_key, _jwk = _rsa_material("key")
    calls = 0

    def respond(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(500)

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as http_client:
        resolver = JwksKeyResolver(http_client=http_client, policy=_policy())
        with pytest.raises(SigningKeyError):
            await resolver.resolve(
                jwks_uri="https://attacker.example.invalid/jwks",
                token=_token(private_key, kid="key", algorithm="RS256"),
            )

    assert calls == 0
