# SRE and AI DevOps reference catalog — candidate selection for Gamma

**Source snapshot:** 2026-11-09, static read of the **READMEs**, not of linked third-party skill implementations.
- [awesome-sre-skills](https://github.com/alimtalbi-ata/awesome-sre-skills), tree `962f6a2149d0688a8c32d9e12948c5102cc9d184`. This is a curated **link directory**, not an installed skill bundle.
- [awesome-devops-ai](https://github.com/alimtalbi-ata/awesome-devops-ai), README. This is a catalog of AI/DevOps products, agents, MCPs and practices, **not** code integrated into Gamma.
Links, capabilities, prices, licenses and maintenance can change. All references below are *candidates*, not approved, installed or production qualified.

## Engineering selection (value versus integration risk)

| Priority | Listed reference | What to learn or evaluate | Gamma deliverable / acceptance | Caveat |
|---|---|---|---|---|
| P0 | [OpenSearch Agent Skills](https://github.com/opensearch-project/opensearch-agent-skills) | PPL-based log/trace investigation | Typed, read-only, bounded OpenSearch tool contracts and provenance | Inspect upstream skills/permissions and test index mappings and DLS |
| P0 | [OpenTelemetry Agent Skills](https://github.com/ollygarden/opentelemetry-agent-skills/tree/main/skills), [OpenTelemetry Skill](https://github.com/o11y-dev/opentelemetry-skill/blob/main/SKILL.md) | Instrumentation, Collector, OTTL, sampling, cardinality and missing-signal diagnosis | OTel/Data Prepper contracts tested against `observability-stack`; valid service/CI links and signal freshness | Validate against actually deployed versions |
| P0 | [SLO Architect](https://github.com/alirezarezvani/claude-skills/tree/main/engineering/skills/slo-architect), [SRE Practice Skills](https://github.com/paulip114/sre-practice-skills) | SLIs, SLOs, error budgets, burn-rate alerts | Explicit objective/error-budget contracts, alert thresholds and incident triage tests | Reference methodology, not an SLO implementation |
| P1 | [Incident Response (Anthropic)](https://github.com/anthropics/knowledge-work-plugins/tree/main/engineering/skills/incident-response), [Incident Commander](https://github.com/borghei/Claude-Skills/blob/main/engineering/incident-commander/SKILL.md) | SEV triage, event timeline, blameless postmortems | Evidence-backed incident timeline, ITSM correlation, handover and postmortem templates | Must be bound to Core incident authority |
| P1 | [Grafana Skills](https://github.com/grafana/skills), [Prometheus Skill](https://github.com/julianobarbosa/claude-code-skills/tree/main/skills/prometheus) | PromQL/SLO investigation and on-call triage | Tenant-safe **constructed** Cortex queries; 501 until isolation qualified | No raw model-supplied PromQL or arbitrary endpoints |
| P1 | [K8sGPT](https://github.com/k8sgpt-ai/k8sgpt), [Robusta](https://github.com/robusta-dev/robusta) | Kubernetes diagnosis, failure signals, RCA validation | Optional read-only diagnostic provider with evidence schema, shadow evaluations | Do not grant kubectl mutations from an LLM |
| P2 | [Chaos Engineering](https://github.com/borghei/Claude-Skills/blob/main/engineering/chaos-engineering/SKILL.md) | Hypothesis-driven fault injection and blast-radius limits | Synthetic/replay fault matrix and recovery verification | Isolated simulator only, not LIVE |
| P2 | [Trivy](https://github.com/aquasecurity/trivy), [Argo CD](https://github.com/argoproj/argo-cd) from awesome-devops-ai | Supply-chain hygiene and GitOps auditability | CI security checks and immutable infra-change provenance | Selection only; not automatically installed |
| P2 | MCP and agent-framework sections of awesome-devops-ai | Tool discovery and typed capabilities | Restricted read-only tool gateway, audit and bounded permissions | Broad MCP catalogs are a **security exposure**, not automatically trusted |
| P2 | Agent governance / policy and sandbox references in awesome-devops-ai | Independent policy, sandboxing and action review | Policy/HITL, runbook allowlist, replay-proof receipts, low-risk gates | Existing `aiops` Policy/Temporal remain canonical |

## Explicit exclusions

- **No automatic execution of downloaded skills or scripts.** The awesome-sre-skills README expressly warns that skills can execute code and must be audited before installing. The registry is a discovery tool, not an approval authority.
- **No blanket MCP access to production** or cloud admin credentials. Restrict each tool to a read-only and tenant-specific capability until independently qualified.
- **No second observability backend** (e.g. another APM/metrics database) without a documented gap; `observability-stack` already owns telemetry.
- **No parallel Core, ITSM, Temporal or Policy control plane**; rely on `aiops` authoritative services.
- **No auto-execution of remediation** from AI output, confidence score, unsigned skill manifest, synthetic alert or on-call instruction.

## Candidate qualification checklist

1. Pin exact source revision/commit and upstream license before reusing code.
2. Read full skill instructions and all referenced scripts, dependencies, network endpoints and permissions; identify prompt-injection and exfiltration paths.
3. Define bounded read-only input/output schemas, tenant ACL, rate limits, timeouts, redirects, maximum response bytes and data redaction.
4. Map results to Gamma's canonical evidence references with timestamps, freshness and source trust; permit UNKNOWN.
5. Unit-test malformed, stale and hostile inputs; replay integration tests in an isolated simulator.
6. Add benchmark baseline and expected outcomes; require maintainer review before rollout.
7. Add documentation, PR/issue link, rollback and handover evidence.
8. Do not promote autonomous LIVE actions without independent Core/Policy/HITL/Temporal qualification.

## Recommendation and follow-up

**Do next:** OpenSearch/OTel safe tool adapter contracts and SLO/error-budget evaluation as **read-only** components; prioritize tenant ACL first (#2), telemetry (#3), incident/ITSM (#4), RCA (#5) and Policy (#6). The external catalogs are research inputs, not a fourth or fifth runtime platform.

Current evidence supports only the catalog descriptions in the two user-supplied READMEs. It does **not** verify individual vendor implementations, license terms or operational safety.
