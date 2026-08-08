"""Minimal, secret-free security audit events for MCP authentication and authorization."""

from enum import StrEnum

import structlog

from mcp_server_auth_template.domain.principal import Principal

logger = structlog.get_logger(__name__)


class SecurityAuditAction(StrEnum):
    """Stable security event actions suitable for downstream alerting and audit rules."""

    AUTHENTICATION_REJECTED = "authentication_rejected"
    AUTHORIZATION_DENIED = "authorization_denied"
    OAUTH_SCOPE_STEP_UP = "oauth_scope_step_up"
    TRANSPORT_REJECTED = "transport_rejected"
    OUTBOUND_CREDENTIAL_BLOCKED = "outbound_credential_blocked"


class SecurityAuditOutcome(StrEnum):
    """Stable event outcomes."""

    DENIED = "denied"
    CHALLENGED = "challenged"


def emit_security_audit(
    action: SecurityAuditAction,
    outcome: SecurityAuditOutcome,
    *,
    reason: str,
    principal: Principal | None = None,
    tool_name: str | None = None,
    status_code: int | None = None,
    required_scope_count: int | None = None,
    target_kind: str | None = None,
) -> None:
    """Emit one allowlisted audit record without tokens, claims, scopes, or request bodies."""
    fields: dict[str, object] = {
        "schema_version": 1,
        "action": action.value,
        "outcome": outcome.value,
        "reason": _bounded_text(reason, 128),
    }
    if principal is not None:
        fields["principal_kind"] = principal.kind.value
        fields["client_id"] = _bounded_text(principal.client_id, 256)
    if tool_name is not None:
        fields["tool_name"] = _bounded_text(tool_name, 256)
    if status_code is not None:
        fields["status_code"] = status_code
    if required_scope_count is not None:
        fields["required_scope_count"] = required_scope_count
    if target_kind is not None:
        fields["target_kind"] = target_kind
    logger.info("security_audit", **fields)


def _bounded_text(value: str, limit: int) -> str:
    """Bound attacker-influenced audit dimensions without changing short identifiers."""
    return value if len(value) <= limit else value[:limit] + "..."
