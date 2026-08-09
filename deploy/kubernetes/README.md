# Kubernetes reference deployment

This directory is a hardened deployment baseline for the MCP HTTP server. It is intentionally
small enough to adapt to a managed Kubernetes platform rather than pretending to be a universal
production stack.

## Before applying

1. Replace the all-zero image digest in `deployment.yaml` with the immutable digest produced by
   your image build/release pipeline. Do not replace it with `latest`.
2. Replace the `.invalid` resource-server, issuer, and audience values in `configmap.yaml`. The
   ConfigMap sets `APP_ENV=production`, so the process preflight intentionally refuses to start
   while those placeholders remain.
3. Switch the provider block if deploying against Microsoft Entra ID.
4. Configure ingress/TLS so the public `Host` forwarded to `/mcp` matches
   `MCP_SERVER_RESOURCE_SERVER_URL` or an explicitly allowed transport host.
5. Add platform-specific NetworkPolicy/egress controls that permit DNS plus only the selected
   authorization-server/JWKS destinations. Generic CIDR examples are intentionally omitted because
   identity-provider addresses vary by provider and deployment.

No Kubernetes Secret is required by the resource-server template itself: it verifies access tokens
and does not hold an OAuth client secret. Add Secret delivery only for application-specific
extensions that actually require one.

## Apply

After replacing the placeholders:

```bash
kubectl apply -k deploy/kubernetes
```

The baseline runs two stateless replicas with a zero-unavailable rolling-update strategy, a
PodDisruptionBudget, node-level topology spreading, explicit resource requests/limits, startup /
readiness / liveness probes, no mounted service-account token, `RuntimeDefault` seccomp, a read-only
root filesystem, and all Linux capabilities dropped.

The 45-second Pod termination grace period intentionally exceeds the application's default
30-second graceful-shutdown deadline.

The node-level `DoNotSchedule` spread constraint assumes at least two eligible Kubernetes nodes.
For a single-node development cluster, relax that constraint explicitly rather than weakening the
checked-in production baseline.

## Validate

CI validates the Kubernetes resource manifests with Kubeconform in strict mode against the
Kubernetes 1.36 schema family. To run the same check locally with Docker:

```bash
docker run --rm \
  -v "$PWD:/work:ro" \
  ghcr.io/yannh/kubeconform:v0.8.0 \
  -strict \
  -summary \
  -kubernetes-version 1.36.0 \
  -ignore-filename-pattern '(^|/)kustomization\\.yaml$' \
  /work/deploy/kubernetes
```

Kubeconform validates Kubernetes OpenAPI structure; cluster admission policies and server-side
validation still need a real target cluster or a platform-specific validation environment.
