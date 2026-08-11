# ADR 0024: Official MCP Registry integration

## Status

Accepted for P2.1 readiness. Publication is deferred to P2.3.

## Context

The server is distributed as a public multi-platform GHCR image and exposes MCP through protected
Streamable HTTP. It is not a stdio server and the project does not currently operate a stable hosted
remote MCP endpoint.

The Official MCP Registry currently uses the `2025-12-11` `server.json` schema. OCI package ownership
is verified through the `io.modelcontextprotocol.server.name` image annotation, which must match the
Registry server name. GitHub authentication naturally grants the personal namespace
`io.github.brunovicco/*`.

The Registry schema supports Streamable HTTP for packages, but does not express conditional
environment-variable requirements for alternative authorization providers.

## Decision

Publish under:

```text
io.github.brunovicco/mcp-server-auth-template
```

Use one GHCR OCI package with:

- versioned tag `v<server.version>` and no `latest` tag;
- `runtimeHint: docker`;
- `transport.type: streamable-http`;
- loopback transport URL `http://127.0.0.1:8000/mcp`;
- loopback-only Docker port publishing;
- read-only filesystem, dedicated `/tmp`, dropped capabilities and `no-new-privileges`;
- explicit OAuth/OIDC configuration inputs;
- provider-specific settings documented as conditional rather than globally required.

Do not declare `remotes` until the project operates a stable public MCP endpoint.

Add the required OCI ownership label to the production image. Because `v0.6.0` is immutable and was
published without this label, Registry-ready image publication requires `v0.6.1`.

Validate two layers separately:

1. project-owned invariants through `scripts/validate_registry_metadata.py`;
2. official schema/semantic behavior through checksum-verified `mcp-publisher validate`.

The secure release pipeline remains authoritative. Registry publication must not happen until the
final multi-platform OCI index, platform digests, policy results, attestations and GitHub Release are
validated. Automated Registry publication is a later P2.4 decision.

## Consequences

### Positive

- Registry metadata reflects the real HTTP transport instead of copying stdio examples.
- OCI ownership is cryptographically downstream of the same scanned release candidates.
- Version drift between source metadata, Git tags and package tags fails closed.
- The Registry entry does not falsely imply a hosted service.

### Trade-offs

- Provider-specific configuration cannot be modeled conditionally in the current schema.
- Registry package metadata remains an installation/deployment description, not an identity-provider
  provisioning system.
- `v0.6.1` is required solely because image metadata is part of the immutable OCI artifact.
