# AIOPS_GAMMA

Socle d'intégration AIOps **Python/FastAPI + PostgreSQL + OpenSearch Observability**.

> **Version 0.1 : MVP de développement, pas encore prêt pour la production.** Les moteurs de corrélation, CMDB, RCA et agents IA restent ceux de la plateforme existante : ce dépôt fournit leurs futurs points d'intégration, pas une réimplémentation fictive.

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
- `POST /api/v1/observability/metrics/query` : `501` tant qu'un constructeur PromQL isolé par tenant n'est pas implémenté.

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
