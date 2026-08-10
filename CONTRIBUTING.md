# Contributing

This is a personal template repository kept open for reference and reuse. Issues and focused pull
requests are welcome.

## Before opening a PR

```bash
uv lock --check
uv sync --frozen --all-groups
uv run python scripts/quality_gate.py
```

`quality_gate.py` is the canonical definition of done: lint, format, architecture boundaries,
strict typing, tests/coverage, security, dependency audit, supply-chain controls, governance and
vendored contract validation. Use `--list` or `--check NAME` only for focused feedback; the complete
gate must pass before review.

## Expectations

- Keep changes scoped to the stated goal; do not bundle unrelated refactors.
- Add or update tests for behavior changes.
- Respect the Clean Architecture dependency rule enforced by `scripts/validate_architecture.py`.
- Never commit secrets, tokens or real IdP credentials. Tests use local keys and synthetic
  identities.
- Update `CHANGELOG.md` under `## [Unreleased]` for user-visible changes.
- Keep editor, coding-agent and personal automation state outside the public repository.
- Use `docs/DEVELOPMENT.md`, `docs/ARCHITECTURE.md` and `docs/adr/` as the durable project guidance.
