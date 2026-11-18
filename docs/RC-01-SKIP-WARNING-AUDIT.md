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
