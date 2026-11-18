# RC-01 — Skip and warning audit (UX15.42.2)
2026-11-18. HOLD / NO_GO LIVE. Candidate 59f3627e379084a3dd1a4c25d9f61065b0b87531 remains unchanged.
Original evidence: https://github.com/alimtalbi-ata/AIOPS_GAMMA/actions/runs/44373935789/job/135047892192
2481 passed, 15 skipped, 12 warnings, 8 subtests passed.
## Warning classification (12/12)
| Test node suffix (under tests/) | Warning |
|---|---|
| test_correlation.py::test_direct_correlation_revalidates_mutated_evidence_reference_types | evidence_refs integer 42 |
| test_itil_contract_boundaries.py::test_preview_does_not_trust_nonboolean_cmdb_verification[false] | boolean string |
| test_itil_mutable_boundary.py::test_mutated_ci_verification_flag_must_be_literal_boolean[false] | boolean string |
| test_itil_contract_boundaries.py::test_preview_does_not_trust_nonboolean_cmdb_verification[true] | boolean string |
| test_itil_mutable_boundary.py::test_mutated_ci_verification_flag_must_be_literal_boolean[true] | boolean string |
| test_itil_mutable_boundary.py::test_model_copy_update_cannot_bypass_ci_verification_boolean_validation | boolean string |
| test_itil_contract_boundaries.py::test_preview_does_not_trust_nonboolean_cmdb_verification[1] | boolean integer |
| test_itil_mutable_boundary.py::test_mutated_ci_verification_flag_must_be_literal_boolean[1] | boolean integer |
| test_itil_contract_boundaries.py::test_preview_does_not_crash_on_unvalidated_nonstring_cmdb_id | cmdb_ci_id integer |
| test_itil_mutable_boundary.py::test_mutated_ci_verification_flag_must_be_literal_boolean[0] | boolean integer |
| test_synthetic_runbook_hitl_usecase.py::test_mutated_non_boolean_approval_flag_rejected | recipe_approved list |
| fastapi/testclient.py:1 | StarletteDeprecationWarning HTTPX integration |
Eleven Pydantic serializer warnings originate from negative regression tests; retain them. One dependency deprecation requires compatibility review, no automatic upgrade. Separate Node runner warnings are not counted in pytest's twelve.
## Skip evidence pending
Original run lacks -rs and JUnit artifact; exact 15 node IDs not established. Diagnostic branch qualify/gamma-rc01-59f3627 commit 1477d482fcb6b516e9740915ea76d77a5e805232 changes only CI reporting, retaining original exclusions and test scope. Run https://github.com/alimtalbi-ata/AIOPS_GAMMA/actions/runs/44390727084 was queued at observation. Collect JUnit skipped cases, reasons, logs, SHA, Python version and dependency inventory; compare counts and map dedicated PostgreSQL coverage. Artifact retention 14 days. New run is a reproduction, not retroactive proof of original exact skips. Dependencies are not pinned by this change.
RC-01 remains OPEN until actual results and individual coverage/risk decisions are reviewed. No merge, deployment or LIVE authorization.

## UX15.42.2-B — reproduced skip inventory and coverage
Diagnostic run 44390727084: 2481 passed, 15 skipped, 12 warnings, 8 subtests passed. All 5 Python jobs, 6 deployment jobs and 1 role preflight job succeeded (12 observed jobs; no new RLS qualification claimed).
Artifact 14469330317: https://github.com/alimtalbi-ata/AIOPS_GAMMA/actions/runs/44390727084/artifacts/14469330317
Downloaded ZIP SHA256 verified against GitHub: 148f61243a1f945cfa8bb3da9849cffb77813ea1bc83d6ae1ffe740a2fa61faf. All five files present, sha.txt matches 1477d482fcb6b516e9740915ea76d77a5e805232. Parsed JUnit exact skipped nodes below (prefix tests/).
| Node | Skip reason | Coverage on original candidate |
|---|---|---|
| test_gateway_cross_key_replay.py::test_concurrent_cross_key_replay | Disposable database required | RLS suite |
| test_gateway_replay.py::test_replay_reservation_is_atomic_across_independent_postgres_sessions | GAMMA_TEST_DATABASE_URL not configured; disposable PostgreSQL required | Related concurrent reservation test in dedicated replay suite; exact node not run |
| test_gateway_replay.py::test_postgres_cleanup_preserves_live_rows_and_respects_batch_limit | same | gap: exact cleanup behavior not demonstrated by dedicated suite |
| test_gateway_replay.py::test_two_postgres_cleanup_workers_race_with_fresh_gateway_authentication | same | gap: cleanup/auth race not demonstrated |
| test_opensearch_staging_readonly.py::test_real_opensearch_tenant_and_service_isolation | Explicit staging opt-in required | staging HOLD |
| test_outbox_role_preflight.py::test_worker_privilege_preflight[GAMMA_WORKER_A_DSN] | Disposable database required | RLS suite |
| test_outbox_role_preflight.py::test_worker_privilege_preflight[GAMMA_WORKER_B_DSN] | Disposable database required | RLS suite |
| test_outbox_transaction_model.py::test_delivery_rollback_then_replay | Disposable PostgreSQL required | RLS suite |
| test_outbox_worker_postgres.py::test_worker_identity_and_concurrent_claims | Disposable database required | RLS suite |
| test_rls_all_tables.py::test_rls_crud_isolation[InboxEvent] | Explicit disposable PostgreSQL opt-in required | RLS suite |
| test_rls_all_tables.py::test_rls_crud_isolation[OutboxEvent] | same | RLS suite |
| test_rls_all_tables.py::test_rls_crud_isolation[ServiceBinding] | same | RLS suite |
| test_rls_all_tables.py::test_rls_crud_isolation[Evidence] | same | RLS suite |
| test_tenant_isolation.py::test_postgres_rls_denies_cross_tenant_reads_and_writes | GAMMA_TEST_DATABASE_URL must point to restricted gamma_app role | RLS suite |
| test_tenant_session_context.py::test_context_rebound_and_pool_clean | Disposable database required | RLS suite |

RLS job 135047892657 on 59f3627 explicitly selects the seven relevant files and reports 60 passed, no skips. Thus 11 cases have direct suite evidence. Replay job 135047892174 selects only test_gateway_replay_postgres.py (19 passed), including concurrent reservations; not the three exact skipped nodes in test_gateway_replay.py. One related coverage case, two gaps, one staging HOLD. Do not equate related coverage with exact execution. Next: qualify three exact replay nodes with existing disposable DB restrictions on an isolated branch; obtain approved staging evidence separately. Original 15 skips have matching reproduced count but no original JUnit; no retroactive claim. RC-01 remains OPEN. Candidate PR #12 rechecked unchanged, draft, not merged. No deployment or LIVE.

## UX15.42.2-C — exact replay qualification configured
Qualification SHA b213fa9f5292d9421a8181bce10210261ea037c0 on qualify/gamma-rc01-59f3627 adds only 78 lines to ci.yml. Dedicated job rc01-replay-cleanup-postgres uses fresh PG16 on actual loopback, separate bootstrap admin and gamma_app without superuser/BYPASSRLS/CREATEDB/CREATEROLE, full 0006 head, verifies server/database/role/revision, empty replay table and four forced-RLS tables before running the three exact skipped nodes. JUnit must contain exactly three non-skipped, non-failing cases. Artifact rc01-replay-evidence, 14-day retention; container removal always attempted. No application/test/migration changes. Run https://github.com/alimtalbi-ata/AIOPS_GAMMA/actions/runs/44392047552 ; deployment 44392047452, preflight 44392047477. Job status at observation: [{"id":135112004833,"status":"in_progress","conclusion":null}]. No PASS claimed before log and artifact review. Candidate PR #12 verified unchanged, draft, unmerged. RC-01 remains OPEN; OpenSearch staging HOLD. No merge/deploy/LIVE.

## UX15.42.2-D — actual restricted-role failure
Diagnostic SHA b213fa9f5292d9421a8181bce10210261ea037c0: 12/13 observed jobs passed (Python 5/6, deployment 6/6, preflight 1/1). Dedicated job 135112004833 failed. Full migration and prerequisite checks passed. Exact JUnit: atomic reservation PASS, bounded cleanup FAIL, concurrent cleanup/auth FAIL; zero skips. Artifact 14469711188 downloaded and XML parsed, SHA256 89884cbab30d9f9b5f103e4220125c515dd023247a2e5be8bd438527425a9488 matches GitHub. Container removal confirmed. Evidence https://github.com/alimtalbi-ata/AIOPS_GAMMA/actions/runs/44392047552/job/135112004833 .
Both failures occur in app/gateway_replay.py purge_expired_assertions SQL SELECT FOR UPDATE SKIP LOCKED with insufficient privilege on gateway_assertion_replay. Migration 0003 grants gamma_app SELECT, INSERT, DELETE but not UPDATE; PostgreSQL row locking requires UPDATE privilege on at least one column. This is a likely confirmed-by-code explanation, not a tested repair. Do not grant unrestricted UPDATE to gamma_app, run as owner, or remove locking to pass. Review dedicated least-privilege maintenance role and explicit negative mutation/tenant access tests with Foundation before changing ACL or SQL. Atomicity adds one direct case: 12/15 across original and diagnostic SHAs, 2 failed cleanup cases, 1 staging HOLD. RC-01 OPEN; no single-SHA full qualification claimed. PR #12 remains draft, unmerged, head 59f3627. No application changes, merge or deployment.
