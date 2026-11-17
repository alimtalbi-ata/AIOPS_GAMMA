# Investigation RCA multi-hypothèses — shadow offline

Module : `app/reused/shadow_investigation.py`. Tests : `tests/test_shadow_investigation.py`.

## Contrat

`investigate_shadow(InvestigationInput(...))` évalue un ensemble fini d'hypothèses sur des preuves synthétiques fournies par l'appelant. Chaque preuve porte un tenant, un incident, une hypothèse, une polarité, un horodatage et une déclaration de vérification de source.

Étapes : (1) validation stricte de l'identité, de la politique et des types ; (2) filtrage tenant/incident, source, fenêtre temporelle et hypothèse ; (3) collecte des soutiens et contradictions ; (4) évaluation de chaque hypothèse ; (5) abstention si une preuve est rejetée, si aucune hypothèse ne satisfait les critères ou si plusieurs hypothèses sont admissibles.

Une unique hypothèse avec au moins deux identités de sources déclarées distinctes de soutien et aucune contradiction peut produire `REVIEW_CANDIDATE`. Les identités de sources distinctes sont uniquement déclarées par l'appelant ; elles ne démontrent **pas** l'indépendance réelle ou l'authenticité des sources. Les références multiples d'une même source ne satisfont pas le seuil. Une identité manquante entraîne une abstention. Toute preuve rejetée entraîne `ABSTAIN`. Le rapport expose les motifs et les références sans contenu brut.

## Limites de sécurité

Aucun LLM, outil, HTTP, source canonique, stockage, moteur d'exécution, rollback ou mutation ITSM. `authoritative=false`, `live_execution_authorized=false`, `tools_invoked=false` et `itsm_mutations_performed=false` sans exception.

Le moteur est câblé au parcours agrégé en mode synthétique strictement non autoritatif ; l'intégration préserve la distinction entre preuve déclarée et preuve authentifiée. Avant toute source réelle : ACL actor→tenant→resource indépendante, provenance immuable, déduplication par source et fenêtre de validité, puis benchmark de RCA adjudiqué. Aucun verdict synthétique ne peut autoriser le LIVE.

## Qualification

Tests ajoutés mais aucun résultat CI ni exécution locale attesté dans cette livraison. Conserver PR #1 en Draft ; **HOLD / NO_GO LIVE**.

## Raccordement au parcours agrégé

`IncidentShadowInput.investigation` est optionnel. Lorsqu'il est renseigné, `evaluate_incident_shadow` ajoute `stages.investigation` et impose l'identité tenant/incident identique. Même une RCA synthétique `REVIEW_CANDIDATE` n'active pas les décisions de runbook ou d'autonomie : `evidence_source_verified` et la RCA sont traitées comme non qualifiées. Le contrat existant reste inchangé en absence d'investigation.

Les tests d'intégration couvrent le cas positif non autoritatif, les contradictions et les divergences de tenant/incident. Aucun test exécuté ou CI verte n'est revendiqué.

## Critères du prochain jalon

Avant tout passage à une investigation sur sources réelles : attester indépendamment l'identité et la provenance des sources (les identifiants déclarés ne prouvent pas l'indépendance), des références de preuves immuables, une fenêtre temporelle liée à l'incident, une ACL serveur vérifiée et un benchmark avec cas ambigus, contradictoires et négatifs. Les champs `source_verified` fournis par l'appelant restent des déclarations synthétiques.

## Benchmark RCA synthétique

`app/reused/shadow_rca_benchmark.py` et `tests/test_shadow_rca_benchmark.py` définissent un contrat d'évaluation reproductible sur fixtures étiquetées. Le jeu initial contient huit cas (positif, contradictoire, ambigu, sources dupliquées, périmé, non vérifié, inter-tenant, sans preuves). Les attentes sont définies dans les tests, et ne sont pas des observations réelles.

Indicateurs : sélections correctes, faux positifs, causes manquées, abstentions correctes, taux d'abstention, précision des sélections (null si aucune sélection), exactitude par cas. Une sélection de la mauvaise cause, même sur un incident ayant une cause attendue, est comptée comme faux positif. Les cas sans cause attendue exigent l'abstention. Les doublons d'identifiants de cas et les attentes inconnues échouent fermés.

Ce benchmark de développement n'est pas un benchmark indépendant ou représentatif de production : il ne mesure ni la robustesse d'un LLM, ni l'ACL, ni l'authenticité des sources, ni les actions réelles. Les tests ont été ajoutés au dépôt, sans exécution locale ou succès CI revendiqué.

## Normalisation des identifiants de source

Les identifiants `source_id` sont normalisés par suppression des espaces de bord avant le calcul du nombre de sources distinctes. Ainsi `otel` et ` otel ` ne peuvent pas satisfaire le seuil de deux sources. La normalisation n'atteste **ni l'identité réelle, ni l'indépendance réelle** des systèmes déclarés. Les tests unitaires et le smoke test sans dépendance couvrent ce cas.

## Identifiants RCA non ambigus

Les identifiants d'hypothèse doivent être non vides et ne peuvent comporter d'espaces de bord. Les références de preuves sont comparées après suppression des espaces de bord pour détecter les doublons : `metric` et ` metric ` provoquent un rejet explicite. Le texte d'une référence valide est conservé pour le compte rendu ; ce contrôle ne certifie pas son origine. Les identifiants de source restent normalisés au comptage de l'indépendance déclarée.
