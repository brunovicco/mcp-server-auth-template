"""Ports the token verifiers depend on.

Defined here, at the application layer, so
:class:`~mcp_server_auth_template.adapters.generic_oidc_token_verifier.GenericOidcTokenVerifier`
and
:class:`~mcp_server_auth_template.adapters.entra_token_verifier.EntraTokenVerifier`
depend on an interface rather than on the concrete ``httpx``/``PyJWKClient``-backed
adapters directly. Tests inject fakes that satisfy these protocols instead of
performing real network I/O.
"""

from __future__ import annotations

from typing import Protocol

from jwt import PyJWK

from mcp_server_auth_template.domain.oidc_metadata import OidcMetadata


class DiscoveryPort(Protocol):
    """Resolves OIDC discovery metadata for an issuer."""

    async def resolve(self, issuer_base_url: str) -> OidcMetadata:
        """Return the discovery metadata for ``issuer_base_url``."""
        ...


class KeyResolverPort(Protocol):
    """Resolves the signing key matching a JWT's ``kid`` header."""

    async def resolve(self, *, jwks_uri: str, token: str) -> PyJWK:
        """Return the signing key that matches ``token``'s ``kid`` header."""
        ...
