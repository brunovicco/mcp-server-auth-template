# ADR 0025: OCI version encoding for the Official MCP Registry

## Status

Accepted.

## Context

The first manual P2.3 publication attempt used `mcp-publisher` 1.8.1 against the Official MCP
Registry. `mcp-publisher validate server.json` succeeded, but `mcp-publisher publish` returned HTTP
400 because the OCI package contained `packages[0].version`.

The generic `2025-12-11` `server.json` schema permits the optional `Package.version` property because
the same package model is shared by multiple registry types. The Official MCP Registry OCI backend
applies a stricter package-specific contract:

- `registryBaseUrl` must be absent;
- `version` must be absent;
- `fileSha256` must be absent;
- the OCI version or digest must be encoded in the canonical `identifier`.

For example:

```text
ghcr.io/brunovicco/mcp-server-auth-template:v0.6.2
```

The failed publication did not create a Registry server version.

The `v0.6.1` Git tag, GitHub Release and GHCR image are already immutable project artifacts and must
not be moved, deleted or recreated.

## Decision

For `registryType: "oci"`:

1. keep the root `server.json.version`;
2. encode the released OCI version only in `packages[].identifier`;
3. omit `packages[].version`;
4. reject `registryBaseUrl`, `version` and `fileSha256` in the project-owned Registry validator;
5. continue using versioned OCI tags and never introduce `latest`;
6. publish the corrected metadata only from a new immutable release, `v0.6.2`.

The secure release pipeline remains authoritative. The manual Official MCP Registry publication is
retried only after the public `v0.6.2` multi-platform OCI release and its evidence are independently
validated.

Registry automation remains deferred to P2.4 and must not be introduced until a manual publication
has succeeded end to end.

## Consequences

### Positive

- Project validation now mirrors the Registry backend's OCI-specific contract.
- OCI package identity has one unambiguous version source: the canonical `identifier`.
- Existing immutable `v0.6.1` evidence remains untouched.
- A successful manual publication remains a prerequisite for automation.

### Trade-offs

- `mcp-publisher validate` alone is not treated as proof that an OCI package is publishable.
- `v0.6.2` is required even though the MCP authorization runtime itself does not change.
- The project must continue tracking both generic schema evolution and registry-type-specific
  backend validation rules.
