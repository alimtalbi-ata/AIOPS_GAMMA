# Gateway — contrat ACL métier (provisoire, HOLD)

## Émission
Le Gateway authentifie l'acteur, vérifie son appartenance tenant et ses droits dans une source ACL indépendante. Il ne recopie jamais des permissions fournies par le client. Il supprime les en-têtes identité entrants non fiables et transmet X-Internal-API-Key et X-Gateway-Principal sur un canal interne protégé. Le contrôle réseau/mTLS reste à qualifier.

Assertion : base64url sans padding du JSON UTF-8, point, base64url sans padding du HMAC-SHA256 du premier segment ASCII. Secret partagé distinct de la clé API, minimum 32 octets, jamais journalisé. Claims : iss, aud, sub, actor_type (user/service), jti unique, iat, exp, method, path, tenant_id (UUID canonique non nul), tenant_access=true. TTL maximum 60 secondes, tolérance iat futur 5 secondes. Une assertion par tentative HTTP; le rejeu est rejeté après consommation PostgreSQL.

## Permissions métier signées
business_permissions est une liste sans doublon, limitée aux cinq valeurs suivantes. Absence = aucun droit.

| Méthode | Route | Permission | Contrôle complémentaire |
|---|---|---|---|
| POST | /api/v1/integrations/opensearch/alerts | alerts:ingest | Feature flag |
| GET | /api/v1/topology/bindings | bindings:read | Tenant |
| POST | /api/v1/topology/bindings | bindings:write | Tenant |
| GET | /api/v1/incidents/{incident_id}/evidence | evidence:read | evidence_incident_grants exact |
| POST | /api/v1/incidents/{incident_id}/evidence | evidence:write | evidence_incident_grants exact |

Les recherches logs exigent log_service_grants exact. Ces permissions ne couvrent pas exhaustivement les autres routes, notamment les snapshots upstream. Aucun wildcard. Les permissions ne sont pas une approbation de remédiation.

## Révocation et rotation
Le Gateway doit cesser d'émettre immédiatement après révocation de l'accès. Une assertion déjà signée non consommée peut rester utilisable jusqu'à exp; aucune révocation immédiate côté Gamma n'est implémentée. Le mode registre GATEWAY_ASSERTION_KEYS (objet JSON kid → secret) exige un kid signé connu et GATEWAY_ASSERTION_SECRET vide. Le mode historique mono-clé interdit kid. En transition, configurer K1 et K2 sur toutes les instances, puis émettre avec K2, attendre expiration des assertions K1 ou retirer K1 immédiatement en cas de compromission. Le retrait doit être propagé sur toutes les instances. Aucun rechargement dynamique ni coffre-fort intégré. Le replay reste indexé par issuer et jti, indépendamment du kid; qualification concurrente inter-clés restant à faire. Procédure de rotation, propagation des ACL et séparation des responsabilités à valider avant LIVE.

## Qualification
401 pour assertion invalide/rejouée; 403 pour permission absente; 503 si protection replay indisponible. Les tests synthétiques ne démontrent pas la validité de l'IdP, des ACL upstream ou du canal réseau. Contrat incompatible avec anciens émetteurs sans business_permissions sur ces cinq opérations. HOLD / NO_GO LIVE, PR draft, aucun déploiement.
