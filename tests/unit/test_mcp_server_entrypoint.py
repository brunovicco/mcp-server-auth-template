"""Unit tests for the entrypoint's provider selection.

``build_server()`` itself is covered by an integration test (see
``@pytest.mark.integration``) since it wires a full ``MCPServer``; here we
only test the pure decision this module makes: which ``TokenVerifier``
subclass to build for a given :class:`Settings`.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import httpx
import pytest

from mcp_server_auth_template.adapters.entra_token_verifier import EntraTokenVerifier
from mcp_server_auth_template.adapters.generic_oidc_token_verifier import GenericOidcTokenVerifier
from mcp_server_auth_template.entrypoints.mcp_server import _build_token_verifier
from mcp_server_auth_template.entrypoints.settings import Settings


@pytest.fixture
async def http_client() -> AsyncIterator[httpx.AsyncClient]:
    async with httpx.AsyncClient() as client:
        yield client


async def test_builds_an_entra_verifier_for_entra_settings(http_client: httpx.AsyncClient) -> None:
    settings = Settings(
        auth_provider="entra",
        resource_server_url="https://mcp.example.invalid",
        entra_tenant_id="11111111-1111-1111-1111-111111111111",
        entra_audience="api://00000000-0000-0000-0000-000000000000",
    )

    verifier = _build_token_verifier(settings, http_client=http_client)

    assert isinstance(verifier, EntraTokenVerifier)


async def test_builds_a_generic_verifier_for_generic_settings(
    http_client: httpx.AsyncClient,
) -> None:
    settings = Settings(
        auth_provider="generic",
        resource_server_url="https://mcp.example.invalid",
        generic_issuer_url="https://as.example.invalid",
        generic_audience="https://mcp.example.invalid",
    )

    verifier = _build_token_verifier(settings, http_client=http_client)

    assert isinstance(verifier, GenericOidcTokenVerifier)
