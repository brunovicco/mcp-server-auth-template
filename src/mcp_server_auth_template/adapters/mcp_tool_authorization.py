"""MCP ServerMiddleware enforcing per-tool authorization and visibility."""

from typing import Any

from mcp.server.context import CallNext, HandlerResult, ServerRequestContext
from mcp_types import CallToolResult, ListToolsResult, TextContent

from mcp_server_auth_template.adapters.mcp_principal import AuthProvider, principal_from_request
from mcp_server_auth_template.adapters.security_audit import (
    SecurityAuditAction,
    SecurityAuditOutcome,
    emit_security_audit,
)
from mcp_server_auth_template.application.tool_authorization import ToolAuthorizationService

_DENIED_TEXT = "Authorization denied for this tool."


class ToolAuthorizationMiddleware:
    """Apply one policy set to ``tools/list`` and ``tools/call`` requests."""

    def __init__(
        self, *, authorizer: ToolAuthorizationService, auth_provider: AuthProvider
    ) -> None:
        """Bind one policy registry to one configured authentication provider."""
        self._authorizer = authorizer
        self._auth_provider = auth_provider

    async def __call__(
        self,
        ctx: ServerRequestContext[Any, Any],
        call_next: CallNext,
    ) -> HandlerResult:
        """Filter tool discovery and reject unauthorized calls before tool execution."""
        if ctx.method == "tools/list":
            return self._filter_tool_list(await call_next(ctx), ctx)

        if ctx.method != "tools/call":
            return await call_next(ctx)

        params = ctx.params
        tool_name = params.get("name") if params is not None else None
        if not isinstance(tool_name, str) or not tool_name:
            # Preserve the SDK's normal validation error for malformed calls.
            return await call_next(ctx)

        principal = principal_from_request(ctx.request, self._auth_provider)
        decision = self._authorizer.authorize(tool_name, principal)
        if decision.allowed:
            return await call_next(ctx)

        emit_security_audit(
            SecurityAuditAction.AUTHORIZATION_DENIED,
            SecurityAuditOutcome.DENIED,
            reason=decision.reason.value,
            principal=principal,
            tool_name=tool_name,
        )
        return CallToolResult(
            content=[TextContent(type="text", text=_DENIED_TEXT)],
            is_error=True,
        )

    def _filter_tool_list(
        self, result: HandlerResult, ctx: ServerRequestContext[Any, Any]
    ) -> HandlerResult:
        """Keep only the tools the request principal may call.

        The SDK runner serializes handler results to their wire dict inside the
        middleware chain, so ``call_next`` normally returns a mapping here; a
        ``ListToolsResult`` is still accepted for handlers that return the model.
        Any other shape fails closed to an empty catalog rather than leaking it.
        """
        principal = principal_from_request(ctx.request, self._auth_provider)
        if isinstance(result, ListToolsResult):
            visible_models = [
                tool for tool in result.tools if self._authorizer.is_visible(tool.name, principal)
            ]
            return result.model_copy(update={"tools": visible_models})
        if isinstance(result, dict):
            tools = result.get("tools")
            if isinstance(tools, list):
                visible = [
                    tool
                    for tool in tools
                    if isinstance(tool, dict)
                    and isinstance(name := tool.get("name"), str)
                    and self._authorizer.is_visible(name, principal)
                ]
                return {**result, "tools": visible}
        return ListToolsResult(tools=[])
