# ADR-0023: Scan platform images before publishing a multi-platform release

- Status: Accepted
- Date: 2026-08-10

## Context

`v0.5.0` established a fail-closed release boundary where the production container is built,
inventoried, scanned and policy-approved before the release job receives GHCR credentials.

The published v0.5.0 image is only `linux/amd64`. Apple Silicon therefore requires emulation, while
the project now wants one release reference that resolves natively on AMD64 and ARM64.

Publishing directly with a multi-platform `buildx --push` would put bytes in the registry before the
existing vulnerability policy has approved both architectures. Rebuilding after local scans would
also weaken evidence binding because the scanned and published subjects would be separate builds.

## Decision

For each release tag:

1. configure QEMU and Buildx through SHA-pinned Actions;
2. build `linux/amd64` and `linux/arm64` as local single-platform images;
3. generate an independent CycloneDX image SBOM and complete Grype report for each platform;
4. evaluate the vulnerability policy independently for both platforms;
5. authenticate to GHCR only after both evaluations pass;
6. push the exact scanned local images under immutable architecture-specific version and commit tags;
7. resolve and compare the registry digest of each platform;
8. create version and commit OCI indexes from those two canonical platform digests;
9. require both index tags to resolve to the same digest;
10. validate the final registry index contains exactly `linux/amd64` and `linux/arm64`;
11. attest build provenance for the final index and attach each platform SBOM to its own digest.

Architecture-specific evidence aliases are retained:

```text
vX.Y.Z-amd64
vX.Y.Z-arm64
sha-<commit>-amd64
sha-<commit>-arm64
```

Normal consumers should use the version index or its immutable digest.

## Consequences

### Positive

- Apple Silicon receives a native ARM64 image.
- Windows Docker Desktop, Intel Mac and x86_64 Linux continue using AMD64.
- Registry authentication remains after vulnerability-policy approval.
- Published platform images are the same local image subjects that were scanned.
- Security evidence remains independently inspectable per architecture.
- `image-platforms.json` binds the final index to the exact scanned platform digests.

### Trade-offs

- ARM64 release builds use QEMU on the AMD64 GitHub-hosted runner and increase release duration.
- Evidence size increases because image SBOM, Grype and policy files exist per platform.
- Four immutable platform aliases are retained in addition to the version and commit index tags.
- A failure after platform push but before index publication is a partial release; the affected
  version must not be reused.

## Alternatives rejected

### Publish the multi-platform image before scanning

Rejected because publication would precede security-policy approval.

### Scan only AMD64

Rejected because OS packages and architecture-specific artifacts can differ.

### Rebuild after scanning

Rejected because the published subject would not be the exact scanned build.

### Keep separate platform-only release tags

Rejected because consumers should have one standard multi-platform version reference.
