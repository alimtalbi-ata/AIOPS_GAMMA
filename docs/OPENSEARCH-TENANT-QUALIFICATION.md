# OpenSearch tenant isolation — staging qualification gate

Status: **NOT QUALIFIED**. This is a manual staging acceptance procedure, not
proof of OpenSearch document-level security (DLS).

## Preconditions

- Use a disposable staging OpenSearch cluster, never production data.
- Two authorized test tenants A and B and two services `checkout` and `payments`.
- A service account with the **same** effective permissions and index pattern
  that GAMMA will use. Do not run only as an OpenSearch administrator.
- Confirm the index template and actual backing indices resolve
  `tenant.id` and `resource.attributes.service.name` as exact-match
  `keyword` fields (or explicit `.keyword` subfields, updating the query
  builder accordingly). Confirm `@timestamp` is `date` and
  `severityText` has the intended exact-match mapping.
- Confirm the GAMMA API key is only injected by a trusted gateway that
  authenticates the caller and authorizes their tenant. A client-supplied
  `X-Tenant-ID` is **not** proof of authorization.

## Synthetic fixture matrix

Insert uniquely identifiable, non-sensitive test documents:

| Tenant | Service | Severity | Timestamp |
| --- | --- | --- | --- |
| A | checkout | ERROR | inside test window |
| A | payments | WARN | inside test window |
| B | checkout | ERROR | inside test window |
| B | payments | WARN | inside test window |
| A | checkout | ERROR | outside test window |

Use a unique fixture run ID to avoid collisions and remove the fixtures
after the test.

## Acceptance checks

1. With an authenticated principal authorized for A, search `checkout`
   within the test window: only the A/checkout document is returned.
2. Repeat for B and `checkout`: only the B/checkout document is returned.
3. Repeat for both tenants with `payments`: only the matching tenant/service
   document is returned.
4. Add a severity filter and confirm it excludes nonmatching documents.
5. Confirm the out-of-window document is excluded.
6. With a missing/invalid API key, a malformed tenant UUID, and a tenant
   **not authorized for the principal**, verify requests are rejected before
   querying OpenSearch. The last case requires the real gateway/authorization
   layer; the prototype internal key alone cannot enforce it.
7. Disable OpenSearch and confirm fail-closed HTTP 503 without a backend call.
8. Simulate timeout/unavailable backend and confirm sanitized HTTP 502,
   no leaked credentials, and `Cache-Control: no-store`.
9. Verify index aliases, wildcard expansion, hidden indices and role
   permissions cannot expose other tenants. Check DLS/FLS or equivalent
   backend enforcement independently of GAMMA's query filter.
10. Record OpenSearch version, mappings, effective role, fixture IDs,
    requests, redacted responses, test timestamps and reviewer sign-off.

## Release gate

Do **not** enable `ENABLE_OPENSEARCH` in a shared or production environment
until all checks pass, backend-enforced tenant isolation is demonstrated,
and gateway tenant authorization is verified. Query-DSL tests alone are
insufficient; a forged or overprivileged service account can bypass an
application-level tenant filter.

## Automated coverage

- `tests/test_opensearch_tenant_contract.py`: deterministic query-builder
  matrix; no network, mapping, role, or DLS verification.
- `tests/test_observability_readonly_http.py`: authenticated FastAPI route
  with mocked backend; no real OpenSearch or gateway verification.

## Validation snapshot — 2026-11-10

- Local partial laboratory: `python -m pytest -q` completed with **54 passed**
  in 1.63 s. This laboratory is a subset of the repository and must **not**
  be described as the complete PR test suite.
- GitHub PR branch head `dc7f965fd2b8a53ff407e3a258717ac449407e45`:
  `Python checks` and `Deployment contract (static + runtime smoke)`
  are reported as **failure** by GitHub Actions. Their test outcome is
  **unqualified** until actionable job logs or a reproducible runner are
  available; the summary alone does not prove a Python assertion failure.
- No real OpenSearch cluster, role/DLS, mappings, or gateway authorization
  was exercised by the local laboratory. Production enablement remains blocked.
