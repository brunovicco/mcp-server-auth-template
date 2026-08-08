"""Adapt the MCP SDK's request-scoped identity into the domain Principal model."""

from typing import Literal

from mcp.server.auth.middleware.bearer_auth import AuthenticatedUser
from mcp.server.auth.provider import AccessToken

from mcp_server_auth_template.domain.principal import Principal, PrincipalKind
from mcp_server_auth_template.domain.scope_claims import roles_from_claims

AuthProvider = Literal["entra", "generic"]


def principal_from_request(request: object | None, auth_provider: AuthProvider) -> Principal | None:
    """Build a principal from the authenticated user attached to this HTTP request.

    Authorization deliberately reads the current request instead of the SDK's
    access-token context variable, so a decision cannot inherit identity from a
    different request or legacy session.
    """
    access_token = _access_token_from_request(request)
    if access_token is None:
        return None
    return principal_from_access_token(access_token, auth_provider)


def principal_from_access_token(
    access_token: AccessToken, auth_provider: AuthProvider
) -> Principal:
    """Normalize one already-validated MCP access token into authorization facts."""
    claims = access_token.claims or {}
    issuer_value = claims.get("iss")
    issuer = str(issuer_value) if issuer_value is not None else None

    if auth_provider == "entra":
        kind = _entra_principal_kind(claims)
        roles = frozenset(roles_from_claims(claims))
    else:
        kind = PrincipalKind.UNKNOWN
        roles = frozenset()

    return Principal(
        client_id=access_token.client_id,
        subject=access_token.subject,
        issuer=issuer,
        kind=kind,
        scopes=frozenset(access_token.scopes),
        roles=roles,
    )


def _entra_principal_kind(claims: dict[str, object]) -> PrincipalKind:
    """Classify Entra tokens without trusting ``roles`` as proof of app identity."""
    scp = claims.get("scp")
    has_delegated_scopes = isinstance(scp, str) and bool(scp.split())
    idtyp = claims.get("idtyp")

    if has_delegated_scopes:
        # Contradictory token shapes fail closed instead of satisfying either
        # delegated or application-only policies.
        return PrincipalKind.UNKNOWN if idtyp == "app" else PrincipalKind.DELEGATED
    if idtyp == "app":
        return PrincipalKind.APPLICATION
    return PrincipalKind.UNKNOWN


def _access_token_from_request(request: object | None) -> AccessToken | None:
    if request is None:
        return None
    try:
        user = getattr(request, "user", None)
    except AssertionError:
        # Starlette raises when AuthenticationMiddleware did not populate the request.
        return None
    if not isinstance(user, AuthenticatedUser):
        return None
    return user.access_token
