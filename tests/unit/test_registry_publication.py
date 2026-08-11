"""Tests for Official MCP Registry publication response validation."""

import pytest
from scripts.validate_registry_publication import OFFICIAL_META, validate_payload


def _server(version: str = "0.6.2") -> dict[str, object]:
    return {
        "$schema": ("https://static.modelcontextprotocol.io/schemas/2025-12-11/server.schema.json"),
        "name": "io.github.brunovicco/mcp-server-auth-template",
        "version": version,
        "repository": {
            "url": "https://github.com/brunovicco/mcp-server-auth-template",
            "source": "github",
            "id": "1327263126",
        },
        "packages": [
            {
                "registryType": "oci",
                "identifier": (f"ghcr.io/brunovicco/mcp-server-auth-template:v{version}"),
                "transport": {
                    "type": "streamable-http",
                    "url": "http://127.0.0.1:8000/mcp",
                },
            }
        ],
    }


def _entry(
    version: str = "0.6.2",
    *,
    status: str = "active",
    is_latest: bool = True,
) -> dict[str, object]:
    return {
        "server": _server(version),
        "_meta": {
            OFFICIAL_META: {
                "status": status,
                "isLatest": is_latest,
            }
        },
    }


def test_source_payload_is_valid() -> None:
    validate_payload(kind="source", payload=_server(), version="0.6.2")


def test_exact_active_latest_payload_is_valid() -> None:
    validate_payload(kind="exact", payload=_entry(), version="0.6.2")


def test_existing_older_exact_payload_can_be_verified_idempotently() -> None:
    validate_payload(
        kind="exact",
        payload=_entry(is_latest=False),
        version="0.6.2",
        latest_state="any",
    )


def test_oci_package_version_is_rejected() -> None:
    server = _server()
    packages = server["packages"]
    assert isinstance(packages, list)
    package = packages[0]
    assert isinstance(package, dict)
    package["version"] = "0.6.2"

    with pytest.raises(ValueError, match="must not declare version"):
        validate_payload(kind="source", payload=server, version="0.6.2")


def test_wrong_oci_identifier_is_rejected() -> None:
    server = _server()
    packages = server["packages"]
    assert isinstance(packages, list)
    package = packages[0]
    assert isinstance(package, dict)
    package["identifier"] = "ghcr.io/brunovicco/mcp-server-auth-template:v9.9.9"

    with pytest.raises(ValueError, match="unexpected OCI identifier"):
        validate_payload(kind="source", payload=server, version="0.6.2")


def test_inactive_registry_entry_is_rejected() -> None:
    with pytest.raises(ValueError, match="status must be active"):
        validate_payload(
            kind="exact",
            payload=_entry(status="deprecated"),
            version="0.6.2",
        )


def test_latest_endpoint_must_resolve_requested_version() -> None:
    with pytest.raises(ValueError, match="unexpected server version"):
        validate_payload(
            kind="latest",
            payload=_entry("0.6.3"),
            version="0.6.2",
        )


def test_discovery_requires_exact_server_version() -> None:
    payload = {"servers": [_entry("0.6.3")], "metadata": {"count": 1}}

    with pytest.raises(ValueError, match="exactly one matching"):
        validate_payload(kind="discovery", payload=payload, version="0.6.2")


def test_discovery_payload_is_valid() -> None:
    payload = {"servers": [_entry()], "metadata": {"count": 1}}

    validate_payload(kind="discovery", payload=payload, version="0.6.2")
