"""Package smoke tests."""


def test_package_is_importable() -> None:
    """Ensure the generated package is importable."""
    import mcp_server_auth_template  # noqa: F401
