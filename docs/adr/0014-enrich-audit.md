# ADR 0014 — Audit post-enrichissement TMDB

- Statut : **Acceptée** (P1.8 livré — voir `tools/tmdb_snapshot.py`)
- Date : 2026-06-10 (mise à jour suite CR senior + CR archi P1.7)
- Décideurs : équipe Reco

## Contexte

Le pipeline `tools/enrich_tmdb.py` matche les Items par titre + créateur
via l'API TMDB, en mode « best-effort fuzzy ». Conséquence : si un titre
est commun (« Vice », « Heat », « Mortel »…), la première réponse TMDB
peut correspondre à une œuvre **différente** de celle réellement recom-
mandée. Sans audit, ces erreurs polluent :

- les liens « watch providers » FR (on dirige l'utilisateur vers la mauvaise
  œuvre) ;
- les éventuelles futures déduplications par `external_ids.tmdb` ;
- les liens TMDB exposés dans l'UI.

Sur le dataset `un-bon-moment` (juin 2026) : 261 items sur 2651 sont
enrichis TMDB. On ne peut pas relire tout à la main — il faut **un signal
automatique** qui flag les enrichissements probablement faux.

Options envisagées :

1. **Réécrire le matcher** — coûteux (changement d'algorithme = risque de
   régression) et ne couvre pas le passif (261 items déjà enrichis).
2. **Flag `enrichmentSuspect` directement sur l'entité `Item`** — intrusif :
   pollue le domaine éditorial avec un détail d'audit, force une bump de
   `schema_version`, casse l'idempotence sur les items inchangés.
3. **Sidecar files versionnés** : un fichier
   `tools/output/enrich_audit/<source>/<item>.json` par verdict, avec
   `schemaVersion`, `auditorVersion`, `auditedAt`. Découplé de l'entité,
   jetable, extensible, archivable.
4. **Check intégré à `enrich_tmdb.py`** — couplage fort. Le matcher
   re-tournerait sur chaque audit, et on ne pourrait pas auditer le passif
   sans relancer l'enrichissement complet.
5. **SQLite** — overkill aujourd'hui ; intéressant **si >5000 sidecars**
   par source. Critère de bascule chiffré.
6. **JSONL d'événements** (sans sidecar par item) — utile pour la time-
   line, complémentaire des sidecars (cf. décision additive ci-dessous).

## Décision

On retient l'**option 3 — sidecar files versionnés** + **option 6 en
additif** pour la timeline. Architecture :

- Une bibliothèque pure `tools/enrich_audit/` qui sépare strictement :
  - `types.py` : VOs immuables (`Suspicion`, `AuditResult`, `Severity` enum,
    `Check` Protocol, `TmdbPayload` alias, constantes versions).
  - `thresholds.py` : seuils par défaut (source unique de vérité).
  - `service.py` : `EnrichAuditService` (orchestration, isolation
    exceptions par check via try/except).
  - `flag_writer.py` : I/O sidecars + archive + restore.
  - `providers.py` : `make_cache_provider` (LRU, supporte format legacy
    + format versionné `_cacheVersion: 1`).
  - `reporters/` : markdown, json, jsonl (cohérent avec `lint/reporters/`).
  - `<check>_check.py` : un check par module.
- Le CLI `tools/audit_tmdb.py` n'est qu'une fine couche argparse autour
  de `cli_runner.run_audit(opts)`.

### Checks livrés (par ordre d'exécution)

1. **`check_tmdb_type_mismatch`** (CRITICAL) — détecte un Item taggé film
   matché avec un payload TMDB de type série (et inversement). C'est **le**
   check critique qu'on est censé détecter ; sans lui, les autres checks
   peuvent passer en faux négatif sur le bug principal.
2. **`check_title_similarity`** — ratio Levenshtein normalisé
   (`SequenceMatcher`) sur l'union de tous les titres TMDB
   (`original_title`, `title`, `original_name`, `name`), **max**. Seuil
   0.7. Normalisation NFKC + casefold + map œ/æ/ß explicite + ponctuation.
3. **`check_year_mismatch`** — tolérance ±1 an, severity WARNING (delta
   ≤ 10) ou CRITICAL (delta > 10).
4. **`check_runtime_coherence`** — film < 20 min → INFO « court probable
   à vérifier » ; série > 180 min/épisode → WARNING « TV-movie suspect » ;
   série < 8 min → INFO « cartoon court ».

### Sidecar format (`schemaVersion: 1`)

```json
{
  "schemaVersion": 1,
  "auditorVersion": "0.2.0",
  "auditedAt": "2026-06-10T12:00:00Z",
  "itemId": "abc12345",
  "tmdbId": 1577,
  "enrichmentSuspect": true,
  "suspicions": [
    {"kind": "title_mismatch", "detail": "…", "severity": "warning",
     "confidence": 0.83}
  ]
}
```

- `auditedAt` est **injecté** depuis l'appelant (CLI / tests), jamais
  `datetime.now()` côté module. Garantit l'idempotence sha256 sur deux
  runs aux mêmes inputs.
- Source de vérité de `is_suspect` à la **lecture** : `len(suspicions) > 0`.
  Un `enrichmentSuspect` persisté incohérent est ignoré + warning logué
  (compteur `sidecar_malformed`).

### Cache TMDB format

- **Legacy** (rétro-compat) : payload TMDB brut à la racine du fichier.
- **v1** : `{"_cacheVersion": 1, "kind": "movie"|"tv", "fetchedAt": ISO8601,
  "payload": {...}}`. Cache version mismatch → skip + warning.

### Convention API : sidecar (Item) vs in-place (Episode)

L'audit `enrich_audit` écrit en **sidecar** parce qu'un Item est une
**entité pure** (œuvre éditoriale). En miroir, `match_audit` (cf. ADR
0013) écrit **in-place** un flag `matchSuspect` parce qu'un Episode est
une **relation** (épisode ↔ vidéo YouTube) — l'information appartient
naturellement au lien. Cette dualité est documentée explicitement pour
éviter une fausse incohérence ressentie.

### Workflow

```
tmdb_snapshot.py (P1.8)  →  tmdb_cache/<id>.json (v1)
                                    ↓
audit_tmdb.py --source X  →  EnrichAuditService.audit_items(...)
                                    ↓
                          SourceAuditReport (in-memory)
                                    ↓
                ┌────────────────┬─────────────────┐
                ↓                ↓                 ↓
        sidecar JSON      JSONL log         stdout report
   (--apply : versionné)  (per suspect)   (markdown / json)
```

### Seuils

Tous centralisés dans `tools/enrich_audit/thresholds.py` (source unique
de vérité), tous **injectables CLI** (`--title-threshold`, `--year-
tolerance`, `--film-min-runtime`).

Seuils par défaut, calibrés sur le corpus test
`tests/enrich_audit/test_corpus_reference.py` (20+ cas étiquetés
suspects/clean FR/EN films/séries) :

| Constante | Valeur | Rationale |
|---|---|---|
| `DEFAULT_TITLE_THRESHOLD` | 0.7 | Tolère orthographe approximative sans bénir « Vice » ↔ « Iron Man ». |
| `DEFAULT_YEAR_TOLERANCE` | 1 an | Absorbe sortie multi-pays. |
| `DEFAULT_FILM_MIN_RUNTIME` | 20 min | Abaissé de 40 (CR senior H3) : court éditorial OK, sketch suspect. |
| `DEFAULT_SERIES_EPISODE_MAX_RUNTIME` | 180 min | Abaissé de 240 (CR senior H2). |
| `DEFAULT_SERIES_EPISODE_MIN_RUNTIME` | 8 min | Nouveau (CR senior H2). |

Pour ajuster les seuils sur une nouvelle source : passer les flags CLI
(test rapide) puis, si concluant, étendre `SourceConfig.enrich_audit_
thresholds` (Phase 1.B — voir #12 reportée, dépend de l'extension du
schéma source).

### Critères de bascule (futur)

- `rapidfuzz` au lieu de `SequenceMatcher` si **>2 % faux positifs**
  observés sur corpus calibré (≈8 faux positifs sur 400 items audités).
  Tant que `SequenceMatcher` tient, on garde stdlib.
- SQLite au lieu de sidecars JSON si **>5000 sidecars / source** ou si
  l'IO devient un goulot (>5 s pour un `--apply` complet).
- Index hash sur titre normalisé si recherche cross-source nécessaire
  (P3+, hors scope actuel).

## Conséquences

### Positives

- **Domaine pur** : `Item` reste un agrégat éditorial. Le champ Zod
  `enrichmentSuspect` ajouté est forward-compat sans bump
  `schema_version`.
- **Idempotent / jetable** : `auditedAt` injectable + `clear → archive`
  rend les runs reproductibles ET réversibles (`--undo-last`).
- **Testable** : 100 % de couverture (215 tests). Aucun appel réseau.
- **Composable** : ajouter un check = ajouter un module + entrée dans
  `default_service()`. Service ne change pas (OCP).
- **Sûr** : un check qui lève n'arrête pas l'audit (compteur
  `skipped_check_error`). Tous les segments de chemin passent par une
  whitelist regex + Windows-reserved + null-byte (CR M6).
- **Démo réelle** sur `un-bon-moment` : 2 suspects détectés sur 5 items
  audités (un mismatch année + un court probable).
- **Calibration tracée** : `test_corpus_reference` garde 20+ cas qui
  passent ; tout déplacement de seuil casse le test → effet recherché.

### Négatives

- **Cache TMDB pas alimenté en prod** — seuls 5 fichiers manuels existent
  aujourd'hui dans `tools/output/tmdb_cache/`. Tant que P1.8
  (`tmdb_snapshot.py`) n'est pas livré, l'audit produit
  `skipped_no_cache=256` sur les 261 items enrichis. **Statut « bloquée
  prod » jusqu'à P1.8.**
- **Pas d'écriture du flag `enrichmentSuspect` côté Item.json** — le
  schéma Zod l'accepte (forward-compat), mais aucun script ne le
  remplit. Le badge UI viendra avec un job d'agrégation séparé
  (Phase 1/2, à tracker en roadmap).
- **Pas de convergence cross-modules** (`audit_common`, alignement
  `Severity`/`Check` Protocol avec `match_audit`) — reportée fin
  Phase 1 (cf. ADR 0016).

### Notes

- Seuils à revisiter quand le corpus de verdicts manuels (Phase 1
  item #9) sera disponible. `test_corpus_reference` est le bon point
  d'entrée.
- Si on bascule sur `rapidfuzz`, garder la signature
  `check_title_similarity(item, tmdb_data, threshold=…)` strictement
  identique — c'est elle qui est testée.
- Extension à d'autres APIs (Spotify, MusicBrainz) : créer
  `tools/enrich_audit/spotify_*_check.py` + ajouter au pipeline.
  **Un service par API ; les VOs (`Suspicion`, `Severity`, `Check`)
  sont partagés** via `types.py`. La contrainte du provider injecté
  reste valide.

## Mise à jour 2026-06-10 (Fixer cumulatif Phase 1)

- **P1.8 livré** : `tools/tmdb_snapshot.py` (CLI + tests 100% couvert) alimente
  `tools/output/tmdb_cache/<id>.json` au format v1
  (`_cacheVersion`, `kind`, `fetchedAt`, `payload`). Rate-limit 40 req/10s,
  idempotence 30 jours, lockfile pipeline, lecture `TMDB_API_KEY` depuis
  l'environnement (aucun secret écrit en clair).
- **Job d'agrégation sidecar → `Item.enrichmentSuspect`** (cf. CR Dette-12 /
  D-03) : reporté en **Phase 1.B / 2** — voir `docs/roadmap-2026.md`. Le
  consommateur Astro (`src/content.config.ts`, `RecoCard.astro`) reste libre
  de lire les sidecars directement ou via un agrégat futur. Pas d'ADR
  dédié : périmètre trivial (un script `aggregate_*` qui mappe
  `<item>.json → item.enrichmentSuspect: bool`).
