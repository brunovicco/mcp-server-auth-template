# Official MCP Registry

This repository is prepared for publication as:

```text
io.github.brunovicco/mcp-server-auth-template
```

The Registry metadata is intentionally different from a hosted-service declaration. The project
publishes a public OCI package on GHCR, but it does not currently operate a stable public `/mcp`
service. `server.json` therefore declares an OCI package using Streamable HTTP and does not declare
`remotes`.

## Version and package binding

The following values must move together:

```text
pyproject.toml project.version
server.json version
server.json OCI identifier tag v<version>
Git release tag v<version>
```

For `registryType: "oci"`, `packages[].version` must be omitted. OCI version identity is encoded
only in the canonical `identifier`, for example
`ghcr.io/brunovicco/mcp-server-auth-template:v0.6.2`.

`registryBaseUrl` and `fileSha256` are also intentionally absent from the OCI package metadata.

`latest` is never used. The secure release workflow resolves the version tag to the final immutable
multi-platform OCI index digest and records that digest as release evidence.

## OCI ownership

The Official MCP Registry verifies OCI package ownership through this image label:

```text
io.modelcontextprotocol.server.name=io.github.brunovicco/mcp-server-auth-template
```

The label is checked in the Dockerfile, in CI-built images, and again for each release candidate
before GHCR authentication or publication.

## Streamable HTTP package profile

The Registry package launches the image through Docker with a loopback-only port publication and
the same runtime hardening used by project CI:

```text
--read-only
--tmpfs /tmp:rw,noexec,nosuid,nodev,size=16m
--cap-drop ALL
--security-opt no-new-privileges:true
--publish 127.0.0.1:8000:8000
```

The package transport is `http://127.0.0.1:8000/mcp`. OAuth/OIDC deployment values remain explicit
configuration inputs. The current `server.json` schema cannot express conditional inputs, so Entra
and generic-OIDC provider-specific fields are documented as conditionally required rather than
incorrectly marked as globally required.

This package metadata is not a claim that enterprise identity configuration is one-click. Production
deployments still own TLS termination, identity-provider registration, consent, secrets, proxy
configuration and organization-specific authorization policy.

## Validation

Project invariants:

```bash
uv run python scripts/validate_registry_metadata.py
```

Official schema and semantic validation:

```bash
publisher_dir="$(mktemp -d)"
bash scripts/install_mcp_publisher.sh "$publisher_dir"
"$publisher_dir/mcp-publisher" validate server.json
```

The installer pins the current publisher release and verifies the platform archive SHA-256 before
execution.

For a release tag:

```bash
uv run python scripts/validate_registry_metadata.py --release-tag v0.6.2
```

## Automated publication

The first successful publication was completed manually for `v0.6.2` to establish the production
contract before automation.

Future releases are published by `.github/workflows/publish-mcp-registry.yml` only after
`secure-release-publication` completes successfully. The Registry workflow is deliberately separate
from immutable artifact publication so a Registry outage or retry cannot cause GHCR tags or GitHub
Release assets to be recreated.

Before requesting a Registry credential, automation verifies the secure-release workflow identity,
annotated tag and commit, default-branch ancestry, published GitHub Release, immutable release digest,
version/commit OCI digest equality, both platform ownership labels and the release `server.json`.

Authentication uses `mcp-publisher login github-oidc`. The publication job has only `contents: read`
and `id-token: write`; no Registry PAT or dedicated secret is stored. Authentication happens
immediately before `publish` so the short-lived Registry JWT is not consumed by earlier validation.

Retries are idempotent. If the exact Registry version already exists and matches the immutable
release, the workflow verifies it and does not publish again.

After a new publication the workflow verifies the exact version, `latest`, and discovery before
completing.
