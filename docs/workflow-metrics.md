# Métriques de workflow

Mesure de **chaque exécution réelle** du pipeline et des décisions de relecture
qui en découlent, pour calibrer plus tard un estimateur (« Reco Estimator ») sur
des observations, pas sur des souvenirs. Module : `tools/telemetry/`.

Décision : [ADR 0054](adr/0054-metriques-de-workflow.md). Principe : *instrument first,
optimize later*. L'instrumentation est additive :
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
| `RECO_PIPELINE_PROFILE` | — | étiquette lisible des runs (ex. `ubm-s6-opus55-2026-10`) ; n'entre pas dans la sélection de cohorte |
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
| `extract` | `extract_recos.extract_for_episode`, lot, banc d'essai | voir ci-dessous |
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

### Extraction LLM

Une tentative `extract` par épisode. Configuration et empreinte : fournisseur,
modèle, transport (`sync` | `batch`), `max_tokens` effectif, effort, chunks
(`24 000` caractères, recouvrement `500`), `prompt_version`
(`recos-extraction-v1`), `prompt_sha256` — empreinte des **gabarits** système et
consigne, jamais du prompt rempli —, `recipe_version`
(`cultural-recommendations-v1`). La température n'est pas fixée : `null`.

Un appel fournisseur réel = une ligne de `llm_calls`, écrite par l'adaptateur
(`_AnthropicExtractor`, `_OpenAIExtractor`) qui continue de rendre ses recos :
`chunk_index` (à partir de 0), `chunk_count`, `chars_in_chunk`, durée,
identifiant de requête du fournisseur, jetons, `candidates_raw`, `parse_status`
(`json` | `empty` | `non_json`).

| Fournisseur | Jetons relevés |
|---|---|
| Anthropic | `usage.input_tokens`, `output_tokens`, `cache_read_input_tokens`, `cache_creation_input_tokens` ; raisonnement compris dans la sortie (`reasoning_tokens` = `null`) |
| OpenAI | `prompt_tokens`, `completion_tokens`, `prompt_tokens_details.cached_tokens`, `completion_tokens_details.reasoning_tokens` |

Réponse sans usage : jetons `null`, `usage_source = unavailable`, coût inconnu,
tentative incomplète. Requête refusée (4xx) : `failed` ; autre échec (délai,
coupure, 5xx) : `billing_uncertain`, coût inconnu.

Par épisode : `raw_candidates` (somme des chunks, doublons compris),
`unique_candidates` (après normalisation et déduplication), `recos_created`,
`recos_updated`. Un `--dry-run` est un `skipped` / `dry_run` avec
`planned_calls` ; une transcription absente, `skipped` / `missing_input`.

**Lot** (`--batch`). Une tentative par épisode, ouvertes ensemble. Le lot
(`llm_batches` : `submit_elapsed_ms`, `wait_ms`, `result_processing_ms`, dernier
statut) et la correspondance `custom_id` → épisode et chunk (`batch_requests`)
sont écrits **avant** de scruter : un lot interrompu reste attribuable. Chaque
résultat va dans l'épisode de sa requête, une seule fois (index unique
fournisseur + lot + `custom_id`) : une collecte rejouée ne compte pas double.
L'attente du lot n'est **pas** répartie entre épisodes. Une requête du lot en
échec rend sa tentative `failed`.

**Secours** (modèle disparu, 404) : la tentative du modèle disparu est `failed`
(`error_code = 404`) ; celle du secours est une `retry` qui lui est rattachée.

**Banc d'essai** (`banc_modeles.py`) : run et tentatives `experiment`, jamais
mêlés aux passes nominales.

### Coûts

Tarifs datés dans `tools/telemetry/tarifs.json` (version, `valid_from`, source,
date de relevé), aucun dans le code. Un appel est valorisé **à sa date** et le
montant est figé dans sa ligne (`cost_decimal`, `pricing_snapshot_id`) : un
rapport recalculé plus tard donne le même montant. Calcul en `Decimal`, sans
arrondi par appel.

Coût **inconnu** (`null`), jamais zéro, quand : les jetons manquent ; le modèle
ou le transport n'a pas de tarif (OpenAI n'est pas relevé) ; l'appel lit ou
écrit du cache sans prix de cache relevé ; l'appel a échoué. Le lot a son
propre tarif (−50 %). `observed_cost_decimal` (facture rapprochée) reste `null`.

`cost_owner` (`user_byok` | `reco_managed` | `local_machine` | `unknown`) est
déduit du client, à sa création, selon d'où vient sa clé : un client fait par
`common.make_anthropic_client` / `make_openai_client` (clé du `.env` de
l'opérateur) est `reco_managed`. Un futur client à clé fournie par
l'utilisateur sera `user_byok` (des jetons qu'il paie ne sont pas à refacturer
par Reco). Un client sans marque : `unknown`, jamais une supposition.

### Relecture

Journal append-only (`review_events`), écrit **après** l'écriture du fichier de
la reco, jamais à l'ouverture d'un formulaire. Un seul branchement : chaque POST
de la page de relecture relit sur disque les recos visées avant et après
l'action (et repère au listage du dossier les recos apparues) ; seul ce qui a
changé est journalisé. Une action refusée, un aperçu, une annulation sans objet
n'écrivent rien.

| Action | Origine |
|---|---|
| `validate`, `discard`, `citation`, `guest-work` | `POST /save`, ou décision de `/consolidate` |
| `edit` | `/edit`, `/retirer-lien`, `/accept-type`, `/rename-guest` |
| `add`, `delete`, `merge`, `undo`, `reenrich` | routes du même nom (`undo` : `/undo-save`, `/undo-merge`) |
| `mark_unsure` | verdict `unsure` d'un agent |

Champs modifiés : leurs **noms**, jamais leurs valeurs. Catégories **dérivées**
(pas une seconde action) : `reassign_speaker` (`recommendedBy`),
`timestamp_corrected`, `type_corrected`, `external_link_corrected` (`links`,
`linksRejected`), `title_corrected`, `creator_corrected`, `year_corrected`,
`quote_corrected`, `kind_changed`.

Acteur : un clic de la page → `human` ; `apply_verdicts.py` → `agent`. Un
verdict d'agent ne produit aucun temps humain.

Attribution à l'extraction (`source_stage_attempt_id`) : seulement si la base
connaît **une seule** extraction réussie de l'épisode (`provenance_quality =
inferred`) ; sinon `null` / `unknown`. Jamais « la dernière » par défaut.

### Temps de relecture actif

La durée d'un `POST` est une latence serveur, pas un temps de relecture. Le
temps actif vient de battements (`POST /activite`, table `review_activity`) :

- le navigateur en envoie un toutes les **15 s**, seulement si l'onglet est
  **visible** et qu'une interaction (clic, touche, défilement, saisie) a eu
  lieu depuis moins de **60 s** (`review_client_activite.js`) ;
- le serveur fixe la valeur d'un battement (15 s) et ignore un battement à
  moins de 10 s du précédent de la même session ;
- le temps se calcule au rapport par **union** des intervalles : deux onglets
  ouverts ensemble ne comptent pas double ; par épisode, seulement les
  battements qui portent l'épisode affiché ;
- sans battement : `human_active_ms = null`, jamais 0.

Une session est un identifiant tiré au hasard par l'onglet (cookie de session
`reco_revue_session`, envoyé aussi avec les décisions pour les relier au temps
actif). Ni texte, ni identité, ni IP : la page de relecture est locale.

**À calibrer** : les seuils (15 s, 60 s) sont des choix, pas des mesures. Avant
d'utiliser ces durées dans l'estimateur, les comparer à une relecture
chronométrée à la main.

Première comparaison, S6-E06 (2026-10-23) : 22 min chronométrées, 13 min 15 s
actives, et 22 min 13 s du premier au dernier battement. Les 9 minutes manquantes
mêlaient des recherches pour la relecture dans d'autres onglets et une
discussion sans rapport : le temps actif est une borne basse. Une seule séance
ne suffit pas à régler un seuil ; à recalibrer sur une relecture sans
interruption.

Une panne de télémétrie n'interrompt jamais la relecture.

## Rapports

```bash
cd tools
python metrics_report.py coverage --source un-bon-moment            # ce qui est mesuré, et les trous
python metrics_report.py workflows --source un-bon-moment --format csv
python metrics_report.py cohort --source un-bon-moment --season 6   # sélection et exclusions
python metrics_report.py summary --source un-bon-moment --cohort qualified --format markdown
python metrics_report.py export --source un-bon-moment --season 6 \
  --output output/telemetry/export.json                             # pour l'estimateur
python metrics_report.py recover --older-than-hours 24              # runs restés « started »
python metrics_report.py purge --activity-days 395                  # battements bruts anciens
```

Lecture seule, sauf `recover` (passe en `interrupted` ce qui est resté `started`
au-delà du seuil, sans rien effacer ; `tick.sh` le lance une fois par semaine) et
`purge`. Une base absente donne des
rapports vides, sans créer de fichier. Les exports vivent sous `tools/output/`
(ignoré par Git), jamais sous `public/`.

Règles de calcul :

- une somme sur une valeur absente est `null` (pas une somme partielle
  présentée comme totale) ; un coût ne s'additionne que dans sa devise ;
- **nominal** = premières passes ; **surcoût opérationnel** = `retry`,
  `manual_rerun`, `experiment`, `source_migration`, `backfill`, `unknown`,
  chacun à part ; un épisode retraité ne compte qu'une fois dans le nominal ;
- `processing` (machine), temps humain actif et délai de bout en bout (avec
  attentes de lot et de relecture) ne se confondent pas ;
- ratios (`costPerAudioHour`, `candidatesPerAudioHour`,
  `humanMinutesPerReviewAction`, `manualReworkRate`) : seulement sur une
  cohorte **qualifiée**, avec `sampleSize` ; `reviewMinutesPerCandidate` reste
  `null` (plusieurs fiches sont relues ensemble) ;
- `manualReworkRate` = recos retouchées par un humain (`edit`, `merge`) /
  recos ayant reçu une décision humaine — jamais déduit des seuls statuts.

L'export suit la forme de la spécification (`schemaVersion` 1 : `cohort`,
`coverage`, `observed`, plus `derived`, `overhead`, `warnings`) et est validé
avant d'être écrit (`reports.valider`) ; un export non conforme échoue.

## Cohorte de référence : *Un Bon Moment*, saison 6

La saison 6 est une cohorte **candidate**. Un épisode n'est retenu que si,
pour la transcription ET l'extraction :

1. sa saison est écrite dans le catalogue (`season` de l'épisode, tirée du
   titre « S6-E05 » à la détection) et vaut 6 ;
2. une tentative `standard_first_pass` a **réussi** (pas un cache, pas un saut) ;
3. elle a la configuration de référence : l'empreinte de configuration la plus
   fréquente parmi les candidats. L'empreinte change d'elle-même avec le
   modèle, le prompt, le découpage ou la version du moteur ; un profil déclaré
   n'est qu'une étiquette et ne la remplace jamais ;
4. l'origine du média est celle de la référence (YouTube) ;
5. aucune migration de source n'a touché l'épisode ;
6. la durée audio et l'usage de **chaque** appel sont mesurés.

Codes d'exclusion, dans l'ordre où ils s'appliquent : `season_unknown`,
`not_season`, `no_telemetry`, `source_migration`, `experiment_only`,
`retry_only`, `not_standard`, `not_succeeded`, `mixed_configuration`,
`media_mismatch`, `missing_duration`, `missing_usage`.

Statut `qualified` à partir de 3 épisodes retenus (`--min-episodes`), sinon
`insufficient_data` — résultat honnête, pas une panne.

Les épisodes traités **avant** la télémétrie (S6-E01 à E05, et les 110 épisodes
Acast/YouTube historiques) sont exclus pour `no_telemetry` : leurs appels,
reprises, jetons et temps humain ne sont **pas** reconstruits. Seul leur état
final (catalogue : source et modèle de transcription, statuts des recos) est
rapporté (`finalState`).

## Ce qui reste non mesuré

| Donnée | Pourquoi |
|---|---|
| `gpu_active_ms` | aucune instrumentation GPU fiable (venus transcrit en CPU) |
| coût d'exploitation local (électricité, amortissement) | pas de profil matériel chiffré : seul le temps est mesuré |
| prix du cache, tarifs OpenAI | non relevés : coût inconnu tant qu'ils ne sont pas dans `tarifs.json` |
| facture réelle (`observed_cost_decimal`) | pas de rapprochement avec la facturation du fournisseur |
| latence par requête d'un lot | non observable |
| détection (liste yt-dlp) | tourne à chaque passage, coût négligeable, non mesurée |
| temps humain par fiche | les battements disent l'épisode affiché, pas la fiche |
| curation (`/curation`), passes automatiques de liens | hors journal de relecture |
