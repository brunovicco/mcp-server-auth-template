"""Full-stack tool discovery through the production ``build_server`` wiring.

Only the token verifier is replaced; the SDK runner, tool authorization
middleware, and Streamable HTTP app are the real ones, so these tests see the
result shape the SDK actually hands to middleware.
"""

from collections.abc import Callable
from typing import cast

import pytest
from mcp.server.auth.provider import AccessToken, TokenVerifier
from starlette.testclient import TestClient

from mcp_server_auth_template.entrypoints import mcp_server
from mcp_server_auth_template.entrypoints.settings import Settings

_PROTOCOL_VERSION = "2026-07-28"
_RESOURCE_URL = "https://mcp.example.invalid"
type Post = Callable[[str, str], dict[str, object]]

_TOKEN_SCOPES = {
    "basic-token": ["mcp:tools:call"],
    "health-token": ["mcp:tools:call", "mcp:tools:health"],
}


class _ScopedTokenVerifier:
    async def verify_token(self, token: str) -> AccessToken | None:
        scopes = _TOKEN_SCOPES.get(token)
        if scopes is None:
            return None
        return AccessToken(
            token=token,
            client_id="discovery-client",
            scopes=scopes,
            subject=token.removesuffix("-token"),
            resource=_RESOURCE_URL,
        )


def _settings() -> Settings:
    return Settings.model_validate(
        {
            "auth_provider": "generic",
            "resource_server_url": _RESOURCE_URL,
            "generic_issuer_url": "https://as.example.invalid",
            "generic_audience": _RESOURCE_URL,
        }
    )


@pytest.fixture
def post(monkeypatch: pytest.MonkeyPatch) -> Post:
    def build_verifier(*_: object, **__: object) -> TokenVerifier:
        return _ScopedTokenVerifier()

    monkeypatch.setattr(mcp_server, "_build_token_verifier", build_verifier)
    settings = _settings()
    app = mcp_server._build_streamable_http_app(mcp_server.build_server(settings), settings)

    def send(method: str, token: str) -> dict[str, object]:
        request = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": method,
            "params": {
                "_meta": {
                    "io.modelcontextprotocol/protocolVersion": _PROTOCOL_VERSION,
                    "io.modelcontextprotocol/clientInfo": {"name": "discovery", "version": "1"},
                    "io.modelcontextprotocol/clientCapabilities": {},
                }
            },
        }
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "MCP-Protocol-Version": _PROTOCOL_VERSION,
            "Mcp-Method": method,
        }
        with TestClient(app, base_url=_RESOURCE_URL) as client:
            response = client.post("/mcp", json=request, headers=headers)
        assert response.status_code == 200, response.text
        return cast(dict[str, object], response.json()["result"])

    return send


def _tool_names(result: dict[str, object]) -> list[str]:
    tools = cast(list[dict[str, object]], result["tools"])
    return [cast(str, tool["name"]) for tool in tools]


def test_tools_list_shows_every_tool_the_principal_may_call(post: Post) -> None:
    assert _tool_names(post("tools/list", "health-token")) == ["whoami", "health"]


def test_tools_list_hides_tools_outside_the_principal_scopes(post: Post) -> None:
    assert _tool_names(post("tools/list", "basic-token")) == ["whoami"]
