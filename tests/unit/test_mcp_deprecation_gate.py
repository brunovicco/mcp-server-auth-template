"""MCP SDK deprecations fail the suite so MCP 3 breakage surfaces on MCP 2.x."""

import warnings

import pytest
from mcp import MCPDeprecationWarning
from mcp.server.auth.settings import AuthSettings


def test_pytest_promotes_mcp_deprecations_to_errors() -> None:
    """``filterwarnings`` in ``pyproject.toml`` turns SDK deprecations into failures."""
    with pytest.raises(MCPDeprecationWarning):
        warnings.warn("deprecated MCP API", MCPDeprecationWarning, stacklevel=1)


def test_implicit_token_resource_validation_is_rejected() -> None:
    """Leaving ``validate_token_resource`` to the SDK default cannot pass CI."""
    with pytest.raises(MCPDeprecationWarning, match="validate_token_resource"):
        AuthSettings(
            issuer_url="https://issuer.example.test",
            resource_server_url="https://mcp.example.test/mcp",
        )


def test_only_mcp_deprecations_are_promoted(pytestconfig: pytest.Config) -> None:
    """Only the SDK's own warning class is escalated; other deprecations need evaluation first."""
    assert pytestconfig.getini("filterwarnings") == ["error::mcp.MCPDeprecationWarning"]
