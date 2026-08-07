"""Generic OAuth 2.1 / OIDC resource-server token verifier.

Implements :class:`mcp.server.auth.provider.TokenVerifier` against any
authorization server that publishes standard OIDC discovery and JWKS
endpoints (Auth0, Keycloak, WorkOS AuthKit, and similar). For Microsoft Entra
ID specifically, use
:class:`mcp_server_auth_template.adapters.entra_token_verifier.EntraTokenVerifier`
instead — Entra's claim shape (``scp``/``roles`` instead of ``scope``) and
tenant-scoped discovery URL need their own adapter.

Per the MCP 2026-07-28 authorization specification, this resource server
never talks to the authorization server's token endpoint; it only verifies
tokens that a client already obtained and validates that they were minted
for *this* resource (RFC 8707 audience binding).
"""

import jwt
import structlog
from mcp.server.auth.provider import AccessToken

from mcp_server_auth_template.application.auth_ports import DiscoveryPort, KeyResolverPort
from mcp_server_auth_template.domain.auth_errors import TokenVerificationError
from mcp_server_auth_template.domain.scope_claims import scopes_from_claims

logger = structlog.get_logger(__name__)

_ACCEPTED_ALGORITHMS = ["RS256", "ES256"]
_CLOCK_SKEW_LEEWAY_SECONDS = 60


class GenericOidcTokenVerifier:
    """Verifies bearer tokens issued by a standards-compliant OIDC authorization server."""

    def __init__(
        self,
        *,
        issuer_url: str,
        audience: str,
        discovery: DiscoveryPort,
        key_resolver: KeyResolverPort,
    ) -> None:
        """Build a verifier scoped to one issuer and one resource audience."""
        self._issuer_url = issuer_url
        self._audience = audience
        self._discovery = discovery
        self._key_resolver = key_resolver

    async def verify_token(self, token: str) -> AccessToken | None:
        """Validate signature, issuer, audience, and expiry; never raises.

        Returns ``None`` on any failure, per the ``TokenVerifier`` contract -
        callers must not be able to distinguish "expired" from "malformed"
        from "wrong audience" through this return value alone. Rejection
        reasons are logged by class, never with the token or its claims.
        """
        try:
            metadata = await self._discovery.resolve(self._issuer_url)
            signing_key = await self._key_resolver.resolve(jwks_uri=metadata.jwks_uri, token=token)
            claims = jwt.decode(
                token,
                signing_key.key,
                algorithms=_ACCEPTED_ALGORITHMS,
                audience=self._audience,
                issuer=metadata.issuer,
                leeway=_CLOCK_SKEW_LEEWAY_SECONDS,
                options={"require": ["exp", "iat", "iss", "aud", "sub"]},
            )
        except TokenVerificationError:
            logger.info("bearer_token_rejected", reason="discovery_or_key_resolution_failed")
            return None
        except jwt.exceptions.InvalidTokenError as exc:
            logger.info("bearer_token_rejected", reason=type(exc).__name__)
            return None

        return AccessToken(
            token=token,
            client_id=str(claims.get("azp") or claims.get("client_id") or claims["sub"]),
            scopes=scopes_from_claims(claims),
            expires_at=int(claims["exp"]),
            resource=self._audience,
            subject=str(claims["sub"]),
            claims=claims,
        )
