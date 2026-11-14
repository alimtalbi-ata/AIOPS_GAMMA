# Gateway identity contract — GAMMA tenant boundary

**Qualification status: HOLD / NO_GO.** This document records the service-side assertion contract already implemented in `app/security.py`. It does not claim that a real gateway, IdP, membership directory, key distribution, or network path has been integrated or tested.

## Existing service-side contract

For every tenant-scoped API request, the service expects:

- `X-Internal-API-Key`: service-to-service workload credential. It authenticates the calling workload only; it is not tenant authorization.
- `X-Gateway-Principal`: compact `base64url(payload).base64url(HMAC-SHA256)` assertion signed over the encoded payload.
- The service ignores `X-Tenant-ID` for authorization. Tenant context is taken only from the verified assertion.

The assertion payload must contain:

| Claim | Requirement |
|---|---|
| `iss` | Exact configured gateway issuer |
| `aud` | Exact GAMMA API audience |
| `sub` | Non-empty actor subject, max 256 chars |
| `actor_type` | `user` or `service` |
| `tenant_id` | Canonical, non-zero UUID string |
| `tenant_access` | Boolean `true`, attesting that gateway already checked membership |
| `iat`, `exp` | Integer timestamps; lifetime positive and no more than 60 seconds |
| `jti` | Unique assertion identifier, 8–128 printable ASCII chars |
| `method`, `path` | Exact HTTP method and request path; assertion is request-bound |

The HMAC key must be at least 32 UTF-8 bytes. Duplicate JSON claims, malformed/noncanonical base64url, invalid signature, wrong issuer/audience, stale/overlong lifetime, mismatched method/path and malformed actor/tenant claims are rejected. Missing verifier configuration fails closed.

## Required gateway owner decisions — do not infer

Before deployment, the gateway/IdP owner must provide and approve:

1. Issuer and audience values for the deployed gateway and GAMMA API (the code defaults are placeholders, not a production decision).
2. A written guarantee that the gateway authenticates the actor, resolves actor→tenant membership from an authoritative server-side source, strips inbound client-supplied identity headers, and only then signs `tenant_access=true`.
3. Actor subject format and lifecycle; allowed actor types and service-account membership semantics.
4. HMAC key generation, secret-manager/Kubernetes Secret delivery, rotation overlap, revocation and incident response. Never put key material in Git, Helm values, logs or frontend configuration.
5. Exact gateway Kubernetes namespace labels and pod labels, plus service port and any mTLS identity. The chart now defaults API ingress to an explicit deny-all policy; it permits API ingress only when both non-empty gateway namespace and pod label selectors are supplied. Those selectors remain intentionally empty until approved by the platform owner.
6. Replay policy for `jti`: current service verifies short TTL and request binding but does not persist/consume assertion IDs. Gateway must use one-time assertions and the owner must decide whether server-side replay cache is required for the threat model.

## Deployment blockers

- Helm now exposes explicit issuer, audience and TTL values and can optionally mount the HMAC assertion key from a Kubernetes Secret. The Secret reference is omitted while `api.gatewayAssertionSecret` is empty; in that default state the service verifier remains unconfigured and fails closed. Configure a real Secret only after gateway-owner approval.
- Trusted gateway namespace/pod selectors are intentionally empty. API ingress therefore remains deny-all until the platform owner supplies the exact approved selectors.
- No live gateway/IdP contract, key rotation, mTLS, network bypass test or two-principal actor→tenant test has been evidenced.
- Existing signed-assertion unit tests prove verifier behavior against synthetic HMAC tokens only. They do not prove the gateway issued the token after checking a real membership directory.

## Acceptance evidence

Do not enable tenant-scoped canonical/OpenSearch/GLPI reads or merge the feature until all of the following are attached to the issue/PR:

- Gateway owner approval of the claims and membership semantics above.
- Staging configuration evidence for issuer/audience and secret delivery without disclosing secrets.
- Positive actor A→tenant A request succeeds; actor A→tenant B forged header fails before backend access.
- Missing, expired, wrong-issuer, wrong-audience, tampered, replayed and request-mismatched assertions fail closed.
- Direct pod-to-API traffic from a non-gateway workload is denied by NetworkPolicy.
- CI passes on the exact PR HEAD; real staging ACL and upstream resource authorization are separately qualified.

**No automatic activation. No LIVE. No merge.**
