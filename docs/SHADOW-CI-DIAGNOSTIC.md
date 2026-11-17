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
