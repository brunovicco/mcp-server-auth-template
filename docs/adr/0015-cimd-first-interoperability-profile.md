# ADR-0015: Publish the CIMD-first pair interoperability profile

- Status: Accepted
- Date: 2026-08-09

## Context

This repository is an OAuth resource server and does not register MCP clients. The companion
client already delegates Client ID Metadata Document selection to the official MCP Python SDK,
but the shared cross-repository contract and client-owned E2E proved only Dynamic Client
Registration.

MCP 2026-07-28 deprecates DCR for new integrations and recommends Client ID Metadata Documents
when client and authorization server have no pre-existing relationship. Because both repositories
publish the same compatibility contract, the resource-server repository must record the richer
pair evidence even though its runtime behavior is unchanged.

## Decision

- Add `client-id-metadata-document` to the shared cross-repository positive-evidence set while
  retaining `dynamic-client-registration` as backwards-compatibility evidence.
- Keep client registration outside this resource server. The companion client owns the fake
  authorization-server behavior and live E2E proving that CIMD skips DCR, uses the configured
  HTTPS metadata URL as `client_id`, carries no client secret, and reaches an authenticated tool.
- Treat authorization-server fetching and validation of the remote metadata document as outside
  the pair's executable claim. Those controls belong to the authorization server and include its
  own SSRF, caching, document-validation, redirect-URI, and trust-policy boundary.

## Consequences

- The shared contract now reflects the recommended MCP 2026 registration path without moving
  authorization-server responsibilities into this repository.
- The server runtime, token verification, Protected Resource Metadata, and public compatibility
  ranges remain unchanged.
- Merge this server contract before the companion client change, because the client E2E compares
  its contract with `server/main` before starting the OAuth flow.
- Existing DCR deployments remain covered as a legacy interoperability path.
