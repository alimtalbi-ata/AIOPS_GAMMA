# GAMMA — catalogue des cas d’usage produit

Ce catalogue reprend **les identifiants UC01–UC10 déjà définis dans [ROADMAP.md](ROADMAP.md#use-cases-and-acceptance-gates-2026-11-14)** et utilisés dans les scénarios synthétiques. Une prévisualisation ne constitue ni une intégration canonique, ni une qualification de production.

> Correction de traçabilité (2026-11-14) : une première version de ce catalogue avait réattribué les IDs UC02, UC03, UC05–UC10 et créé UC11–UC12. Cette numérotation était incompatible avec la roadmap et les tests. **La roadmap UC01–UC10 fait foi.** Les thèmes transverses restent présents, sans nouveaux IDs concurrents.

## Catalogue aligné sur la roadmap

| ID stable | Parcours opérateur | Implémentation et preuve de code | Limite et prochain critère de sortie |
|---|---|---|---|
| UC01 | Command center et supervision | UI React de démonstration, `GET /api/v1/health/live` | DEMO ≠ REAL ; santé du processus ≠ santé métier ; authentification et données réelles à qualifier |
| UC02 | Corrélation d’alertes | `POST /api/v1/incidents/correlation/preview`, `app/reused/correlation.py`, `tests/test_correlation.py` | Déduplication en mémoire uniquement ; concurrence, replay et clustering durable #4 non qualifiés |
| UC03 | Investigation et preuves | `app/reused/correlation_evidence.py`, `app/reused/investigation.py`, `tests/test_correlation_evidence.py` ; prévisualisations HTTP | Preuves fournies par l’appelant, intégrité non authentifiée ; ACL ressource, collecte et provenance canoniques manquantes |
| UC04 | Topologie et estimation d’impact | `app/reused/impact.py`, `app/reused/synthetic_impact.py`, `app/reused/topology_preview.py`, `tests/test_topology_preview.py` | Parcours de graphe **synthétique** avec dépendances directes/indirectes, chemins explicatifs et parcours inverse des consommateurs potentiellement touchés, incertitude des relations manquantes limitée au sous-graphe accessible, et estimation séparée sur comptes de chemins ; cycles et relations manquantes → UNKNOWN ; ces distances ne sont pas un score d’impact ; CMDB/Twin canonique non vérifiée |
| UC05 | ITSM/GLPI et dossier d’incident | `app/reused/itsm_contract.py`, `app/reused/itil.py`, `POST /api/v1/itil4/incidents/sync-preview` ; lecture GLPI désactivée par défaut | Proposition non autoritative ; aucun ticket/problème/changement créé ; priorité, entité et idempotence à qualifier en staging |
| UC06 | Analyse RCA assistée | `app/reused/investigation.py`, `tests/test_synthetic_rca_usecase.py`, scénarios RCA synthétiques | Hypothèses/provenance locales seulement ; pas d’agent autonome qualifié, de benchmark adjudiqué ni de preuve canonique |
| UC07 | Observabilité AI/LLM et SLO | `POST /api/v1/observability/llm/kpis/preview`, `app/reused/llm_kpi.py` | Échantillons fournis par l’appelant ; pas de collecte Sentinel/ArgusLM live, historique durable ni SLO qualifié |
| UC08 | Runbook, changement et approbation | `POST /api/v1/policy/remediation/preview`, `app/reused/synthetic_runbook_hitl.py`, `app/reused/itil.py` | Conseil/dry-run synthétique ; pas de runbook approuvé, de receipt HITL indépendant ni d’écriture ITSM |
| UC09 | Récupération contrôlée et vérification | Core/Temporal existant identifié comme **intégration cible** ; simulations de planification uniquement | **NO_GO LIVE** : Policy/HITL, fencing, rollback, vérification SLI et réconciliation non qualifiés |
| UC10 | Postmortem et apprentissage | `app/reused/synthetic_postmortem.py`, `tests/test_synthetic_postmortem_usecase.py`, `tests/test_synthetic_end_to_end_usecase.py` | Brouillon **synthétique** avec UNKNOWN et revue humaine requise ; aucune clôture ni leçon canonique persistée |

## Parcours de bout en bout

1. **UC01–UC02** — présenter des signaux étiquetés DEMO/REAL et les regrouper sans écrire dans le Core.
2. **UC03–UC04** — relier preuves et dépendances ; afficher UNKNOWN si provenance, couverture ou CMDB sont incertaines.
3. **UC05–UC06** — préparer l’ITSM et les hypothèses RCA, avec citations et contradictions explicites.
4. **UC07–UC08** — examiner les KPI LLM et une proposition de runbook/changement sans conférer d’autorité.
5. **UC09–UC10** — n’envisager l’exécution qu’après qualification indépendante ; produire aujourd’hui uniquement un postmortem synthétique soumis à revue humaine.

## Thèmes transverses, sans nouvel identifiant UC

- **Ingestion et recherche** : `POST /api/v1/observability/logs/search` et `POST /api/v1/integrations/opensearch/alerts` ; OpenSearch/TLS/DLS/RBAC, mapping et isolation restent à qualifier (#3).
- **Gouvernance et audit** : identité gateway, ACL **acteur→tenant→ressource** (#2), approbations indépendantes, receipts et traçabilité. Un `tenant_id` déclaré ne suffit jamais.
- **ITIL 4** : incident→problème→changement est une projection UC05/UC08, pas un second parcours UC autonome.
- **Qualité CI** : les tests présents dans le dépôt ne sont pas des tests exécutés. Le blocage pré-étapes GitHub Actions (#8) empêche une qualification sur le HEAD courant.

## Critères de sortie prioritaires

| Priorité | Parcours | Preuves attendues |
|---|---|---|
| P0 | UC01, sécurité transverse | CI sur SHA exact ; principal authentifié et ACL ressource ; données DEMO/REAL explicites |
| P1 | UC02–UC05 | Tests tenant positifs/négatifs ; provenance, limites et timeouts ; replay/concurrence ; CMDB/ITSM staging qualifiés |
| P2 | UC06–UC07 | Benchmark RCA adjudiqué, contradictions et UNKNOWN ; sources KPI en lecture seule, fraîcheur et couverture |
| P3 | UC08 | Catalogue de runbooks approuvés ; Policy/HITL indépendant, plans rollback/vérification et idempotence ITSM |
| P4 | UC09–UC10 | Fencing, rollback, SLI post-action, réconciliation, audit et postmortem revu ; aucune autonomie avant les gates |

## Garde-fous

- Une projection synthétique, un hash de payload ou une couverture de preuves ne prouve pas une source canonique.
- Les données d’UI, les KPI LLM et les hypothèses RCA ne confèrent jamais d’autorisation d’exécution.
- Aucune lecture canonique sans ACL acteur→tenant→ressource vérifiée côté serveur.
- Aucune écriture ITSM ou remédiation sans approbation indépendante, idempotence et audit.
- PR #1 demeure **Draft — HOLD / NO_GO** : aucun merge, déploiement, accès PostgreSQL réel ou LIVE.

## Références

- [Roadmap et IDs UC01–UC10](ROADMAP.md)
- [Architecture AI SRE](AI-SRE-PLATFORM.md)
- [UX produit](PRODUCT-UX-DESIGN.md)
- [Gouvernance ITIL 4](ITIL4-GOVERNANCE.md)
- [Contrat de principal gateway](TRUSTED-TENANT-PRINCIPAL-CONTRACT.md)
