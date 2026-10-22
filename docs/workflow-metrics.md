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

## Points de mesure

### Runs

| Invocation | `trigger` | `command` | `intent` |
|---|---|---|---|
| chaîne de venus (`traiter_nouveaux_episodes.py <étape>`, lancée par `tick.sh`) | `scheduler` (`RECO_TRIGGER` pour surcharger) | `traiter_nouveaux_episodes:<étape>` | `standard_first_pass` déclaré, qualifié par tentative |
| `run_pipeline.py` | `cli` | `run_pipeline` | `--intent`, sinon `RECO_RUN_INTENT`, sinon `unknown` |
| `transcribe.py`, `extract_recos.py` seuls | `cli` | nom du script | idem |
| fonction appelée hors de tout run | `library` | nom de l'étape | `unknown` |

Les sondes de `tick.sh` (`a-extraire`, `a-finaliser`…) et la détection ne sont
pas mesurées : elles tournent à chaque passage (toutes les dix minutes le
dimanche) pour presque rien. Un run n'est écrit qu'à sa première étape, ou s'il
échoue : un passage sans travail ne laisse aucune ligne.

### Étapes

| `stage` | Où | Ce qui est mesuré |
|---|---|---|
| `fetch` | `run_pipeline` | durée de la collecte RSS |
| `transcribe` | `transcribe.transcribe_episode` | voir ci-dessous |
| `extract` | `extract_recos` | PR3 |
| `quote_relisten` | chaîne, après l'extraction | réécoute ciblée des citations (Whisper) : durée |
| `quote_align` | chaîne, après l'extraction | calage des citations sur la transcription : durée |
| `finalize` | chaîne, par épisode | liens, œuvres, mentions : durée, échec si refusée |
| `link_search`, `publish`, `comment` | chaîne, d'un bloc | durée ; pas de découpe par épisode |

### Transcription

Origine **réellement** utilisée (`media_origin` : `youtube`, `acast`, `other`),
jamais l'option demandée. `media_identifier` : `youtube:<id>` (public) ou
l'empreinte de l'URL Acast, jamais l'URL. `media_checksum` : SHA-256 du fichier
audio. `media_duration_ms` : durée **de l'audio**, rendue par le décodeur
(`null` si absente) — jamais confondue avec le temps de calcul.

| Mesure | Unité | |
|---|---|---|
| `audio_cache_hit` | bool | audio réutilisé : pas de téléchargement |
| `download_ms`, `download_bytes` | ms, octets | seulement si téléchargé |
| `audio_bytes` | octets | taille du fichier transcrit |
| `model_load_ms` | ms | chargement du modèle Whisper |
| `transcribe_ms` | ms | transcription longue (VAD) |
| `speech_duration_ms` | ms | parole après VAD |
| `gap_repair_ms` | ms | réécoute des trous (`combler_trous`), chronométrée à part |
| `gap_candidates`, `gaps_filled`, `gap_words_added`, `gaps_unfilled` | nombre | bilan de la réécoute |
| `language_detected`, `language_probability` | ISO 639-1, ratio | |

Une transcription déjà présente donne `skipped` / `cache_hit` : ni durée de
calcul ni coût. La configuration (moteur et versions, modèle, `int8`, faisceau,
VAD, présence de l'amorce, réglages de la réécoute) fait l'empreinte
`config_fingerprint` ; le texte de l'amorce n'y entre pas (il cite le titre).

Coût : transcription locale, `cost_owner = local_machine`, **aucun coût
fournisseur**. Un coût d'exploitation se déduira plus tard d'un profil matériel
(`machine_json` du run : CPU, nombre de cœurs, empreinte de la machine).
