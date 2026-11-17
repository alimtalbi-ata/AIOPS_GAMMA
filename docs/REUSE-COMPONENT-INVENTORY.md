# Inventaire de réutilisation des dépôts GitHub — AIOPS_GAMMA

**Inspection : 2026-11-09.** Périmètre : 20 dépôts accessibles sous `alimtalbi-ata`; examen des arbres de 10 dépôts techniques prioritaires et de leurs documents de référence. Ce document identifie des **candidats** et des fichiers effectivement repérés, pas une certification de leur fonctionnement, compatibilité, provenance juridique ou sécurité. Vérifier la licence et le commit exact de chaque module avant copie/vendorisation.

## Matrice de composants réutilisables

| Priorité | Dépôt | Composants/fichiers repérés | Stratégie | Conditions / risques |
| --- | --- | --- | --- | --- |
| **P0** | [aiops](https://github.com/alimtalbi-ata/aiops) | `app/core/main.py`, `app/policy/main.py`, `app/evidence/main.py`, `app/twin/`, `app/simulator/`, `app/worker/`; `integration/glpi_copilot_bridge.py`; `app/portal/noc_correlation.py`; `app/portal/glpi_operator_view.py` | **Réutiliser par API** comme source d'autorité ; fonctions pures en adaptateurs versionnés | Ne pas créer un second Core/Policy/ITSM writer ; auth tenant et receipts à qualifier |
| **P0** | [observability-stack](https://github.com/alimtalbi-ata/observability-stack) | `charts/observability-stack/`, `charts/observability-stack/templates/otel-collector-configmap.yaml`, `.../cortex-configmap.yaml`, `.../init-dashboards-job.yaml`, `.../files/saved-queries-metrics.yaml`, `.../files/saved-queries-traces.yaml` | **Déployer séparément / interroger** OpenSearch + Cortex/Prometheus | TLS, tenant isolation, index mappings, métriques réelles, quotas, cardinalité |
| **P1** | [sentinel-llm](https://github.com/alimtalbi-ata/sentinel-llm) | `crates/sentinel-core/src/metrics.rs`, `crates/sentinel-api/src/handlers/metrics.rs`, `crates/sentinel-detection/src/agents/anomaly_detection.rs`, `.../incident_correlation.rs`, `crates/sentinel-alerting/src/deduplication.rs`, `deployments/grafana/dashboards/` | **Connecteur read-only**, métriques/anomalies et panneaux de référence | Corriger alignement fenêtres/compteurs, mapping tenant/modèle, qualité et reset |
| **P1** | [arguslm-llm](https://github.com/alimtalbi-ata/arguslm-llm) | `arguslm/server/core/metrics.py`, `.../uptime.py`, `.../benchmark_engine.py`, `.../alert_evaluator.py`, `arguslm/server/api/monitoring.py`, `.../benchmarks.py`, `frontend/src/pages/DashboardPage.tsx` | **Adaptateur de projection** uptime/TTFT/TPS/coûts ; s'inspirer de l'UX | Ne pas déclencher benchmark depuis la console ; coût estimé non facturé ; API à sécuriser par tenant |
| **P1** | [aurora](https://github.com/alimtalbi-ata/aurora) | `client/src/app/api/artifacts/`, `client/src/app/api/audit-log/route.ts`, `client/src/app/api/chat-sessions/`, flux d'investigation et d'actions | **PoC d'enquêteur**, reprendre idées de RCA/postmortem et audit, pas les actions directes | Peut utiliser des outils shell/cloud : isoler, réduire aux lectures ; coût/licence à vérifier |
| **P1** | [holmesgpt](https://github.com/alimtalbi-ata/holmesgpt) | `docs/data-sources/api-toolsets.md`, `docs/data-sources/builtin-toolsets/`, `.github/workflows/eval-regression.yaml`, `.claude/skills/create-eval/` | **Candidat enquêteur principal**, réutiliser toolsets lecture seule et fixtures d'évaluation | Toolsets pouvant muter ; allowlist et sandbox ; ne pas importer tous les connecteurs |
| **P2** | [akmatori-sre](https://github.com/alimtalbi-ata/akmatori-sre) | `agent-worker/src/agent-runner.ts`, `.../gateway-tools.ts`, `.../tool-output-limit.ts`, `docs/TOOL_ARCHITECTURE.md`, `.claude/rules/tool-authorization.md` | **Réutilisation ciblée** des contrats de tool gateway, budgets et garde-fous | Ne pas connecter `script-executor.ts` à la production GAMMA |
| **P2** | [incidentfox-sre](https://github.com/alimtalbi-ata/incidentfox-sre) | `charts/incidentfox/`, `config_service/`, `ai_pipeline/`, intégrations, pipeline de connaissance | **Benchmark fonctionnel / option alternative** pour RCA et intégrations | Éviter double orchestrateur, double KB et double incident store ; complexité forte |
| **P3** | [floci](https://github.com/alimtalbi-ata/floci) | `charts/floci/`, `compatibility-tests/` (AWS SDK/Terraform) | **Environnement de tests isolé**, seulement si besoins AWS compatibles | Émulation ≠ preuve de comportement AWS réel ; pas sur chemin de production |
| **P3** | [awesome-sre-skills](https://github.com/alimtalbi-ata/awesome-sre-skills) | `README.md` | **Catalogue documentaire** de pratiques et outils | Ne pas installer de skills externes sans revue supply chain |

### Dépôts repérés mais hors périmètre immédiat

`OpenPDF-Studio`, `ODMM-Migration-NAS`, `OpenRemote-Studio`, `OpenVisio`, `StorageScope-Architecte`, `aiops-debian-audit`, `aiops-recovery-data`, `aiops-debian-rebuild-private`, `awesome-devops-ai` : présents dans l'inventaire du compte mais non inspectés en profondeur pour ce plan. Ils peuvent servir à des besoins ultérieurs (reporting, DR, exploitation, catalogue), **sans décision de réutilisation** à ce stade.

## Réutiliser, adapter ou éviter

### Réutiliser en priorité (pas de fork inutile)
1. **Core/Policy/Evidence/Twin/Worker/GLPI de `aiops`** via APIs contractuelles. Réutiliser la gouvernance, pas la dupliquer.
2. **OTel/OpenSearch/Cortex/Alertmanager de `observability-stack`** via déploiement indépendant et requêtes tenant-scopées. Réutiliser dashboards et tests Helm comme point de départ.
3. **Mesures et détection de `sentinel-llm` + `arguslm-llm`** via adaptateurs read-only avec normalisation KPI, sources et qualité.

### Évaluer avant de choisir
- **HolmesGPT** : premier candidat de pilote investigation lecture seule grâce à la surface toolsets/evals repérée. Comparer avec **Aurora** sur mêmes incidents historiques, mêmes permissions, mêmes budgets et scoring humain. **IncidentFox** et **Akmatori** servent de références alternatives, sans déploiement simultané par défaut.
- **Recherche de code** : préférer connecteur Git read-only avec recherche de chemin/symbole/stack trace, commit SHA et ligne ; utiliser RAG pour documents et runbooks, pas comme seule méthode de code search.
- **UI** : GAMMA conserve React/FastAPI ; reprendre des patterns et composants graphiques seulement après vérification de licences et d'API, pas copier des interfaces entières.

### Éviter
- Deux sources d'autorité pour incident/Run, GLPI et politique de remédiation.
- Des agents qui exécutent `kubectl`, scripts ou modifications cloud depuis le BFF.
- Le mélange de tenants dans Prometheus/OpenSearch, et la remontée de prompts bruts dans les KPI.
- La duplication de stores vectoriels, bus, bases incidents ou ordonnanceurs avant preuve du besoin.
- Les chiffres de performances annoncés dans des README comme critères de recette sans benchmark local.

## Tableau d'intégration (premier incrément)

| Interface GAMMA | Source candidate | Sens | Qualification minimale |
| --- | --- | --- | --- |
| `GET canonical incident/run/evidence` | `aiops` Core/Evidence | Lecture | Auth gateway, tenant, version, pagination, timeouts, idempotence |
| `GET logs/traces` | OpenSearch | Lecture | Index/tenant DLS, PPL allowlist, bornes temporelles, redaction |
| `GET metrics` | Cortex/Prometheus | Lecture | PromQL construit serveur, tenant label enforced, cardinalité |
| `GET anomaly metrics` | Sentinel | Lecture | Endpoint fixe, TLS, ACL, reset de compteur, provenance |
| `GET LLM uptime/benchmark results` | ArgusLM | Lecture | Modèle/tenant ACL, GET-only, coût estimé, pas de benchmark déclenché |
| `POST investigation shadow run` | moteur choisi + Evidence | Déclenchement **sans effet externe** | Budget, tool allowlist, citations vérifiées, audit |
| `GET GLPI incident snapshot` | GLPI | Lecture | Flag OFF par défaut, tenant/entity, staging RBAC |
| `POST remediation` | Core/Policy/Worker | **Interdit à ce stade** | Gate L4 séparé, approbation, fencing, rollback |

## Preuves de compatibilité requises avant promotion

- Figer SHA/tag upstream, inventorier dépendances et licences, SCA/SBOM, secrets et vulnérabilités.
- Tests contractuels réels en staging avec jeu de données synthétique multi-tenant ; refus croisé et erreurs de réseau.
- Tests de charge et de dérive des schémas, de latence, de rétention, de cardinalité et de coût.
- Audit des chemins d'écriture : outil IA, navigateur et KPI ne peuvent atteindre les systèmes de mutation.
- Maintenir `AIOPS_GAMMA` en PR draft jusqu'à validation explicite des gates.

Voir [TARGET-ARCHITECTURE-2026](TARGET-ARCHITECTURE-2026.md), [AI-SRE-PLATFORM](AI-SRE-PLATFORM.md) et [ROADMAP](ROADMAP.md).

## Gate supplémentaire de réutilisation : double packaging

Un candidat n'est promu de « réutilisable » à « intégré » qu'après preuve de démarrage **Docker Compose** et **Kubernetes/Helm**, à partir d'une image OCI épinglée, avec healthchecks/probes, secrets, volumes, observabilité, isolation tenant, sécurité réseau et tests de contrat. Pour les composants déjà fournis avec des charts/Compose upstream, préférer les dépendances versionnées à une copie. Un moteur disponible uniquement sous forme de script/CLI doit être enveloppé dans un service/job conteneurisé avec la même API et les mêmes restrictions dans les deux environnements. Voir [DEPLOYMENT-CONTRACT](DEPLOYMENT-CONTRACT.md).
