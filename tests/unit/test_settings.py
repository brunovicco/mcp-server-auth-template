"""Unit tests for :class:`Settings`."""

from __future__ import annotations

import pytest

from mcp_server_auth_template.entrypoints.settings import Settings


def test_entra_mode_accepts_matching_fields() -> None:
    settings = Settings(
        auth_provider="entra",
        resource_server_url="https://mcp.example.invalid",
        entra_tenant_id="11111111-1111-1111-1111-111111111111",
        entra_audience="api://00000000-0000-0000-0000-000000000000",
    )

    assert settings.auth_provider == "entra"


def test_entra_mode_rejects_missing_fields() -> None:
    with pytest.raises(ValueError, match="entra_tenant_id"):
        Settings(auth_provider="entra", resource_server_url="https://mcp.example.invalid")


def test_generic_mode_accepts_matching_fields() -> None:
    settings = Settings(
        auth_provider="generic",
        resource_server_url="https://mcp.example.invalid",
        generic_issuer_url="https://as.example.invalid",
        generic_audience="https://mcp.example.invalid",
    )

    assert settings.auth_provider == "generic"


def test_generic_mode_rejects_missing_fields() -> None:
    with pytest.raises(ValueError, match="generic_issuer_url"):
        Settings(auth_provider="generic", resource_server_url="https://mcp.example.invalid")
