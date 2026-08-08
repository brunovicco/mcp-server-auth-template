"""Unit tests for scope/role claim extraction and scope qualification."""

from mcp_server_auth_template.domain.scope_claims import (
    qualify_scopes,
    roles_from_claims,
    scopes_from_claims,
)


def test_reads_a_plain_oauth_scope_string() -> None:
    assert scopes_from_claims({"scope": "mcp:tools:call mcp:tools:list"}) == [
        "mcp:tools:call",
        "mcp:tools:list",
    ]


def test_reads_entra_delegated_scp_claim() -> None:
    assert scopes_from_claims({"scp": "Data.Read Data.Write"}) == ["Data.Read", "Data.Write"]


def test_application_roles_do_not_become_oauth_scopes() -> None:
    assert scopes_from_claims({"roles": ["Data.Read", "Data.Write"]}) == []


def test_reads_roles_through_the_explicit_role_extractor() -> None:
    assert roles_from_claims({"roles": ["Data.Write", "Data.Read", "Data.Read", 123, ""]}) == [
        "Data.Read",
        "Data.Write",
    ]


def test_merges_only_scope_and_scp_claims() -> None:
    claims = {"scope": "shared", "scp": "shared delegated", "roles": ["shared", "app-only"]}

    assert scopes_from_claims(claims) == ["delegated", "shared"]
    assert roles_from_claims(claims) == ["app-only", "shared"]


def test_returns_empty_lists_when_permission_claims_are_absent() -> None:
    claims = {"sub": "user-123"}

    assert scopes_from_claims(claims) == []
    assert roles_from_claims(claims) == []


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
