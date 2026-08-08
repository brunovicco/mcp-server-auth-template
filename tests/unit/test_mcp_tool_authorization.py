from types import SimpleNamespace
from typing import Any, cast

from mcp.server.auth.middleware.bearer_auth import AuthenticatedUser
from mcp.server.auth.provider import AccessToken
from mcp.server.context import CallNext, HandlerResult, ServerRequestContext
from mcp_types import CallToolResult, ListToolsResult, TextContent, Tool

from mcp_server_auth_template.adapters.mcp_tool_authorization import ToolAuthorizationMiddleware
from mcp_server_auth_template.application.tool_authorization import (
    ToolAuthorizationService,
    ToolPolicy,
)


def _request(*, scopes: list[str], claims: dict[str, object]) -> object:
    token = AccessToken(
        token="opaque-token-value",
        client_id="client-123",
        scopes=scopes,
        subject="subject-456",
        claims=claims,
    )
    return SimpleNamespace(user=AuthenticatedUser(token))


def _context(
    method: str, *, params: dict[str, object] | None, request: object
) -> ServerRequestContext[Any, Any]:
    return cast(
        ServerRequestContext[Any, Any],
        SimpleNamespace(method=method, params=params, request=request),
    )


def _next_returning(result: HandlerResult) -> CallNext:
    async def call_next(_: ServerRequestContext[Any, Any]) -> HandlerResult:
        return result

    return call_next


async def test_tools_list_hides_tools_the_principal_cannot_call() -> None:
    authorizer = ToolAuthorizationService(
        {
            "health": ToolPolicy.authenticated(),
            "customer": ToolPolicy.delegated_scopes("customer.read"),
            "payment": ToolPolicy.application_roles("Payment.Execute"),
        }
    )
    middleware = ToolAuthorizationMiddleware(authorizer=authorizer, auth_provider="entra")
    result = ListToolsResult(
        tools=[
            Tool.model_validate(
                {"name": "health", "description": "health", "inputSchema": {"type": "object"}}
            ),
            Tool.model_validate(
                {
                    "name": "customer",
                    "description": "customer",
                    "inputSchema": {"type": "object"},
                }
            ),
            Tool.model_validate(
                {
                    "name": "payment",
                    "description": "payment",
                    "inputSchema": {"type": "object"},
                }
            ),
            Tool.model_validate(
                {
                    "name": "unconfigured",
                    "description": "unconfigured",
                    "inputSchema": {"type": "object"},
                }
            ),
        ]
    )
    ctx = _context(
        "tools/list",
        params=None,
        request=_request(scopes=["customer.read"], claims={"scp": "customer.read"}),
    )

    filtered = await middleware(ctx, _next_returning(result))

    assert isinstance(filtered, ListToolsResult)
    assert [tool.name for tool in filtered.tools] == ["health", "customer"]


async def test_tools_call_denies_before_the_tool_handler_runs() -> None:
    authorizer = ToolAuthorizationService(
        {"payment": ToolPolicy.application_roles("Payment.Execute")}
    )
    middleware = ToolAuthorizationMiddleware(authorizer=authorizer, auth_provider="entra")
    called = False

    async def call_next(_: ServerRequestContext[Any, Any]) -> HandlerResult:
        nonlocal called
        called = True
        return CallToolResult(content=[TextContent(type="text", text="ok")])

    ctx = _context(
        "tools/call",
        params={"name": "payment", "arguments": {}},
        request=_request(
            scopes=["Payment.Execute"],
            claims={"scp": "Payment.Execute", "roles": ["Payment.Execute"]},
        ),
    )

    result = await middleware(ctx, call_next)

    assert isinstance(result, CallToolResult)
    assert result.is_error is True
    assert called is False


async def test_tools_call_allows_explicit_app_role_with_app_identity() -> None:
    authorizer = ToolAuthorizationService(
        {"payment": ToolPolicy.application_roles("Payment.Execute")}
    )
    middleware = ToolAuthorizationMiddleware(authorizer=authorizer, auth_provider="entra")
    expected = CallToolResult(content=[TextContent(type="text", text="ok")])
    ctx = _context(
        "tools/call",
        params={"name": "payment", "arguments": {}},
        request=_request(
            scopes=[],
            claims={"idtyp": "app", "roles": ["Payment.Execute"]},
        ),
    )

    result = await middleware(ctx, _next_returning(expected))

    assert result is expected


async def test_malformed_tools_call_is_left_to_sdk_validation() -> None:
    authorizer = ToolAuthorizationService({"health": ToolPolicy.authenticated()})
    middleware = ToolAuthorizationMiddleware(authorizer=authorizer, auth_provider="generic")
    expected = CallToolResult(content=[TextContent(type="text", text="ok")])
    ctx = _context(
        "tools/call",
        params={"arguments": {}},
        request=_request(scopes=[], claims={}),
    )

    result = await middleware(ctx, _next_returning(expected))

    assert result is expected
