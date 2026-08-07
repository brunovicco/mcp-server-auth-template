"""Microsoft Entra ID resource-server token verifier.

Entra ID cannot act as a full MCP authorization server for arbitrary
clients: it supports neither Dynamic Client Registration nor Client ID
Metadata Documents, only pre-registration of known clients (see
``docs/adr/0002-oauth21-resource-server.md``). This adapter is the resource
server half of that pattern - it only verifies tokens Entra already issued.

It reuses :class:`GenericOidcTokenVerifier` for signature/issuer/audience/
expiry checks against Entra's own tenant-scoped OIDC discovery document, then
adds one check that is specific to Entra and easy to miss: binding the
token's ``tid`` (tenant ID) claim to the tenant this server was configured
for. Skipping it lets a token from a *different* tenant that happens to share
the same multi-tenant app registration pass every other check.
"""

import structlog
from mcp.server.auth.provider import AccessToken

from mcp_server_auth_template.adapters.generic_oidc_token_verifier import GenericOidcTokenVerifier
from mcp_server_auth_template.application.auth_ports import DiscoveryPort, KeyResolverPort

logger = structlog.get_logger(__name__)

_ENTRA_ISSUER_TEMPLATE = "https://login.microsoftonline.com/{tenant_id}/v2.0"


class EntraTokenVerifier:
    """Verifies bearer tokens issued by a specific Microsoft Entra ID tenant."""

    def __init__(
        self,
        *,
        tenant_id: str,
        audience: str,
        discovery: DiscoveryPort,
        key_resolver: KeyResolverPort,
    ) -> None:
        """Build a verifier scoped to one Entra tenant and one resource audience."""
        self._tenant_id = tenant_id
        self._delegate = GenericOidcTokenVerifier(
            issuer_url=_ENTRA_ISSUER_TEMPLATE.format(tenant_id=tenant_id),
            audience=audience,
            discovery=discovery,
            key_resolver=key_resolver,
        )

    async def verify_token(self, token: str) -> AccessToken | None:
        """Delegate signature/issuer/audience/expiry checks, then bind the tenant."""
        access_token = await self._delegate.verify_token(token)
        if access_token is None:
            return None

        token_tenant = (access_token.claims or {}).get("tid")
        if token_tenant != self._tenant_id:
            logger.info("bearer_token_rejected", reason="tenant_mismatch")
            return None

        return access_token
