# Contrat de décision AIOps en shadow mode — UC02 à UC10

**Statut : expérimental, synthétique, non autoritatif.** Code : `app/reused/shadow_incident_journey.py`. Tests : `tests/test_shadow_incident_journey.py` et `tests/test_synthetic_end_to_end_usecase.py`.

## Objectif métier

Pour un même tenant et un même incident : détecter et corréler les signaux, identifier les dépendances, établir une RCA avec preuves contradictoires, proposer un runbook approuvé, demander une autorisation indépendante, vérifier les SLI après action, puis réconcilier l'ITSM et préparer un postmortem. La chaîne de production n'est **pas** implémentée par ce module : il agrège uniquement trois évaluateurs purs, sans accès réseau, stockage, agent, Core ou Temporal.

## Contrat de sortie

`evaluate_incident_shadow(IncidentShadowInput(...))` retourne :
- `tenant_id`, `incident_id`, `service` et `mode=synthetic_shadow`.
- `stages.runbook` : `ABSTAIN` ou `REVIEW_CANDIDATE`, motifs, version de recette et SLI de vérification si sélection unique.
- `stages.autonomy` : `ABSTAIN` ou `REVIEW_CANDIDATE`, avec les contrôles manquants.
- `stages.recovery` : `UNKNOWN`, `RECOVERED` ou `NOT_RECOVERED` **uniquement sur des mesures synthétiques**, avec proposition de revue de rollback si le SLI reste dégradé.
- `execution_state=NOT_EXECUTED` par défaut ; `SYNTHETIC_ACTION_ONLY` si l'appelant indique une action simulée. Cette indication n'est **jamais** une preuve d'exécution.
- `authoritative=false`, `live_execution_authorized=false`, `itsm_mutations_performed=false` dans tous les cas.

## Garde-fous

1. Aucune RCA `unknown` ou `rejected` ne sélectionne un runbook ; les contradictions et l'absence de preuves vérifiées bloquent l'autonomie.
2. Aucun runbook ambigu, non approuvé ou sans rollback défini n'est sélectionné.
3. Une mesure post-action fournie sans action simulée produit `UNKNOWN`, jamais `RECOVERED`.
4. Une action simulée et un SLI redevenu conforme ne constituent **pas** une guérison réelle, une permission d'exécution, une autorisation de clôture ITSM ni une preuve de monitoring authentifié.
5. Les booléens `policy_approved` et `hitl_approved` sont des entrées de simulation, **pas** des reçus signés ou vérifiés.
6. Les champs tenant et incident ne sont que des identifiants déclarés ; aucune ACL actor→tenant→resource n'est démontrée.

## Prochain jalon d'autonomie

Après déblocage de la CI (#8) et qualification de l'identité/ACL (#2), connecter **une source d'alertes et un service** en lecture seule, ajouter des références de preuves immuables, exécuter une RCA multi-étapes en shadow mode avec benchmark adjudiqué, puis qualifier séparément Policy/HITL, Core/Temporal, fencing, rollback et mesures SLI de staging. **HOLD / NO_GO LIVE** jusqu'à ces preuves.
