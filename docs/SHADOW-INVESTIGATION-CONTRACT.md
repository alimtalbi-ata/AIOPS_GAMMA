# Investigation RCA multi-hypothèses — shadow offline

Module : `app/reused/shadow_investigation.py`. Tests : `tests/test_shadow_investigation.py`.

## Contrat

`investigate_shadow(InvestigationInput(...))` évalue un ensemble fini d'hypothèses sur des preuves synthétiques fournies par l'appelant. Chaque preuve porte un tenant, un incident, une hypothèse, une polarité, un horodatage et une déclaration de vérification de source.

Étapes : (1) validation stricte de l'identité, de la politique et des types ; (2) filtrage tenant/incident, source, fenêtre temporelle et hypothèse ; (3) collecte des soutiens et contradictions ; (4) évaluation de chaque hypothèse ; (5) abstention si une preuve est rejetée, si aucune hypothèse ne satisfait les critères ou si plusieurs hypothèses sont admissibles.

Une unique hypothèse avec au moins deux identités de sources déclarées distinctes de soutien et aucune contradiction peut produire `REVIEW_CANDIDATE`. Les identités de sources distinctes sont uniquement déclarées par l'appelant ; elles ne démontrent **pas** l'indépendance réelle ou l'authenticité des sources. Les références multiples d'une même source ne satisfont pas le seuil. Une identité manquante entraîne une abstention. Toute preuve rejetée entraîne `ABSTAIN`. Le rapport expose les motifs et les références sans contenu brut.

## Limites de sécurité

Aucun LLM, outil, HTTP, source canonique, stockage, moteur d'exécution, rollback ou mutation ITSM. `authoritative=false`, `live_execution_authorized=false`, `tools_invoked=false` et `itsm_mutations_performed=false` sans exception.

Ce moteur n'est pas encore câblé au parcours agrégé : l'intégration doit préserver la distinction entre preuve déclarée et preuve authentifiée. Avant toute source réelle : ACL actor→tenant→resource indépendante, provenance immuable, déduplication par source et fenêtre de validité, puis benchmark de RCA adjudiqué. Aucun verdict synthétique ne peut autoriser le LIVE.

## Qualification

Tests ajoutés mais aucun résultat CI ni exécution locale attesté dans cette livraison. Conserver PR #1 en Draft ; **HOLD / NO_GO LIVE**.

## Raccordement au parcours agrégé

`IncidentShadowInput.investigation` est optionnel. Lorsqu'il est renseigné, `evaluate_incident_shadow` ajoute `stages.investigation` et impose l'identité tenant/incident identique. Même une RCA synthétique `REVIEW_CANDIDATE` n'active pas les décisions de runbook ou d'autonomie : `evidence_source_verified` et la RCA sont traitées comme non qualifiées. Le contrat existant reste inchangé en absence d'investigation.

Les tests d'intégration couvrent le cas positif non autoritatif, les contradictions et les divergences de tenant/incident. Aucun test exécuté ou CI verte n'est revendiqué.

## Critères du prochain jalon

Avant tout passage à une investigation sur sources réelles : attester indépendamment l'identité et la provenance des sources (les identifiants déclarés ne prouvent pas l'indépendance), des références de preuves immuables, une fenêtre temporelle liée à l'incident, une ACL serveur vérifiée et un benchmark avec cas ambigus, contradictoires et négatifs. Les champs `source_verified` fournis par l'appelant restent des déclarations synthétiques.
