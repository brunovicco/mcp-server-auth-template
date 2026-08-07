"""MCP resource-server entrypoint.

Wires the configured authentication adapter into ``mcp.server.mcpserver.MCPServer``.
The SDK owns Protected Resource Metadata (RFC 9728), the 401 + ``WWW-Authenticate``
challenge, and per-request scope enforcement once ``auth`` and ``token_verifier``
are set - this module's job is only to build the right ``TokenVerifier`` for the
configured provider and register example tools. See
``docs/adr/0002-oauth21-resource-server.md`` for why the server never issues
tokens itself.

Run locally with:

    uv run uvicorn mcp_server_auth_template.entrypoints.mcp_server:create_app --factory --reload
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.server.auth.provider import TokenVerifier
from mcp.server.auth.settings import AuthSettings
from mcp.server.mcpserver import MCPServer
from starlette.applications import Starlette

from mcp_server_auth_template.adapters.entra_token_verifier import EntraTokenVerifier
from mcp_server_auth_template.adapters.generic_oidc_token_verifier import GenericOidcTokenVerifier
from mcp_server_auth_template.adapters.jwks_key_resolver import JwksKeyResolver
from mcp_server_auth_template.adapters.oidc_discovery import OidcDiscoveryClient
from mcp_server_auth_template.entrypoints.logging import configure_logging
from mcp_server_auth_template.entrypoints.settings import Settings


def _build_token_verifier(settings: Settings, *, http_client: httpx.AsyncClient) -> TokenVerifier:
    """Return the adapter matching ``settings.auth_provider``.

    Raises:
        RuntimeError: The provider-specific fields are missing. ``Settings``
            already validates this at startup, so reaching this branch means
            ``Settings`` was constructed without going through its own
            validator (e.g. in a test) - fail loudly rather than proceed with
            a verifier that can never issue a matching ``TokenVerifier``.
    """
    discovery = OidcDiscoveryClient(http_client=http_client)
    key_resolver = JwksKeyResolver()

    if settings.auth_provider == "entra":
        if not (settings.entra_tenant_id and settings.entra_audience):
            raise RuntimeError("auth_provider=entra requires entra_tenant_id and entra_audience")
        return EntraTokenVerifier(
            tenant_id=settings.entra_tenant_id,
            audience=settings.entra_audience,
            discovery=discovery,
            key_resolver=key_resolver,
        )

    if not (settings.generic_issuer_url and settings.generic_audience):
        raise RuntimeError("auth_provider=generic requires generic_issuer_url and generic_audience")
    return GenericOidcTokenVerifier(
        issuer_url=settings.generic_issuer_url,
        audience=settings.generic_audience,
        discovery=discovery,
        key_resolver=key_resolver,
    )


def _whoami() -> dict[str, object]:
    """Return the identity carried by the caller's bearer token."""
    access_token = get_access_token()
    if access_token is None:
        return {"authenticated": False}
    return {
        "authenticated": True,
        "client_id": access_token.client_id,
        "subject": access_token.subject,
        "scopes": access_token.scopes,
    }


def _health() -> dict[str, str]:
    """Liveness check for the authenticated caller."""
    return {"status": "ok"}


def _resolve_issuer_url(settings: Settings) -> str:
    """Return the OIDC issuer URL for ``settings.auth_provider``.

    Raises:
        RuntimeError: No issuer URL could be resolved. ``Settings`` already
            validates the generic-provider fields at startup, so reaching
            this branch means ``Settings`` was constructed without going
            through its own validator (e.g. in a test).
    """
    if settings.auth_provider == "entra":
        return f"https://login.microsoftonline.com/{settings.entra_tenant_id}/v2.0"
    if settings.generic_issuer_url is None:
        raise RuntimeError(
            f"could not resolve issuer_url for auth_provider={settings.auth_provider!r}"
        )
    return settings.generic_issuer_url


def build_server() -> MCPServer:
    """Construct the configured ``MCPServer``, ready to serve as an ASGI app."""
    settings = Settings()  # values come from the environment
    configure_logging(service=settings.service_name, environment="local", version="0.1.0")

    http_client = httpx.AsyncClient(timeout=10.0)
    token_verifier = _build_token_verifier(settings, http_client=http_client)
    issuer_url = _resolve_issuer_url(settings)

    @asynccontextmanager
    async def lifespan(_: MCPServer) -> AsyncIterator[None]:
        try:
            yield None
        finally:
            await http_client.aclose()

    server = MCPServer(
        name=settings.service_name,
        token_verifier=token_verifier,
        auth=AuthSettings(
            issuer_url=issuer_url,
            resource_server_url=settings.resource_server_url,
            required_scopes=settings.required_scopes or None,
        ),
        lifespan=lifespan,
    )

    server.tool(
        name="whoami", description="Return the identity carried by the caller's bearer token."
    )(_whoami)
    server.tool(name="health", description="Liveness check for the authenticated caller.")(_health)

    return server


def create_app() -> Starlette:
    """ASGI app factory. Run with ``uvicorn ...:create_app --factory``.

    Deferring construction to a factory (instead of a module-level ``app =
    build_server()...``) keeps importing this module side-effect-free, so it
    can be imported for its ``_build_token_verifier`` helper - or by any
    other tooling - without ``Settings`` needing real environment variables
    at import time.
    """
    return build_server().streamable_http_app()
