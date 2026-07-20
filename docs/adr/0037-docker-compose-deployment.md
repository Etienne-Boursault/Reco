# ADR 0037 — Docker Compose : pipeline + review + site en 1 commande

- Statut : Acceptée
- Date : 2026-06-11
- Décideurs : équipe Reco
- Roadmap item : #18 (Phase 3, Vague 1)

## Contexte

Reco est un kit duplicable (Astro 5 + Python 3.12) destiné à être self-hosté
par des forks (autres podcasts). Le mode d'emploi actuel impose à un nouvel
adoptant de :

1. Installer Node 20 + npm,
2. Installer Python 3.12 + créer un venv,
3. `pip install -r tools/requirements.txt` (incl. `fastembed`, `faster-whisper` —
   nécessitent `build-essential`),
4. Lancer trois processus séparés (pipeline, review_server, `astro dev`),
5. Gérer les variables d'env (TMDB, Spotify, secrets reports…).

Friction réelle : 30-60 min de setup, échecs fréquents (toolchain C++ pour
onnxruntime, conflit Python système vs venv, ports occupés). Pour un kit qui
se veut « fork-then-run », c'est trop.

Options envisagées :

- **Image monolithique unique** : `python:3.12` + Node + tout copié. Lourd
  (~1.5 GB), difficile à patcher, mélange surfaces d'attaque.
- **Kubernetes / Helm** : surdimensionné pour un kit mono-utilisateur. Aucun
  besoin de scaling, scheduling, ingress.
- **Procfile + foreman / systemd units** : peu portable, n'isole pas les
  toolchains (Node ↔ Python).
- **Nix / devcontainer** : intéressant pour le dev mais ne livre pas une
  cible de déploiement.
- **Docker Compose multi-services** : standard, portable amd64+arm64,
  multistage = image runtime fine, profiles pour les jobs ponctuels.

## Décision

On adopte Docker Compose comme cible d'entrée du kit, avec un Dockerfile
multistage qui sépare la chaîne Node de la chaîne Python.

### Architecture

```
Dockerfile (multistage)
├── node-builder    : npm ci + astro build  → /app/dist
├── python-builder  : venv + pip install    → /app/.venv
└── runtime         : python:3.12-slim + curl/jq
                     ← copies .venv, dist/, tools/, src/content/, docker/

docker-compose.yml
├── reco-review    (port 8000)  : review_server local
├── reco-site      (port 4321)  : `python -m http.server` sur dist/
└── reco-pipeline  (profile)    : build_cache + lints + audits
```

Une seule commande pour démarrer : `docker compose up`.

### Détails d'implémentation

- **Bind 0.0.0.0** : `tools/review_server.py:100` instancie
  `HTTPServer(("127.0.0.1", port), …)` en dur. Hors conteneur c'est correct
  (mono-utilisateur, surface d'attaque réduite). En conteneur, ce bind n'est
  pas joignable depuis l'hôte. On évite de patcher review_server.py (zone
  Phase 2 close, gardée stable) et on introduit `docker/review_launcher.py`
  qui monkeypatche `http.server.HTTPServer.__init__` avant l'import. Single
  point of change.
- **Healthcheck** : review_server n'expose pas de `/healthz`. On utilise un
  TCP check Python embarqué dans l'image (`socket.connect_ex`), pas de
  dépendance externe à `curl --fail-with-body`.
- **Volumes** : `./src/content` (données éditables) et `./tools/output`
  (caches SQLite, embeddings, audits) sont mountés en bind — évite que les
  caches re-coûteux (TMDB, embeddings ~150 MB) soient perdus à chaque
  `down`.
- **Secrets** : `.env` mounté via `env_file` Docker Compose, jamais
  `COPY .env`. `.dockerignore` exclut `.env`, `tools/.env`, `.env.*`
  (sauf `.env.example` whitelisté).
- **Profiles** : `reco-pipeline` est opt-in (`--profile pipeline`) — c'est
  un job ponctuel, pas un long-running service.
- **Multi-arch** : `python:3.12-slim` et `node:20-slim` publient amd64+arm64.
  Build local utilisable tel quel ; pour publier multi-arch :
  `docker buildx build --platform linux/amd64,linux/arm64 …`. Pas exécuté
  Phase 3 (publication d'image hors scope).
- **Root vs non-root** : runtime tourne en root. Justifié pour Phase 3 :
  volumes mountés du host (UID arbitraire), pas de mode prod multi-tenant.
  À revisiter si on publie une image officielle (gh ghcr) → user `reco`
  non-root + chown adapté.

## Conséquences

### Positives

- **Setup divisé par 10** : `cp .env.example .env && docker compose up`,
  environ 3-5 min de cold build, <10 s après.
- **Reproductible** : même image sur amd64/arm64, isolation Node ↔ Python.
- **Toolchain encapsulée** : pas besoin de `build-essential` sur l'hôte,
  même pour les libs C++ (onnxruntime, ctranslate2).
- **Itération local rapide** : volume `./src/content` permet d'éditer les
  recos JSON et de voir le changement dans review_server sans rebuild.
- **Discoverable** : `Makefile` documente les opérations courantes,
  `docker compose ps` donne l'état.

### Négatives

- **Dépendance à Docker** : exclut les forkeurs qui ne veulent pas
  l'installer. Compensé par la doc qui maintient le chemin natif.
- **Image dev ~600 MB** (slim + venv pipeline). Pas un blocker pour un kit
  self-host (vs ~50 MB d'un Go binaire), mais à monitorer si on ajoute
  `torch`/CUDA dans le pipeline.
- **Réplication données** : `./tools/output` mounté → si le forkeur efface
  ce dossier, il perd ses caches. Doc à venir (`docs/fork-guide.md §Docker`).

### Notes

- Critère de bascule : si le kit grossit au-delà de ~10 services
  (microservices internes), on évalue K8s. Aujourd'hui : 3 services dont
  un opt-in → Compose suffit largement.
- Tests : `tests/docker/test_dockerfile_lint.py` valide statiquement la
  structure (multistage, healthcheck, profiles, secrets). Smoke test
  intégration `test_docker_smoke.py` skippé si daemon docker absent.
- Revisite suggérée : Phase 3 Vague 2, après retours premiers forks.
