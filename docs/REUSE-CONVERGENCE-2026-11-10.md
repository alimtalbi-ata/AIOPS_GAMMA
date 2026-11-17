# Convergence fonctionnelle inter-dépôts — 2026-11-10

Statut : **inventaire de code et de documentation uniquement**. Aucun portage supplémentaire ni qualification runtime n'est revendiqué dans ce document.

## Déjà présent dans GAMMA (vérifié par lecture du code de la branche)

| Capacité | Code GAMMA | État vérifié |
|---|---|---|
| Estimation d'impact, transitions de Run | `app/reused/impact.py` | Fonctions pures adaptées de `aiops/app/shared/domain.py` ; topologie non vérifiée |
| Garde de politique LIVE | `app/reused/policy.py` | Décision consultative ; `live_execution_authorized=false` sans exception |
| Prévisualisation de corrélation | `app/reused/correlation.py` | Déduplication et regroupement déterministes ; pas de création d'incident ni de ticket |
| Ingestion d'alertes | `app/main.py` | Inbox/outbox tenant-scopés, désactivés par défaut |
| Recherche OpenSearch | `app/main.py` | Adaptateur protégé, désactivé par défaut |
| Topologie | `app/models.py`, `app/main.py` | Liaisons CMDB/service, pas de découverte ni de validation de graphe |

## Sources candidates et ordre de portage

1. **`alimtalbi-ata/aiops` — Evidence/Policy/Run** : source principale. Son catalogue `docs/COMPONENT-CATALOG-AND-REUSE.md` distingue candidats V145 non qualifiés et composants actuels. Priorité à la normalisation des preuves, provenance, fraîcheur et états UNKNOWN, sous forme de fonctions pures et tests déterministes.
2. **`alimtalbi-ata/aiops` — GLPI/HITL** : reprendre les contrats de lecture et de proposition, mais **aucune action LIVE** avant preuve d'autorisation à usage unique, fencing, idempotence et réconciliation. Les PR #192/#193/#194 se recouvrent : ne pas les fusionner aveuglément.
3. **`alimtalbi-ata/StorageScope-Architecte`** : isoler calculs métier et décisions stockage, sans importer Tkinter/SQLite Windows dans l'API serveur. Les tests historiques ne valent pas qualification Windows.
4. **`alimtalbi-ata/observability-stack`** : comparer les conventions OpenTelemetry, pipelines logs/traces et alertes avec les adaptateurs GAMMA ; ne pas déployer une seconde pile sans analyse de ressources et de sécurité.
5. **`alimtalbi-ata/holmesgpt`, `incidentfox-sre`, `akmatori-sre`** : inspiration pour RCA, mémoire d'incident, outils bornés et approbations. Vérifier licences, dépendances et contrats avant tout emprunt de code.
6. **`sentinel-llm`, `arguslm-llm`** : surveillance de qualité, latence, tokens et coûts LLM ; option après le socle Evidence/Run.

## Prochain incrément accepté

**Evidence normalization v1**, lecture seule, sans base de données : contrat versionné `tenant_id / incident_id / source / observed_at / evidence_ref / freshness / integrity` ; horodatage UTC explicite ; preuve manquante, périmée ou contradictoire = `UNKNOWN`. Tester déduplication, collision inter-tenant, timestamps naïfs, données contradictoires, charge bornée, refus d'action LIVE.

Avant d'écrire ce module : lire la source exacte et les tests du composant Evidence dans `aiops`, identifier la révision, vérifier la compatibilité de licence et de schéma. Aucun secret, dump, sauvegarde ou donnée de production ne doit être copié.

## Barrières de livraison

- PR brouillon uniquement, aucun merge ni déploiement sans validation explicite.
- Tests unitaires réels dans le laboratoire si GitHub Actions est bloqué par la facturation ; noter les commandes et résultats, sans assimiler mocks et runtime.
- Docker rootless, PostgreSQL et workflows LIVE restent non qualifiés.
