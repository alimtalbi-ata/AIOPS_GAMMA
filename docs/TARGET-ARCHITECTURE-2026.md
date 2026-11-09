# AIOPS_GAMMA — Architecture cible AI SRE / ITIL 4 (2026)

**Statut : PLAN CIBLE / ADR proposé, non déployé.** Basé sur l'inspection des arbres et de documents des dépôts GitHub accessibles au compte le 2026-11-09. Ne confondre ni présence de code, ni promesses des README, avec qualification de sécurité, intégration, performances ou licences. Voir [inventaire de réutilisation](REUSE-COMPONENT-INVENTORY.md).

## 1. Décision d'architecture

**AIOPS_GAMMA = console fédératrice + BFF d'observabilité et d'investigation.** Ne pas reconstruire un deuxième système de gestion des incidents, un deuxième orchestrateur de remédiation ni un deuxième moteur de stockage des logs. Le dépôt `aiops` reste propriétaire des incidents/runs, Policy, Evidence, Twin, Temporal/Worker et intégration ITSM. `observability-stack` reste propriétaire de la collecte et du stockage des métriques, logs et traces. Les moteurs IA et LLM restent des services spécialisés **subordonnés** à la gouvernance centrale.

### Vue logique

```text
[Opérateurs NOC / SRE / ITSM / sécurité]
                 |
          [SSO/OIDC + RBAC]
                 |
      [GAMMA React / BFF FastAPI] ------ [Audit, configuration, tenant scope]
        |          |          |
        |          |          +--> [KPI API: normalisation, qualité, fenêtres, SLO]
        |          |                        |               |
        |          |                 [Sentinel LLM]    [ArgusLM]
        |          |
        |          +--> [Investigation Workbench / read-only tool gateway]
        |                     |            |           |
        |                  [Evidence]  [HolmesGPT / Aurora] [Code search/RAG]
        |                     |            |
        |                     +-- [Critic, source attestations, RCA review]
        |
        +--> [Canonical Core: aiops] <-- [Correlation/normalisation]
                       |                         ^
                       |                         |
             [Temporal / Worker]        [Alertmanager / Sentinel / webhooks]
                       |                         ^
                 [Policy + HITL]                 |
                       |                [OTel Collector / Data Prepper]
            [Approved runbook only]              |
                       |                [Services / infra / LLM telemetry]
                 [Verify / audit]                |
                       |                         v
             [GLPI / CMDB / ITSM]      [OpenSearch + Cortex/Prometheus]
                       |
                [Reconciliation]
```

Les flèches représentent des **contrats à qualifier** ; pas des intégrations actuellement opérationnelles. En particulier, **GAMMA n'appelle jamais directement un exécuteur LIVE** et aucun moteur IA ne détient de droit implicite de mutation.

## 2. Domaines et responsabilités

| Domaine | Autorité / service recommandé | Données et contrat |
| --- | --- | --- |
| Présentation / BFF | `AIOPS_GAMMA` | Vue par tenant, fenêtre, statut de source, preuves et actions permises |
| Identité / sécurité | Gateway d'entreprise + Policy de `aiops` | OIDC, actor/tenant/roles signés, séparation des permissions, egress |
| Ingestion / observabilité | `observability-stack` | OTLP → Data Prepper/OpenSearch ; Cortex/PromQL ; Alertmanager |
| Normalisation / corrélation | `aiops` + fonctions pures GAMMA | événements dédupliqués, source IDs, fenêtres, topologie, faux regroupements |
| Incident / Run | **`aiops` Core, writer unique** | incident ID, version, état, sévérité, owner, ITSM ref, idempotence |
| Evidence / RCA | `aiops` Evidence + enquêteur choisi | références attestées, contradicteurs, critic, UNKNOWN |
| Investigation IA | HolmesGPT **ou** Aurora **ou** IncidentFox en pilote, pas les trois en parallèle | appels read-only allowlist, budgets, citations, résultats évalués |
| Topologie / impact | `aiops` Twin/Simulator | CI, dépendances observées/inférées, fraîcheur, blast radius |
| LLM anomalies | `sentinel-llm` | anomalies, compteurs, dérive, alertes, Prometheus |
| LLM performance | `arguslm-llm` | uptime, TTFT, TPS, latence, tokens, coûts estimés |
| Gouvernance exécution | **`aiops` Policy → Temporal/Worker** | autorisation indépendante, HITL, idempotence, rollback et vérification |
| ITSM / CMDB | GLPI + intégration existante `aiops` | tickets et CIs autoritatifs, lecture avant écriture, reconciliation |

## 3. Contrats transversaux non négociables

- **Tenant/actor/asset** : identité dérivée d'une gateway authentifiée, jamais d'un simple header navigateur. Autoriser tenant + environnement + service + modèle + CI par source.
- **EventEnvelope v1** : `event_id`, `tenant_id`, `source`, `external_event_id`, `observed_at`, `ingested_at`, `service_id`, `ci_id?`, `severity`, `fingerprint`, `evidence_refs[]`, `schema_version`; déduplication par `(tenant,source,external_event_id)`.
- **EvidenceRef v1** : `tenant_id`, `incident_id`, `source`, `source_record_id`, `observed_at`, `retrieved_at`, `source_version`, `integrity_digest?`, `redaction_policy`, `freshness`; ne pas confondre référence locale et preuve attestée.
- **InvestigationRun v1** : `run_id`, `canonical_incident_id`, `tenant_id`, `stage`, `tool_receipts[]`, `hypotheses[]`, `critic_verdict`, `unknowns[]`, `human_review`, `cost_estimate`, `created_at`, `version`. Enregistrement append-only et budget de temps/tokens/outils.
- **KpiFact v1** : `tenant_id`, `service_id`, `model_id?`, `source`, `metric_name`, `value`, `unit`, `window_start/end`, `sample_count`, `coverage`, `watermark`, `quality_flags`, `estimated`, `schema_version`; `null` pour absent, pas de zéro fictif.
- **ActionProposal v1** : `runbook_id/version`, `target_asset`, `preconditions`, `risk`, `dry_run`, `rollback_plan`, `policy_decision`, `HITL_receipt`; une recommandation IA **n'est pas** une permission d'exécuter.
- **ITSM** : le GLPI et le Core existants gardent l'autorité sur les tickets et les CIs. Écriture uniquement par adapter canonique, après contrat/idempotence/validation staging.

## 4. Flux opérationnels

**Flux A — détection → incident.** OTel/Alertmanager/Sentinel → réception authentifiée → normalisation + déduplication → corrélation temporelle/topologique → Core incident existant → GAMMA affiche l'impact et la provenance. L'échec d'OpenSearch ne doit pas empêcher le Core de traiter les incidents.

**Flux B — investigation.** Core incident → plan d'enquête borné → outils lecture seule tenant-scopés (logs, traces, métriques, changements, code exact, KB/RAG) → références de preuves → hypothèses concurrentes + contradicteurs → critic → revue humaine → RCA ou UNKNOWN → brouillon de postmortem. Un agent ne reçoit pas d'accès shell arbitraire.

**Flux C — KPI.** Sentinel/ArgusLM → adaptateurs serveurs read-only → normalisation d'unités, prix estimé et horodatage → facts avec source/fraîcheur/couverture → fenêtres/SLO qualifiés → Command Center. Les compteurs cumulés nécessitent delta, reset et alignement des périodes. Ne pas mélanger coût facturé et coût estimé.

**Flux D — remédiation future.** Hypothèse revue → proposition de runbook → Policy indépendant → HITL si requis → Core/Temporal/Worker → vérification SLI → rollback si qualifié → réconciliation GLPI et audit. **Non autorisé dans GAMMA aujourd'hui.**

## 5. Architecture de déploiement cible

- **Zone UI** : React derrière reverse proxy, CSP stricte, SSO; aucun secret de provider ni accès direct à Prometheus/GLPI depuis le navigateur.
- **Zone API** : BFF GAMMA FastAPI, authentification/autorisation côté serveur, rate limits, requêtes bornées, egress allowlist et mTLS vers services internes.
- **Zone data** : OpenSearch, Cortex/Prometheus, Postgres de projection GAMMA (uniquement cache/mesures et non l'état canonique Core), conservation et purge par tenant.
- **Zone investigation** : worker isolé avec outil read-only allowlist, réseau limité, budget, traces d'outils et aucun privilège Kubernetes mutateur.
- **Zone exécution** : Core/Policy/Temporal/Worker séparés physiquement/logiquement ; pas de chemin direct depuis l'agent ou le BFF.
- **Zone intégration** : GLPI/CMDB, providers LLM, connecteurs externes derrière secrets manager et sorties réseau approuvées.

## 6. Roadmap d'implémentation et portes de validation

| Ordre | Livrable | Critère d'acceptation |
| --- | --- | --- |
| P0 | Inventaire + ADR + ownership | composants et licences qualifiés, aucune double autorité |
| P1 | Auth OIDC/tenant/RBAC et contrats versionnés | tests inter-tenant, deny-by-default, secrets et egress |
| P2 | Telemetry + Sentinel/ArgusLM read-only | données staging réelles, timestamps, units, provenance, quotas |
| P3 | Incident correlation + GLPI staging | tests doublons, faux merges, CMDB stale, tickets non modifiés |
| P4 | Investigation agent shadow mode | 1 service, 1 source, 0 write, citations vérifiées, critic et UNKNOWN |
| P5 | KPI/SLO et UX complète | MTTA/MTTR définis par timestamps canoniques, RCA accuracy revue, échantillons/fraîcheur affichés |
| P6 | Runbook/HITL/exécution qualifiée | approbation indépendante, fencing, rollback, audit et exercice de reprise |

**Décisions ouvertes** : sélectionner **un seul** moteur d'investigation primaire (HolmesGPT, Aurora, IncidentFox ou Akmatori), modèle d'auth inter-services, stockage des facts KPI, licence des modules à redistribuer, topologie réseau et budgets SLO. Les tests CI unitaires ne remplacent pas la qualification staging.

## 7. État réel au 2026-11-09

GAMMA a une UI React de démonstration, une API FastAPI, des prévisualisations de corrélation, ITIL, remédiation, KPI LLM et investigation, un adaptateur GLPI read-only désactivé par défaut et une intégration OpenSearch optionnelle. Les prévisualisations utilisent des données fournies par l'appelant et ne constituent pas une collecte/attestation live. Pas de SSO/RBAC production qualifié, pas d'exécution autonome, pas de KPI d'efficacité AI SRE mesuré en production.
