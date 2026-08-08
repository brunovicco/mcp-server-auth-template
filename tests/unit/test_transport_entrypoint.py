"""Integration tests for the hardened Streamable HTTP app wiring."""

from typing import cast

from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.server.auth.provider import AccessToken
from mcp.server.auth.settings import AuthSettings
from mcp.server.mcpserver import MCPServer
from starlette.testclient import TestClient

from mcp_server_auth_template.entrypoints.mcp_server import (
    _build_streamable_http_app,
    _build_transport_security,
)
from mcp_server_auth_template.entrypoints.settings import Settings

_PROTOCOL_VERSION = "2026-07-28"
_RESOURCE_URL = "https://mcp.example.invalid"


class _TokenVerifier:
    def __init__(self) -> None:
        self.calls = 0

    async def verify_token(self, token: str) -> AccessToken | None:
        self.calls += 1
        if token not in {"alice-token", "bob-token"}:
            return None
        subject = token.removesuffix("-token")
        return AccessToken(
            token=token,
            client_id=f"{subject}-client",
            scopes=[],
            expires_at=None,
            resource=_RESOURCE_URL,
            subject=subject,
        )


def _settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "auth_provider": "generic",
        "resource_server_url": _RESOURCE_URL,
        "generic_issuer_url": "https://as.example.invalid",
        "generic_audience": _RESOURCE_URL,
    }
    values.update(overrides)
    return Settings.model_validate(values)


def _modern_tool_request() -> dict[str, object]:
    return {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {
            "name": "whoami",
            "arguments": {},
            "_meta": {
                "io.modelcontextprotocol/protocolVersion": _PROTOCOL_VERSION,
                "io.modelcontextprotocol/clientInfo": {
                    "name": "transport-security-test",
                    "version": "1.0.0",
                },
                "io.modelcontextprotocol/clientCapabilities": {},
            },
        },
    }


def _headers(token: str, *, session_id: str | None = None) -> dict[str, str]:
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Accept": "application/json",
        "MCP-Protocol-Version": _PROTOCOL_VERSION,
        "Mcp-Method": "tools/call",
        "Mcp-Name": "whoami",
    }
    if session_id is not None:
        headers["Mcp-Session-Id"] = session_id
    return headers


def _server(verifier: _TokenVerifier) -> MCPServer:
    server = MCPServer(
        name="transport-security-test",
        token_verifier=verifier,
        auth=AuthSettings(
            issuer_url="https://as.example.invalid",
            resource_server_url=_RESOURCE_URL,
        ),
    )

    def whoami() -> dict[str, object]:
        access_token = get_access_token()
        assert access_token is not None
        return {
            "subject": access_token.subject,
            "client_id": access_token.client_id,
        }

    server.tool(name="whoami", description="Return the request-scoped principal.")(whoami)
    return server


def test_transport_security_derives_exact_resource_authority_and_extras() -> None:
    settings = _settings(
        transport_allowed_hosts=["proxy.example.invalid:8443"],
        transport_allowed_origins=["https://console.example.invalid"],
    )

    security = _build_transport_security(settings)

    assert security.enable_dns_rebinding_protection is True
    assert security.allowed_hosts == [
        "mcp.example.invalid",
        "mcp.example.invalid:443",
        "proxy.example.invalid:8443",
    ]
    assert security.allowed_origins == [
        "https://mcp.example.invalid",
        "https://console.example.invalid",
    ]


def test_modern_requests_ignore_legacy_session_header_and_keep_identity_request_scoped() -> None:
    verifier = _TokenVerifier()
    app = _build_streamable_http_app(_server(verifier), _settings())
    shared_legacy_session = "legacy-session-id-must-not-bind-principal"

    with TestClient(app, base_url=_RESOURCE_URL) as client:
        alice = client.post(
            "/mcp",
            json=_modern_tool_request(),
            headers=_headers("alice-token", session_id=shared_legacy_session),
        )
        bob = client.post(
            "/mcp",
            json=_modern_tool_request(),
            headers=_headers("bob-token", session_id=shared_legacy_session),
        )

    assert alice.status_code == 200
    assert bob.status_code == 200
    assert "mcp-session-id" not in alice.headers
    assert "mcp-session-id" not in bob.headers
    alice_result = cast(dict[str, object], alice.json()["result"])
    bob_result = cast(dict[str, object], bob.json()["result"])
    assert cast(dict[str, object], alice_result["structuredContent"])["subject"] == "alice"
    assert cast(dict[str, object], bob_result["structuredContent"])["subject"] == "bob"
    assert verifier.calls == 2


def test_invalid_origin_is_rejected_before_bearer_verification() -> None:
    verifier = _TokenVerifier()
    app = _build_streamable_http_app(_server(verifier), _settings())
    headers = _headers("alice-token")
    headers["Origin"] = "https://evil.example.invalid"

    with TestClient(app, base_url=_RESOURCE_URL) as client:
        response = client.post("/mcp", json=_modern_tool_request(), headers=headers)

    assert response.status_code == 403
    assert verifier.calls == 0


def test_request_body_limit_is_wired_into_the_sdk_transport() -> None:
    verifier = _TokenVerifier()
    settings = _settings(transport_max_request_body_bytes=1024)
    app = _build_streamable_http_app(_server(verifier), settings)
    oversized_body = b"{" + (b" " * 2048) + b"}"

    with TestClient(app, base_url=_RESOURCE_URL) as client:
        response = client.post(
            "/mcp",
            content=oversized_body,
            headers=_headers("alice-token"),
        )

    assert response.status_code == 413
