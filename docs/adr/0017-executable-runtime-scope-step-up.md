# ADR-0017: Make runtime scope step-up executable with an elevated health profile

- Status: Accepted
- Date: 2026-08-09

## Context

ADR-0006 established the server-side bridge from per-tool policy to an HTTP `403
insufficient_scope` challenge, and the companion client delegates reauthorization to the official
MCP Python SDK. The live pair suite proved the challenge shape only with a manually minted token;
it did not prove that a normal client preserves its prior grant, obtains an elevated token, and
completes the original operation.

An executable step-up needs one operation whose minimum scope is intentionally absent from the
initial Protected Resource Metadata baseline. The authenticated MCP `health` example is distinct
from the unauthenticated operational probes at `/livez` and `/readyz`, so it can carry this advanced
authorization example without coupling deployment health checks to OAuth.

## Decision

- Keep `mcp:tools:call` as the global initial scope and require `mcp:tools:health` for the MCP
  `health` tool.
- Use a delegated-scope policy for Entra and an OAuth-scope policy for generic OIDC. Entra scope
  names continue to be qualified with the configured Application ID URI, and application
  principals are not offered an impossible delegated step-up.
- Continue producing one pre-dispatch `403` challenge containing every scope required for the
  operation. The handler is not invoked for the rejected request.
- Delegate scope union, interactive reauthorization, token persistence, and the single HTTP replay
  to the official MCP SDK. Do not add server state or an application-level retry loop.
- Add the successful runtime step-up, scope union, and pre-dispatch replay to the shared pair
  contract; the companion client owns the complete E2E.

## Consequences

- A default demo now exercises least-privilege incremental consent rather than describing it only
  in framework code and unit tests.
- Authorization-server setup must expose `mcp:tools:health` in addition to `mcp:tools:call`; it is
  deliberately omitted from the initial resource baseline and requested from the runtime challenge.
- The OAuth replay does not weaken the client's no-generic-tool-retry policy: the first attempt is
  rejected during bearer verification before MCP dispatch, and the SDK performs only the
  authorization recovery retry.
- Existing operational probes remain unauthenticated and unaffected.
- Merge this server change before the client change because the client E2E compares with
  `server/main`.
