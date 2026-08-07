# Privacy and data handling

This service holds no persistence layer of its own (no database, no file storage, no cache beyond
in-memory JWKS/discovery caches) - the only "data" it handles is the bearer token on each request
and the claims decoded from it. Extend this document if a concrete deployment of this template
later adds a datastore or processes other personal data.

## Data inventory

| Data category | Source | Purpose | Legal/contractual basis | Destination | Retention | Deletion method |
|---|---|---|---|---|---|---|
| Bearer token + its decoded claims (`sub`, `client_id`, `scope`/`scp`/`roles`, `tid` for Entra) | Caller's `Authorization` header | Verify the request is authenticated and scoped, and answer `whoami` with the caller's own identity | Necessary to provide the requested service (RFC 6749/8707 resource-server verification) | Process memory only, for the duration of the request | Not retained - discarded when the request completes | N/A (never written to disk, a database, or a log) |

## Controls

- Data minimization: only the claims required for verification (`exp`, `iat`, `iss`, `aud`, `sub`)
  and identity display (`client_id`, `scope`/`scp`/`roles`) are read; the full claim set is kept on
  `AccessToken.claims` in memory for the request but never serialized or logged wholesale.
- Access control: the `whoami` tool only ever returns the identity of the caller's own token - there
  is no cross-caller lookup.
- Encryption in transit: this app talks to the authorization server's discovery/JWKS endpoints over
  HTTPS via `httpx`. The app itself does not terminate TLS for inbound traffic - deploy it behind a
  TLS-terminating proxy/load balancer.
- Encryption at rest: not applicable - no data is persisted.
- Masking/tokenization: not applicable - no data is persisted.
- Non-production data strategy: tests never call a real authorization server or use a real token;
  `tests/unit/auth_testing.py` generates a local RSA keypair and self-signs test JWTs offline.
- Logging and tracing restrictions: token-rejection logs use a stable event name and a `reason`
  field only (see `adapters/generic_oidc_token_verifier.py`, `adapters/entra_token_verifier.py`) -
  never the token or its claims. Document any enabled tracing backend, content-capture approval,
  redaction, retention, and access policy before enabling content-bearing tracing. Generic
  OpenTelemetry spans are metadata-only: custom attributes pass through a bounded allowlist and must
  never contain prompts, responses, credentials, authorization headers, personal data, arbitrary
  URLs, tool output, or production payloads. The public tracing wrappers enforce this policy for
  span and event attributes, operation names, status descriptions, and exception details. W3C
  baggage is not propagated by default.
- Data-subject deletion/anonymization: not applicable - nothing is retained past the request.
- External processors: the configured authorization server (Entra ID or the generic OIDC AS) is the
  only external system this service calls, and only for discovery/JWKS metadata; a caller's token
  itself is never forwarded elsewhere. If the optional OpenTelemetry or Langfuse tracing extras are
  enabled, their configured OTLP/Langfuse endpoint becomes an additional external processor - keep
  it metadata-only per the policy above.
- Incident-response owner: set per deployment - this template does not prescribe one.

## Prohibited logging

Secrets, authentication headers, personal identifiers, full financial identifiers, complete request/response payloads, prompts, and model outputs containing sensitive data.
