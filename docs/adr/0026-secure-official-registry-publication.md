# ADR 0026: Secure Official MCP Registry publication automation

- Status: Accepted
- Date: 2026-08-11

## Context

The first Official MCP Registry publication was intentionally manual. That P2.3 path established the
real production contract and exposed two facts that matter for automation:

1. the Official Registry applies OCI-specific validation beyond the generic `server.json` schema;
2. the Registry JWT obtained through interactive GitHub login is short-lived enough that lengthy
   checks between authentication and publication can cause a valid session to expire.

The secure release workflow already owns a separate, fail-closed boundary for Python artifacts,
multi-platform OCI publication, vulnerability policy, attestations and the GitHub Release. Registry
publication must consume that completed release rather than become another producer inside it.

GitHub's `workflow_run` trigger is privileged. A workflow using it must not execute untrusted
pull-request content. This project therefore treats the default branch as the trusted automation
source and treats the release tag as data until its provenance has been verified.

## Decision

Official MCP Registry publication is automated in a dedicated workflow that runs only after
`secure-release-publication` completes successfully.

Before requesting any Registry credential, the workflow verifies the triggering workflow identity,
tag event, annotated tag SHA, default-branch ancestry, published GitHub Release, immutable
`server.json`, release `image-digest.txt`, public version/commit OCI digests and both platform MCP
ownership labels.

Only after those checks may the workflow request a Registry credential with:

```text
mcp-publisher login github-oidc
```

The job receives only `contents: read` and `id-token: write`. No Registry PAT, repository secret or
organization secret is introduced. The checksum-verified project installer remains the source of the
pinned `mcp-publisher` binary.

Authentication and `publish` are adjacent steps so the short-lived Registry JWT is not held while
release or OCI verification runs.

After publication, the workflow verifies the exact version. When the current version is expected to
be latest, it also verifies the `latest` endpoint and Registry discovery.

Retries are idempotent. If the exact version already exists and matches the immutable release, the
workflow performs verification only and does not request a new OIDC token or republish the entry.

## Consequences

The GitHub/OCI release remains independently valid if Registry publication is unavailable. Registry
failures live in a separate workflow and can be retried without attempting to overwrite immutable
GitHub Release or GHCR artifacts.

The automation intentionally has no `pull_request`, `pull_request_target`, direct tag-push or manual
dispatch trigger. It consumes only a successfully completed secure release and re-verifies the
handoff before using OIDC.

The workflow executes scripts from the trusted default branch. Release-tag content is inspected only
after the tag SHA and default-branch ancestry checks succeed.

The Registry remains a preview service. A future breaking Registry change must fail closed and be
handled by a new reviewed repository change rather than by weakening these checks.

## Rejected alternatives

### Publish inside `secure-release-publication`

Rejected because Registry availability would become coupled to the immutable artifact release and a
Registry retry could tempt operators to rerun publication stages that intentionally refuse to
overwrite OCI tags.

### Trigger on the GitHub `release` event

Rejected because ordinary events caused with a workflow's `GITHUB_TOKEN` do not create another
workflow run. `workflow_run` gives an explicit completion handoff without a PAT or GitHub App token.

### GitHub PAT authentication

Rejected because GitHub OIDC is officially supported for Registry publication and requires no
long-lived dedicated Registry secret.

### `pull_request_target` or untrusted `workflow_run` checkout

Rejected because privileged workflows must not execute untrusted pull-request code.
