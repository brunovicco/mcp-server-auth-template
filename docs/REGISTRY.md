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

Automated Registry publication remains deliberately out of scope here. The first manual publication
attempt with `v0.6.1` exposed an OCI-specific backend rule that is stricter than the generic
`server.json` schema: OCI packages must encode their version only in `identifier`.

The first successful Registry publication therefore happens only after the corrected secure
`v0.6.2` OCI release is public and independently validated.
