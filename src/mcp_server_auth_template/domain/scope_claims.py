"""Normalizes OAuth scope claims across authorization-server conventions.

A plain OAuth 2.1 authorization server puts delegated scopes in a
space-delimited ``scope`` string (RFC 6749 §3.3). Microsoft Entra ID splits
that idea in two: ``scp`` for scopes delegated by a signed-in user, and
``roles`` for application permissions granted to a service principal with no
user present. A token can carry either, both, or neither claim.
"""

from __future__ import annotations

from typing import Any


def scopes_from_claims(claims: dict[str, Any]) -> list[str]:
    """Return the effective scope list for ``claims``, deduplicated and sorted.

    Recognizes, in order: ``scope`` (space-delimited, RFC 6749), ``scp``
    (space-delimited, Entra delegated permissions), and ``roles`` (a list,
    Entra application permissions).
    """
    scopes: set[str] = set()

    scope_claim = claims.get("scope")
    if isinstance(scope_claim, str):
        scopes.update(scope_claim.split())

    scp_claim = claims.get("scp")
    if isinstance(scp_claim, str):
        scopes.update(scp_claim.split())

    roles_claim = claims.get("roles")
    if isinstance(roles_claim, list):
        scopes.update(role for role in roles_claim if isinstance(role, str))

    return sorted(scopes)
