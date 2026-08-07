"""Unit tests for :func:`scopes_from_claims`."""

from __future__ import annotations

from mcp_server_auth_template.domain.scope_claims import scopes_from_claims


def test_reads_a_plain_oauth_scope_string() -> None:
    assert scopes_from_claims({"scope": "mcp:tools:call mcp:tools:list"}) == [
        "mcp:tools:call",
        "mcp:tools:list",
    ]


def test_reads_entra_delegated_scp_claim() -> None:
    assert scopes_from_claims({"scp": "Data.Read Data.Write"}) == ["Data.Read", "Data.Write"]


def test_reads_entra_application_roles_claim() -> None:
    assert scopes_from_claims({"roles": ["Data.Read", "Data.Write"]}) == ["Data.Read", "Data.Write"]


def test_merges_and_deduplicates_across_all_three_claims() -> None:
    claims = {"scope": "shared", "scp": "shared delegated", "roles": ["shared", "app-only"]}

    assert scopes_from_claims(claims) == ["app-only", "delegated", "shared"]


def test_returns_an_empty_list_when_no_scope_claim_is_present() -> None:
    assert scopes_from_claims({"sub": "user-123"}) == []
