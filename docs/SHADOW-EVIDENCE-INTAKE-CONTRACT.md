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

## Empreinte et benchmark de parcours complet

`snapshot_fingerprint` calcule un SHA-256 déterministe des métadonnées déclarées : identité du snapshot, tenant, incident, capture, références de preuves, sources, polarités et horodatages. L'ordre des preuves n'affecte pas l'empreinte. Il ne s'agit **ni d'une signature, ni d'une attestation de provenance, ni d'une preuve d'intégrité des contenus bruts** ; le hash est recalculé à partir de données fournies par l'appelant.

`app/reused/shadow_snapshot_benchmark.py` fournit `evaluate_snapshot_benchmark` pour mesurer ensemble : sélection correcte, faux positif, cause manquée, abstention correcte, refus d'accès attendu, refus inattendu et refus manqué. Les refus déclaratifs sont comptabilisés indépendamment des décisions RCA. Les cas invalides sont rejetés ; un benchmark n'exécute aucun connecteur.

Les tests de `tests/test_shadow_snapshot_benchmark.py` couvrent les empreintes, contradictions, refus, refus manqués et cas invalides. Les métriques attendues sont des assertions de fixtures, **pas des résultats d'exécution attestés**.

## Validité du jeu de référence

Le benchmark refuse désormais toute cause attendue qui n'appartient pas au catalogue d'hypothèses du cas. Les tests distinguent explicitement un faux positif (cause sélectionnée différente de l'étiquette) d'une cause manquée (abstention alors qu'une cause était attendue). Les étiquettes sont synthétiques et déclarées par l'auteur des fixtures : elles ne prouvent pas une RCA de production.

## Référence d'intégrité facultative

`SnapshotRequest.expected_fingerprint_sha256` accepte `None` (mode historique) ou une empreinte SHA-256 hexadécimale minuscule de 64 caractères. Après les contrôles d'identité, de grant déclaré et de fraîcheur, l'ingestion recalcule l'empreinte des métadonnées et rejette une différence par `ValueError("Snapshot fingerprint mismatch")`. Une empreinte malformée est également rejetée. La comparaison ne porte **pas** sur le contenu brut des preuves et ne vérifie pas l'auteur de la référence ; un attaquant contrôlant simultanément l'instantané et son empreinte peut les modifier ensemble. Aucun accès LIVE n'est accordé.

## Cohérence temporelle de la capture

L'ingestion rejette désormais toute preuve dont `observed_at` est strictement postérieur à `snapshot.captured_at`, même si elle se situe avant `as_of`. Les comparaisons utilisent les instants des `datetime` avec fuseau horaire, pas les chaînes d'affichage. Cette règle interdit de qualifier un instantané qui prétend contenir une observation encore inexistante au moment de sa capture. Elle ne constitue ni une horloge de confiance, ni une attestation de collecte réelle.
