from types import SimpleNamespace

from mcp.server.auth.middleware.bearer_auth import AuthenticatedUser
from mcp.server.auth.provider import AccessToken

from mcp_server_auth_template.adapters.mcp_principal import (
    principal_from_access_token,
    principal_from_request,
)
from mcp_server_auth_template.domain.principal import PrincipalKind


def _token(*, scopes: list[str], claims: dict[str, object]) -> AccessToken:
    return AccessToken(
        token="opaque-token-value",
        client_id="client-123",
        scopes=scopes,
        subject="subject-456",
        claims=claims,
    )


def test_entra_scp_is_classified_as_delegated_even_when_user_roles_exist() -> None:
    token = _token(
        scopes=["api://resource/customer.read"],
        claims={
            "iss": "https://login.microsoftonline.com/tenant/v2.0",
            "scp": "customer.read",
            "roles": ["Report.Reader"],
        },
    )

    principal = principal_from_access_token(token, "entra")

    assert principal.kind is PrincipalKind.DELEGATED
    assert principal.scopes == frozenset({"api://resource/customer.read"})
    assert principal.roles == frozenset({"Report.Reader"})


def test_entra_application_identity_requires_explicit_app_token_type() -> None:
    principal = principal_from_access_token(
        _token(scopes=[], claims={"roles": ["Payment.Execute"], "idtyp": "app"}),
        "entra",
    )

    assert principal.kind is PrincipalKind.APPLICATION
    assert principal.roles == frozenset({"Payment.Execute"})


def test_entra_roles_without_idtyp_do_not_prove_application_identity() -> None:
    principal = principal_from_access_token(
        _token(scopes=[], claims={"roles": ["Payment.Execute"]}),
        "entra",
    )

    assert principal.kind is PrincipalKind.UNKNOWN


def test_entra_contradictory_app_and_scp_shape_fails_closed() -> None:
    principal = principal_from_access_token(
        _token(scopes=["customer.read"], claims={"scp": "customer.read", "idtyp": "app"}),
        "entra",
    )

    assert principal.kind is PrincipalKind.UNKNOWN


def test_generic_oidc_does_not_infer_identity_mode_or_roles() -> None:
    principal = principal_from_access_token(
        _token(scopes=["customer.read"], claims={"roles": ["Payment.Execute"]}),
        "generic",
    )

    assert principal.kind is PrincipalKind.UNKNOWN
    assert principal.scopes == frozenset({"customer.read"})
    assert principal.roles == frozenset()


def test_principal_comes_from_the_current_authenticated_request() -> None:
    token = _token(scopes=["customer.read"], claims={"scp": "customer.read"})
    request = SimpleNamespace(user=AuthenticatedUser(token))

    principal = principal_from_request(request, "entra")

    assert principal is not None
    assert principal.client_id == "client-123"


def test_missing_request_identity_returns_none() -> None:
    assert principal_from_request(None, "entra") is None
    assert principal_from_request(SimpleNamespace(user=object()), "entra") is None
