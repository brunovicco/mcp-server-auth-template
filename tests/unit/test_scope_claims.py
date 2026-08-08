"""Unit tests for scope claim extraction and qualification."""

from mcp_server_auth_template.domain.scope_claims import qualify_scopes, scopes_from_claims


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


def test_qualifies_short_permissions_with_the_resource_uri() -> None:
    assert qualify_scopes(
        ["mcp:tools:call", "mcp:tools:list"],
        "api://22222222-2222-2222-2222-222222222222",
    ) == [
        "api://22222222-2222-2222-2222-222222222222/mcp:tools:call",
        "api://22222222-2222-2222-2222-222222222222/mcp:tools:list",
    ]


def test_keeps_already_qualified_permissions_unchanged() -> None:
    scope = "api://other-resource/mcp:tools:call"

    assert qualify_scopes(
        [scope],
        "api://22222222-2222-2222-2222-222222222222",
    ) == [scope]


def test_resource_uri_trailing_slash_does_not_create_double_slash() -> None:
    assert qualify_scopes(["Data.Read"], "api://resource/") == ["api://resource/Data.Read"]
