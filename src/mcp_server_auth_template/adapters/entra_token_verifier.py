"""Microsoft Entra ID resource-server token verifier.

Entra ID cannot act as a full MCP authorization server for arbitrary
clients: it supports neither Dynamic Client Registration nor Client ID
Metadata Documents, only pre-registration of known clients (see
``docs/adr/0002-oauth21-resource-server.md``). This adapter is the resource
server half of that pattern - it only verifies tokens Entra already issued.

It reuses :class:`GenericOidcTokenVerifier` for signature/issuer/audience/
expiry checks against Entra's own tenant-scoped OIDC discovery document, then
adds two Entra-specific normalizations: tenant binding through ``tid`` and
qualification of short delegated ``scp`` values with the API's Application ID
URI so they match the scope strings advertised to MCP clients. ``roles`` stays
separate in the validated raw claims and never enters the SDK scope gate.
"""

import structlog
from mcp.server.auth.provider import AccessToken

from mcp_server_auth_template.adapters.generic_oidc_token_verifier import GenericOidcTokenVerifier
from mcp_server_auth_template.application.auth_ports import DiscoveryPort, KeyResolverPort
from mcp_server_auth_template.domain.scope_claims import qualify_scopes

logger = structlog.get_logger(__name__)

_ENTRA_ISSUER_TEMPLATE = "https://login.microsoftonline.com/{tenant_id}/v2.0"


class EntraTokenVerifier:
    """Verifies bearer tokens issued by a specific Microsoft Entra ID tenant."""

    def __init__(
        self,
        *,
        tenant_id: str,
        audience: str,
        application_id_uri: str,
        discovery: DiscoveryPort,
        key_resolver: KeyResolverPort,
    ) -> None:
        """Build a verifier scoped to one Entra tenant and one resource audience."""
        self._tenant_id = tenant_id
        self._application_id_uri = application_id_uri
        self._delegate = GenericOidcTokenVerifier(
            issuer_url=_ENTRA_ISSUER_TEMPLATE.format(tenant_id=tenant_id),
            audience=audience,
            discovery=discovery,
            key_resolver=key_resolver,
        )

    async def verify_token(self, token: str) -> AccessToken | None:
        """Validate the token, tenant-bind it, then normalize Entra permissions."""
        access_token = await self._delegate.verify_token(token)
        if access_token is None:
            return None

        token_tenant = (access_token.claims or {}).get("tid")
        if token_tenant != self._tenant_id:
            logger.info("bearer_token_rejected", reason="tenant_mismatch")
            return None

        return access_token.model_copy(
            update={
                "scopes": qualify_scopes(
                    access_token.scopes,
                    self._application_id_uri,
                )
            }
        )
