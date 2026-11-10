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

## Opt-in read-only staging execution

The optional `tests/test_opensearch_staging_readonly.py` uses the production
query builder and actual async OpenSearch client. It **does not seed or delete**
data. Provision the five synthetic documents described above using a separate
staging fixture procedure, then configure the service account with the same
effective role intended for GAMMA. The marker must appear in the seeded
`_source` documents. Do not use production credentials or production indices.

Example (values are illustrative; replace with actual staging fixtures):

```sh
export GAMMA_OPENSEARCH_STAGING_TEST=1
export ENABLE_OPENSEARCH=true
export OPENSEARCH_URL=https://staging-search.example.invalid:9200
export OPENSEARCH_USERNAME=gamma-staging-readonly
export OPENSEARCH_PASSWORD='from-secure-secret-store'
export OPENSEARCH_VERIFY_CERTS=true
export OPENSEARCH_CA_CERTS=/path/to/staging-ca.pem
export OPENSEARCH_LOGS_INDEX='staging-gamma-fixtures'
export GAMMA_STAGING_TENANT_A=11111111-1111-4111-8111-111111111111
export GAMMA_STAGING_TENANT_B=22222222-2222-4222-8222-222222222222
export GAMMA_STAGING_SERVICE_A=checkout
export GAMMA_STAGING_SERVICE_B=payments
export GAMMA_STAGING_WINDOW_START=2026-11-10T11:00:00+00:00
export GAMMA_STAGING_WINDOW_END=2026-11-10T12:00:00+00:00
export GAMMA_STAGING_FIXTURE_MARKER=gamma-staging-run-unique-001
python -m pytest -q tests/test_opensearch_staging_readonly.py
```

The staging test now requires one explicit index name (no wildcard or comma-separated aliases), canonical non-nil tenant UUIDs, and fixture-compatible service names and marker. The test fails if a tenant/service combination has no marked fixture, if
returned hits include another tenant or service, or if required HTTPS/TLS
and authenticated service-account settings are absent. The result does
**not** establish DLS enforcement by itself: separately test role privileges,
forged gateway identity, index aliases and wildcard expansion, and record
redacted evidence before approving the release gate. In ordinary CI this
test is skipped.

## Generate staging fixtures offline

A deterministic generator emits five synthetic documents as OpenSearch Bulk
NDJSON (two lines per document) **to standard output only**. It never opens
a connection, creates an index, or imports anything.

```sh
python deploy/scripts/generate-opensearch-staging-fixtures.py \
  --tenant-a 11111111-1111-4111-8111-111111111111 \
  --tenant-b 22222222-2222-4222-8222-222222222222 \
  --service-a checkout --service-b payments \
  --marker gamma-staging-run-unique-001 \
  --index staging-gamma-fixtures \
  --at 2026-11-10T11:30:00+00:00 > /tmp/gamma-staging-fixtures.ndjson
```

A staging operator must first review the NDJSON and confirm the target index
has the required keyword/date mappings. Import and cleanup are intentionally
outside this script, require separate authorization, and must never target
production. The fifth document is timestamped two days before the other four
and should fall outside the example test window. The test window must contain
the first four documents and exclude the fifth. The generator's output is
covered by `tests/test_opensearch_staging_fixtures.py`.

## Staging test interpretation

The automated staging check requires **exactly one** document bearing
`gamma_fixture_marker` for each tenant/service pair in the selected time
window, with expected `ERROR` for the first service and `WARN` for the
second. It also runs a mismatched severity search, checks that the
generator's fifth, out-of-window fixture is absent from the normal window,
and uses a separate narrow read-only query to **confirm that fixture exists**
at its expected timestamp. A missing positive control fails qualification.

Use a fresh marker and a clean disposable index per run. If a tenant/service, severity or time query returns **500 hits**, the test
fails as **inconclusive**: the configured result cap may hide relevant
fixtures or cross-tenant data. Use a clean disposable index with fewer than
500 matching documents per query; do not raise the production search limit
or interpret a saturated result set as evidence of isolation. Do not treat
passing this application-filter test as proof of OpenSearch DLS, gateway
authorization or index-role isolation. Those checks remain separate release
gates.
