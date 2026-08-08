"""Declarative, default-deny authorization policies for MCP tools."""

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum

from mcp_server_auth_template.domain.principal import Principal, PrincipalKind


class ToolPolicyKind(StrEnum):
    """Authorization signals a tool policy may require."""

    AUTHENTICATED = "authenticated"
    DELEGATED_SCOPES = "delegated_scopes"
    APPLICATION_ROLES = "application_roles"
    OAUTH_SCOPES = "oauth_scopes"


class AuthorizationReason(StrEnum):
    """Stable, non-secret reason codes for authorization decisions."""

    ALLOWED = "allowed"
    POLICY_MISSING = "policy_missing"
    UNAUTHENTICATED = "unauthenticated"
    WRONG_PRINCIPAL_KIND = "wrong_principal_kind"
    MISSING_PERMISSION = "missing_permission"


@dataclass(frozen=True, slots=True)
class ToolPolicy:
    """One explicit policy for one MCP tool."""

    kind: ToolPolicyKind
    permissions: frozenset[str] = frozenset()

    def __post_init__(self) -> None:
        """Reject malformed policy combinations at construction time."""
        if self.kind is ToolPolicyKind.AUTHENTICATED and self.permissions:
            raise ValueError("authenticated tool policies cannot declare permissions")
        if self.kind is not ToolPolicyKind.AUTHENTICATED and not self.permissions:
            raise ValueError(f"{self.kind.value} tool policies require at least one permission")

    @classmethod
    def authenticated(cls) -> "ToolPolicy":
        """Require only a successfully authenticated principal."""
        return cls(kind=ToolPolicyKind.AUTHENTICATED)

    @classmethod
    def delegated_scopes(cls, *scopes: str) -> "ToolPolicy":
        """Require all delegated OAuth scopes and a delegated principal."""
        return cls(kind=ToolPolicyKind.DELEGATED_SCOPES, permissions=_scope_permissions(scopes))

    @classmethod
    def application_roles(cls, *roles: str) -> "ToolPolicy":
        """Require all application roles and an application principal."""
        return cls(kind=ToolPolicyKind.APPLICATION_ROLES, permissions=_permissions(roles))

    @classmethod
    def oauth_scopes(cls, *scopes: str) -> "ToolPolicy":
        """Require OAuth scopes without asserting delegated-vs-app identity mode.

        This is the generic OAuth/OIDC escape hatch. Prefer ``delegated_scopes``
        for Entra user-delegated authorization, where the token shape is known.
        """
        return cls(kind=ToolPolicyKind.OAUTH_SCOPES, permissions=_scope_permissions(scopes))


@dataclass(frozen=True, slots=True)
class AuthorizationDecision:
    """Result of evaluating one tool policy."""

    allowed: bool
    reason: AuthorizationReason
    required_scopes: tuple[str, ...] = ()


class ToolAuthorizationService:
    """Evaluate explicit per-tool policies with a fail-closed default."""

    def __init__(self, policies: Mapping[str, ToolPolicy]) -> None:
        """Copy the policy registry so authorization is stable after startup."""
        self._policies = dict(policies)

    def authorize(self, tool_name: str, principal: Principal | None) -> AuthorizationDecision:
        """Return whether ``principal`` may invoke ``tool_name``."""
        policy = self._policies.get(tool_name)
        if policy is None:
            return AuthorizationDecision(False, AuthorizationReason.POLICY_MISSING)
        if principal is None:
            return AuthorizationDecision(
                False,
                AuthorizationReason.UNAUTHENTICATED,
                self._required_scopes(policy),
            )
        if policy.kind is ToolPolicyKind.AUTHENTICATED:
            return AuthorizationDecision(True, AuthorizationReason.ALLOWED)
        if policy.kind is ToolPolicyKind.DELEGATED_SCOPES:
            if principal.kind is not PrincipalKind.DELEGATED:
                return AuthorizationDecision(
                    False,
                    AuthorizationReason.WRONG_PRINCIPAL_KIND,
                    self._required_scopes(policy),
                )
            return self._permission_decision(policy, principal.scopes)
        if policy.kind is ToolPolicyKind.APPLICATION_ROLES:
            if principal.kind is not PrincipalKind.APPLICATION:
                return AuthorizationDecision(False, AuthorizationReason.WRONG_PRINCIPAL_KIND)
            return self._permission_decision(policy, principal.roles)
        return self._permission_decision(policy, principal.scopes)

    def is_visible(self, tool_name: str, principal: Principal | None) -> bool:
        """Return whether a tool should be exposed through ``tools/list``."""
        return self.authorize(tool_name, principal).allowed

    def required_scopes_for(self, tool_name: str) -> tuple[str, ...]:
        """Return OAuth scopes a transport-layer step-up challenge should advertise."""
        policy = self._policies.get(tool_name)
        return self._required_scopes(policy) if policy is not None else ()

    @staticmethod
    def _required_scopes(policy: ToolPolicy) -> tuple[str, ...]:
        if policy.kind not in {ToolPolicyKind.DELEGATED_SCOPES, ToolPolicyKind.OAUTH_SCOPES}:
            return ()
        return tuple(sorted(policy.permissions))

    def _permission_decision(
        self,
        policy: ToolPolicy,
        granted: frozenset[str],
    ) -> AuthorizationDecision:
        required_scopes = self._required_scopes(policy)
        if policy.permissions.issubset(granted):
            return AuthorizationDecision(True, AuthorizationReason.ALLOWED, required_scopes)
        return AuthorizationDecision(False, AuthorizationReason.MISSING_PERMISSION, required_scopes)


def _permissions(values: tuple[str, ...]) -> frozenset[str]:
    permissions = frozenset(value for value in values if value)
    if not permissions:
        raise ValueError("tool policy permissions must contain at least one non-empty value")
    return permissions


def _scope_permissions(values: tuple[str, ...]) -> frozenset[str]:
    permissions = _permissions(values)
    for scope in permissions:
        if not _is_valid_oauth_scope_token(scope):
            raise ValueError(f"invalid OAuth scope token: {scope!r}")
    return permissions


def _is_valid_oauth_scope_token(value: str) -> bool:
    # RFC 6749 scope-token = 1*( %x21 / %x23-5B / %x5D-7E ).
    # Spaces delimit scope tokens and quotes/backslashes are excluded, making
    # the validated values safe to serialize into WWW-Authenticate.
    return all(
        code == 0x21 or 0x23 <= code <= 0x5B or 0x5D <= code <= 0x7E for code in map(ord, value)
    )
