# GAMMA — matrice de qualification E2E (PR #1)

Statut : **HOLD / NO_GO**. Cette matrice décrit les preuves requises, pas une certification de production.

| Chaîne / besoin | Contrat vérifiable | Preuve disponible | Blocage / suite |
| --- | --- | --- | --- |
| Gateway → tenant → incident → preuve | Assertion HMAC liée à la méthode et au chemin, droit explicite, lecture/écriture cloisonnées | Tests HTTP `tests/test_evidence_resource_acl_http.py`, y compris scénario deux tenants ; base simulée | Exécuter dans CI ; refaire sur PostgreSQL réel, avec deux tenants et migrations |
| Ressources persistées | Identité tenant uniquement depuis le principal vérifié, filtres SQL tenant+incident et limite 500 | Tests AST et HTTP avec inspection SQLAlchemy | Vérifier sur PostgreSQL : RLS/permissions, concurrence, transactions et indexes |
| OpenSearch logs | Recherche read-only, tenant/service/time, DLS côté cluster | Tests unitaires d'adaptateur et contrat `docs/OPENSEARCH-READ-CONTRACT.md` | DLS OpenSearch réel et tests négatifs inter-tenants non qualifiés |
| Inbox/outbox alertes | Retry idempotent, conflit 409, transaction atomique | Tests de logique ingestion | PostgreSQL réel : unicité, concurrence, rollback, publication/retry worker |
| Corrélation / RCA / impact | Previews non autoritaires, provenance et incertitude | Fonctions et tests de previews | Sources canoniques, CMDB/ITSM et parcours utilisateur intégrés non qualifiés |
| Sentinel/ArgusLM KPI/SLO | Couverture, fenêtres, seuils, états indéterminés | Tests unitaires KPI/SLO | Mesures réelles, provenance, observabilité des erreurs et SLO métier |
| Policy / HITL / remédiation | Aucun effet LIVE sans décision qualifiée | Endpoints de prévisualisation read-only | Exécution interdite ; audit, approbation et contrôle d'effet à concevoir/qualifier |
| Frontend → BFF | Flux de navigation et erreurs 401/403/422/503 sans fuite | UI partiellement synthétique | Playwright sur build UI + BFF réel, accessibilité et états d'erreur |
| Déploiement | Compose, Helm, image rootless, migrations | Configurations et workflows présents | GitHub Actions en échec avant allocation runner ; aucune preuve de runtime |

## Procédure de qualification

1. Exécuter `python -m pytest -q tests/test_evidence_resource_acl_http.py tests/test_gateway_assertion.py tests/test_gateway_resource_acl_contract.py` dans un environnement disposant des dépendances du projet.
2. Rejouer le scénario deux tenants sur PostgreSQL réel et vérifier les tables, la séparation, les transactions et les contraintes.
3. Exécuter les parcours API complets avec un émetteur d'assertions gateway **indépendant** et des assertions négatives (signature, expiration, méthode, chemin, tenant, ressource).
4. Exécuter la chaîne OpenSearch avec DLS effectif, les tests d'ingestion/outbox en concurrence et les parcours UI.
5. Récupérer les journaux CI, qualifier les runners et faire passer tous les jobs avant de lever HOLD.

**Ne pas confondre** un TestClient avec persistance simulée, une validation SQLAlchemy, une CI verte et une qualification E2E PostgreSQL/OpenSearch. Aucune autorisation LIVE, merge ou déploiement ne découle des tests actuels.
