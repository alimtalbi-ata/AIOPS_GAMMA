# Audit de compatibilité des lectures canoniques AIOps — 2026-11-12

## Décision

**NO_GO pour toute activation Core / Evidence / Twin depuis GAMMA.** Les dépôts contiennent des capacités réutilisables, mais l'audit statique des endpoints upstream ne démontre pas une ACL multi-tenant. Le simple transfert de `X-Tenant-Id`, un bearer partagé ou un champ `tenant_id` renvoyé par le serveur ne constitue pas une autorisation.

## Sources inspectées (refs exactes)

- `alimtalbi-ata/aiops`, branche `main`, `app/core/main.py`, blob `43b61a08d4dd099c7c28ee0d73e5a3e1f681cdca`.
  - Routes observées : `/api/incidents`, `/api/runs`, `/api/runs/{rid}`, `/api/noc/runs/{rid}`, etc. Pas de préfixe `/api/v1/incidents` dans le routeur inspecté.
  - Le fichier importe `reject_unqualified_tenant_scope`, mais cette seule importation ne prouve pas son application à chaque route. Le source inspecté ne contient pas de champ `tenant_id` (0 occurrence) dans ce routeur.
  - L'authentification visible utilise un token interne partagé; aucune preuve de membership actor→tenant ni de filtre de ressource par tenant n'a été établie dans ce fichier.
- `alimtalbi-ata/aiops`, `app/evidence/main.py`, blob `c581d407c8e84de87acbdf749a4e2aa8f052dedf`.
  - `GET /api/evidence` et `GET /api/evidence/{eid}` ne montrent pas d'authentification, de tenant scope ou de filtre tenant dans le routeur inspecté.
- `alimtalbi-ata/aiops`, `app/twin/main.py`, blob `e098ec039b5f352f537ed8985e721067a1386508`.
  - Les routes GET `/api/twin/summary`, `/api/twin/nodes`, `/api/twin/graph`, `/api/twin/impact/{node_id}`, `/api/twin/at` ne montrent pas de principal ni de filtre tenant dans le routeur inspecté.
- GAMMA `app/reused/upstream.py`, blob `e7a34575a02803de243c56b8d69ed4910c8d7943`.
  - Adaptateur GET-only, origines HTTPS fixes, redirects désactivés, proxy d'environnement désactivé, TLS vérifié, timeout 3s, corps JSON limité à 256 KiB et écho tenant vérifié.
  - Les chemins configurés (`/api/v1/incidents`, `/api/v1/evidence`, `/api/v1/topology`) ne correspondent pas aux routes observées dans les fichiers Core/Evidence/Twin ci-dessus.
  - La vérification d'un `tenant_id` dans la réponse est une cohérence de payload, pas une preuve d'ACL amont.

## Réutilisation conservée

- `aiops` reste le propriétaire canonique des incidents/runs, Evidence, Twin, Policy et Worker. GAMMA ne crée pas de second writer.
- `observability-stack` reste le candidat de collecte OTel/Data Prepper/OpenSearch/Cortex. GAMMA doit consommer des API tenant-aware en lecture seule; ne pas exposer les backends directement au navigateur.
- `aurora`, `holmesgpt`, `akmatori-sre` et `incidentfox-sre` restent des candidats d'investigation à comparer en shadow mode, pas des exécuteurs à connecter. Aucun outil shell/cloud ni action automatique n'est autorisé par cet audit.

## Travail requis avant reprise de #2

1. Dans `aiops`, identifier le middleware/guard tenant réellement appliqué à chaque route Core/Evidence/Twin et ses tests. L'import d'un helper n'est pas une preuve.
2. Définir un contrat inter-service authentifié (OIDC/mTLS ou assertion signée à audience/service/route) avec actor, tenant, scopes et identité du workload; le service amont doit dériver/valider l'accès côté serveur.
3. Ajouter un filtre tenant obligatoire au niveau query/service/DB pour chaque ressource et un test positif + refus croisé pour chaque route. Si le modèle de données canonique n'a pas de tenant, ne pas exposer ces données comme multi-tenant.
4. Fixer les vrais chemins, schémas, pagination et contrats de Core/Evidence/Twin après qualification; ne pas deviner les URLs.
5. Ajouter des tests HTTP contractuels contre deux tenants dans un environnement PostgreSQL jetable; vérifier refus 401/403, absence de fuite, timeout, redirect, payload invalide et indisponibilité.
6. Seulement après ces preuves, créer des adaptateurs GAMMA distincts à scopes minimaux. Garder `ENABLE_CANONICAL_READS=false` jusque-là.

## Statut

Audit de source statique uniquement. Aucun service upstream appelé, aucun test PostgreSQL/HTTP d'intégration exécuté, aucune ACL runtime qualifiée. Ne pas fusionner ni déployer sur la base de ce document seul.


## Addendum — current fail-closed state, 2026-11-16

This addendum supersedes any implication in the original snapshot that the current Gamma adapters perform live upstream reads or validate a tenant echo. At current branch HEAD before this addendum, `app/reused/upstream.py:fetch_canonical` unconditionally returns HTTP 503 for every known resource before creating an HTTP client, even if the legacy enable flag and service token are configured. `app/reused/glpi_read.py:read_glpi_incident` likewise unconditionally returns HTTP 503; its private `_read_glpi_incident_unqualified` helper is not called by the API entrypoint and is not an authorization boundary. No canonical Evidence/Twin/Core or GLPI network reads are enabled.

The current source-level upstream review additionally confirms that the inspected Evidence and Twin GET handlers do not show actor/tenant/resource ACL enforcement. The canonical Portal GLPI handoff explicitly says it will not issue GLPI/Core requests before independently verified server-derived actor+tenant ACL and authoritative ticket/Run mapping. Therefore the older transport-contract observations above are historical design/test notes only, not evidence of an enabled or qualified adapter.

A static regression tripwire was added in `tests/test_tenant_integration_hold_guard.py` to assert that both public unqualified read entrypoints contain no HTTP client or request calls and raise fail-closed. This source-level guard is not a substitute for pytest execution or upstream ACL integration tests. No test execution is claimed. **NO_GO remains.**
