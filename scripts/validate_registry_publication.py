#!/usr/bin/env python3
"""Validate persisted Official MCP Registry publication responses."""

import argparse
import json
import sys
from pathlib import Path
from typing import cast

SCHEMA_URL = "https://static.modelcontextprotocol.io/schemas/2025-12-11/server.schema.json"
SERVER_NAME = "io.github.brunovicco/mcp-server-auth-template"
REPOSITORY_URL = "https://github.com/brunovicco/mcp-server-auth-template"
REPOSITORY_ID = "1327263126"
OFFICIAL_META = "io.modelcontextprotocol.registry/official"


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _object(value: object, label: str) -> dict[str, object]:
    _require(isinstance(value, dict), f"{label} must be an object")
    return cast(dict[str, object], value)


def _list(value: object, label: str) -> list[object]:
    _require(isinstance(value, list), f"{label} must be an array")
    return cast(list[object], value)


def _validate_server(server: dict[str, object], version: str) -> None:
    _require(server.get("$schema") == SCHEMA_URL, "unexpected server schema")
    _require(server.get("name") == SERVER_NAME, "unexpected server name")
    _require(server.get("version") == version, "unexpected server version")

    repository = _object(server.get("repository"), "repository")
    _require(repository.get("url") == REPOSITORY_URL, "unexpected repository URL")
    _require(repository.get("source") == "github", "unexpected repository source")
    _require(repository.get("id") == REPOSITORY_ID, "unexpected repository ID")

    packages = _list(server.get("packages"), "packages")
    _require(len(packages) == 1, "exactly one Registry package is required")
    package = _object(packages[0], "packages[0]")

    _require(package.get("registryType") == "oci", "Registry package must remain OCI")
    _require(
        package.get("identifier") == f"ghcr.io/brunovicco/mcp-server-auth-template:v{version}",
        "unexpected OCI identifier",
    )

    transport = _object(package.get("transport"), "packages[0].transport")
    _require(transport.get("type") == "streamable-http", "unexpected transport type")
    _require(
        transport.get("url") == "http://127.0.0.1:8000/mcp",
        "unexpected transport URL",
    )

    for forbidden in ("registryBaseUrl", "version", "fileSha256"):
        _require(forbidden not in package, f"OCI package must not declare {forbidden}")

    _require("remotes" not in server, "hosted remotes must remain absent")


def _validate_meta(meta: object, latest_state: str) -> None:
    response_meta = _object(meta, "_meta")
    official = _object(response_meta.get(OFFICIAL_META), f"_meta.{OFFICIAL_META}")
    _require(official.get("status") == "active", "Registry status must be active")

    is_latest = official.get("isLatest")
    _require(isinstance(is_latest, bool), "Registry isLatest must be boolean")

    if latest_state == "true":
        _require(is_latest is True, "Registry entry must be latest")
    elif latest_state == "false":
        _require(is_latest is False, "Registry entry must not be latest")
    elif latest_state != "any":
        raise ValueError(f"unsupported latest-state: {latest_state}")


def validate_payload(
    *,
    kind: str,
    payload: object,
    version: str,
    latest_state: str = "true",
) -> None:
    """Validate one source or Registry API payload."""
    if kind == "source":
        _validate_server(_object(payload, "server.json"), version)
        return

    response = _object(payload, "Registry response")

    if kind in {"exact", "latest"}:
        server = _object(response.get("server"), "server")
        _validate_server(server, version)
        _validate_meta(response.get("_meta"), latest_state)
        return

    if kind == "discovery":
        entries = _list(response.get("servers"), "servers")
        matches: list[dict[str, object]] = []
        for raw_entry in entries:
            entry = _object(raw_entry, "servers[]")
            server = _object(entry.get("server"), "servers[].server")
            if server.get("name") == SERVER_NAME and server.get("version") == version:
                matches.append(entry)

        _require(len(matches) == 1, "discovery must contain exactly one matching server/version")
        selected = matches[0]
        server = _object(selected.get("server"), "servers[].server")
        _validate_server(server, version)
        _validate_meta(selected.get("_meta"), latest_state)

        metadata = _object(response.get("metadata"), "metadata")
        _require(isinstance(metadata.get("count"), int), "metadata.count must be an integer")
        return

    raise ValueError(f"unsupported validation kind: {kind}")


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--kind",
        required=True,
        choices=("source", "exact", "latest", "discovery"),
    )
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--version", required=True)
    parser.add_argument(
        "--latest-state",
        choices=("true", "false", "any"),
        default="true",
    )
    return parser.parse_args()


def main() -> int:
    """Validate one persisted Registry payload."""
    args = parse_args()
    try:
        with args.input.open(encoding="utf-8") as handle:
            payload = json.load(handle)
        validate_payload(
            kind=args.kind,
            payload=payload,
            version=args.version,
            latest_state=args.latest_state,
        )
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(f"Registry publication validation failed: {exc}", file=sys.stderr)
        return 1

    print(f"Registry publication {args.kind} validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
