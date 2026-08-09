"""Tests for OAuth Client Credentials extension advertisement."""

from mcp_server_auth_template.adapters.oauth_client_credentials_extension import (
    OAUTH_CLIENT_CREDENTIALS_EXTENSION_ID,
    OAuthClientCredentialsExtension,
)


def test_extension_advertises_the_standard_identifier_without_settings() -> None:
    extension = OAuthClientCredentialsExtension()

    assert extension.identifier == OAUTH_CLIENT_CREDENTIALS_EXTENSION_ID
    assert extension.settings() == {}
