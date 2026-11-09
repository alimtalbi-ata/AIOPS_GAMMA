# GLPI read-only incident adapter (experimental)

Endpoint: `GET /api/v1/itil4/glpi/incidents/{ticket_id}/snapshot`.

This is a **disabled-by-default**, server-configured, **single-tenant** prototype using the GLPI legacy `/apirest.php/Ticket/{id}` API. It is not a qualified production connector. No GLPI session initialization, ticket creation, update, CMDB mutation, or change approval occurs.

Required environment settings:
- `ENABLE_GLPI_READS=true` (default false)
- `GLPI_READ_URL=https://glpi.internal` (fixed HTTPS origin, no path)
- `GLPI_TENANT_ID=<trusted UUID>` (server-side binding, never browser supplied)
- `GLPI_ENTITY_ID=<authorized GLPI entity integer>`
- `GLPI_SESSION_TOKEN=<service session token>`
- `GLPI_APP_TOKEN=<application token>`

A trusted internal gateway must authenticate the principal, strip client-supplied identity headers and enforce its own tenant authorization. The service token must have **read-only** permissions restricted to the configured GLPI entity. The adapter compares the returned `entities_id`, ticket `id`, and GLPI ticket `type=1` (incident) to server-owned values, and emits only a minimal safe projection (no ticket descriptions, names, user identities or raw vendor payload).

Transport is GET-only, TLS-verified, redirect-disabled, proxy-environment-disabled, time-bounded and response-size-bounded. Network egress/DNS allowlisting, token rotation and audit logging remain infrastructure responsibilities. GLPI permission enforcement must be validated in staging; a matching entity field is **not** a substitute for GLPI RBAC. Do not activate against production until service-account scope, version-specific payloads, and multi-entity inheritance behavior are verified.

Remaining: GLPI version-pinned contract tests, service-session lifecycle/expiry, ACL-backed multi-tenant credential registry, CI matching, reconciliation and evidence links, staging integration tests, and secret management. No ITSM writes are authorized.

## CI and staging qualification
- Historical run `42671763231` on `d505bfca` failed, but later run `42674584843` on `b69374ac` **passed**. Recheck CI on the latest HEAD after each change; this does not qualify live GLPI behavior.
- Validate GLPI API version, session-token expiry, entity inheritance, denial of out-of-scope tickets, and actual RBAC against a staging instance.
- Route-level tests cover missing internal authentication, invalid tenant identity and cross-tenant denial. No live GLPI calls or staging integration tests have been executed in this handover.

## Failure-mode contract
- GLPI redirects (301/302), expired or rejected sessions (401/403), missing tickets (404), rate limiting (429), and upstream server failures (5xx) are **not** retried or followed; they yield a generic HTTP 502 response without propagating vendor payloads or credentials.
- Non-JSON 200 responses are rejected. The upstream GET uses a bounded timeout and body size, and the client does not honor environment proxy variables.
- Tests use HTTPX mock transport; these are simulated failures, **not** evidence of a real GLPI deployment's behavior. A staging test plan must verify session expiry, entity ACL, inherited entity access, API version and actual upstream response shapes.
