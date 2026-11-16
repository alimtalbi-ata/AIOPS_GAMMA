# GAMMA — matrice de qualification E2E (PR #1)

Statut : **HOLD / NO_GO**. Cette matrice décrit les preuves requises, pas une certification de production.

| Chaîne / besoin | Contrat vérifiable | Preuve disponible | Blocage / suite |
| --- | --- | --- | --- |
| Gateway → tenant → incident → preuve | Assertion HMAC liée à la méthode et au chemin, droit explicite, lecture/écriture cloisonnées | Tests HTTP simulés et nouveau `tests/test_evidence_http_postgres_e2e.py` (création/lecture deux tenants, écriture refusée, path binding) ; job CI ajouté | **Non exécuté sur PostgreSQL** : obtenir job steps/logs et attestation des migrations |
| Ressources persistées | Identité tenant uniquement depuis le principal vérifié, filtres SQL tenant+incident et limite 500 | Tests AST/HTTP avec inspection SQLAlchemy ; `tests/test_resource_list_http_postgres.py` raccordé au job dédié | Tests PostgreSQL non exécutés ; RLS absente/non qualifiée, concurrence/transactions/indexes à vérifier |
| OpenSearch logs | Recherche read-only, tenant/service/time, DLS côté cluster | Tests unitaires d'adaptateur et contrat `docs/OPENSEARCH-READ-CONTRACT.md` | DLS OpenSearch réel et tests négatifs inter-tenants non qualifiés |
| Inbox/outbox alertes | Retry idempotent, conflit 409, transaction atomique | Tests de logique ingestion ; scénario PostgreSQL ajouté pour deux tenants, idempotence, conflit 409, création inbox/outbox, et appel du relais vers HTTP MockTransport | Scénario PG non exécuté ; réessai HTTP 503 → 202 désormais couvert par test non exécuté ; concurrence même tenant/clé ajoutée au scénario PostgreSQL mais non exécutée |
| Corrélation / RCA / impact | Previews non autoritaires, provenance et incertitude | Fonctions et tests de previews | Sources canoniques, CMDB/ITSM et parcours utilisateur intégrés non qualifiés |
| Sentinel/ArgusLM KPI/SLO | Couverture, fenêtres, seuils, états indéterminés | Tests unitaires KPI/SLO | Mesures réelles, provenance, observabilité des erreurs et SLO métier |
| Policy / HITL / remédiation | Aucun effet LIVE sans décision qualifiée | Endpoints de prévisualisation read-only | Exécution interdite ; audit, approbation et contrôle d'effet à concevoir/qualifier |
| Frontend → BFF | Flux de navigation et erreurs 401/403/422/503 sans fuite | UI partiellement synthétique | Playwright sur build UI + BFF réel, accessibilité et états d'erreur |
| Déploiement | Compose, Helm, image rootless, migrations | Configurations et workflows présents | Job `tenant-evidence-postgres-e2e` ajouté au workflow (PG16 jetable, rôle non-superutilisateur, Alembic 0002) ; vérification d'exécution en attente, ancienne CI pré-step échouée |

## Livraisons de la reprise du 16 novembre 2026

- `8348a91` : test HTTP+PostgreSQL de création/lecture tenant-isolées, refus d'écriture et chemin signé, sur base explicitement jetable.
- `d9585f0` : CI PostgreSQL 16 avec rôle non-superutilisateur, migration et exécution des deux modules d'intégration ; non exécutée dans ce laboratoire.
- `9bc0f2a`, `b0cac16` : robustesse des DSN et du nettoyage des preuves de test.
- `04d7d4a` : refus de lecture sans grant ajouté au scénario PostgreSQL.
- `93e7071` : CI scindée entre tests indépendants de PostgreSQL et E2E sur base jetable ; les skips E2E sont rapportés, pas validés comme passes.
- `9c85efc`, `8580ded` : requêtes HTTP et vérifications PostgreSQL dans une seule boucle événementielle.
- `0dc0e0a` : droits d'incident explicites dans les assertions des anciens tests PostgreSQL.
- `9efdc79`, `36520bf` : nouveau scénario ingestion HTTP → PostgreSQL inbox/outbox → relais HTTP simulé, et nettoyage des écritures partielles par tenants éphémères.
- `3184717` : nettoyage des preuves E2E par tenants éphémères, y compris si la réponse HTTP manque après commit.
- `10da7f2` : scénario PostgreSQL du relais outbox avec HTTP 503, tentative différée et récupération HTTP 202 (récepteur simulé, non exécuté).
- `aaaeb63` : course entre deux requêtes HTTP pour la même clé d'alerte et le même tenant ; une seule paire inbox/outbox attendue (PG non exécuté).
- `bd73a4c` : contrôle fail-closed de l'ingestion désactivée (`503`, `no-store`, zéro ligne inbox/outbox) dans le scénario PG non exécuté.
- `3778015` : vérification que la même clé externe avec des charges utiles différentes reste indépendante entre tenants, tout en rejetant les conflits au sein d'un tenant (scénario PG non exécuté).
- `8930b8f` : ingestion d'alertes refuse les identités forgées sans assertion signée et les assertions liées à la mauvaise méthode (`401`), sans aucune écriture PG (scénario non exécuté).
- `8cda68d` : course entre deux charges utiles contradictoires sur la même clé/tenant ; une seule création (`200`), un conflit (`409`) et une seule paire inbox/outbox attendus (PG non exécuté).
- `5843277` : assertion signée insuffisante sans clé de service ; clé absente ou erronée → `401` et zéro écriture inbox/outbox (PG non exécuté).
- **Preuve d'exécution** : aucune réussite PG/CI attestée sur ces commits. Les résultats du laboratoire précédent concernent des tests isolés/simulés ; ils ne remplacent pas une qualification de bout en bout.
- **Limite architecturale importante** : le frontend est une démonstration synthétique qui bloque volontairement `/api` ; le parcours frontend → BFF réel n'est pas développé/qualifié. La sécurité ne doit pas être affaiblie pour produire artificiellement un test vert.

## Procédure de qualification

1. Exécuter `python -m pytest -q tests/test_evidence_resource_acl_http.py tests/test_gateway_assertion.py tests/test_gateway_resource_acl_contract.py` dans un environnement disposant des dépendances du projet.
2. Exécuter le job `tenant-evidence-postgres-e2e` du nouveau HEAD (migrations + `tests/test_resource_list_http_postgres.py` et `tests/test_evidence_http_postgres_e2e.py`, incluant ingestion/outbox/relais simulé) puis consigner les logs/étapes ; vérifier séparément RLS, contraintes et concurrence.
3. Exécuter les parcours API complets avec un émetteur d'assertions gateway **indépendant** et des assertions négatives (signature, expiration, méthode, chemin, tenant, ressource).
4. Exécuter la chaîne OpenSearch avec DLS effectif, les tests d'ingestion/outbox en concurrence et les parcours UI.
5. Récupérer les journaux CI, qualifier les runners et faire passer tous les jobs avant de lever HOLD.

**Ne pas confondre** un TestClient avec persistance simulée, une validation SQLAlchemy, une CI verte et une qualification E2E PostgreSQL/OpenSearch. Aucune autorisation LIVE, merge ou déploiement ne découle des tests actuels.
