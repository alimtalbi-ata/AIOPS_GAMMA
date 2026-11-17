# GLPI staging qualification — read-only incident snapshots

**Status:** not executed. This document is a gate/checklist, not evidence of a qualified connector.

## Prerequisites
1. Isolated GLPI staging instance, pinned GLPI version and legacy REST API contract; record API URL and version **without** secrets.
2. Dedicated service account with read-only Ticket permission, scoped to one authorized entity. Verify whether inherited/recursive entities are enabled and explicitly exclude them unless approved.
3. Trusted authenticated gateway that strips caller-supplied `X-Tenant-Id` and `X-Internal-Api-Key`, then sets authorized tenant identity. Restrict egress and DNS to the exact GLPI host; TLS certificates must be trusted.
4. Provision `GLPI_SESSION_TOKEN` and `GLPI_APP_TOKEN` through the deployment secret manager. Do not put secrets in GitHub issues, logs, screenshots, or CI output.
5. Set `GLPI_READ_URL`, `GLPI_TENANT_ID`, `GLPI_ENTITY_ID`; leave `ENABLE_GLPI_READS=false` until the above controls are verified. Only turn it on in staging.

## Contract matrix
| Case | Staging setup / action | Expected API behavior | Evidence to record |
| --- | --- | --- | --- |
| Valid incident | Existing type=1 ticket in configured entity | 200, minimal projection; no PII | Sanitized request ID, HTTP status, GLPI version |
| Different entity | Existing incident outside authorized entity | GLPI denies or adapter returns generic 502; never returns ticket data | Entity ACL screenshot with secrets masked; status |
| Different tenant | Trusted gateway sends another tenant identity | 403 before GLPI network call | Sanitized gateway trace and HTTP status |
| Non-incident | Ticket type=2 (request) in same entity | 502, no payload leakage | HTTP status and ticket type only |
| Missing ticket | Nonexistent positive ticket ID | 502, no upstream body | HTTP status |
| Expired/revoked session | Revoke test session token | 502; no implicit reauthentication | HTTP status and token revocation timestamp |
| Wrong application token | Replace token in staging secret manager | 502 | HTTP status only |
| Redirect | Controlled staging reverse proxy returns 302 | 502; no redirect followed | Destination host and network trace, no credentials |
| Oversized or malformed response | Controlled mock/reverse-proxy fixture | 502, no raw body | Fixture identifier and status |
| GLPI version variation | Compare expected fields `id`, `entities_id`, `type`, `status` | Confirm strict integer types and entity semantics | Sanitized schema and GLPI version |
| Disabled flag | `ENABLE_GLPI_READS=false` | 503; no GLPI request | HTTP status |

## Acceptance criteria
- All cases have an identified tester, date, environment version and redacted evidence; unexpected behavior is filed as an issue.
- GLPI service account has no create/update/delete rights, including through alternate endpoints.
- Actual tenant identity is authenticated and authorized at the gateway, not trusted from unverified client headers.
- No service credentials or incident PII appear in logs, responses, issues, or artifacts.
- CI passes on the PR HEAD; operations/security reviewers approve egress, TLS, secrets and RBAC.
- Any mismatch in GLPI API field types, session lifecycle or entity inheritance blocks activation until code/tests are revised.

## Rollback
Set `ENABLE_GLPI_READS=false` in staging and redeploy/reload configuration. Revoke the service session token if compromise is suspected. No incident writeback or GLPI mutation is implemented.

## Known limits
This is a **single-tenant** prototype with a pre-provisioned session token. There is no session refresh, credential registry, recursive-entity authorization model, or production-ready audit integration. No staging endpoint or credentials are currently available to this implementation workflow, so none of the above cases have been run against a real GLPI server.
