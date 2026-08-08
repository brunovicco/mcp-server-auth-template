"""Normalize OAuth scopes without conflating them with role claims.

OAuth ``scope`` and Microsoft Entra ``scp`` values represent OAuth scopes.
Microsoft Entra ``roles`` is a distinct authorization signal: on app-only
tokens it carries application permissions, while delegated tokens can also
contain roles assigned to the signed-in user. Promoting ``roles`` into the
SDK's ``AccessToken.scopes`` therefore erases a security boundary and can let
an application role satisfy a policy that was intended to require a delegated
scope.
"""

from typing import Any


def scopes_from_claims(claims: dict[str, Any]) -> list[str]:
    """Return only OAuth scope values, deduplicated and sorted.

    ``scope`` is the standard space-delimited OAuth representation and ``scp``
    is Microsoft Entra's delegated-scope claim. ``roles`` is deliberately not
    consumed here; callers that authorize roles must do so explicitly instead
    of relying on the MCP SDK's scope gate.
    """
    scopes: set[str] = set()

    scope_claim = claims.get("scope")
    if isinstance(scope_claim, str):
        scopes.update(scope_claim.split())

    scp_claim = claims.get("scp")
    if isinstance(scp_claim, str):
        scopes.update(scp_claim.split())

    return sorted(scopes)


def roles_from_claims(claims: dict[str, Any]) -> list[str]:
    """Return role claim values without promoting them to OAuth scopes."""
    roles_claim = claims.get("roles")
    if not isinstance(roles_claim, list):
        return []
    return sorted({role for role in roles_claim if isinstance(role, str) and role})


def qualify_scopes(scopes: list[str], resource_uri: str) -> list[str]:
    """Qualify short scope names with an OAuth resource/application ID URI.

    Microsoft Entra clients request custom delegated API scopes as
    ``{application_id_uri}/{scope_name}``, while the access token's ``scp``
    claim normally contains only the short permission value. Values that are
    already URI-qualified are kept unchanged so a permission for a different
    resource cannot accidentally be rewritten into an allowed one.
    """
    prefix = f"{resource_uri.rstrip('/')}/"
    qualified = {scope if "://" in scope else f"{prefix}{scope}" for scope in scopes if scope}
    return sorted(qualified)
