# Diagnostic CI — shadow RCA (2026-11-17)

## Observation GitHub

Le workflow `Python checks` (run 44180794321) signalait quatre jobs en échec : `gateway-replay-postgres`, `test`, `tenant-evidence-postgres-e2e`, `frontend`. La consultation des étapes de chacun de ces jobs a renvoyé une liste vide. La récupération des journaux a retourné une erreur de ressource introuvable (`BlobNotFound`).

**Conclusion limitée :** aucun test Python, frontend ou PostgreSQL n'est attesté comme exécuté par ces réponses. L'échec peut provenir de la planification du runner ou d'un incident de service ; les données consultées ne permettent pas d'identifier la cause racine.

## Mesure de diagnostic

Le workflow `.github/workflows/shadow-rca-checks.yml` fournit une voie de qualification séparée et strictement hors ligne, sur `ubuntu-latest` et Python 3.11. Il compile les modules RCA et lance cinq fichiers de tests synthétiques, sans secrets, PostgreSQL, connecteur, mutation ITSM ou action de remédiation.

Déclenchement manuel possible (`workflow_dispatch`) et sur PR lorsque les chemins shadow changent. La présence du workflow **n'implique pas** qu'un runner a démarré, qu'un test a réussi ou que la CI globale est réparée.

## Critères de levée du blocage de qualification

1. Obtenir un job avec `runner_id` non nul et des étapes effectivement renseignées.
2. Observer les étapes de compilation et pytest terminées avec succès, avec logs récupérables.
3. Contrôler séparément les jobs Python, frontend et PostgreSQL de la CI générale.
4. Conserver la PR en Draft et `HOLD / NO_GO LIVE` tant que ces vérifications et les contrôles de provenance/ACL réelles ne sont pas achevés.

## Nouvelle observation et qualification de secours

Le run 44181341370 du workflow isolé s'est terminé en `failure`, avec un job `shadow-contracts` dont la liste d'étapes est vide. Les runs 44181341372 (`Python checks`) et 44181341464 (`Deployment contract`) sont également en échec. Cela ne constitue pas une preuve d'échec des tests applicatifs.

Un script Python sans dépendance tierce (`scripts/check_shadow_rca_stdlib.py`) permet désormais de vérifier localement des invariants de décision, refus de tenant, source dupliquée, contradiction, fraîcheur, empreinte et métriques du benchmark. Commande depuis la racine : `python scripts/check_shadow_rca_stdlib.py`. Le workflow isolé exécute ce smoke test **avant** l'installation de pytest. Ce script est une qualification partielle, pas un substitut à la suite complète. Aucun résultat d'exécution de ce script n'est revendiqué dans cette livraison.
