# LLM observability policy

## Vendor-neutral application tracing

The server uses `a2a-otel-kit[mcp]>=0.6,<0.7` as a core dependency. The ASGI composition root
configures one `Observability` facade and inserts `TracingASGIMiddleware` inside hardened HTTP
admission and outside authentication/tool dispatch. Every admitted MCP Streamable HTTP request
continues W3C `traceparent`/`tracestate` and creates a fixed `mcp.server.streamable_http` span.

Observability is disabled by default. Unless `A2A_OTEL_ENABLED=true` and
`A2A_OTEL_OTLP_ENDPOINT` are both configured, no exporter, worker, or telemetry network connection
is created. The MCP server lifespan owns `observability.shutdown()` after readiness is cleared and
the OIDC HTTP client is closed. This does not alter the separate `LlmCallObserver` or its optional
`tracing` extra described below.

The adapter never reads request or response bodies and never records authorization data, MCP
arguments/results, arbitrary headers, URLs, baggage, or exception text. Trace context is only a
correlation mechanism; it does not participate in authentication or authorization. Structured
logs derive `trace_id` and `span_id` only from a valid current span.

### OpenTelemetry configuration

| Variable | Required | Purpose |
| --- | --- | --- |
| `A2A_OTEL_ENABLED` | no (default `false`) | Enables tracing and OTLP export |
| `A2A_OTEL_OTLP_ENDPOINT` | required when enabled | Complete OTLP HTTP traces endpoint |
| `A2A_OTEL_OTLP_TIMEOUT_SECONDS` | no (default `10.0`) | Export timeout |
| `A2A_OTEL_LOG_LEVEL` | no (default `INFO`) | Logging level used during facade setup |
| `A2A_OTEL_LOG_FORMAT` | no (default `json`) | `json` or `console` |

Tests keep tracing disabled or use in-memory exporters; they never require a collector, network
access, credentials, or an external service.

## Langfuse LLM tracing

This project can optionally trace LLM calls (latency, token usage, cost, and model name) to
Langfuse through `src/mcp_server_auth_template/adapters/tracing.py`. Structured application logging itself
is always configured through `src/mcp_server_auth_template/entrypoints/logging.py` and is not part of this
policy—it never carries prompts or model responses; see the security and observability contract
in `AGENTS.md`.

## Design principle

Tracing is opt-in and defaults to metadata only. `build_llm_call_observer()` returns a no-op
observer whenever the `tracing` optional dependency is not installed or Langfuse credentials are
not set, so application code never needs to branch on whether tracing is enabled.

## Default behavior

- No prompt or completion content is sent to Langfuse unless `LANGFUSE_CAPTURE_CONTENT=true` is
  set explicitly.
- Only metadata is recorded by default: call name, model, latency, token counts, and the bounded
  allowlisted fields enforced by `sanitize_metadata()`. Unknown, nested, content-bearing, and
  oversized metadata is discarded.

## Enabling tracing

1. Confirm a business need for prompt/response-level debugging or evaluation that latency and
   token metrics alone do not satisfy.
2. Choose a Langfuse deployment: cloud (`https://cloud.langfuse.com` EU,
   `https://us.cloud.langfuse.com` US, `https://jp.cloud.langfuse.com` Japan,
   or the HIPAA-eligible region) or self-hosted.
3. `uv sync --extra tracing` to install the `langfuse` package.
4. Set `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, and `LANGFUSE_BASE_URL` from a secret manager
   or environment injection - never commit real values; `.env.example` documents the variable
   names only.
5. Keep `LANGFUSE_CAPTURE_CONTENT=false` unless the approval checklist below has been completed
   for this project.
6. Record the decision (scope, data classes, retention) in `docs/PRIVACY.md`.

## Approval checklist before enabling `LANGFUSE_CAPTURE_CONTENT=true`

- Named business and technical owner for the tracing data.
- Data classification of what a prompt or completion is expected to contain (PII, credentials,
  regulated data must not appear; if they can, redact at the call site before recording).
- Retention period configured in Langfuse and a deletion procedure.
- Access control for who can read traces in the Langfuse project.
- Non-production data used for any test or staging traces.
- Confirmation that no MCP tool output, secrets, or credentials can reach `prompt`/`completion`
  fields. The tracing adapter allowlists metadata, but when content capture is enabled the caller
  remains responsible for redacting the explicit `prompt` and `completion` values.

## Configuration reference

| Variable | Required | Purpose |
| --- | --- | --- |
| `LANGFUSE_PUBLIC_KEY` | to enable tracing | Project public key |
| `LANGFUSE_SECRET_KEY` | to enable tracing | Project secret key; environment-injected only |
| `LANGFUSE_BASE_URL` | no (defaults to EU cloud) | Cloud region or self-hosted URL |
| `LANGFUSE_CAPTURE_CONTENT` | no (defaults to `false`) | Set `true` only after the approval checklist |

## Uninstrumented by default

Leaving all four variables unset keeps the project fully untraced; `build_llm_call_observer()`
returns `NullLlmCallObserver`, which discards every call outcome. This matches the harness's MCP
governance model: nothing external is connected until a project deliberately opts in.
