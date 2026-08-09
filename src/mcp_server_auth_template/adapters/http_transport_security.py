"""Early admission controls for the Streamable HTTP surface.

The MCP SDK validates Host/Origin again inside the transport.  This outer
ASGI middleware intentionally repeats that check *before* authentication so a
malformed or DNS-rebinding request cannot consume JWT verification or OIDC/JWKS
work first.  It also bounds header parsing fallout and in-process concurrency.
"""

from threading import Lock
from typing import cast

from mcp.server.transport_security import TransportSecurityMiddleware, TransportSecuritySettings
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp, Receive, Scope, Send

from mcp_server_auth_template.adapters.security_audit import (
    SecurityAuditAction,
    SecurityAuditOutcome,
    emit_security_audit,
)

_CRITICAL_SINGLETON_HEADERS = frozenset(
    {
        b"authorization",
        b"content-length",
        b"content-type",
        b"host",
        b"mcp-method",
        b"mcp-name",
        b"mcp-protocol-version",
        b"mcp-session-id",
        b"origin",
        b"transfer-encoding",
    }
)


class HttpTransportAdmissionMiddleware:
    """Reject abusive HTTP envelopes before auth and MCP request processing."""

    def __init__(
        self,
        app: ASGIApp,
        *,
        transport_security: TransportSecuritySettings,
        mcp_path: str,
        max_header_count: int,
        max_header_bytes: int,
        max_concurrent_requests: int,
        operational_paths: frozenset[str] | None = None,
    ) -> None:
        """Create a bounded, fail-closed admission boundary."""
        self._app = app
        self._transport_security = TransportSecurityMiddleware(transport_security)
        self._mcp_path = mcp_path
        self._max_header_count = max_header_count
        self._max_header_bytes = max_header_bytes
        self._max_concurrent_requests = max_concurrent_requests
        self._operational_paths = operational_paths or frozenset()
        self._in_flight = 0
        self._in_flight_lock = Lock()

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Validate the envelope and admit at most the configured concurrency."""
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return

        rejection = self._validate_envelope(scope)
        if rejection is not None:
            await rejection(scope, receive, send)
            return

        if scope["path"] in self._operational_paths:
            # Keep envelope budgets, but probes must not depend on public Host/Origin or auth load.
            await self._app(scope, receive, send)
            return

        request = Request(scope, receive)
        transport_rejection = await self._transport_security.validate_request(
            request,
            is_post=request.method == "POST",
        )
        if transport_rejection is not None:
            _audit_transport_rejection("host_or_origin_rejected", transport_rejection.status_code)
            await transport_rejection(scope, receive, send)
            return

        if scope["path"] == self._mcp_path and request.method != "POST":
            _audit_transport_rejection("method_not_allowed", 405)
            response = Response(status_code=405, headers={"Allow": "POST"})
            await response(scope, receive, send)
            return

        if not self._try_admit():
            _audit_transport_rejection("concurrency_limit", 503)
            response = Response(
                "Server is at its request concurrency limit",
                status_code=503,
                headers={"Retry-After": "1"},
            )
            await response(scope, receive, send)
            return

        try:
            await self._app(scope, receive, send)
        finally:
            self._release()

    def _try_admit(self) -> bool:
        with self._in_flight_lock:
            if self._in_flight >= self._max_concurrent_requests:
                return False
            self._in_flight += 1
            return True

    def _release(self) -> None:
        with self._in_flight_lock:
            self._in_flight -= 1

    def _validate_envelope(self, scope: Scope) -> Response | None:
        headers = cast(list[tuple[bytes, bytes]], scope.get("headers", []))
        if len(headers) > self._max_header_count:
            _audit_transport_rejection("header_count_limit", 431)
            return Response("Too many request headers", status_code=431)

        total_bytes = sum(len(name) + len(value) + 4 for name, value in headers)
        if total_bytes > self._max_header_bytes:
            _audit_transport_rejection("header_bytes_limit", 431)
            return Response("Request headers too large", status_code=431)

        seen_singletons: set[bytes] = set()
        has_content_length = False
        has_transfer_encoding = False
        for raw_name, _ in headers:
            name = raw_name.lower()
            if name == b"content-length":
                has_content_length = True
            elif name == b"transfer-encoding":
                has_transfer_encoding = True

            if name not in _CRITICAL_SINGLETON_HEADERS:
                continue
            if name in seen_singletons:
                _audit_transport_rejection("duplicate_security_header", 400)
                return Response("Duplicate security-critical header", status_code=400)
            seen_singletons.add(name)

        if has_content_length and has_transfer_encoding:
            _audit_transport_rejection("ambiguous_request_framing", 400)
            return Response("Ambiguous request framing", status_code=400)
        return None


def _audit_transport_rejection(reason: str, status_code: int) -> None:
    emit_security_audit(
        SecurityAuditAction.TRANSPORT_REJECTED,
        SecurityAuditOutcome.DENIED,
        reason=reason,
        status_code=status_code,
    )
