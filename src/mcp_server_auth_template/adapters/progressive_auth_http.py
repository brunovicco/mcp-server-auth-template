"""HTTP bridge for MCP progressive OAuth authorization challenges.

MCP 2026-07-28 mirrors the request method and principal name into HTTP
headers, allowing a resource server to determine the minimum OAuth scopes for
an operation before MCP dispatch.  This module intentionally does not parse
the JSON-RPC body or validate bearer tokens; those responsibilities remain
with the MCP SDK.
"""

import base64
import binascii
import json
from contextvars import ContextVar
from dataclasses import dataclass

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from mcp_server_auth_template.adapters.security_audit import (
    SecurityAuditAction,
    SecurityAuditOutcome,
    emit_security_audit,
)

_MODERN_PROTOCOL_VERSION = "2026-07-28"
_BASE64_PREFIX = "=?base64?"
_BASE64_SUFFIX = "?="
_CONTEXT_KEY: ContextVar["ProgressiveAuthorizationContext | None"] = ContextVar(
    "mcp_progressive_authorization_context",
    default=None,
)


@dataclass(frozen=True, slots=True)
class McpRequestTarget:
    """Trusted-enough routing metadata for a modern MCP HTTP request.

    The SDK still validates these mirrored headers against the JSON-RPC body.
    This target only lets authentication fail early with an OAuth scope
    challenge; it is never the final authorization decision.
    """

    method: str
    name: str


@dataclass(slots=True)
class ProgressiveAuthorizationContext:
    """Mutable request-local state shared with the token-verifier decorator."""

    is_mcp_request: bool
    target: McpRequestTarget | None
    required_scopes: tuple[str, ...] = ()


class ProgressiveAuthorizationMiddleware:
    """Translate a verifier-declared scope upgrade into HTTP 403.

    The MCP SDK owns authentication.  When the decorated verifier determines
    that a valid token is missing a configured global scope or a modern
    ``tools/call`` scope, it records those scopes in this middleware's
    request-local context and returns ``None``. The SDK consequently emits its
    ordinary 401 response;
    this outer middleware replaces that response with the MCP/OAuth-required
    403 ``insufficient_scope`` challenge.
    """

    def __init__(
        self,
        app: ASGIApp,
        *,
        resource_metadata_url: str,
        mcp_path: str = "/mcp",
    ) -> None:
        """Wrap an MCP Starlette app with one protected-resource metadata URL."""
        self._app = app
        self._resource_metadata_url = resource_metadata_url
        self._mcp_path = mcp_path

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Serve the request while carrying progressive-auth request state."""
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return

        is_mcp_request = scope.get("method") == "POST" and scope.get("path") == self._mcp_path
        context = ProgressiveAuthorizationContext(
            is_mcp_request=is_mcp_request,
            target=_target_from_scope(scope) if is_mcp_request else None,
        )
        reset_token = _CONTEXT_KEY.set(context)
        response_replaced = False

        async def send_with_scope_challenge(message: Message) -> None:
            nonlocal response_replaced
            if message["type"] == "http.response.start" and context.required_scopes:
                emit_security_audit(
                    SecurityAuditAction.OAUTH_SCOPE_STEP_UP,
                    SecurityAuditOutcome.CHALLENGED,
                    reason="missing_permission",
                    tool_name=context.target.name if context.target is not None else None,
                    status_code=403,
                    required_scope_count=len(context.required_scopes),
                )
                await _send_insufficient_scope_response(
                    send,
                    required_scopes=context.required_scopes,
                    resource_metadata_url=self._resource_metadata_url,
                )
                response_replaced = True
                return
            if message["type"] == "http.response.body" and response_replaced:
                # The replacement response body was sent together with its start.
                return
            await send(message)

        try:
            await self._app(scope, receive, send_with_scope_challenge)
        finally:
            _CONTEXT_KEY.reset(reset_token)


def current_progressive_authorization_context() -> ProgressiveAuthorizationContext | None:
    """Return the HTTP request state visible to the token verifier."""
    return _CONTEXT_KEY.get()


async def _send_insufficient_scope_response(
    send: Send,
    *,
    required_scopes: tuple[str, ...],
    resource_metadata_url: str,
) -> None:
    body = json.dumps(
        {
            "error": "insufficient_scope",
            "error_description": "Additional authorization is required for this operation.",
        },
        separators=(",", ":"),
    ).encode("utf-8")
    scope_value = " ".join(required_scopes)
    challenge = (
        'Bearer error="insufficient_scope", '
        f'scope="{scope_value}", '
        f'resource_metadata="{resource_metadata_url}"'
    ).encode("ascii")

    await send(
        {
            "type": "http.response.start",
            "status": 403,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(body)).encode("ascii")),
                (b"cache-control", b"no-store"),
                (b"www-authenticate", challenge),
            ],
        }
    )
    await send({"type": "http.response.body", "body": body})


def _target_from_scope(scope: Scope) -> McpRequestTarget | None:
    if scope.get("method") != "POST":
        return None

    protocol_version = _single_header(scope, b"mcp-protocol-version")
    method = _single_header(scope, b"mcp-method")
    name = _single_header(scope, b"mcp-name")
    if protocol_version != _MODERN_PROTOCOL_VERSION or method != "tools/call" or name is None:
        return None

    decoded_name = _decode_header_value(name)
    if decoded_name is None or not decoded_name:
        return None
    return McpRequestTarget(method=method, name=decoded_name)


def _single_header(scope: Scope, expected_name: bytes) -> str | None:
    headers: list[tuple[bytes, bytes]] = scope.get("headers", [])
    values = [value for name, value in headers if name.lower() == expected_name]
    if len(values) != 1:
        return None
    try:
        return values[0].decode("ascii")
    except UnicodeDecodeError:
        return None


def _decode_header_value(value: str) -> str | None:
    if value.startswith(_BASE64_PREFIX) and value.endswith(_BASE64_SUFFIX):
        encoded = value[len(_BASE64_PREFIX) : -len(_BASE64_SUFFIX)]
        try:
            return base64.b64decode(encoded, validate=True).decode("utf-8")
        except (binascii.Error, UnicodeDecodeError):
            return None

    # Plain values in the standard header format must not need the sentinel
    # encoding. Leading/trailing whitespace is one of the cases that does.
    if value != value.strip():
        return None
    return value
