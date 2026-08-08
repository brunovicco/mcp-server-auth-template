"""Decorate an MCP TokenVerifier with per-tool OAuth scope step-up support."""

from mcp.server.auth.provider import AccessToken, TokenVerifier

from mcp_server_auth_template.adapters.mcp_principal import (
    AuthProvider,
    principal_from_access_token,
)
from mcp_server_auth_template.adapters.progressive_auth_http import (
    current_progressive_authorization_context,
)
from mcp_server_auth_template.adapters.security_audit import (
    SecurityAuditAction,
    SecurityAuditOutcome,
    emit_security_audit,
)
from mcp_server_auth_template.application.tool_authorization import (
    AuthorizationReason,
    ToolAuthorizationService,
)


class ProgressiveAuthorizationTokenVerifier:
    """Request a standards-compliant scope upgrade without re-verifying a token.

    The delegate remains the single cryptographic/token-validation authority.
    The wrapper only evaluates an already-validated ``AccessToken`` against the
    routing metadata carried by MCP 2026-07-28 HTTP headers.
    """

    def __init__(
        self,
        *,
        delegate: TokenVerifier,
        authorizer: ToolAuthorizationService,
        auth_provider: AuthProvider,
        global_required_scopes: tuple[str, ...] = (),
    ) -> None:
        """Bind one verifier and one immutable tool-policy registry."""
        self._delegate = delegate
        self._authorizer = authorizer
        self._auth_provider = auth_provider
        self._global_required_scopes = tuple(sorted(set(global_required_scopes)))

    async def verify_token(self, token: str) -> AccessToken | None:
        """Verify once, then signal an OAuth scope challenge when appropriate."""
        access_token = await self._delegate.verify_token(token)
        if access_token is None:
            emit_security_audit(
                SecurityAuditAction.AUTHENTICATION_REJECTED,
                SecurityAuditOutcome.DENIED,
                reason="token_verification_failed",
            )
            return None

        context = current_progressive_authorization_context()
        if context is None or not context.is_mcp_request:
            return access_token

        challenge_scopes: set[str] = set()
        if not set(self._global_required_scopes).issubset(access_token.scopes):
            challenge_scopes.update(self._global_required_scopes)

        if context.target is not None:
            decision = self._authorizer.authorize(
                context.target.name,
                principal_from_access_token(access_token, self._auth_provider),
            )
            if (
                not decision.allowed
                and decision.reason is AuthorizationReason.MISSING_PERMISSION
                and decision.required_scopes
            ):
                challenge_scopes.update(decision.required_scopes)

        if challenge_scopes:
            context.required_scopes = tuple(sorted(challenge_scopes))
            # Returning None lets the SDK stop before MCP dispatch.  The outer
            # ASGI middleware replaces the SDK's resulting 401 with the 403
            # insufficient_scope response required for progressive auth.
            return None

        return access_token
