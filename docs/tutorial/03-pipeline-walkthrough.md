# Tutorial 3 — Pipeline pas-à-pas

> **Objectif** : comprendre chaque étape du pipeline RSS → site statique,
> ses commandes, ses sorties attendues et ses pièges courants.

## Vue d'ensemble

```
RSS → fetch → match → transcribe → extract → enrich → review → cache → build → site
       (1)    (2)        (3)         (4)       (5)      (6)     (7)     (8)
```

Toutes les commandes acceptent `--source <slug>` ou `--source all`.

---

## 1. Fetch épisodes RSS — `fetch_episodes.py`

```bash
python tools/fetch_episodes.py --source mon-podcast
```

**Entrées** : `rssUrl` dans `src/content/sources/<slug>.json`.

**Sorties** : `src/content/episodes/<slug>/*.json` (un fichier par épisode).

**Durée** : ~10 s pour 200 épisodes.

**Edge cases** :

- Flux RSS sans `guid` stable → fallback sur hash titre + date.
- User-Agent par défaut (certains hébergeurs filtrent les requêtes sans UA).
- Idempotent : `write_json_if_changed` ne touche que ce qui change.

---

## 2. Match YouTube — `match_youtube.py`

```bash
python tools/match_youtube.py --source mon-podcast
```

**Entrées** : `youtubeChannel` dans le source JSON.

**Sorties** : `youtubeUrl`, `youtubeTitle`, `youtubeDuration` ajoutés à chaque épisode.

**Durée** : ~30 s pour lister 200 vidéos via `yt-dlp --flat`.

**Edge cases** :

- Filtre `<30 min` : ignore extraits, jeux, blindtests.
- Anciens épisodes sans pattern `Sx-Ex` → utiliser `rematch_with_ocr.py`
  (validation via OCR de miniature, Anthropic Haiku Vision).

---

## 3. Transcription — `transcribe.py`

```bash
python tools/transcribe.py --source mon-podcast --all --youtube
```

**Entrées** : audio YouTube (`--youtube`) ou audio Acast (fallback).

**Sorties** : `tools/output/transcripts/<slug>/<guid>.json` (segments + timecodes).

**Durée** : longue (Whisper) — ~10 min par heure d'audio sur CPU,
~1 min sur GPU CUDA.

**Moteurs interchangeables** (port `TranscriberEngine`) :

- `faster-whisper` (CPU/CUDA, modèle `small` par défaut).
- `whisper.cpp` (CUDA, vieux GPU compatibles `-DCMAKE_CUDA_ARCHITECTURES=50`).

**Mode démo** (sans Whisper) :

```bash
cp tools/fixtures/episodes_demo.json tools/output/transcripts/mon-podcast/demo.json
```

---

## 4. Extraction LLM cross-validée — `extract_recos.py`

```bash
python tools/extract_recos.py --source mon-podcast --all --provider anthropic
python tools/extract_recos.py --source mon-podcast --all --provider openai
```

**Entrées** : `tools/output/transcripts/<slug>/*.json`.

**Sorties** : `src/content/recos/<slug>/*.json` (upsert sur clé `episodeGuid + titre normalisé`).

**Durée** : ~5 s par épisode/provider. Mode `--batch` (Anthropic) : −50 % coût.

**Cross-LLM** :

- `extractors: ["anthropic"]` — vu par 1 LLM seulement.
- `extractors: ["anthropic", "openai"]` — ⭐ confirmée par 2 LLMs (priorité review).

**Edge cases** :

- Transcripts longs → chunks avec overlap.
- Coûts : pour ~200 épisodes, ~5 $ par provider avec Sonnet/gpt-4o-mini.

---

## 5. Enrichissement — `enrich_*.py`

```bash
python tools/enrich_tmdb.py        --source mon-podcast
python tools/enrich_spotify.py     --source mon-podcast
python tools/enrich_musicbrainz.py --source mon-podcast
```

**Entrées** : recos avec `kind` typé (film, série, album…).

**Sorties** : champs `poster`, `year`, `tmdbId`, `spotifyId`, etc.

**Durée** : ~2 s par reco (cache HTTP local).

**Audit** :

```bash
python tools/audit_tmdb.py --source mon-podcast    # détecte enrichments suspects
```

Cf. [ADR 0019 — audit core pipeline](../adr/0019-audit-core.md).

---

## 6. Relecture humaine — `review_server.py`

```bash
python tools/review_server.py --source mon-podcast
```

**UI** : <http://localhost:8000> — galerie de vignettes + page d'épisode avec lecteur YT embarqué.

**États visuels** :

- 🟢 normal — recos en attente de validation.
- ⏳ filigrane — transcription en cours.
- 🟠 « 0 reco » — transcript présent mais extraction vide.
- opaque/grisé — toutes les recos validated.

**Workflow** : `draft → validated` (ou `rejected`). Écrit directement dans
les JSON de `src/content/recos/`.

---

## 7. Build cache + lints — `build_cache.py`

```bash
python tools/build_cache.py    --source mon-podcast
python tools/lint_dataset.py   --source mon-podcast
```

**Sorties** : `tools/output/cache.json` consommé par Astro au build.

**Lints** : détecte recos orphelines, champs manquants, doublons.

---

## 8. Build site — `npm run build`

```bash
npm run build
```

**Sortie** : `dist/` (HTML statique, ~5793 pages pour *Un Bon Moment*).

**CI** : `pa11y-ci` + `vitest` + `pytest`. Cf. [ADR 0024](../adr/0024-ci-quality-gates.md).

---

## Pipeline orchestré

Pour tout enchaîner d'un coup :

```bash
python tools/run_pipeline.py --source mon-podcast
# ou via Docker :
docker compose --profile pipeline run --rm reco-pipeline
```

---

## Référence CLIs

| CLI | Rôle | ADR |
|---|---|---|
| `fetch_episodes.py` | RSS → épisodes | 0001 |
| `match_youtube.py` | YT → métadonnées | — |
| `ocr_thumbnails.py` | Vision LLM → numéros d'épisode | — |
| `rematch_with_ocr.py` | Re-match validé par OCR | — |
| `transcribe.py` | Audio → transcript | — |
| `extract_recos.py` | Transcript → recos LLM | — |
| `enrich_tmdb.py` | Films/séries TMDB | 0023 |
| `enrich_spotify.py` | Albums/artistes Spotify | — |
| `enrich_musicbrainz.py` | Musique MusicBrainz | — |
| `audit_tmdb.py` | Détecte enrichments suspects | 0019 |
| `build_cache.py` | Cache build pour Astro | 0019 |
| `lint_dataset.py` | Lint données | 0019 |
| `review_server.py` | UI relecture (port 8000) | — |
| `run_pipeline.py` | Orchestrateur séquentiel | — |
| `inventory_md.py` | Tableau de bord MD | — |

---

## Étape suivante

[Tutorial 4 — déployer](04-deploy-static.md).
