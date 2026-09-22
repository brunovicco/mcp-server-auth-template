"""Full-stack tool discovery and cache hints through the production ``build_server`` wiring.

Only the token verifier is replaced; the SDK runner, tool authorization
middleware, and Streamable HTTP app are the real ones, so these tests see the
result shape the SDK actually hands to middleware.
"""

from collections.abc import Callable, Iterator
from typing import cast

import pytest
from mcp.server.auth.provider import AccessToken, TokenVerifier
from mcp.server.caching import CACHEABLE_METHODS
from mcp_types import ListToolsResult
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
def post(monkeypatch: pytest.MonkeyPatch) -> Iterator[Post]:
    def build_verifier(*_: object, **__: object) -> TokenVerifier:
        return _ScopedTokenVerifier()

    monkeypatch.setattr(mcp_server, "_build_token_verifier", build_verifier)
    settings = _settings()
    app = mcp_server._build_streamable_http_app(mcp_server.build_server(settings), settings)

    with TestClient(app, base_url=_RESOURCE_URL) as client:

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
            response = client.post("/mcp", json=request, headers=headers)
            assert response.status_code == 200, response.text
            return cast(dict[str, object], response.json()["result"])

        yield send


def _tool_names(result: dict[str, object]) -> list[str]:
    tools = cast(list[dict[str, object]], result["tools"])
    return [cast(str, tool["name"]) for tool in tools]


def test_tools_list_shows_every_tool_the_principal_may_call(post: Post) -> None:
    assert _tool_names(post("tools/list", "health-token")) == ["whoami", "health"]


def test_tools_list_hides_tools_outside_the_principal_scopes(post: Post) -> None:
    assert _tool_names(post("tools/list", "basic-token")) == ["whoami"]


@pytest.mark.parametrize("method", ["server/discover", "tools/list"])
def test_discovery_results_carry_bounded_private_cache_hints(post: Post, method: str) -> None:
    result = post(method, "health-token")

    assert result["ttlMs"] == 30_000
    assert result["cacheScope"] == "private"


def test_principal_dependent_tool_catalogs_are_never_shareable(post: Post) -> None:
    """ADR-0028: a catalog that varies by principal must stay in its authorization context."""
    basic = post("tools/list", "basic-token")
    health = post("tools/list", "health-token")

    assert _tool_names(basic) != _tool_names(health)
    assert basic["cacheScope"] == health["cacheScope"] == "private"


def test_cache_hint_policy_is_private_bounded_and_limited_to_discovery() -> None:
    hints = mcp_server._CACHE_HINTS

    assert set(hints) == {"server/discover", "tools/list"}
    assert set(hints) <= CACHEABLE_METHODS
    for hint in hints.values():
        assert hint.scope == "private"
        assert 0 < hint.ttl_ms <= 60_000


def test_fail_closed_tool_catalog_is_immediately_stale_and_private() -> None:
    """The middleware's empty fallback bypasses server hints and keeps SDK-safe defaults."""
    wire = ListToolsResult(tools=[]).model_dump(by_alias=True, mode="json", exclude_none=True)

    assert wire["ttlMs"] == 0
    assert wire["cacheScope"] == "private"
