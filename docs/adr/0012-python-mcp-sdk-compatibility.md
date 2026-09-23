# ADR-0012: Python and MCP SDK compatibility as an executable contract

- Status: Accepted
- Date: 2026-08-09

## Context

The package declares Python `>=3.13,<3.15` and MCP SDK `>=2.0,<3`. A normal lockfile-based
quality gate proves only the exact versions currently recorded in `uv.lock`; it does not prove
that the lower bound still works or that a newly published MCP 2.x release remains compatible.
Documentation alone would also allow the advertised support policy to drift away from CI.

## Decision

Compatibility is verified by a dedicated four-cell CI matrix:

- Python 3.13 + MCP minimum;
- Python 3.13 + MCP latest compatible 2.x;
- Python 3.14 + MCP minimum;
- Python 3.14 + MCP latest compatible 2.x.

The minimum profile installs exactly MCP SDK 2.0.0. The latest profile resolves within
`mcp>=2.0,<3` at job execution time. The compatibility job starts from the locked project
environment, mutates only the disposable virtual environment, runs `uv pip check`, validates the
repository metadata with `scripts/compatibility_contract.py`, and executes the test suite directly
with `.venv/bin/python`.

The existing quality workflow remains lockfile-reproducible. The compatibility workflow runs
weekly in addition to pull requests and `main` pushes so upstream drift inside the supported MCP
major version is detected without changing the lockfile.

## Consequences

- The public Python and MCP SDK ranges are continuously tested rather than merely documented.
- The support floor cannot move accidentally without an explicit policy change.
- A newly published incompatible MCP 2.x version can fail the scheduled matrix and trigger review.
- MCP 3.x remains unsupported until the package metadata, contract, tests, and ADR are updated
  intentionally.
- CI cost increases by four test-suite executions per compatibility workflow run.
- Provider/transport and client-server interoperability matrices remain separate follow-up work.

## Addendum (2026-09-22): MCP SDK 2.2 floor

The support floor moved deliberately to MCP SDK `2.2.0` (`mcp>=2.2,<3`). SDK 2.2 adds the explicit
`AuthSettings.validate_token_resource` policy (ADR-0027) and SEP-2549 cache hints (ADR-0028), which
this repository now depends on. The `minimum` profile installs exactly `mcp==2.2.0`;
`scripts/compatibility_contract.py`, `compatibility.yml` and the package metadata changed together.

The test suite now also promotes `mcp.MCPDeprecationWarning` to an error, so SDK APIs scheduled to
change in MCP 3 fail the compatibility matrix while the project still runs on MCP 2.x.
