# Tests du pipeline Reco

Tests unitaires Python (pytest) sur les fonctions pures du pipeline. Aucun
appel réseau, aucune dépendance LLM/TMDB/Deezer — uniquement de la logique
métier déterministe.

## Lancer

```bash
# depuis la racine du projet
./tools/.venv/Scripts/python.exe -m pytest

# ou (Unix-like)
tools/.venv/bin/pytest

# avec sortie verbose
pytest -v
```

Le `pyproject.toml` à la racine déclare :
- `testpaths = ["tests"]`
- `pythonpath = ["tools"]` → on importe `common`, `match_youtube`, etc. directement.

## Couverture actuelle

| Fichier | Ce qui est testé |
|---|---|
| `test_common.py` | `slugify` (accents/casse/ponct), `reco_prefix` (initiales), `write_json_if_changed` (idempotence, UTF-8) |
| `test_match_youtube.py` | `_normalize`, `_similarity` (inclusion boost), `_parse_se` (séparateurs `-`/`·`/`.`/`–`), `_video_id` |
| `test_enrich_tmdb.py` | `_provider_link` : mapping exact + patterns substring (Apple TV Store, Netflix with Ads, X Amazon Channel) + fallback DuckDuckGo |
| `test_rematch_with_ocr.py` | `_episode_is_extract` : tous les cas-limites (audio absent, YT absent, durées au seuil) |
| `test_inventory_md.py` | `fmt_dur` (zéro, sub-minute, padding 2 chiffres) |
| `test_extract_recos.py` | `_norm` (accents/casse/ponct/digits), `_dedupe` (fusion intelligente des champs manquants) |

## À ajouter plus tard

- **Tests TS** (vitest) sur `src/data/merchants.ts` (résolveur de liens).
- **Tests d'intégration** avec fixtures (mini-RSS + mini-transcript) pour
  tester un pipeline complet `fetch → match → extract` sans appel LLM (mock).
- **Tests des adaptateurs réseau** (TMDB / Deezer / Spotify) avec
  `responses` ou `respx` pour stubber les requêtes HTTP.
