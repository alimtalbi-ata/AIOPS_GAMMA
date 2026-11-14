# GAMMA — catalogue des cas d’usage produit

Ce catalogue relie les parcours opérationnels visés aux capacités réellement présentes dans le dépôt. Il sert de garde-fou produit : une route ou une projection synthétique ne signifie pas qu'un parcours est qualifié en production.

## Légende de maturité

- **Disponible — démonstration synthétique** : parcours local/synthétique, sans source canonique ni écriture externe.
- **Disponible — API sous feature flag / qualification partielle** : contrat présent, dépendances et sécurité encore à qualifier.
- **Prévisualisation uniquement** : proposition non autoritative, sans persistance ni exécution.
- **Cible — non livrée** : cas d’usage produit planifié, dépendant de contrats, ACL, tests et exploitation.

## Catalogue

| ID | Cas d’usage | Valeur utilisateur | Capacités / point d’entrée connus | Maturité et limite |
|---|---|---|---|---|
| UC01 | Supervision et santé de la plateforme | Vérifier que GAMMA répond et visualiser son état de démonstration | `GET /api/v1/health/live`, Overview local | Santé du processus seulement ; ne prouve ni dépendances ni disponibilité métier |
| UC02 | Ingestion et exploration des signaux | Rassembler logs et alertes pour une investigation par tenant/service | `POST /api/v1/observability/logs/search`, `POST /api/v1/integrations/opensearch/alerts` | Feature flags ; OpenSearch/TLS/DLS/RBAC et mappings à qualifier |
| UC03 | Corrélation et regroupement d’incidents | Réduire le bruit en regroupant les signaux liés | `POST /api/v1/incidents/correlation/preview`, démonstration locale « 2 signaux → 1 groupe » | Prévisualisation/démonstration ; tests de permutations, doublons conflictuels et bornes de preuves présents mais non exécutés ; déduplication persistante, concurrence et replay restent à qualifier |
| UC04 | Contexte service et impact CMDB | Relier un incident aux services et CI affectés | `POST/GET /api/v1/topology/bindings`, observations CI synthétiques | Binding ≠ identité CMDB canonique ; ACL et fraîcheur CMDB non qualifiées |
| UC05 | Dossier d’incident et preuves | Constituer un dossier traçable pour l’investigation | `POST/GET /api/v1/incidents/{incident_id}/evidence` | Persistance de preuves disponible dans le code ; autorisation multi-tenant, rétention et audit à qualifier |
| UC06 | KPI LLM Sentinel / ArgusLM | Suivre latence, TTFT, débit, tokens, erreurs et coût estimé | `POST /api/v1/observability/llm/kpis/preview` | Agrégation d’échantillons fournis par l’appelant ; non autoritaire, pas de collecte live ni historique durable |
| UC07 | Analyse RCA assistée | Formuler hypothèses, confronter preuves et documenter les inconnues | Contrats de preuves et architecture AI SRE | Cible ; moteur d’investigation, benchmark humain, provenance et gestion des contradictions à livrer |
| UC08 | Workflow ITIL 4 incident → problème → changement | Préparer une proposition cohérente, liée à l’incident et aux CI | `POST /api/v1/itil4/incidents/sync-preview`, `app/reused/itil.py` | Prévisualisation non autoritative ; pas d’écriture GLPI, de vérification CMDB canonique ni d’approbation |
| UC09 | Planification de remédiation contrôlée | Proposer une action fondée sur un runbook, son risque, son rollback et ses vérifications | `POST /api/v1/policy/remediation/preview` | Conseil uniquement ; catalogue approuvé, Policy/HITL et validation indépendante requis |
| UC10 | Exécution, vérification et réconciliation | Exécuter par le Core/Temporal existant, puis vérifier l’effet et clôturer | Intégration cible Core/Temporal/ITSM | Non livrée / NO_GO ; aucune action LIVE autorisée |
| UC11 | Postmortem et apprentissage | Produire un compte rendu blameless, les actions et les récurrences | Architecture AI SRE et roadmap RCA | Cible ; données canoniques, adjudication humaine et suivi d’actions requis |
| UC12 | Gouvernance, audit et conformité | Expliquer qui a consulté, proposé, approuvé et exécuté quoi | Contrats gateway, Policy/HITL et handover | Partiel ; ACL acteur→tenant→ressource, receipts signés et chaîne d’audit restent à qualifier |

## Parcours de bout en bout cible

1. Détecter : logs, métriques et alertes (UC01–UC02).
2. Corréler : regrouper les signaux et dédupliquer (UC03).
3. Contextualiser : service, topologie et CI canoniques (UC04).
4. Constituer les preuves : provenance, horodatage et contradictions (UC05).
5. Investiguer : hypothèses RCA et UNKNOWN explicite (UC07).
6. Préparer l’ITIL : incident, problème/known error et RFC (UC08).
7. Planifier : runbook approuvé, risque, rollback et vérification (UC09).
8. Autoriser : Policy/HITL indépendant, identité et périmètre vérifiés (UC12).
9. Exécuter et réconcilier : Core/Temporal, preuves post-action et ITSM (UC10).
10. Apprendre : postmortem et suivi (UC11).

## Priorisation et critères d’acceptation

| Priorité | Cas d’usage / incrément | Critères de sortie |
|---|---|---|
| P0 | UC01, contrat UC12 | CI réellement exécutée sur le SHA exact ; gateway authentifie l’acteur ; ACL acteur→tenant→ressource ; aucune confiance dans un tenant fourni par le navigateur |
| P1 | UC02–UC05 | Tests tenant négatifs/positifs ; limites payload/timeout/redirect ; provenance ; idempotence et tests de concurrence ; source canonique et fraîcheur vérifiées |
| P2 | UC06–UC07 | Adaptateurs Sentinel/ArgusLM en lecture seule ; échantillonnage, timestamps, couverture ; benchmark RCA adjudiqué ; preuves sourcées et contradictions |
| P3 | UC08–UC09 | cycle ITSM staging idempotent ; modèles de changement approuvés ; validation indépendante des runbooks, Policy et HITL |
| P4 | UC10–UC11 | tests d’échec, fencing/idempotence, rollback, vérification SLI après action, clôture/réconciliation et postmortem revu |

## Garde-fous non négociables

- Les données synthétiques, prévisualisations et compteurs déclarés par un appelant ne sont jamais des preuves canoniques.
- Aucun KPI, score RCA, statut UI ou test statique ne confère une autorisation d’exécution.
- Toute lecture canonique exige une identité d’acteur et une ACL ressource vérifiées côté serveur, pas seulement un tenant ID.
- Toute écriture ITSM ou remédiation exige approbation indépendante, idempotence, audit et procédure de rollback.
- Le statut « test présent » ne vaut pas « test exécuté » ; une CI sans étapes/logs n'apporte aucune preuve de réussite.
- Les intégrations et fonctionnalités marquées cible ne doivent pas être présentées comme livrées.

## Références de conception

- [Roadmap exécutable](ROADMAP.md)
- [Architecture AI SRE](AI-SRE-PLATFORM.md)
- [UX produit](PRODUCT-UX-DESIGN.md)
- [Gouvernance ITIL 4](ITIL4-GOVERNANCE.md)
- [Contrat de principal gateway](TRUSTED-TENANT-PRINCIPAL-CONTRACT.md)
