# Ingestion de preuves synthétiques — shadow offline

Module : `app/reused/shadow_evidence_intake.py`. Tests : `tests/test_shadow_evidence_intake.py`.

## Portée

`investigate_snapshot(SnapshotRequest(...))` reçoit un snapshot **déjà fourni par l'appelant**. Il ne lit aucun connecteur, aucune base de données et aucune source externe. Le snapshot contient une identité tenant/incident, un horodatage et un tuple de preuves synthétiques.

Avant l'investigation, l'entrée contrôle : acteur non vide, tenant explicitement présent dans les grants déclarés, identité du snapshot, fraîcheur non future et limitée, types des collections. Une violation d'accès produit `PermissionError` ; un snapshot invalide produit `ValueError`. Les preuves sont ensuite filtrées par `investigate_shadow`, avec abstention en présence de preuves rejetées.

Le rapport expose `grant_origin=CALLER_DECLARED_SYNTHETIC`. **Ces grants ne sont pas une ACL serveur** et ne doivent jamais être présentés comme une autorisation réelle. Les identités de source et `source_verified` sont également déclarées par l'appelant ; aucune signature ou provenance n'est attestée.

## Invariants

- `mode=synthetic_shadow`
- `authoritative=false`
- `live_execution_authorized=false`
- `connectors_invoked=false`
- `itsm_mutations_performed=false`

Aucun effet de bord, outil, LLM, exécution de runbook, rollback ou mutation ITSM.

## Conditions avant connecteurs réels

Mettre en place une ACL indépendante `actor→tenant→incident→resource`, une identité d'acteur authentifiée, une provenance de source attestée, une chaîne d'intégrité des références, un budget de collecte, des contrôles de pagination/timeout, une politique de rétention et un audit de lecture. Les données brutes doivent être filtrées pour les secrets et informations personnelles. Tant que ces exigences ne sont pas satisfaites, **HOLD / NO_GO LIVE**.

Les tests sont définis dans le dépôt ; aucun succès d'exécution locale ou CI n'est revendiqué.
