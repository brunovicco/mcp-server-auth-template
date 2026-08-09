"""Fail-fast, secret-safe startup preflight for production deployments."""

import argparse
import json
import sys

from pydantic import ValidationError

from mcp_server_auth_template.entrypoints.settings import Settings


def validate_preflight_settings(settings: Settings) -> Settings:
    """Revalidate a settings object so startup cannot bypass model invariants."""
    return Settings.model_validate(settings.model_dump(mode="python"))


def build_preflight_report(settings: Settings) -> dict[str, object]:
    """Return an allowlisted operational summary that contains no credentials or identifiers."""
    validated = validate_preflight_settings(settings)
    return {
        "status": "ok",
        "environment": validated.app_env,
        "auth_provider": validated.auth_provider,
        "runtime": {
            "port": validated.runtime_port,
            "workers": validated.runtime_workers,
            "graceful_shutdown_seconds": validated.runtime_graceful_shutdown_seconds,
        },
        "limits": {
            "max_request_body_bytes": validated.transport_max_request_body_bytes,
            "max_header_count": validated.transport_max_header_count,
            "max_header_bytes": validated.transport_max_header_bytes,
            "max_concurrent_requests": validated.transport_max_concurrent_requests,
        },
    }


def _safe_validation_issues(exc: ValidationError) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []
    for error in exc.errors(include_url=False, include_context=False, include_input=False):
        location = ".".join(str(part) for part in error["loc"]) or "settings"
        issues.append({"location": location, "type": str(error["type"])})
    return issues


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate MCP server configuration without network access or secret output."
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="emit the allowlisted preflight result as JSON",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the startup preflight and return a process exit code."""
    args = _parser().parse_args(argv)
    try:
        settings = validate_preflight_settings(Settings())
    except ValidationError as exc:
        issues = _safe_validation_issues(exc)
        failure: dict[str, object] = {
            "status": "error",
            "error": "configuration_invalid",
            "issues": issues,
        }
        if args.json:
            print(json.dumps(failure, sort_keys=True))
        else:
            print(
                f"preflight: configuration invalid ({len(issues)} issue(s))",
                file=sys.stderr,
            )
        return 2

    report = build_preflight_report(settings)
    if args.json:
        print(json.dumps(report, sort_keys=True))
    else:
        print(
            "preflight: ok "
            f"(environment={settings.app_env}, "
            f"auth_provider={settings.auth_provider}, "
            f"workers={settings.runtime_workers})"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
