import pytest

from mcp_server_auth_template.application.tool_authorization import (
    AuthorizationReason,
    ToolAuthorizationService,
    ToolPolicy,
)
from mcp_server_auth_template.domain.principal import Principal, PrincipalKind


def _principal(
    *,
    kind: PrincipalKind,
    scopes: set[str] | None = None,
    roles: set[str] | None = None,
) -> Principal:
    return Principal(
        client_id="client-123",
        subject="subject-456",
        issuer="https://issuer.example.invalid",
        kind=kind,
        scopes=frozenset(scopes or set()),
        roles=frozenset(roles or set()),
    )


def test_missing_policy_is_default_deny() -> None:
    service = ToolAuthorizationService({})

    decision = service.authorize(
        "new-tool",
        _principal(kind=PrincipalKind.DELEGATED, scopes={"customer.read"}),
    )

    assert not decision.allowed
    assert decision.reason is AuthorizationReason.POLICY_MISSING


def test_authenticated_policy_accepts_any_authenticated_principal() -> None:
    service = ToolAuthorizationService({"health": ToolPolicy.authenticated()})

    assert service.authorize("health", _principal(kind=PrincipalKind.UNKNOWN)).allowed
    assert not service.authorize("health", None).allowed


def test_delegated_policy_requires_delegated_kind_and_all_scopes() -> None:
    service = ToolAuthorizationService(
        {"customer": ToolPolicy.delegated_scopes("customer.read", "customer.profile")}
    )

    allowed = service.authorize(
        "customer",
        _principal(
            kind=PrincipalKind.DELEGATED,
            scopes={"customer.read", "customer.profile"},
        ),
    )
    missing = service.authorize(
        "customer",
        _principal(kind=PrincipalKind.DELEGATED, scopes={"customer.read"}),
    )
    wrong_kind = service.authorize(
        "customer",
        _principal(
            kind=PrincipalKind.APPLICATION,
            scopes={"customer.read", "customer.profile"},
        ),
    )

    assert allowed.allowed
    assert missing.reason is AuthorizationReason.MISSING_PERMISSION
    assert wrong_kind.reason is AuthorizationReason.WRONG_PRINCIPAL_KIND
    assert service.required_scopes_for("customer") == ("customer.profile", "customer.read")


def test_application_role_never_authorizes_a_delegated_principal() -> None:
    service = ToolAuthorizationService({"payment": ToolPolicy.application_roles("Payment.Execute")})

    delegated = _principal(
        kind=PrincipalKind.DELEGATED,
        roles={"Payment.Execute"},
    )
    application = _principal(
        kind=PrincipalKind.APPLICATION,
        roles={"Payment.Execute"},
    )

    delegated_decision = service.authorize("payment", delegated)
    assert delegated_decision.reason is AuthorizationReason.WRONG_PRINCIPAL_KIND
    assert service.authorize("payment", application).allowed


def test_delegated_scope_never_satisfies_application_role_policy() -> None:
    service = ToolAuthorizationService({"payment": ToolPolicy.application_roles("Payment.Execute")})
    principal = _principal(
        kind=PrincipalKind.DELEGATED,
        scopes={"Payment.Execute"},
    )

    assert not service.authorize("payment", principal).allowed


def test_generic_oauth_scope_policy_uses_scope_namespace_without_kind_inference() -> None:
    service = ToolAuthorizationService({"report": ToolPolicy.oauth_scopes("report.read")})
    principal = _principal(kind=PrincipalKind.UNKNOWN, scopes={"report.read"})

    assert service.authorize("report", principal).allowed
    assert service.required_scopes_for("report") == ("report.read",)


def test_policy_constructors_reject_empty_permission_sets() -> None:
    with pytest.raises(ValueError, match="at least one"):
        ToolPolicy.delegated_scopes("")
    with pytest.raises(ValueError, match="at least one"):
        ToolPolicy.application_roles()


def test_oauth_scope_policy_rejects_values_unsafe_for_www_authenticate() -> None:
    with pytest.raises(ValueError, match="invalid OAuth scope token"):
        ToolPolicy.delegated_scopes("customer.read customer.write")
    with pytest.raises(ValueError, match="invalid OAuth scope token"):
        ToolPolicy.oauth_scopes('report"read')
    with pytest.raises(ValueError, match="invalid OAuth scope token"):
        ToolPolicy.oauth_scopes("report\\read")
    with pytest.raises(ValueError, match="invalid OAuth scope token"):
        ToolPolicy.oauth_scopes("relatório.read")
