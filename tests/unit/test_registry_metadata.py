"""Tests for Official MCP Registry project invariants."""

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from scripts.validate_registry_metadata import ValidationError, validate

ServerMutation = Callable[[dict[str, Any]], None]


@pytest.fixture
def registry_root(tmp_path: Path) -> Path:
    source = Path(__file__).resolve().parents[2]
    for name in ("server.json", "Dockerfile", "pyproject.toml"):
        (tmp_path / name).write_text(
            (source / name).read_text(encoding="utf-8"),
            encoding="utf-8",
        )
    for relative in (
        "scripts/install_mcp_publisher.sh",
        ".github/workflows/quality.yml",
        ".github/workflows/release-artifacts.yml",
    ):
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text((source / relative).read_text(encoding="utf-8"), encoding="utf-8")
    return tmp_path


def _mutate_server(root: Path, mutate: ServerMutation) -> None:
    path = root / "server.json"
    server = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(server, dict)
    mutate(server)
    path.write_text(json.dumps(server, indent=2) + "\n", encoding="utf-8")


def _set_root_value(key: str, value: object) -> ServerMutation:
    def mutate(server: dict[str, Any]) -> None:
        server[key] = value

    return mutate


def _set_package_value(key: str, value: object) -> ServerMutation:
    def mutate(server: dict[str, Any]) -> None:
        server["packages"][0][key] = value

    return mutate


def _set_transport_type(value: str) -> ServerMutation:
    def mutate(server: dict[str, Any]) -> None:
        server["packages"][0]["transport"]["type"] = value

    return mutate


def _set_transport_url(value: str) -> ServerMutation:
    def mutate(server: dict[str, Any]) -> None:
        server["packages"][0]["transport"]["url"] = value

    return mutate


def _set_repository_id(value: str) -> ServerMutation:
    def mutate(server: dict[str, Any]) -> None:
        server["repository"]["id"] = value

    return mutate


def test_registry_metadata_accepts_repository_contract(registry_root: Path) -> None:
    validate(registry_root, release_tag="v0.6.2")


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (_set_root_value("name", "io.github.other/server"), "name"),
        (_set_root_value("$schema", "https://example.invalid/schema"), "schema"),
        (_set_root_value("remotes", []), "hosted remote"),
        (
            _set_package_value(
                "identifier",
                "ghcr.io/brunovicco/mcp-server-auth-template:latest",
            ),
            "OCI identifier",
        ),
        (_set_transport_type("stdio"), "streamable-http"),
        (_set_transport_url("http://127.0.0.1:8000/sse"), "transport URL"),
        (
            _set_package_value("version", "0.6.2"),
            "must not declare version",
        ),
        (
            _set_package_value(
                "registryBaseUrl",
                "https://ghcr.io",
            ),
            "must not declare registryBaseUrl",
        ),
        (
            _set_package_value(
                "fileSha256",
                "0" * 64,
            ),
            "must not declare fileSha256",
        ),
        (_set_repository_id("999"), "repository.id"),
    ],
)
def test_registry_metadata_rejects_drift(
    registry_root: Path,
    mutate: ServerMutation,
    message: str,
) -> None:
    _mutate_server(registry_root, mutate)
    with pytest.raises(ValidationError, match=message):
        validate(registry_root)


def test_registry_metadata_rejects_version_mismatch(registry_root: Path) -> None:
    _mutate_server(registry_root, _set_root_value("version", "0.6.3"))
    with pytest.raises(ValidationError, match="version"):
        validate(registry_root)


def test_registry_metadata_rejects_release_tag_mismatch(registry_root: Path) -> None:
    with pytest.raises(ValidationError, match="release tag"):
        validate(registry_root, release_tag="v0.6.3")


def test_registry_metadata_rejects_missing_docker_label(registry_root: Path) -> None:
    dockerfile = registry_root / "Dockerfile"
    original = dockerfile.read_text(encoding="utf-8")
    label = (
        "      io.modelcontextprotocol.server.name="
        '"io.github.brunovicco/mcp-server-auth-template"\n'
    )
    dockerfile.write_text(original.replace(label, ""), encoding="utf-8")
    with pytest.raises(ValidationError, match="ownership label"):
        validate(registry_root)


def test_registry_metadata_rejects_runtime_hardening_drift(registry_root: Path) -> None:
    def mutate(server: dict[str, Any]) -> None:
        server["packages"][0]["runtimeArguments"] = [
            item
            for item in server["packages"][0]["runtimeArguments"]
            if item["name"] != "--cap-drop"
        ]

    _mutate_server(registry_root, mutate)
    with pytest.raises(ValidationError, match="runtime hardening"):
        validate(registry_root)


def test_registry_metadata_rejects_required_environment_drift(registry_root: Path) -> None:
    def mutate(server: dict[str, Any]) -> None:
        for item in server["packages"][0]["environmentVariables"]:
            if item["name"] == "MCP_SERVER_AUTH_PROVIDER":
                item["isRequired"] = False

    _mutate_server(registry_root, mutate)
    with pytest.raises(ValidationError, match="AUTH_PROVIDER"):
        validate(registry_root)


def test_registry_metadata_rejects_wrong_docker_label(registry_root: Path) -> None:
    dockerfile = registry_root / "Dockerfile"
    original = dockerfile.read_text(encoding="utf-8")
    dockerfile.write_text(
        original.replace(
            'io.modelcontextprotocol.server.name="io.github.brunovicco/mcp-server-auth-template"',
            'io.modelcontextprotocol.server.name="io.github.other/server"',
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValidationError, match="ownership label"):
        validate(registry_root)


def test_registry_metadata_rejects_publisher_pin_drift(registry_root: Path) -> None:
    installer = registry_root / "scripts/install_mcp_publisher.sh"
    installer.write_text(
        installer.read_text(encoding="utf-8").replace('VERSION="1.8.1"', 'VERSION="latest"'),
        encoding="utf-8",
    )
    with pytest.raises(ValidationError, match="version pin"):
        validate(registry_root)


def test_registry_metadata_requires_official_publisher_validation(registry_root: Path) -> None:
    workflow = registry_root / ".github/workflows/quality.yml"
    workflow.write_text(
        workflow.read_text(encoding="utf-8").replace(
            "mcp-publisher validate server.json",
            "echo registry-validation-disabled",
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValidationError, match="official Registry"):
        validate(registry_root)


def test_registry_metadata_requires_release_candidate_label_gate(registry_root: Path) -> None:
    workflow = registry_root / ".github/workflows/release-artifacts.yml"
    workflow.write_text(
        workflow.read_text(encoding="utf-8").replace(
            "Validate Registry ownership on both release candidates",
            "Registry ownership check removed",
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValidationError, match="candidate image labels"):
        validate(registry_root)


def _fake_docker(tmp_path: Path, label: str) -> Path:
    docker = tmp_path / "docker"
    docker.write_text(
        "#!/bin/sh\n"
        'if [ "$1" = image ] && [ "$2" = inspect ]; then\n'
        f"  printf '%s\\n' '{label}'\n"
        "  exit 0\n"
        "fi\n"
        "exit 2\n",
        encoding="utf-8",
    )
    docker.chmod(0o755)
    return docker


def test_registry_metadata_accepts_image_ownership_label(
    registry_root: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _fake_docker(tmp_path, "io.github.brunovicco/mcp-server-auth-template")
    monkeypatch.setenv("PATH", str(tmp_path))
    validate(registry_root, image="mcp-server-auth-template:test")


def test_registry_metadata_rejects_image_ownership_label_mismatch(
    registry_root: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _fake_docker(tmp_path, "io.github.other/server")
    monkeypatch.setenv("PATH", str(tmp_path))
    with pytest.raises(ValidationError, match="wrong MCP ownership label"):
        validate(registry_root, image="mcp-server-auth-template:test")
