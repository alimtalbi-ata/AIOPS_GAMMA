# Contrat d'installation monorépertoire et rootless

**Exigence propriétaire (2026-11-09) — cible obligatoire**, non encore satisfaite par tous les composants. La plateforme GAMMA et ses dépendances auto-hébergées doivent être exploitables à partir d'une **unique racine configurable** `GAMMA_HOME`, sans installation d'artefacts applicatifs dans `/bin`, `/sbin`, `/var`, `/tmp` ou d'autres répertoires système **de l'hôte**.

## Limites à expliciter

- Les images Linux de base contiennent normalement `/bin`, `/usr`, `/lib`, etc. ; leur lecture **à l'intérieur** des images n'est pas une dépendance d'installation sur l'hôte. Il serait faux de promettre qu'aucune image n'utilise ces chemins.
- Un conteneur `USER 10001` est **non-root dans le conteneur** mais ne rend pas Docker Engine rootless. Il faut un daemon Docker rootless (ou Podman rootless avec compatibilité Compose vérifiée).
- Kubernetes ne garantit pas un kubelet/runtime rootless ni un stockage entièrement sous `GAMMA_HOME` : ces éléments appartiennent à l'administrateur du cluster. Le contrat monorépertoire s'applique à **l'arborescence et aux données gérées par l'installation GAMMA**, avec une exception explicitement documentée pour le runtime/cluster externe. Kubernetes peut utiliser PVC/CSI hors de cette arborescence si le stockage est administré par la plateforme ; cela **ne satisfait pas** une exigence d'isolation physique absolue.
- Le daemon rootless peut utiliser les chemins XDG de l'utilisateur (`$HOME/.local/share/docker`, `$XDG_RUNTIME_DIR`) et un socket utilisateur. Pour satisfaire un périmètre strict, configurer un `data-root` sous `GAMMA_HOME` et contrôler le runtime rootless selon les contraintes du système. Les mécanismes de namespaces, cgroups et réseau rootless peuvent nécessiter des prérequis système installés **hors** du répertoire (uidmap/subuid/subgid, systemd utilisateur, kernel). Une machine sans aucun prérequis système n'est **pas** garantie.

## Arborescence cible

```text
$GAMMA_HOME/
  bin/                 # lanceurs livrés par le projet, non dans /usr/bin
  config/              # configurations non secrètes
  secrets/             # permissions 0700/0600, jamais commitées
  compose/             # fichiers Compose versionnés
  helm/                # charts et values versionnés
  images/              # archives OCI facultatives pour mode offline
  docker-data/         # data-root Docker rootless, si configuré
  data/
    postgres/
    opensearch/
    prometheus/
    temporal/
    sentinel/
    arguslm/
  logs/                # exports optionnels ; stdout/stderr en priorité
  run/                 # sockets/PID applicatifs si nécessaires
  cache/               # cache applicatif contrôlé
  backups/             # sauvegardes chiffrées et testées
  releases/            # versions immuables et rollback
```

**Règles** : chemins relatifs à `GAMMA_HOME` ; aucun `sudo` dans les scripts applicatifs ; aucun bind mount sur les répertoires système ; ports non privilégiés ; pas de `privileged`, `hostPID`, `hostNetwork` ou montage de `/var/run/docker.sock`. Fichiers secrets hors Git, permissions minimales, sauvegarde/restore dans la racine ou destination explicitement approuvée.

## Contrat Docker Compose

- Définir `GAMMA_HOME` (chemin absolu) et vérifier qu'il existe et appartient à l'utilisateur courant ; refuser les chemins système interdits et liens symboliques sortant du périmètre.
- Déployer tous les volumes persistants applicatifs en bind mounts **sous** `GAMMA_HOME/data` ; configurer les chemins temporaires applicatifs sous `GAMMA_HOME/cache` ou `GAMMA_HOME/run`.
- Éviter les volumes Docker nommés pour une exigence stricte de localisation : ils sont gérés par le daemon, éventuellement hors `GAMMA_HOME`.
- Exécuter avec Docker Engine rootless et `DOCKER_HOST` pointant vers le socket rootless de l'utilisateur. Vérifier le mode rootless réellement actif et refuser de continuer si absent.
- `read_only: true` lorsque les composants le permettent ; `tmpfs` en mémoire à chemin interne documenté pour les composants qui exigent `/tmp` ; `cap_drop: [ALL]`, `security_opt: [no-new-privileges:true]`, `user: UID:GID` si l'image le permet.
- Certains services upstream (OpenSearch, PostgreSQL, Temporal, OTel) nécessitent un test spécifique des UID, ownership, locks, répertoires de travail et `tmpfs`. Ne pas imposer un `read_only` global avant validation.

## Contrat Kubernetes

- `runAsNonRoot: true`, `runAsUser`/`runAsGroup`, `allowPrivilegeEscalation: false`, `capabilities.drop: [ALL]`, `seccompProfile: RuntimeDefault`, `automountServiceAccountToken: false` sauf besoin explicite.
- `readOnlyRootFilesystem: true` pour les workloads compatibles, `emptyDir` mémoire/volume pour les écritures indispensables, PVC pour les données persistantes, `fsGroup` testé selon CSI.
- Pas de `hostPath` ni de conteneur privilégié ; Pod Security Standards **restricted** à viser en staging.
- La contrainte « un seul répertoire physique sur le nœud » ne peut être assurée avec un cluster managé et des PVC/CSI externes. Pour une installation Kubernetes sur hôte dédié, documenter le `data-dir` du runtime, le chemin kubelet, le stockage CSI et les prérequis ; ne pas annoncer l'absence de dépendance système tant qu'elle n'est pas vérifiée.

## Recette de conformité

1. Sur hôte de test, vérifier Docker rootless et les prérequis système, puis définir `GAMMA_HOME` et `DOCKER_HOST` explicitement.
2. Démarrer avec volumes bindés sous `GAMMA_HOME` ; vérifier `docker inspect` pour chaque montage, UID/GID, privilèges, sockets, chemins temporaires et processus.
3. Vérifier que le daemon rootless utilise un `data-root` autorisé et que les données ne sont pas éparpillées sous `/var/lib/docker`.
4. Tester redémarrage, backup, restauration, migration, rollback, suppression de release et mode offline.
5. Pour Kubernetes, contrôler Pod Security restricted, les SecurityContexts, PVC, Secrets, les répertoires de stockage effectifs et les limites de la distribution choisie.
6. Publier une matrice de conformité **par composant** ; refuser la qualification globale tant que l'un d'eux exige root, un hostPath, un daemon rootful ou des écritures hôte hors racine.

## Écarts existants à résoudre

Le `docker-compose.yml` actuel utilise des volumes nommés `pgdata` et `osdata`, donc leur localisation dépend du daemon. Le chart Helm initial n'applique pas encore `runAsNonRoot` à Nginx (port 80, image upstream) ni `readOnlyRootFilesystem` partout. Le mode rootless du daemon, les volumes de tous les services upstream, les besoins en `/tmp` internes et la parité Kubernetes ne sont pas qualifiés. **Ce document est une spécification et une liste d'écarts, pas une preuve de conformité.**
