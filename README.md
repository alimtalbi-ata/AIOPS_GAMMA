# AIOPS_GAMMA

Socle d'intégration AIOps **Python/FastAPI + PostgreSQL + OpenSearch Observability**.

> **Version de paquet 0.2.0 : MVP de développement, pas encore prêt pour la production.** Les moteurs de corrélation, CMDB, RCA et agents IA restent ceux de la plateforme existante : ce dépôt fournit leurs futurs points d'intégration, pas une réimplémentation fictive.

## Tester GAMMA sans VM ni Docker

Sur un poste avec Python 3.11+ et un clone de cette branche, dans un
environnement virtuel **isolé** (ne pas utiliser de secrets ou de `.env` réels) :

```bash
python -m venv .venv
. .venv/bin/activate
python -m pip install -e '.[test]'
python scripts/smoke_no_vm.py
python -m pytest -q tests/test_no_vm_smoke.py tests/test_quality_p0_imports.py
```

Sous Windows, activer l'environnement virtuel avec
`.venv\\Scripts\\activate` avant les commandes Python.

Le smoke utilise `fastapi.testclient.TestClient` et n'ouvre **aucun port**.
Il vérifie la santé, les routes déclarées et le refus d'un en-tête tenant
non fiable. Il **refuse de s'exécuter** si des secrets de gateway/service
sont configurés. Ce n'est ni un test d'installation Docker, ni une validation
PostgreSQL, frontend ou IdP. Les tests doivent afficher un PASS réel sur
la machine qui les exécute ; ils n'ont pas encore été exécutés ici.

## Démonstration interactive sans VM ni Docker

Deux terminaux sur **le même poste**, avec un clone de la branche :

```bash
# Terminal 1 — API FastAPI, environnement Python isolé
python -m venv .venv
. .venv/bin/activate
python -m pip install -e '.[test]'
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

```bash
# Terminal 2 — interface React/Vite
cd frontend
npm install --no-audit --no-fund
npm run dev
```

Ouvrir **http://127.0.0.1:5173/** → **Overview** →
**« Exécuter le scénario »**. Vite ne relaie vers FastAPI **que**
`/api/v1/demo/correlation`; aucun endpoint tenant authentifié n'est exposé
par cette configuration de développement. Le résultat attendu est
`PASS · Moteur de corrélation API`, **2 signaux → 1 groupe**.

`python scripts/smoke_no_vm.py` permet une validation sans navigateur ni
port réseau. Ce parcours reste **synthétique et non persistant** ; il ne
prouve pas que le frontend ou PostgreSQL fonctionnent en production.
N'utilisez aucun secret réel, aucune `.env` de production et n'exposez
pas ces ports sur une interface publique.

## Démarrage (Docker Compose)

```bash
cp .env.example .env
# Modifier impérativement POSTGRES_PASSWORD et INTERNAL_API_KEY
docker compose up --build -d
curl http://127.0.0.1:8000/api/v1/health/live
# Les migrations Alembic sont appliquées par le service Compose migrate.
# Vérifier API + interface + version PostgreSQL :
python scripts/smoke_local_mvp.py
```

Interface de démonstration : http://127.0.0.1:5173/ (données synthétiques, non connectées à l'API).

Le service `migrate` applique `alembic upgrade head` sur la base locale avant de démarrer l'API. Si la migration échoue, l'API ne démarre pas. Le script `scripts/smoke_local_mvp.py` vérifie uniquement les réponses HTTP et la révision de schéma ; il ne valide pas l'authentification multi-tenant.

Swagger : http://127.0.0.1:8000/docs. Les endpoints métier nécessitent `X-Internal-Api-Key` (authentification du workload) et `X-Gateway-Principal` (assertion HMAC courte, signée par la passerelle, liée à la méthode/route et attestant le tenant). `X-Tenant-Id` fourni par le client n'autorise plus l'accès. La passerelle doit authentifier l'acteur et vérifier son appartenance au tenant avant de signer. Voir [contrat de principal gateway](docs/TRUSTED-TENANT-PRINCIPAL-CONTRACT.md). Cette intégration est partielle et non qualifiée pour la production.

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

## Packaging initial Compose / Kubernetes

Les premiers manifests sont disponibles dans [`deploy/`](deploy/README.md) : surcharge Docker Compose pour la stack existante, chart Helm `gamma` (UI + API), Secrets externes et validation statique en CI. **Ce n'est pas encore une stack intégrée complète** : Core/Temporal, OpenSearch/Cortex, Sentinel, ArgusLM et moteur RCA nécessitent leurs déploiements et tests séparés. Le proxy API côté navigateur, l'authentification SSO et la qualification staging ne sont pas livrés.

## Installation monorépertoire et rootless

La cible impose une installation sous une racine configurable `GAMMA_HOME`, sans écriture dans `/bin`, `/sbin`, `/var` ou `/tmp` **sur l'hôte**, avec Docker Engine rootless et workloads Kubernetes non-root. Voir le [contrat rootless](docs/ROOTLESS-SINGLE-DIRECTORY.md), l'[overlay Compose expérimental](deploy/compose/compose.rootless.yaml) et le [précontrôle](deploy/scripts/check-rootless-home.sh). Les images et le runtime peuvent nécessiter des dépendances Linux internes ou des prérequis système : la conformité totale n'est pas encore démontrée.

## Scénario fonctionnel de démonstration — sans données client

L'API publique `GET /api/v1/demo/correlation` utilise le **vrai moteur**
`app.reused.correlation.correlate` avec deux signaux **fixes et synthétiques**
(payment-timeout). Elle retourne un groupe corrélé, sans lire PostgreSQL,
OpenSearch, GLPI, un tenant réel ou un fournisseur d'identité. Résultat
explicitement `mode=synthetic_demo`, `authoritative=false`,
`persisted=false`, `live_remediation_authorized=false`.

La console React affiche un bouton **« Exécuter le scénario »** dans Overview :
le navigateur appelle cette API via une règle Nginx limitée au seul endpoint
de démonstration. Un échec de connexion est affiché FAIL, jamais un PASS
fictif. Les autres tableaux restent **des exemples statiques** et ne doivent
pas être présentés comme de la télémétrie réelle.

Sur un poste sans VM, `python scripts/smoke_no_vm.py` vérifie aussi cette
corrélation via l'application ASGI en mémoire.

## Investigation interactive de démonstration — sans VM

Dans l'interface React locale, ouvrir **Incidents & RCA** et cliquer sur
**« Relier les preuves »**. Le navigateur appelle uniquement
`GET /api/v1/demo/investigation` (proxy Vite local ou Nginx exact).
Cette API exécute le moteur existant de corrélation **et** le moteur existant
de jointure de preuves, avec deux événements et deux preuves synthétiques.
L'interface affiche le nombre de preuves liées et l'état `UNVERIFIED` :
la correspondance des identifiants est démontrée, **pas** l'authenticité
des sources ni une cause racine confirmée. Un échec HTTP affiche FAIL.

Le test `python scripts/smoke_no_vm.py` vérifie également cette jointure,
sans base de données ni VM. Aucun appel vers les endpoints métier protégés
n'est fait par l'interface. Aucun accès LIVE ni écriture n'est autorisé.

### Détails de preuves dans l'interface

Après **Incidents & RCA → Relier les preuves**, la console montre maintenant
chaque identifiant d'événement, son observation et son état `UNVERIFIED`,
pas seulement un compteur. Les résultats sont rejetés par l'interface si
le format ou le statut attendu diffère. Le serveur Vite de développement
écoute explicitement **127.0.0.1** (pas `0.0.0.0`) afin de ne pas
publier accidentellement la démonstration sur le réseau local.

**Validation restant à effectuer** : `npm run build`, tests Python sur
checkout complet, lancement des deux processus sur un poste utilisateur.
Aucun PASS d'exécution bout en bout n'est affirmé.

### Fiabilité du démarrage

Docker Compose attend désormais que le service API ait démarré avant de
lancer le frontend Nginx, afin que le nom d'hôte `api` de l'upstream
puisse être résolu. Cela ne remplace **pas** une sonde de disponibilité
fonctionnelle de l'API. Les commandes `npm run dev` et `npm run preview`
restent toutes deux limitées à `127.0.0.1`.

Le code n'a pas été exécuté dans un checkout complet ici : le réseau de
l'environnement d'exécution ne résout pas github.com. Aucun résultat
PASS de build ou de tests n'est revendiqué.

### Healthcheck Compose API

Le frontend attend désormais `service_healthy` et non seulement
`service_started` pour l'API. Le conteneur API vérifie avec la bibliothèque
standard Python que `GET /api/v1/health/live` retourne exactement
`{"status":"ok"}`. Le endpoint est public et ne nécessite aucun secret
tenant. La migration PostgreSQL reste une dépendance préalable de l'API.

Cette sonde prouve uniquement la disponibilité HTTP du processus FastAPI,
**pas** l'accès PostgreSQL ni la disponibilité des intégrations. Les jobs
GitHub Actions de la dernière exécution consultée étaient tous en échec,
sans étapes ni journaux exploitables ; aucun succès CI n'est revendiqué.

### Contrôles supplémentaires de la démonstration

`python -m pytest -q tests/test_demo_invariants.py tests/test_no_vm_smoke.py`
vérifie la stabilité du scénario et le fait que la jointure des preuves
ne constitue ni une preuve d'authenticité, ni une RCA confirmée, ni un
ticket ITSM, ni une autorisation de remédiation. Ces tests sont sans
services externes et ne sont pas un substitut à un test d'intégration.

**CI bloquante** : les derniers jobs GitHub Actions consultés échouent
tous avant de fournir des étapes ou journaux exploitables. Vérifier dans
GitHub Actions les restrictions d'exécution, la facturation/quota et les
runners du dépôt avant d'attribuer les échecs à une assertion Python.

### Frontend : aucune route API métier exposée

Les serveurs frontend Vite (développement) et Nginx (conteneur)
n'autorisent que les chemins exacts
`/api/v1/demo/correlation` et `/api/v1/demo/investigation`.
Toute autre URL commençant par `/api/` reçoit HTTP 404 et n'est
ni transmise à FastAPI ni convertie en page HTML SPA. Les routes tenant
authentifiées restent accessibles uniquement par le backend/gateway
prévu à cet effet, pas par la console de démonstration.

### Tests négatifs de jointure de preuves

`python -m pytest -q tests/test_evidence_join_fail_closed.py` couvre
les cas d'échec indispensables : preuve d'un autre tenant refusée,
événement non correspondant, preuve absente, deux incidents contradictoires
dans un même groupe et absence de validation de provenance même lorsque
la jointure par identifiant réussit. Ces tests restent locaux, sans VM
ni intégration externe. Leur exécution réussie n'est pas encore confirmée.
