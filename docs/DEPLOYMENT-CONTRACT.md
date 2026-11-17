# Contrat de déploiement universel — Docker Compose + Kubernetes

**Décision d'architecture obligatoire (2026-11-09)** : chaque composant **exploité par AIOPS_GAMMA** doit être livré sous forme d'image OCI versionnée, déployable via **Docker Compose** et **Kubernetes/Helm**. Cette règle couvre les services de la plateforme et ses dépendances auto-hébergées. Un fournisseur SaaS ou une instance GLPI/SSO externe reste un service externe : on déploie son connecteur, pas nécessairement le service tiers. Aucune fonctionnalité de production ne doit exiger un lancement manuel hors de ces orchestrateurs.

## Parité fonctionnelle, pas identité d'infrastructure

- **Compose** : profil `core` (UI, API, Core, Policy, Evidence, worker, bus et stockage minimal), `observability` (OTel, OpenSearch, Prometheus/Cortex, Alertmanager), `llm-kpi` (Sentinel/ArgusLM), `investigation` (moteur choisi), `demo` (fixtures explicitement synthétiques), `integration` (tests).
- **Kubernetes** : charts Helm versionnés (umbrella chart GAMMA + charts upstream épinglés) ; namespaces, ServiceAccounts/RBAC minimaux, NetworkPolicy, Deployments, StatefulSets/PVC ou services managés externes déclarés, Jobs de migration et CronJobs si nécessaires.
- Les images, ports applicatifs, endpoints de santé, variables d'environnement, schémas d'événements, auth interservices et politiques de sécurité doivent être identiques conceptuellement. La haute disponibilité, le stockage, les volumes et les mécanismes de secret peuvent différer.
- Ne pas déployer une base de données ou un ordonnanceur en doublon lorsque le Core canonique en possède déjà un. Les profils Compose et les sous-charts Helm peuvent activer/désactiver les dépendances **sans casser les contrats**.

## Matrice de livraison

| Domaine / composant | Docker Compose | Kubernetes / Helm | Responsable et contrainte |
| --- | --- | --- | --- |
| GAMMA UI React / reverse proxy | `gamma-ui` | Deployment + Service + Ingress/Gateway | HTTPS, CSP, pas de secrets dans le navigateur |
| GAMMA BFF FastAPI | `gamma-api` | Deployment + Service + HPA optionnel | tenant auth, liveness/readiness, quotas |
| Core canonique + Policy + Evidence + Twin | services `aiops-*` | Deployments isolés | Un seul writer incident/run ; API internes |
| Temporal/Worker | `temporal`, `aiops-worker` | chart Temporal épinglé + Worker Deployment | durable, idempotent, ne pas exposer l'exécuteur |
| OTel Collector / Data Prepper | `otel-collector`, `data-prepper` | charts/Deployments/DaemonSet selon besoin | ingestion OTLP et egress contrôlés |
| OpenSearch | `opensearch` | StatefulSet/chart ou endpoint managé explicite | stockage persistant, TLS, quotas et sauvegardes |
| Cortex/Prometheus + Alertmanager | services dédiés | charts épinglés, PVC | retention, tenant isolation, rules |
| Sentinel LLM | `sentinel` | Deployment + Service | API/métriques en lecture côté GAMMA |
| ArgusLM | `arguslm-api` (+ scheduler selon packaging) | Deployment + worker/CronJob si requis | coûts estimés, secrets fournisseurs, quotas |
| Enquêteur IA sélectionné | profil `investigation` | Deployment/Job isolé | outils read-only allowlist, aucun privilège de mutation |
| Redis/Postgres/bus (si requis) | volumes nommés | StatefulSet/PVC ou service managé | pas de données critiques dans conteneur éphémère |
| GLPI / SSO / providers externes | connecteur/config `external` | Secret + Service/ExternalName ou endpoint configuré | aucune obligation de réhéberger un SaaS |

Les noms de service ci-dessus sont des **noms cibles** ; ils ne prétendent pas que les manifests correspondants existent déjà dans GAMMA.

## Packaging minimal de chaque composant

1. `Dockerfile` multi-stage, image non-root si possible, architecture cible définie, tags immuables **par digest**, SBOM, analyse vulnérabilités et signature selon politique CI.
2. Configuration par environnement, `.env.example` sans secrets pour Compose ; Secret/External Secrets pour Kubernetes, jamais de clé dans Git.
3. Healthchecks Compose et probes Kubernetes (startup/readiness/liveness), arrêt SIGTERM propre, timeout et retry bornés.
4. `cpu/memory` requests/limits K8s ; limites Compose adaptées ; PVC et politique de backup/restore pour état persistant.
5. Journalisation structurée stdout, métriques Prometheus/OTel, trace context et audit tenant-safe ; redaction de prompts/secrets.
6. Identité de service, TLS/mTLS selon frontière, RBAC, NetworkPolicy et règles d'egress. Compose ne remplace pas les contrôles de production K8s.
7. Scripts de migrations idempotents avec plan de retour arrière ; jamais de migration destructive automatique non approuvée.

## Structure cible du dépôt

```text
deploy/
  compose/
    compose.yaml                 # profil core
    compose.observability.yaml   # dépendances optionnelles
    compose.llm-kpi.yaml
    compose.investigation.yaml
    compose.demo.yaml
    .env.example
  helm/
    gamma/                       # umbrella chart, values.yaml
      templates/                 # UI/BFF et garde-fous
      values-dev.yaml
      values-staging.yaml
      values-prod.yaml
  scripts/
    smoke.sh
    check-contracts.sh
```

Les charts upstream peuvent être référencés comme dépendances Helm **avec versions épinglées** ; les manifests upstream ne doivent pas être copiés sans contrôle de licence, sécurité et compatibilité.

## Pipeline CI/CD obligatoire

1. **Build** images OCI par commit et contrôle des dépendances, SBOM, signature et scan.
2. **Compose** : `docker compose -f deploy/compose/compose.yaml config --quiet`, `up -d --wait`, smoke tests, tests inter-tenant, arrêt et nettoyage ; valider aussi les profils optionnels.
3. **Helm** : `helm lint`, `helm template` pour dev/staging/prod, vérification schéma/policies (ex. kubeconform, policy-as-code), tests d'absence de privilèges et de secrets en clair.
4. **Staging K8s** : déploiement en namespace isolé, migrations, tests contractuels entre services, persistence/backup, observabilité et coupure réseau ; qualification GLPI en lecture seule.
5. **Promotion** : images par digest, approbation humaine, déploiement progressif, rollback testé, collecte d'éléments de preuve. **Aucune promotion LIVE depuis une PR draft.**

## Critères de recette par composant

- [ ] Image OCI versionnée, digest traçable, licences et dépendances examinées
- [ ] Démarrage Compose reproductible + smoke tests sans secret réel
- [ ] Déploiement Helm/K8s et probes vérifiés en staging
- [ ] Parité API/schema/config et isolation tenant testées
- [ ] Volumes, sauvegardes, restauration et arrêt propre vérifiés si état persistant
- [ ] Journalisation, métriques, traces, redaction et alertes testées
- [ ] RBAC, réseau, egress, secrets, deny-by-default vérifiés
- [ ] Rollback et documentation d'exploitation validés

**État réel** : ce document est une spécification cible. La présence de Dockerfiles, compose files ou charts dans les dépôts sources n'implique pas qu'un déploiement GAMMA intégré, sécurisé et qualifié existe déjà. Les composants non encore packagés dans les deux formats constituent des écarts à résoudre avant mise en production.
