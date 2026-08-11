#!/usr/bin/env python3
"""Validate project-owned invariants for Official MCP Registry metadata."""

import argparse
import json
import re
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path
from typing import Any

SERVER_NAME = "io.github.brunovicco/mcp-server-auth-template"
SCHEMA_URL = "https://static.modelcontextprotocol.io/schemas/2025-12-11/server.schema.json"
REPOSITORY_URL = "https://github.com/brunovicco/mcp-server-auth-template"
REPOSITORY_ID = "1327263126"
IMAGE_PREFIX = "ghcr.io/brunovicco/mcp-server-auth-template:v"
TRANSPORT_URL = "http://127.0.0.1:8000/mcp"
MCP_LABEL = "io.modelcontextprotocol.server.name"
MCP_PUBLISHER_VERSION = "1.8.1"
MCP_PUBLISHER_CHECKSUMS = {
    "darwin_amd64": "88126981225e7714fcc6b7a10cdba4a80ae5901e9740a8c06d0d5195c8bc294c",
    "darwin_arm64": "e45e520892460732a4bdf37255576415d4a53ec171f8b913faf15bb1aef7cb77",
    "linux_amd64": "a06c9096dcb9727c13555b6be26c7effa707b01f06a4c561ba7a3635443cf2cc",
    "linux_arm64": "8dd75a6cf6845688b5d4e46df58d3ca26d5c8d233bb0626606e1db82c5e883e4",
}
SEMVER_RE = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+(?:[-+][0-9A-Za-z.-]+)?$")


class ValidationError(ValueError):
    """Raised when Registry metadata violates a project invariant."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValidationError(message)


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValidationError(f"could not load {path}: {exc}") from exc

    if not isinstance(value, dict):
        raise ValidationError(f"{path} must contain a JSON object")

    return value


def _project_version(path: Path) -> str:
    try:
        with path.open("rb") as handle:
            project = tomllib.load(handle)
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise ValidationError(f"could not load {path}: {exc}") from exc

    value = project.get("project")

    if not isinstance(value, dict):
        raise ValidationError("pyproject.toml must contain [project]")

    version = value.get("version")

    if not isinstance(version, str) or not version:
        raise ValidationError("project.version must be a string")

    return version


def _validate_repository(server: dict[str, Any]) -> None:
    repository = server.get("repository")

    if not isinstance(repository, dict):
        raise ValidationError("repository metadata is required")

    _require(
        repository.get("url") == REPOSITORY_URL,
        "repository.url must match the public repo",
    )
    _require(
        repository.get("source") == "github",
        "repository.source must be github",
    )
    _require(
        repository.get("id") == REPOSITORY_ID,
        "repository.id must match the stable GitHub repo ID",
    )


def _validate_runtime_arguments(
    package: dict[str, Any],
) -> None:
    args = package.get("runtimeArguments")

    if not isinstance(args, list):
        raise ValidationError("OCI package runtimeArguments are required")

    expected_values: dict[str, str | None] = {
        "--read-only": None,
        "--tmpfs": (
            "/tmp:rw,noexec,nosuid,nodev,size=16m"  # noqa: S108
        ),
        "--cap-drop": "ALL",
        "--security-opt": "no-new-privileges:true",
        "--publish": "127.0.0.1:8000:8000",
    }

    by_name: dict[str, dict[str, Any]] = {}

    for item in args:
        if not isinstance(item, dict):
            raise ValidationError("runtimeArguments entries must be objects")

        name = item.get("name")

        if not isinstance(name, str):
            raise ValidationError("runtimeArguments entries must have string names")

        by_name[name] = item

    _require(
        set(by_name) == set(expected_values),
        "runtime hardening arguments drifted",
    )

    for name, expected in expected_values.items():
        _require(
            by_name[name].get("type") == "named",
            f"{name} must be a named argument",
        )

        if expected is None:
            _require(
                "value" not in by_name[name],
                f"{name} must remain a valueless flag",
            )
        else:
            _require(
                by_name[name].get("value") == expected,
                f"{name} value drifted",
            )


def _validate_environment(package: dict[str, Any]) -> None:
    values = package.get("environmentVariables")

    if not isinstance(values, list):
        raise ValidationError("OCI package environmentVariables are required")

    by_name: dict[str, dict[str, Any]] = {}

    for item in values:
        if not isinstance(item, dict):
            raise ValidationError("environmentVariables entries must be objects")

        name = item.get("name")

        if not isinstance(name, str):
            raise ValidationError("environmentVariables entries must have string names")

        _require(
            name not in by_name,
            f"duplicate environment variable metadata: {name}",
        )

        by_name[name] = item

    for name in (
        "MCP_SERVER_RESOURCE_SERVER_URL",
        "MCP_SERVER_AUTH_PROVIDER",
    ):
        _require(
            by_name.get(name, {}).get("isRequired") is True,
            f"{name} must remain required",
        )

    _require(
        by_name.get("MCP_SERVER_AUTH_PROVIDER", {}).get("choices") == ["entra", "generic"],
        ("MCP_SERVER_AUTH_PROVIDER choices must remain entra/generic"),
    )

    _require(
        by_name.get("MCP_SERVER_REQUIRED_SCOPES", {}).get("default") == '["mcp:tools:call"]',
        "baseline scope metadata drifted",
    )

    _require(
        by_name.get("MCP_SERVER_TRANSPORT_ALLOWED_HOSTS", {}).get("default")
        == '["127.0.0.1:8000"]',
        "local transport Host allowlist drifted",
    )

    conditional = {
        "MCP_SERVER_ENTRA_TENANT_ID": "entra",
        "MCP_SERVER_ENTRA_AUDIENCE": "entra",
        "MCP_SERVER_ENTRA_APPLICATION_ID_URI": "entra",
        "MCP_SERVER_GENERIC_ISSUER_URL": "generic",
        "MCP_SERVER_GENERIC_AUDIENCE": "generic",
    }

    for name, provider in conditional.items():
        item = by_name.get(name)

        if not isinstance(item, dict):
            raise ValidationError(f"missing conditional provider metadata: {name}")

        description = item.get("description")

        _require(
            isinstance(description, str) and f"AUTH_PROVIDER={provider}" in description,
            f"{name} must document its provider condition",
        )

        _require(
            item.get("isRequired") is not True,
            f"{name} must not be globally required",
        )


def _validate_package(
    server: dict[str, Any],
    version: str,
) -> None:
    packages = server.get("packages")

    if not isinstance(packages, list) or len(packages) != 1:
        raise ValidationError("exactly one OCI package is expected")

    package = packages[0]

    if not isinstance(package, dict):
        raise ValidationError("packages[0] must be an object")

    _require(
        package.get("registryType") == "oci",
        "package registryType must be oci",
    )
    _require(
        package.get("runtimeHint") == "docker",
        "OCI package runtimeHint must be docker",
    )
    for forbidden in (
        "registryBaseUrl",
        "version",
        "fileSha256",
    ):
        _require(
            forbidden not in package,
            f"OCI package must not declare {forbidden}",
        )

    identifier = package.get("identifier")
    expected_identifier = f"{IMAGE_PREFIX}{version}"

    _require(
        identifier == expected_identifier,
        "OCI identifier must use the immutable release tag",
    )
    _require(
        "latest" not in expected_identifier.lower(),
        "latest is forbidden",
    )

    transport = package.get("transport")

    if not isinstance(transport, dict):
        raise ValidationError("package transport is required")

    _require(
        transport.get("type") == "streamable-http",
        "transport must be streamable-http",
    )
    _require(
        transport.get("url") == TRANSPORT_URL,
        "transport URL must remain loopback /mcp",
    )

    _validate_runtime_arguments(package)
    _validate_environment(package)


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ValidationError(f"could not load {path}: {exc}") from exc


def _validate_publisher_installer(root: Path) -> None:
    installer = _read_text(root / "scripts/install_mcp_publisher.sh")
    _require(
        f'VERSION="{MCP_PUBLISHER_VERSION}"' in installer,
        "mcp-publisher installer version pin drifted",
    )
    _require(
        "modelcontextprotocol/registry/releases/download/v${VERSION}" in installer,
        "mcp-publisher installer must download from the official Registry release",
    )
    for platform, checksum in MCP_PUBLISHER_CHECKSUMS.items():
        _require(
            f'{platform}) expected="{checksum}"' in installer,
            f"mcp-publisher checksum pin drifted for {platform}",
        )


def _validate_registry_workflows(root: Path) -> None:
    quality = _read_text(root / ".github/workflows/quality.yml")
    _require(
        "bash scripts/install_mcp_publisher.sh" in quality,
        "quality workflow must install checksum-verified mcp-publisher",
    )
    _require(
        "mcp-publisher validate server.json" in quality,
        "quality workflow must run official Registry schema/semantic validation",
    )
    _require(
        "--image mcp-server-auth-template:ci" in quality,
        "container smoke must verify the Registry ownership label",
    )

    release = _read_text(root / ".github/workflows/release-artifacts.yml")
    _require(
        'validate_registry_metadata.py --release-tag "$GITHUB_REF_NAME"' in release,
        "release workflow must bind Registry metadata to the Git tag",
    )
    _require(
        "Validate Registry ownership on both release candidates" in release,
        "release workflow must inspect both candidate image labels",
    )
    ownership = release.find("Validate Registry ownership on both release candidates")
    policy = release.find("enforce_vulnerability_policy.py")
    login = release.find("docker login")
    push = release.find("docker push")
    _require(
        min(ownership, policy, login, push) >= 0 and ownership < policy < login < push,
        "release ordering must remain ownership -> policy -> GHCR login -> push",
    )


def _validate_dockerfile(path: Path) -> None:
    try:
        dockerfile = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ValidationError(f"could not load {path}: {exc}") from exc
    pattern = re.compile(rf"{re.escape(MCP_LABEL)}\s*=\s*[\"']{re.escape(SERVER_NAME)}[\"']")
    _require(
        pattern.search(dockerfile) is not None,
        "Dockerfile MCP ownership label is missing or wrong",
    )


def _validate_image_label(image: str) -> None:
    docker = shutil.which("docker")

    if docker is None:
        raise ValidationError("docker executable is required for image-label validation")

    command = (
        docker,
        "image",
        "inspect",
        "--format",
        f'{{{{ index .Config.Labels "{MCP_LABEL}" }}}}',
        image,
    )

    result = subprocess.run(  # noqa: S603
        command,
        check=False,
        capture_output=True,
        text=True,
    )

    _require(
        result.returncode == 0,
        (f"could not inspect image {image}: {result.stderr.strip()}"),
    )

    _require(
        result.stdout.strip() == SERVER_NAME,
        f"image {image} has wrong MCP ownership label",
    )


def validate(root: Path, *, release_tag: str | None = None, image: str | None = None) -> None:
    """Validate Registry metadata and optional release/image bindings."""
    server = _load_json(root / "server.json")
    version = _project_version(root / "pyproject.toml")

    _require(
        server.get("$schema") == SCHEMA_URL,
        "server.json must pin the current Registry schema",
    )
    _require(server.get("name") == SERVER_NAME, "server.json name must match the GitHub namespace")
    description = server.get("description")
    _require(
        isinstance(description, str) and 1 <= len(description) <= 100,
        "description must be 1..100 chars",
    )
    _require(server.get("version") == version, "server.json version must match project.version")
    _require(SEMVER_RE.fullmatch(version) is not None, "project version must be semantic")
    _require("remotes" not in server, "do not claim a hosted remote endpoint before one exists")
    _validate_repository(server)
    _validate_package(server, version)
    _validate_dockerfile(root / "Dockerfile")
    _validate_publisher_installer(root)
    _validate_registry_workflows(root)

    if release_tag is not None:
        _require(release_tag == f"v{version}", "release tag must equal v{server.version}")
    if image is not None:
        _validate_image_label(image)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--release-tag")
    parser.add_argument("--image")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    try:
        validate(args.root.resolve(), release_tag=args.release_tag, image=args.image)
    except ValidationError as exc:
        print(f"Registry metadata validation failed: {exc}", file=sys.stderr)
        return 1
    print("Registry metadata validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
