# Gamma Unified — release handoff (qualification only)

Decision: GO development; HOLD integration and Outbox; NO_GO LIVE.
Foundation evidence SHA: `c79c7d8bbee94d96844dd516a2e086ee8681302b` (PR #1).
Integrated candidate: `59f3627e379084a3dd1a4c25d9f61065b0b87531` (draft PR #12).
Comparison: diverged; Foundation ahead 82, behind 118; common ancestor `9c46b0dc626b3f29aee87cb73f3c869dac94eec6`. Counts are historical, not a merge recommendation.

## Transfer manifest

Review and port the following paths as a coordinated unit, preserving integrated UI/UX and unrelated changes. Do not replace the whole branch.
| Path | Foundation blob | Integrated blob | Action |
| --- | --- | --- | --- |
| postgres/preflight/01-app-role.sql | 667f95cab84a4601a1df114697eb22e4d370e024 | 667f95cab84a4601a1df114697eb22e4d370e024 | Identical; retain |
| postgres/preflight/02-schema-security.sql | 83f94ac6df416e1ea3b40bcfcf75914b986631cf | 007ba904c72d35f60cc70a5710a6f00bee8761f9 | Port role, identity, ACL, predicates and provisioning HOLD controls |
| .github/workflows/postgres-preflight.yml | 638e53c4a6bae95e5af806b2a7022cec0be346be | 451a11dd3510659a086631e6c268d8801775e573 | Port matching negative tests and Compose dependency contract |
| docker-compose.yml | ea033a602a1175bbc4e9b507d455c00a5a930631 | 088f2e29ac75d0a42709cf31c450a5ac3f8b2f27 | TCP readiness and post-migration gate for API and disabled relay |
| deploy/scripts/audit-rootless-compose.sh | b015d1a90609b4b4441a43995345d40d38aa4f8f | 68a224c86fc63171f7015dc3fb65b13f2990e460 | Exact read-only schema audit bind and successful one-shot handling |
| .github/workflows/deployment-contract.yml | 2bd40e56f69b11262f20863707b1b65af15a8242 | 917f0274121ced43a82626e4e5aab2a430f75175 | Review differences; no wholesale replacement |

## Foundation evidence (same SHA)
- Python checks: https://github.com/alimtalbi-ata/AIOPS_GAMMA/actions/runs/44392891573
- PostgreSQL RLS: https://github.com/alimtalbi-ata/AIOPS_GAMMA/actions/runs/44392891494
- PostgreSQL preflight: https://github.com/alimtalbi-ata/AIOPS_GAMMA/actions/runs/44392891526
- Deployment: https://github.com/alimtalbi-ata/AIOPS_GAMMA/actions/runs/44392891448
- Shadow RCA: https://github.com/alimtalbi-ata/AIOPS_GAMMA/actions/runs/44392891510

All five completed successfully. These results do not qualify a future integrated SHA.

## Acceptance gates
- [ ] Agree on integration owner and exact candidate SHA; no automatic merge/rebase.
- [ ] Port and review manifest; preserve Gateway multi-key and tenant isolation.
- [ ] Execute all integrated CI including real PostgreSQL replay, RLS, schema drift and Shadow RCA.
- [ ] Verify startup failure on schema audit failure using disposable Compose environment; existing CI checks dependency declaration and audit container separately.
- [ ] Review Helm parity, rootless runtime compliance and backup/restore (full restore not qualified).
- [ ] Verify UI accessibility, synthetic provenance, Sentinel/ArgusLM contracts and human review.
- [ ] Keep canonical upstream reads blocked pending actor/tenant/resource ACL evidence (issue #2).
- [ ] Keep relay disabled; worker membership provisioning rejected; individual worker identity qualification unresolved.
- [ ] Review release evidence on one SHA before explicit approval. No LIVE.

Limitations: PostgreSQL 16 pinned expressions, startup audit not continuous monitoring, incomplete global ACL coverage, strict rootless qualification outstanding. No production execution or secrets. Handoff is a proposal, not an integration authorization.
