"""Tests for the early Streamable HTTP admission boundary."""

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any, cast

from mcp.server.transport_security import TransportSecuritySettings
from starlette.types import Message, Receive, Scope, Send

from mcp_server_auth_template.adapters.http_transport_security import (
    HttpTransportAdmissionMiddleware,
)

_APP = Callable[[Scope, Receive, Send], Awaitable[None]]


def _scope(
    *,
    method: str = "POST",
    path: str = "/mcp",
    headers: list[tuple[bytes, bytes]] | None = None,
) -> Scope:
    base_headers = [
        (b"host", b"mcp.example.invalid"),
        (b"content-type", b"application/json"),
    ]
    return cast(
        Scope,
        {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": method,
            "scheme": "https",
            "path": path,
            "raw_path": path.encode("ascii"),
            "query_string": b"",
            "headers": base_headers if headers is None else headers,
            "client": ("127.0.0.1", 12345),
            "server": ("mcp.example.invalid", 443),
            "root_path": "",
        },
    )


def _settings() -> TransportSecuritySettings:
    return TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=["mcp.example.invalid", "mcp.example.invalid:443"],
        allowed_origins=["https://mcp.example.invalid"],
    )


def _middleware(app: _APP, *, concurrency: int = 2) -> HttpTransportAdmissionMiddleware:
    return HttpTransportAdmissionMiddleware(
        app,
        transport_security=_settings(),
        mcp_path="/mcp",
        max_header_count=8,
        max_header_bytes=512,
        max_concurrent_requests=concurrency,
    )


async def _invoke(
    app: _APP,
    scope: Scope,
) -> list[Message]:
    messages: list[Message] = []
    delivered = False

    async def receive() -> Message:
        nonlocal delivered
        if not delivered:
            delivered = True
            return {"type": "http.request", "body": b"", "more_body": False}
        return {"type": "http.disconnect"}

    async def send(message: Message) -> None:
        messages.append(message)

    await app(scope, receive, send)
    return messages


def _status(messages: list[Message]) -> int:
    start = cast(dict[str, Any], messages[0])
    return int(start["status"])


def _response_headers(messages: list[Message]) -> dict[bytes, bytes]:
    start = cast(dict[str, Any], messages[0])
    return dict(cast(list[tuple[bytes, bytes]], start.get("headers", [])))


async def _ok_app(scope: Scope, receive: Receive, send: Send) -> None:
    del scope, receive
    await send({"type": "http.response.start", "status": 204, "headers": []})
    await send({"type": "http.response.body", "body": b""})


async def test_valid_host_and_origin_reach_the_inner_app() -> None:
    headers = [
        (b"host", b"mcp.example.invalid"),
        (b"origin", b"https://mcp.example.invalid"),
        (b"content-type", b"application/json"),
    ]

    messages = await _invoke(_middleware(_ok_app), _scope(headers=headers))

    assert _status(messages) == 204


async def test_invalid_host_is_rejected_before_the_inner_app() -> None:
    messages = await _invoke(
        _middleware(_ok_app),
        _scope(headers=[(b"host", b"evil.invalid"), (b"content-type", b"application/json")]),
    )

    assert _status(messages) == 421


async def test_invalid_origin_is_rejected_before_the_inner_app() -> None:
    headers = [
        (b"host", b"mcp.example.invalid"),
        (b"origin", b"https://evil.invalid"),
        (b"content-type", b"application/json"),
    ]

    messages = await _invoke(_middleware(_ok_app), _scope(headers=headers))

    assert _status(messages) == 403


async def test_post_without_json_content_type_is_rejected() -> None:
    messages = await _invoke(
        _middleware(_ok_app),
        _scope(headers=[(b"host", b"mcp.example.invalid")]),
    )

    assert _status(messages) == 400


async def test_duplicate_security_critical_header_is_rejected() -> None:
    headers = [
        (b"host", b"mcp.example.invalid"),
        (b"content-type", b"application/json"),
        (b"authorization", b"Bearer one"),
        (b"authorization", b"Bearer two"),
    ]

    messages = await _invoke(_middleware(_ok_app), _scope(headers=headers))

    assert _status(messages) == 400


async def test_content_length_and_transfer_encoding_are_rejected_together() -> None:
    headers = [
        (b"host", b"mcp.example.invalid"),
        (b"content-type", b"application/json"),
        (b"content-length", b"2"),
        (b"transfer-encoding", b"chunked"),
    ]

    messages = await _invoke(_middleware(_ok_app), _scope(headers=headers))

    assert _status(messages) == 400


async def test_header_count_is_bounded() -> None:
    headers = [
        (b"host", b"mcp.example.invalid"),
        (b"content-type", b"application/json"),
        *[(f"x-{index}".encode(), b"v") for index in range(7)],
    ]

    messages = await _invoke(_middleware(_ok_app), _scope(headers=headers))

    assert _status(messages) == 431


async def test_header_bytes_are_bounded() -> None:
    headers = [
        (b"host", b"mcp.example.invalid"),
        (b"content-type", b"application/json"),
        (b"x-large", b"a" * 480),
    ]

    messages = await _invoke(_middleware(_ok_app), _scope(headers=headers))

    assert _status(messages) == 431


async def test_mcp_endpoint_accepts_post_only() -> None:
    messages = await _invoke(
        _middleware(_ok_app),
        _scope(method="GET", headers=[(b"host", b"mcp.example.invalid")]),
    )

    assert _status(messages) == 405
    assert _response_headers(messages)[b"allow"] == b"POST"


async def test_concurrency_limit_rejects_excess_request() -> None:
    entered = asyncio.Event()
    release = asyncio.Event()
    first_messages: list[Message] | None = None

    async def blocking_app(scope: Scope, receive: Receive, send: Send) -> None:
        del scope, receive
        entered.set()
        await release.wait()
        await send({"type": "http.response.start", "status": 204, "headers": []})
        await send({"type": "http.response.body", "body": b""})

    middleware = _middleware(blocking_app, concurrency=1)

    async def run_first() -> None:
        nonlocal first_messages
        first_messages = await _invoke(middleware, _scope())

    first_task = asyncio.create_task(run_first())
    await entered.wait()
    second_messages = await _invoke(middleware, _scope())
    assert _status(second_messages) == 503
    assert _response_headers(second_messages)[b"retry-after"] == b"1"
    release.set()
    await first_task

    assert first_messages is not None
    assert _status(first_messages) == 204
