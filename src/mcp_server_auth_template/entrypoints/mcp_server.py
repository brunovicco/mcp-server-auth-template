"""MCP resource-server entrypoint.

Wires the configured authentication adapter into ``mcp.server.mcpserver.MCPServer``.
The SDK owns Protected Resource Metadata (RFC 9728), bearer authentication,
and the global scope baseline once ``auth`` and ``token_verifier`` are set. The
template layers request-scoped per-tool authorization and progressive scope
challenges on top without replacing the SDK transport. See
``docs/adr/0002-oauth21-resource-server.md`` for why the server never issues
tokens itself.

Run locally with:

    uv run uvicorn mcp_server_auth_template.entrypoints.mcp_server:create_app --factory --reload
"""

from collections.abc import AsyncIterator, Mapping
from contextlib import asynccontextmanager
from urllib.parse import urlsplit

import httpx
from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.server.auth.provider import TokenVerifier
from mcp.server.auth.routes import build_resource_metadata_url
from mcp.server.auth.settings import AuthSettings
from mcp.server.mcpserver import MCPServer
from mcp.server.transport_security import TransportSecuritySettings
from starlette.applications import Starlette

from mcp_server_auth_template.adapters.entra_token_verifier import EntraTokenVerifier
from mcp_server_auth_template.adapters.generic_oidc_token_verifier import GenericOidcTokenVerifier
from mcp_server_auth_template.adapters.http_transport_security import (
    HttpTransportAdmissionMiddleware,
)
from mcp_server_auth_template.adapters.jwks_key_resolver import JwksKeyResolver
from mcp_server_auth_template.adapters.mcp_tool_authorization import ToolAuthorizationMiddleware
from mcp_server_auth_template.adapters.oidc_discovery import OidcDiscoveryClient
from mcp_server_auth_template.adapters.oidc_http_security import (
    OidcNetworkSecurityPolicy,
    PinnedOidcAsyncTransport,
)
from mcp_server_auth_template.adapters.progressive_auth_http import (
    ProgressiveAuthorizationMiddleware,
)
from mcp_server_auth_template.adapters.progressive_token_verifier import (
    ProgressiveAuthorizationTokenVerifier,
)
from mcp_server_auth_template.application.tool_authorization import (
    ToolAuthorizationService,
    ToolPolicy,
    ToolPolicyKind,
)
from mcp_server_auth_template.domain.scope_claims import qualify_scopes
from mcp_server_auth_template.entrypoints.logging import configure_logging
from mcp_server_auth_template.entrypoints.settings import Settings

_TOOL_POLICIES = {
    "whoami": ToolPolicy.authenticated(),
    "health": ToolPolicy.authenticated(),
}
_MCP_HTTP_PATH = "/mcp"


def _deduplicate(values: list[str]) -> list[str]:
    return list(dict.fromkeys(values))


def _transport_authority(settings: Settings) -> tuple[list[str], list[str]]:
    """Return exact Host and same-origin values derived from the public resource URL."""
    parsed = urlsplit(str(settings.resource_server_url))
    host = parsed.hostname
    if host is None:
        raise RuntimeError("resource_server_url has no host")

    wire_host = f"[{host}]" if ":" in host else host
    default_port = 443 if parsed.scheme == "https" else 80
    port = parsed.port

    if port is None:
        hosts = [wire_host, f"{wire_host}:{default_port}"]
        origins = [f"{parsed.scheme}://{wire_host}"]
    elif port == default_port:
        hosts = [wire_host, f"{wire_host}:{port}"]
        origins = [f"{parsed.scheme}://{wire_host}", f"{parsed.scheme}://{wire_host}:{port}"]
    else:
        authority = f"{wire_host}:{port}"
        hosts = [authority]
        origins = [f"{parsed.scheme}://{authority}"]
    return hosts, origins


def _build_transport_security(settings: Settings) -> TransportSecuritySettings:
    """Build exact DNS-rebinding allowlists for the public MCP resource."""
    default_hosts, default_origins = _transport_authority(settings)
    return TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=_deduplicate(default_hosts + settings.transport_allowed_hosts),
        allowed_origins=_deduplicate(default_origins + settings.transport_allowed_origins),
    )


def _build_tool_authorizer(
    settings: Settings,
    policies: Mapping[str, ToolPolicy] | None = None,
) -> ToolAuthorizationService:
    """Build the effective policy registry for the configured resource server.

    Entra exposes custom delegated API permissions to OAuth clients as
    ``{application_id_uri}/{scope}``, and P1.1a normalizes token ``scp`` values
    into that same form.  Qualifying short policy scopes here keeps matching
    and progressive ``WWW-Authenticate`` challenges on one canonical value.
    """
    policy_registry = _TOOL_POLICIES if policies is None else policies
    if settings.auth_provider != "entra" or settings.entra_application_id_uri is None:
        return ToolAuthorizationService(policy_registry)

    effective: dict[str, ToolPolicy] = {}
    for tool_name, policy in policy_registry.items():
        if policy.kind not in {ToolPolicyKind.DELEGATED_SCOPES, ToolPolicyKind.OAUTH_SCOPES}:
            effective[tool_name] = policy
            continue
        scopes = qualify_scopes(sorted(policy.permissions), settings.entra_application_id_uri)
        if policy.kind is ToolPolicyKind.DELEGATED_SCOPES:
            effective[tool_name] = ToolPolicy.delegated_scopes(*scopes)
        else:
            effective[tool_name] = ToolPolicy.oauth_scopes(*scopes)
    return ToolAuthorizationService(effective)


def _build_oidc_network_policy(
    settings: Settings,
    issuer_url: str,
) -> OidcNetworkSecurityPolicy:
    """Build the process-wide discovery/JWKS trust boundary for one issuer."""
    allowed_origins = (
        settings.generic_jwks_allowed_origins if settings.auth_provider == "generic" else []
    )
    return OidcNetworkSecurityPolicy(
        issuer_url=issuer_url,
        allow_insecure_loopback=settings.oidc_allow_insecure_loopback,
        jwks_allowed_origins=allowed_origins,
    )


def _build_oidc_http_client(policy: OidcNetworkSecurityPolicy) -> httpx.AsyncClient:
    """Build a direct, no-proxy HTTP client whose transport DNS-pins every OIDC request."""

    def transport_factory() -> httpx.AsyncBaseTransport:
        return httpx.AsyncHTTPTransport(retries=0, trust_env=False)

    transport = PinnedOidcAsyncTransport(
        policy=policy,
        transport_factory=transport_factory,
    )
    return httpx.AsyncClient(
        transport=transport,
        follow_redirects=False,
        timeout=policy.http_timeout_seconds,
        trust_env=False,
    )


def _build_token_verifier(
    settings: Settings,
    *,
    http_client: httpx.AsyncClient,
    network_policy: OidcNetworkSecurityPolicy | None = None,
) -> TokenVerifier:
    """Return the adapter matching ``settings.auth_provider``.

    Raises:
        RuntimeError: The provider-specific fields are missing. ``Settings``
            already validates this at startup, so reaching this branch means
            ``Settings`` was constructed without going through its own
            validator (e.g. in a test) - fail loudly rather than proceed with
            a verifier that can never issue a matching ``TokenVerifier``.
    """
    if settings.auth_provider == "entra":
        if not (
            settings.entra_tenant_id
            and settings.entra_audience
            and settings.entra_application_id_uri
        ):
            raise RuntimeError(
                "auth_provider=entra requires entra_tenant_id, entra_audience, "
                "and entra_application_id_uri"
            )
        issuer_url = _resolve_issuer_url(settings)
        policy = network_policy or _build_oidc_network_policy(settings, issuer_url)
        discovery = OidcDiscoveryClient(http_client=http_client, policy=policy)
        key_resolver = JwksKeyResolver(http_client=http_client, policy=policy)
        return EntraTokenVerifier(
            tenant_id=settings.entra_tenant_id,
            audience=settings.entra_audience,
            application_id_uri=settings.entra_application_id_uri,
            discovery=discovery,
            key_resolver=key_resolver,
        )

    if not (settings.generic_issuer_url and settings.generic_audience):
        raise RuntimeError("auth_provider=generic requires generic_issuer_url and generic_audience")
    policy = network_policy or _build_oidc_network_policy(settings, settings.generic_issuer_url)
    discovery = OidcDiscoveryClient(http_client=http_client, policy=policy)
    key_resolver = JwksKeyResolver(http_client=http_client, policy=policy)
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


def build_server(settings: Settings | None = None) -> MCPServer:
    """Construct the configured ``MCPServer``, ready to serve as an ASGI app."""
    settings = settings or Settings()  # values come from the environment
    configure_logging(service=settings.service_name, environment="local", version="0.1.0")

    issuer_url = _resolve_issuer_url(settings)
    network_policy = _build_oidc_network_policy(settings, issuer_url)
    http_client = _build_oidc_http_client(network_policy)
    base_token_verifier = _build_token_verifier(
        settings,
        http_client=http_client,
        network_policy=network_policy,
    )
    tool_authorizer = _build_tool_authorizer(settings)
    token_verifier = ProgressiveAuthorizationTokenVerifier(
        delegate=base_token_verifier,
        authorizer=tool_authorizer,
        auth_provider=settings.auth_provider,
        global_required_scopes=tuple(settings.effective_required_scopes),
    )

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
            required_scopes=settings.effective_required_scopes or None,
        ),
        lifespan=lifespan,
        middleware=[
            ToolAuthorizationMiddleware(
                authorizer=tool_authorizer,
                auth_provider=settings.auth_provider,
            )
        ],
    )

    server.tool(
        name="whoami", description="Return the identity carried by the caller's bearer token."
    )(_whoami)
    server.tool(name="health", description="Liveness check for the authenticated caller.")(_health)

    return server


def _build_streamable_http_app(server: MCPServer, settings: Settings) -> Starlette:
    """Build the bounded, stateless Streamable HTTP ASGI surface."""
    transport_security = _build_transport_security(settings)
    app = server.streamable_http_app(
        streamable_http_path=_MCP_HTTP_PATH,
        json_response=True,
        stateless_http=True,
        max_request_body_size=settings.transport_max_request_body_bytes,
        transport_security=transport_security,
    )
    resource_metadata_url = build_resource_metadata_url(settings.resource_server_url)
    app.add_middleware(
        ProgressiveAuthorizationMiddleware,
        resource_metadata_url=str(resource_metadata_url),
    )
    # Starlette inserts newly-added middleware at the outside of the stack.
    # Add admission last so Host/Origin/envelope checks run before auth.
    app.add_middleware(
        HttpTransportAdmissionMiddleware,
        transport_security=transport_security,
        mcp_path=_MCP_HTTP_PATH,
        max_header_count=settings.transport_max_header_count,
        max_header_bytes=settings.transport_max_header_bytes,
        max_concurrent_requests=settings.transport_max_concurrent_requests,
    )
    return app


def create_app() -> Starlette:
    """ASGI app factory. Run with ``uvicorn ...:create_app --factory``.

    Deferring construction to a factory (instead of a module-level ``app =
    build_server()...``) keeps importing this module side-effect-free, so it
    can be imported for its ``_build_token_verifier`` helper - or by any
    other tooling - without ``Settings`` needing real environment variables
    at import time.
    """
    settings = Settings()
    return _build_streamable_http_app(build_server(settings), settings)
