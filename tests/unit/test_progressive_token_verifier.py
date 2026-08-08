from mcp.server.auth.provider import AccessToken
from starlette.types import Message, Receive, Scope, Send

from mcp_server_auth_template.adapters.progressive_auth_http import (
    ProgressiveAuthorizationMiddleware,
    current_progressive_authorization_context,
)
from mcp_server_auth_template.adapters.progressive_token_verifier import (
    ProgressiveAuthorizationTokenVerifier,
)
from mcp_server_auth_template.application.tool_authorization import (
    ToolAuthorizationService,
    ToolPolicy,
)


class StubTokenVerifier:
    def __init__(self, access_token: AccessToken | None) -> None:
        self._access_token = access_token
        self.calls = 0

    async def verify_token(self, token: str) -> AccessToken | None:
        self.calls += 1
        return self._access_token


def _access_token(*, scopes: list[str], claims: dict[str, object]) -> AccessToken:
    return AccessToken(
        token="opaque-token-value",
        client_id="client-123",
        scopes=scopes,
        subject="subject-456",
        claims=claims,
    )


def _modern_scope(tool_name: str) -> Scope:
    return {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.5"},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "https",
        "path": "/mcp",
        "raw_path": b"/mcp",
        "query_string": b"",
        "root_path": "",
        "headers": [
            (b"mcp-protocol-version", b"2026-07-28"),
            (b"mcp-method", b"tools/call"),
            (b"mcp-name", tool_name.encode("ascii")),
        ],
        "client": ("127.0.0.1", 12345),
        "server": ("mcp.example.invalid", 443),
    }


async def _receive() -> Message:
    return {"type": "http.request", "body": b"", "more_body": False}


async def _inside_progressive_request(
    verifier: ProgressiveAuthorizationTokenVerifier,
    tool_name: str,
) -> tuple[AccessToken | None, tuple[str, ...]]:
    result: AccessToken | None = None
    challenged_scopes: tuple[str, ...] = ()

    async def app(scope: Scope, receive: Receive, send: Send) -> None:
        nonlocal result, challenged_scopes
        result = await verifier.verify_token("presented-token")
        context = current_progressive_authorization_context()
        assert context is not None
        challenged_scopes = context.required_scopes
        await send({"type": "http.response.start", "status": 204, "headers": []})
        await send({"type": "http.response.body", "body": b""})

    middleware = ProgressiveAuthorizationMiddleware(
        app,
        resource_metadata_url="https://mcp.example.invalid/.well-known/oauth-protected-resource",
    )

    async def send(_: Message) -> None:
        return None

    await middleware(_modern_scope(tool_name), _receive, send)
    return result, challenged_scopes


async def test_missing_delegated_scope_requests_http_step_up_after_one_verification() -> None:
    delegate = StubTokenVerifier(
        _access_token(scopes=["customer.read"], claims={"scp": "customer.read"})
    )
    verifier = ProgressiveAuthorizationTokenVerifier(
        delegate=delegate,
        authorizer=ToolAuthorizationService(
            {"customer": ToolPolicy.delegated_scopes("customer.write")}
        ),
        auth_provider="entra",
    )

    result, challenged_scopes = await _inside_progressive_request(verifier, "customer")

    assert result is None
    assert challenged_scopes == ("customer.write",)
    assert delegate.calls == 1


async def test_sufficient_scope_preserves_the_validated_access_token() -> None:
    access_token = _access_token(
        scopes=["customer.read"],
        claims={"scp": "customer.read"},
    )
    delegate = StubTokenVerifier(access_token)
    verifier = ProgressiveAuthorizationTokenVerifier(
        delegate=delegate,
        authorizer=ToolAuthorizationService(
            {"customer": ToolPolicy.delegated_scopes("customer.read")}
        ),
        auth_provider="entra",
    )

    result, challenged_scopes = await _inside_progressive_request(verifier, "customer")

    assert result is access_token
    assert challenged_scopes == ()
    assert delegate.calls == 1


async def test_wrong_principal_kind_does_not_trigger_a_meaningless_scope_upgrade() -> None:
    access_token = _access_token(
        scopes=[],
        claims={"idtyp": "app", "roles": ["Customer.Read"]},
    )
    delegate = StubTokenVerifier(access_token)
    verifier = ProgressiveAuthorizationTokenVerifier(
        delegate=delegate,
        authorizer=ToolAuthorizationService(
            {"customer": ToolPolicy.delegated_scopes("customer.read")}
        ),
        auth_provider="entra",
    )

    result, challenged_scopes = await _inside_progressive_request(verifier, "customer")

    assert result is access_token
    assert challenged_scopes == ()


async def test_invalid_token_is_not_reclassified_as_insufficient_scope() -> None:
    delegate = StubTokenVerifier(None)
    verifier = ProgressiveAuthorizationTokenVerifier(
        delegate=delegate,
        authorizer=ToolAuthorizationService({"customer": ToolPolicy.oauth_scopes("customer.read")}),
        auth_provider="generic",
    )

    result, challenged_scopes = await _inside_progressive_request(verifier, "customer")

    assert result is None
    assert challenged_scopes == ()
    assert delegate.calls == 1


async def test_global_and_per_tool_scope_requirements_are_challenged_together() -> None:
    delegate = StubTokenVerifier(_access_token(scopes=["openid"], claims={"scp": "openid"}))
    verifier = ProgressiveAuthorizationTokenVerifier(
        delegate=delegate,
        authorizer=ToolAuthorizationService(
            {"customer": ToolPolicy.delegated_scopes("customer.write")}
        ),
        auth_provider="entra",
        global_required_scopes=("mcp.base",),
    )

    result, challenged_scopes = await _inside_progressive_request(verifier, "customer")

    assert result is None
    assert challenged_scopes == ("customer.write", "mcp.base")
    assert delegate.calls == 1
