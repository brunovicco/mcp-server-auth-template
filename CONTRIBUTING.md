# Contributing

This is a personal template repository, kept open for reference and reuse. Issues and PRs are
welcome; there's no formal process beyond what's below.

## Before opening a PR

```bash
uv lock --check
uv sync --frozen --all-groups
uv run python scripts/quality_gate.py
```

`quality_gate.py` is the canonical check - lint, format, architecture boundaries, MCP config,
typing, tests (with coverage), security (bandit), and dependency audit (pip-audit). Use `--list`
to see the resolved commands or `--check NAME` to run one in isolation. A PR isn't ready until
this passes clean; CI runs the same gate.

## Expectations

- Keep changes scoped to the stated goal - no unrelated refactors bundled into a fix.
- Add or update tests for behavior changes; see `docs/DEVELOPMENT.md` for local setup and
  `AGENTS.md` for the full completion bar.
- Respect the Clean Architecture dependency rule (`entrypoints -> application -> domain`,
  `adapters -> application/domain`) - `scripts/validate_architecture.py` enforces it and will
  fail the gate on a violation. See `docs/ARCHITECTURE.md` and `docs/adr/` for the reasoning.
- Never commit secrets, tokens, or real IdP credentials. Tests sign their own local JWTs
  (`tests/unit/auth_testing.py`) instead of hitting a real authorization server.
- Update `CHANGELOG.md` under `## [Unreleased]` for user-visible changes.

## Agent-assisted contributions

If you're using Claude Code, Codex, or a similar tool against this repo, follow the durable
project guidance in `AGENTS.md`, the checked-in workflows under `.agents/skills/`, and trusted
project configuration under `.codex/`. These project-owned instructions take precedence over
generic defaults.
