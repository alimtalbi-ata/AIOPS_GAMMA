# AIOPS_GAMMA

Socle d'intégration AIOps **Python/FastAPI + PostgreSQL + OpenSearch Observability**.

> **Version de paquet 0.2.0 : MVP de développement, pas encore prêt pour la production.** Les moteurs de corrélation, CMDB, RCA et agents IA restent ceux de la plateforme existante : ce dépôt fournit leurs futurs points d'intégration, pas une réimplémentation fictive.

## Démarrage (Docker Compose)

```bash
cp .env.example .env
# Modifier impérativement POSTGRES_PASSWORD et INTERNAL_API_KEY
docker compose up --build -d
curl http://127.0.0.1:8000/api/v1/health/live
# Appliquer les tables de démarrage (nouvelle instance uniquement)
docker compose exec api python -m app.init_db
```

Swagger : http://127.0.0.1:8000/docs. Les endpoints métier nécessitent les en-têtes `X-Internal-Api-Key` et `X-Tenant-Id` (UUID), fournis exclusivement par une passerelle interne de confiance.

### API livrée

- `GET /api/v1/health/live` : santé du processus.
- `POST /api/v1/observability/logs/search` : recherche OpenSearch par tenant et service (feature flag).
- `POST /api/v1/integrations/opensearch/alerts` : ingestion idempotente d'alertes dans inbox + outbox (feature flag).
- `POST /api/v1/topology/bindings` et `GET /api/v1/topology/bindings` : bindings CMDB → service OTel.
- `POST /api/v1/incidents/{incident_id}/evidence`, `GET ...` : preuves RCA persistées.
- `POST /api/v1/observability/metrics/query` : `501` tant qu'un constructeur PromQL isolé par tenant n'est pas implémenté.\n- `POST /api/v1/observability/llm/kpis/preview` : agrégation **non autoritative** d'échantillons LLM fournis par l'appelant (Sentinel / ArgusLM), sans collecte automatique ni persistance.\n- `GET /api/v1/itil4/glpi/incidents/{ticket_id}/snapshot` : lecture GLPI strictement limitée et **désactivée par défaut**, non qualifiée sur staging.\n- `POST /api/v1/itil4/incidents/sync-preview` : proposition ITSM/ITIL 4, sans création de ticket.\n- `POST /api/v1/policy/remediation/preview` : conseil uniquement, sans exécution LIVE.

### OpenSearch

Le profil `observability-demo` démarre **un OpenSearch de démonstration, sans sécurité et non exposé sur l'hôte** :

```bash
docker compose --profile observability-demo up -d opensearch
```

Les fonctionnalités OpenSearch restent **désactivées** tant que `ENABLE_OPENSEARCH=false`. Pour l'APM complet (Collector / Data Prepper / dashboards), utiliser une version figée de [la stack officielle](https://github.com/opensearch-project/observability-stack) : cette version du dépôt ne prétend pas fournir ces pipelines.

### Tests

```bash
python -m pip install -e '.[test]'
python -m pytest -q
```

Voir [architecture et prochaines étapes](docs/ARCHITECTURE.md).

**Sécurité** : ne jamais exposer directement ce backend aux navigateurs ou à Internet. Les entêtes de tenant ne sont sûrs que derrière un gateway qui authentifie, autorise, supprime les entêtes externes et les recrée. Remplacer la clé interne par des identités de service OIDC/mTLS avant production. Ne pas exposer OpenSearch en mode sécurité désactivée.

## Objectif produit : plateforme AI SRE

AIOPS_GAMMA cible la chaîne **détecter → corréler → identifier les assets/impacts → tracer en ITSM → analyser RCA → proposer une remédiation fondée sur un runbook → vérifier Policy/HITL → exécuter par le Core/Temporal existant → vérifier et réconcilier**. Les fonctions opérationnelles autonomes ne sont pas encore qualifiées. Voir [architecture AI SRE](docs/AI-SRE-PLATFORM.md) et [réutilisation des services AIOps existants](docs/SOURCE-REUSE-AIOPS.md).

Une API de **prévisualisation non exécutoire** est ajoutée : `POST /api/v1/policy/remediation/preview` (accès interne, aucune action LIVE).

## Sélection des trois dépôts sources

[Décisions de réutilisation et limites d'intégration](docs/THREE-SOURCE-INTEGRATION.md). Nouveau moteur de **prévisualisation de corrélation** : `POST /api/v1/incidents/correlation/preview`, interne, sans écriture ITSM ni exécution LIVE.


## Mesure des KPI LLM — Sentinel et ArgusLM

Le premier contrat KPI est documenté dans [LLM-KPI-CONTRACT](docs/LLM-KPI-CONTRACT.md). Il s'appuie sur les définitions de métriques de [sentinel-llm](https://github.com/alimtalbi-ata/sentinel-llm) et les mesures de [arguslm-llm](https://github.com/alimtalbi-ata/arguslm-llm) : succès/erreurs, latence P50/P95/P99, TTFT P95, tokens/s, tokens, coût **estimé** USD et taux d'anomalies. Les valeurs absentes restent `null`, et le résultat précise `authoritative=false`.

Exemple de requête (réservée au gateway interne ; valeurs fictives) :

```bash
curl -X POST http://127.0.0.1:8000/api/v1/observability/llm/kpis/preview \\
  -H 'Content-Type: application/json' \\
  -H 'X-Internal-Api-Key: <clé-interne-de-test>' \\
  -H 'X-Tenant-Id: 00000000-0000-0000-0000-000000000001' \\
  -d '{"tenant_id":"00000000-0000-0000-0000-000000000001","model_id":"demo/model","observations":[{"status":"ok","latency_ms":120,"ttft_ms":30,"tps":45,"input_tokens":100,"output_tokens":40,"estimated_cost_usd":0.001}],"sentinel_anomalies_total":1,"sentinel_events_processed_total":100}'
```

**Limites :** aucun connecteur live Sentinel/ArgusLM, aucun historique horodaté, aucune mesure SLO de production, aucune autorisation de remédiation. L'API ne doit pas être exposée directement au public. Voir [statut du projet](docs/PROJECT-STATUS.md), [roadmap](docs/ROADMAP.md), [adaptateur GLPI](docs/GLPI-READ-ADAPTER.md) et [qualification staging](docs/GLPI-STAGING-QUALIFICATION.md).

## Design produit — AI SRE centré incidents

Le [blueprint UX evidence-first](docs/PRODUCT-UX-DESIGN.md) définit le futur Command Center, l'Incident Workbench, les panneaux RCA avec preuves contradictoires, l'espace KPI Sentinel/ArgusLM et les garde-fous Policy/HITL. Il s'inspire de quatre articles sur les workflows LLM fiables, la corrélation AIOps, la recherche de code structurée et la gestion des incidents. **C'est une spécification UX ; les nouvelles vues ne sont pas encore implémentées dans la console.**

## Investigation RCA — prévisualisation sécurisée

`POST /api/v1/incidents/investigation/preview` valide des hypothèses et leurs références de preuves horodatées, avec contrôle du tenant. **Aucun agent n'est exécuté et les preuves ne sont pas vérifiées auprès des sources.** Voir [INVESTIGATION-PREVIEW](docs/INVESTIGATION-PREVIEW.md) et [PRODUCT-UX-DESIGN](docs/PRODUCT-UX-DESIGN.md).

## Architecture cible et composants réutilisables

Le [plan d'architecture AI SRE / ITIL 4](docs/TARGET-ARCHITECTURE-2026.md) définit les responsabilités, flux, contrats, zones de sécurité et jalons de déploiement. L'[inventaire des composants réutilisables](docs/REUSE-COMPONENT-INVENTORY.md) recense les candidats dans les dépôts GitHub accessibles : aiops (Core/Policy/Evidence/GLPI), observability-stack (OTel/OpenSearch/Cortex), sentinel-llm, arguslm-llm, HolmesGPT, Aurora, Akmatori et IncidentFox. **Plan cible uniquement : aucun connecteur supplémentaire ni service LIVE déployé par cette documentation.**

## Déploiement cible : Docker Compose et Kubernetes

**Exigence d'architecture** : tous les composants de la plateforme exploités par GAMMA devront être livrés en images OCI et déployables via **Docker Compose (local/démo/intégration)** et **Kubernetes/Helm (staging/production)**. Les services externes peuvent être raccordés par connecteur. Le [contrat de déploiement](docs/DEPLOYMENT-CONTRACT.md) définit la matrice, les profils, les critères CI, les secrets, les volumes et les garde-fous. Cette exigence est une cible à implémenter, pas une certification des manifests existants.
