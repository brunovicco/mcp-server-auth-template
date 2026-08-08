import asyncio
import base64
import json

from starlette.types import Message, Receive, Scope, Send

from mcp_server_auth_template.adapters.progressive_auth_http import (
    ProgressiveAuthorizationMiddleware,
    current_progressive_authorization_context,
)


def _scope(*, headers: list[tuple[bytes, bytes]]) -> Scope:
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
        "headers": headers,
        "client": ("127.0.0.1", 12345),
        "server": ("mcp.example.invalid", 443),
    }


async def _receive() -> Message:
    return {"type": "http.request", "body": b"", "more_body": False}


async def test_scope_challenge_replaces_the_sdk_auth_response() -> None:
    observed_name: str | None = None

    async def app(scope: Scope, receive: Receive, send: Send) -> None:
        nonlocal observed_name
        context = current_progressive_authorization_context()
        assert context is not None
        assert context.target is not None
        observed_name = context.target.name
        context.required_scopes = ("files:write",)
        await send(
            {
                "type": "http.response.start",
                "status": 401,
                "headers": [(b"content-type", b"application/json")],
            }
        )
        await send({"type": "http.response.body", "body": b'{"error":"invalid_token"}'})

    middleware = ProgressiveAuthorizationMiddleware(
        app,
        resource_metadata_url="https://mcp.example.invalid/.well-known/oauth-protected-resource",
    )
    messages: list[Message] = []

    async def send(message: Message) -> None:
        messages.append(message)

    await middleware(
        _scope(
            headers=[
                (b"mcp-protocol-version", b"2026-07-28"),
                (b"mcp-method", b"tools/call"),
                (b"mcp-name", b"write_file"),
            ]
        ),
        _receive,
        send,
    )

    assert observed_name == "write_file"
    assert [message["type"] for message in messages] == [
        "http.response.start",
        "http.response.body",
    ]
    start = messages[0]
    assert start["status"] == 403
    headers = dict(start["headers"])
    challenge = headers[b"www-authenticate"].decode("ascii")
    assert 'error="insufficient_scope"' in challenge
    assert 'scope="files:write"' in challenge
    assert (
        'resource_metadata="https://mcp.example.invalid/.well-known/oauth-protected-resource"'
        in challenge
    )
    assert headers[b"cache-control"] == b"no-store"
    body = json.loads(messages[1]["body"])
    assert body["error"] == "insufficient_scope"


async def test_base64_encoded_mcp_name_is_decoded_for_policy_lookup() -> None:
    tool_name = "relatório"
    encoded = base64.b64encode(tool_name.encode("utf-8")).decode("ascii")
    observed_name: str | None = None

    async def app(scope: Scope, receive: Receive, send: Send) -> None:
        nonlocal observed_name
        context = current_progressive_authorization_context()
        assert context is not None
        assert context.target is not None
        observed_name = context.target.name
        await send({"type": "http.response.start", "status": 204, "headers": []})
        await send({"type": "http.response.body", "body": b""})

    middleware = ProgressiveAuthorizationMiddleware(
        app,
        resource_metadata_url="https://mcp.example.invalid/.well-known/oauth-protected-resource",
    )
    messages: list[Message] = []

    async def send(message: Message) -> None:
        messages.append(message)

    await middleware(
        _scope(
            headers=[
                (b"mcp-protocol-version", b"2026-07-28"),
                (b"mcp-method", b"tools/call"),
                (b"mcp-name", f"=?base64?{encoded}?=".encode("ascii")),
            ]
        ),
        _receive,
        send,
    )

    assert observed_name == tool_name
    assert messages[0]["status"] == 204


async def test_legacy_or_ambiguous_headers_are_not_used_for_pre_dispatch_policy() -> None:
    observed_targets: list[object | None] = []

    async def app(scope: Scope, receive: Receive, send: Send) -> None:
        context = current_progressive_authorization_context()
        assert context is not None
        observed_targets.append(context.target)
        await send({"type": "http.response.start", "status": 401, "headers": []})
        await send({"type": "http.response.body", "body": b"legacy"})

    middleware = ProgressiveAuthorizationMiddleware(
        app,
        resource_metadata_url="https://mcp.example.invalid/.well-known/oauth-protected-resource",
    )

    async def run(headers: list[tuple[bytes, bytes]]) -> list[Message]:
        messages: list[Message] = []

        async def send(message: Message) -> None:
            messages.append(message)

        await middleware(_scope(headers=headers), _receive, send)
        return messages

    legacy_messages = await run(
        [
            (b"mcp-protocol-version", b"2025-11-25"),
            (b"mcp-method", b"tools/call"),
            (b"mcp-name", b"customer"),
        ]
    )
    duplicate_messages = await run(
        [
            (b"mcp-protocol-version", b"2026-07-28"),
            (b"mcp-method", b"tools/call"),
            (b"mcp-name", b"customer"),
            (b"mcp-name", b"payment"),
        ]
    )

    assert observed_targets == [None, None]
    assert legacy_messages[0]["status"] == 401
    assert duplicate_messages[0]["status"] == 401


async def test_concurrent_requests_do_not_share_scope_challenge_state() -> None:
    async def app(scope: Scope, receive: Receive, send: Send) -> None:
        context = current_progressive_authorization_context()
        assert context is not None
        assert context.target is not None
        await asyncio.sleep(0)
        context.required_scopes = (f"{context.target.name}:write",)
        await send({"type": "http.response.start", "status": 401, "headers": []})
        await send({"type": "http.response.body", "body": b"denied"})

    middleware = ProgressiveAuthorizationMiddleware(
        app,
        resource_metadata_url="https://mcp.example.invalid/.well-known/oauth-protected-resource",
    )

    async def run(tool_name: str) -> str:
        messages: list[Message] = []

        async def send(message: Message) -> None:
            messages.append(message)

        await middleware(
            _scope(
                headers=[
                    (b"mcp-protocol-version", b"2026-07-28"),
                    (b"mcp-method", b"tools/call"),
                    (b"mcp-name", tool_name.encode("ascii")),
                ]
            ),
            _receive,
            send,
        )
        headers: list[tuple[bytes, bytes]] = messages[0]["headers"]
        return dict(headers)[b"www-authenticate"].decode("ascii")

    customer_challenge, report_challenge = await asyncio.gather(
        run("customer"),
        run("report"),
    )

    assert 'scope="customer:write"' in customer_challenge
    assert 'scope="report:write"' in report_challenge
