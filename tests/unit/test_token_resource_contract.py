"""Executable contract for ADR-0027: explicit token-resource validation.

The SDK's ``validate_token_resource`` compares ``AccessToken.resource`` to
``resource_server_url`` as strings. Provider audiences are not that URL, so the
template pins the flag to ``False`` and relies on the token verifier's own
audience check. These tests prove the flag is explicit, that the verifier still
refuses tokens minted for another resource through the full HTTP stack, and
why SDK string equality cannot be enabled.
"""

from dataclasses import dataclass
from typing import cast

import pytest
from jwt import PyJWK
from mcp.server.auth.settings import AuthSettings
from mcp.server.mcpserver import MCPServer
from starlette.testclient import TestClient

from mcp_server_auth_template.adapters.generic_oidc_token_verifier import GenericOidcTokenVerifier
from mcp_server_auth_template.domain.oidc_metadata import OidcMetadata
from mcp_server_auth_template.entrypoints.mcp_server import (
    _build_auth_settings,
    _build_streamable_http_app,
    _whoami,
    build_server,
)
from mcp_server_auth_template.entrypoints.settings import Settings
from tests.unit.auth_testing import SigningKeyPair, generate_test_keypair, sign_test_token

_PROTOCOL_VERSION = "2026-07-28"
_ISSUER = "https://as.example.invalid"
_RESOURCE_URL = "https://mcp.example.invalid"
# A provider API identifier that is deliberately not textually equal to the MCP URL.
_API_AUDIENCE = "api://mcp-server-auth-template"


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


def _settings() -> Settings:
    return Settings.model_validate(
        {
            "auth_provider": "generic",
            "resource_server_url": _RESOURCE_URL,
            "generic_issuer_url": _ISSUER,
            "generic_audience": _API_AUDIENCE,
        }
    )


def _server(keypair: SigningKeyPair, auth: AuthSettings) -> MCPServer:
    verifier = GenericOidcTokenVerifier(
        issuer_url=_ISSUER,
        audience=_API_AUDIENCE,
        discovery=_FakeDiscovery(OidcMetadata(issuer=_ISSUER, jwks_uri=f"{_ISSUER}/jwks")),
        key_resolver=_FakeKeyResolver(keypair.signing_key),
    )
    server = MCPServer(name="token-resource-contract-test", token_verifier=verifier, auth=auth)
    server.tool(name="whoami", description="Return the caller identity.")(_whoami)
    return server


def _call_whoami(server: MCPServer, token: str) -> int:
    app = _build_streamable_http_app(server, _settings())
    request = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {
            "name": "whoami",
            "arguments": {},
            "_meta": {
                "io.modelcontextprotocol/protocolVersion": _PROTOCOL_VERSION,
                "io.modelcontextprotocol/clientInfo": {"name": "contract-test", "version": "1"},
                "io.modelcontextprotocol/clientCapabilities": {},
            },
        },
    }
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Accept": "application/json",
        "MCP-Protocol-Version": _PROTOCOL_VERSION,
        "Mcp-Method": "tools/call",
        "Mcp-Name": "whoami",
    }
    with TestClient(app, base_url=_RESOURCE_URL) as client:
        response = client.post("/mcp", json=request, headers=headers)
    if response.status_code == 200:
        result = cast(dict[str, object], response.json()["result"])
        content = cast(dict[str, object], result["structuredContent"])
        assert content["authenticated"] is True
    return response.status_code


@pytest.mark.parametrize(
    "overrides",
    [
        {
            "auth_provider": "generic",
            "generic_issuer_url": _ISSUER,
            "generic_audience": _RESOURCE_URL,
        },
        {
            "auth_provider": "entra",
            "entra_tenant_id": "11111111-1111-1111-1111-111111111111",
            "entra_audience": "33333333-3333-3333-3333-333333333333",
            "entra_application_id_uri": "api://33333333-3333-3333-3333-333333333333",
        },
    ],
    ids=["generic", "entra"],
)
def test_token_resource_policy_is_explicit_for_every_provider(overrides: dict[str, str]) -> None:
    settings = Settings.model_validate({"resource_server_url": _RESOURCE_URL, **overrides})

    server = build_server(settings)

    assert server.settings.auth is not None
    assert "validate_token_resource" in server.settings.auth.model_fields_set
    assert server.settings.auth.validate_token_resource is False


def test_accepts_the_provider_audience_when_it_differs_from_the_resource_url(
    keypair: SigningKeyPair,
) -> None:
    token = sign_test_token(keypair, issuer=_ISSUER, audience=_API_AUDIENCE)
    server = _server(keypair, _build_auth_settings(_settings(), _ISSUER))

    assert _call_whoami(server, token) == 200


@pytest.mark.parametrize(
    "audience",
    [
        "api://some-other-api",
        _RESOURCE_URL,  # the MCP URL itself is not the configured provider audience
        f"{_RESOURCE_URL}/other",
    ],
)
def test_rejects_a_token_minted_for_another_resource(
    keypair: SigningKeyPair, audience: str
) -> None:
    token = sign_test_token(keypair, issuer=_ISSUER, audience=audience)
    server = _server(keypair, _build_auth_settings(_settings(), _ISSUER))

    assert _call_whoami(server, token) == 401


def test_sdk_string_equality_would_reject_valid_provider_tokens(keypair: SigningKeyPair) -> None:
    """Counterfactual: why ADR-0027 cannot delegate audience checks to the SDK."""
    token = sign_test_token(keypair, issuer=_ISSUER, audience=_API_AUDIENCE)
    strict = _build_auth_settings(_settings(), _ISSUER).model_copy(
        update={"validate_token_resource": True}
    )
    server = _server(keypair, strict)

    assert _call_whoami(server, token) == 401
