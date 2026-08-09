"""Capability advertisement for the MCP OAuth Client Credentials extension."""

from mcp.server.extension import Extension

OAUTH_CLIENT_CREDENTIALS_EXTENSION_ID = "io.modelcontextprotocol/oauth-client-credentials"


class OAuthClientCredentialsExtension(Extension):
    """Advertise that the resource server accepts client-credentials bearer tokens."""

    identifier = OAUTH_CLIENT_CREDENTIALS_EXTENSION_ID
