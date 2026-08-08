"""Security audit contract and token-boundary regression tests."""

from dataclasses import fields
from typing import Any

import pytest

from mcp_server_auth_template.adapters import security_audit
from mcp_server_auth_template.adapters.security_audit import (
    SecurityAuditAction,
    SecurityAuditOutcome,
    emit_security_audit,
)
from mcp_server_auth_template.domain.principal import Principal, PrincipalKind
from mcp_server_auth_template.entrypoints.logging import redact_security_secrets


class _CapturedLogger:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict[str, object]]] = []

    def info(self, event: str, **fields: object) -> None:
        self.events.append((event, fields))


def _principal() -> Principal:
    return Principal(
        client_id="client-123",
        subject="user@example.invalid",
        issuer="https://issuer.example.invalid",
        kind=PrincipalKind.DELEGATED,
        scopes=frozenset({"customer.read"}),
        roles=frozenset({"Operator"}),
    )


def test_principal_cannot_carry_raw_token_or_claims() -> None:
    names = {field.name for field in fields(Principal)}

    assert "token" not in names
    assert "access_token" not in names
    assert "claims" not in names


def test_audit_event_contains_only_minimized_identity(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = _CapturedLogger()
    monkeypatch.setattr(security_audit, "logger", captured)

    emit_security_audit(
        SecurityAuditAction.AUTHORIZATION_DENIED,
        SecurityAuditOutcome.DENIED,
        reason="missing_permission",
        principal=_principal(),
        tool_name="payment",
        status_code=403,
        required_scope_count=1,
    )

    event, payload = captured.events[0]
    assert event == "security_audit"
    assert payload == {
        "schema_version": 1,
        "action": "authorization_denied",
        "outcome": "denied",
        "reason": "missing_permission",
        "principal_kind": "delegated",
        "client_id": "client-123",
        "tool_name": "payment",
        "status_code": 403,
        "required_scope_count": 1,
    }
    serialized = repr(payload)
    assert "user@example.invalid" not in serialized
    assert "customer.read" not in serialized
    assert "Operator" not in serialized


def test_logging_redactor_removes_nested_credentials_and_bearer_strings() -> None:
    event: dict[str, Any] = {
        "authorization": "Bearer top-secret-token",
        "nested": {
            "refresh_token": "refresh-secret",
            "message": "request failed: Bearer another-secret",
        },
        "url": "https://example.invalid/callback?access_token=query-secret&ok=1",
        "safe": "keep-me",
    }

    redacted = redact_security_secrets(None, "info", event)

    serialized = repr(redacted)
    assert "top-secret-token" not in serialized
    assert "refresh-secret" not in serialized
    assert "another-secret" not in serialized
    assert "query-secret" not in serialized
    assert redacted["safe"] == "keep-me"
