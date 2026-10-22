# Métriques de workflow

Mesure de **chaque exécution réelle** du pipeline et des décisions de relecture
qui en découlent, pour calibrer plus tard un estimateur (« Reco Estimator ») sur
des observations, pas sur des souvenirs. Module : `tools/telemetry/`.

Principe : *instrument first, optimize later*. L'instrumentation est additive :
elle ne change ni les CLI, ni les JSON éditoriaux, ni la relecture.

## Où vivent les observations

Base SQLite dédiée, append-only, **hors du catalogue** : enregistrer une
métrique ne demande aucun commit.

| Réglage | Défaut | Rôle |
|---|---|---|
| `RECO_METRICS_ENABLED` | `1` | `0` : enregistreur nul, rien n'est écrit |
| `RECO_METRICS_DB` | `tools/output/telemetry/reco_metrics.sqlite` | chemin de la base (ignorée par Git) |
| `RECO_METRICS_STRICT` | `0` | `1` : une observation impossible à écrire arrête l'exécution |
| `RECO_METRICS_JOURNAL` | `wal` | `delete` sur un disque réseau, où le WAL est déconseillé |
| `RECO_PIPELINE_PROFILE` | — | profil déclaré de la configuration (ex. `ubm-s6-prod-2026-10`) |
| `RECO_RUN_INTENT` | `unknown` | intention par défaut d'un run lancé à la main |

Sur venus, `tools/output/` est dans le clone monté en `/app` : la base survit
aux conteneurs jetables, et la chaîne comme la page de relecture y écrivent
(journal WAL, attente de verrou de 5 s). Les trois caches SQLite
(enrichissement, HTTP, embeddings) sont d'autres fichiers : en vider un
n'efface aucune observation.

Le schéma est migré par `PRAGMA user_version` (`tools/telemetry/schema.py`) ;
une migration ne fait qu'ajouter.

## Contrat d'événements

| Table | Une ligne = |
|---|---|
| `workflow_runs` | une invocation (une CLI, une étape de `tick.sh`) |
| `stage_attempts` | une **tentative** d'étape pour un épisode ; chaque reprise a la sienne |
| `llm_calls` | un appel fournisseur **réel** (pas un chunk logique, pas une candidate) |
| `llm_batches`, `batch_requests` | un lot, et la correspondance `custom_id` → épisode |
| `review_events` | une décision ou action de relecture |

Identifiants : UUID pour les runs, tentatives, appels et événements ;
`source_id` + `episode_guid` pour le métier (jamais le numéro d'épisode seul) ;
`correlation_id` = `source:guid`, stable à travers les étapes d'un épisode ;
`retry_of_attempt_id` relie une reprise à la tentative qu'elle reprend.

Statuts d'une tentative : `started | succeeded | failed | skipped | cancelled |
interrupted`. Un `skipped` (cache, entrée manquante, dry-run) n'est **jamais**
une exécution : ni coût, ni appel.

Finalisation : une tentative est écrite `started` à son début, puis finalisée
**une seule fois** (`ended_at`, `status`, mesures). Un arrêt brutal la laisse
`started` ; elle n'est jamais effacée.

### `null` n'est pas `0`

`NULL` = non mesuré ; `0` = mesuré à zéro. Une durée audio inconnue, des jetons
non rendus par le fournisseur, un temps humain non suivi restent `NULL` dans la
base **et** dans les rapports. Une tentative réussie dont un champ requis manque
a `telemetry_complete = 0`.

### Temps

- `started_at`, `ended_at` : UTC ISO-8601, pour l'affichage.
- `elapsed_ms` : horloge monotone (`perf_counter_ns`), dans le même processus.
- `cpu_time_ms` : `process_time_ns` du processus — tous ses fils compris
  (faster-whisper calcule dans le processus), mais **ni** GPU **ni** API
  externe. Sur venus, la transcription est en CPU.
- `gpu_active_ms` : non mesuré (aucune instrumentation GPU fiable).

### Intention (`intent`)

`standard_first_pass | retry | manual_rerun | experiment | source_migration |
backfill | unknown`. Jamais déduite de la saison, du succès ou de l'absence de
`--force`.

- Un run qui **déclare** le chemin nominal (`standard_first_pass` : la chaîne de
  venus) qualifie chaque tentative d'après la base : aucune tentative antérieure
  (hors sauts) → première passe ; la dernière a échoué → `retry`, rattachée ;
  une passe a déjà réussi → `unknown`.
- Ailleurs, l'intention est celle que le run déclare (`--intent`,
  `RECO_RUN_INTENT`), `unknown` par défaut.

### Échecs d'écriture

Une métrique perdue ne casse ni une reco ni la chaîne, mais ne passe pas
inaperçue : journal d'erreur, compteur `lost_observations` sur le run. En mode
strict, elle lève `TelemetryError`.

### Confidentialité

Jamais dans la base : clés d'API, prompts remplis, transcriptions, texte des
œuvres, IP, URL avec paramètres. Les messages d'erreur sont expurgés (URL et
secrets masqués, 160 caractères). Le nom de la machine n'est gardé qu'en
empreinte (`machine_id`). Le fichier est créé en `0600` sous POSIX.
