# Gateway key rotation — operations proposal (HOLD / NO_GO LIVE)

This is a qualification runbook, not an activation approval.

## Configuration
- Compose: set GATEWAY_ASSERTION_KEYS to a JSON object mapping key IDs to HMAC keys; unset GATEWAY_ASSERTION_SECRET in registry mode.
- Helm: reference an existing Secret with api.gatewayAssertionKeysSecret and api.gatewayAssertionKeysSecretKey. Leave api.gatewayAssertionSecret empty.
- Legacy mode: use only the legacy secret and leave the registry absent or empty.
- Never commit real key material or print rendered secret values to logs.
- The application rejects simultaneous nonempty legacy and registry modes.

## Rotation within registry mode
1. Provision a new distinct key ID and key through the approved secret manager.
2. Publish a registry containing both old and new keys to all API instances; recreate/restart workloads to reload environment variables.
3. Qualify both key IDs, tenant ACLs and cross-key replay rejection before switching signing.
4. Switch the trusted signer to the new key ID only after every verifier is qualified.
5. Wait for the maximum assertion lifetime (60 seconds), accounting for approved clock skew and in-flight requests, then remove the old key and roll verifiers again.
6. Confirm old-key rejection and new-key acceptance. If the old key is compromised, use the incident response process instead of normal overlap.

## Rollback
Before old-key removal, restore the signer to the old key only if it remains trusted and all verifiers accept it. After removal, coordinate verifier and signer changes; never restore a compromised key. Legacy-to-registry conversion requires a separately approved coordinated cutover because the two modes cannot coexist in one verifier.

## Outstanding qualification
- CI execution and runtime Helm/Compose evidence remain required.
- The strict rootless audit currently expects all containers to be running and bind sources to be under GAMMA_HOME/data. One-shot preflight/migration containers and read-only code mounts require explicit audit design; do not waive existing checks.
- PostgreSQL role preflight covers attributes and membership graph, not complete ACL, ownership, SECURITY DEFINER, credential or RLS qualification.
- No deployment or production activation is authorized by this document.
