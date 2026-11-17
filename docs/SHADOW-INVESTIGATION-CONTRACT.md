# Investigation RCA multi-hypothèses — shadow offline

Module : `app/reused/shadow_investigation.py`. Tests : `tests/test_shadow_investigation.py`.

## Contrat

`investigate_shadow(InvestigationInput(...))` évalue un ensemble fini d'hypothèses sur des preuves synthétiques fournies par l'appelant. Chaque preuve porte un tenant, un incident, une hypothèse, une polarité, un horodatage et une déclaration de vérification de source.

Étapes : (1) validation stricte de l'identité, de la politique et des types ; (2) filtrage tenant/incident, source, fenêtre temporelle et hypothèse ; (3) collecte des soutiens et contradictions ; (4) évaluation de chaque hypothèse ; (5) abstention si une preuve est rejetée, si aucune hypothèse ne satisfait les critères ou si plusieurs hypothèses sont admissibles.

Une unique hypothèse avec au moins deux références distinctes de soutien et aucune contradiction peut produire `REVIEW_CANDIDATE`. Les références distinctes ne démontrent **pas** l'indépendance réelle des sources : le seuil est un garde-fou minimal synthétique, pas une qualification de provenance. Toute preuve rejetée entraîne `ABSTAIN`. Le rapport expose les motifs et les références sans contenu brut.

## Limites de sécurité

Aucun LLM, outil, HTTP, source canonique, stockage, moteur d'exécution, rollback ou mutation ITSM. `authoritative=false`, `live_execution_authorized=false`, `tools_invoked=false` et `itsm_mutations_performed=false` sans exception.

Ce moteur n'est pas encore câblé au parcours agrégé : l'intégration doit préserver la distinction entre preuve déclarée et preuve authentifiée. Avant toute source réelle : ACL actor→tenant→resource indépendante, provenance immuable, déduplication par source et fenêtre de validité, puis benchmark de RCA adjudiqué. Aucun verdict synthétique ne peut autoriser le LIVE.

## Qualification

Tests ajoutés mais aucun résultat CI ni exécution locale attesté dans cette livraison. Conserver PR #1 en Draft ; **HOLD / NO_GO LIVE**.
