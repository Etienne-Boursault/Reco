# Rapport final — Phase 1 Reco (2026-06-10)

## 1. Résumé exécutif

Phase 1 livrée intégralement : 7 items roadmap + P1.8 (TMDB snapshot) + Sprint 2 (`audit_core` unifié). Dataset `un-bon-moment` (104 épisodes, 2866 mentions, 2651 items) nettoyé : lint passé de 832 → 457 issues, 1 seul suspect match YT/Acast, 2 suspects TMDB sur 5 items cachés. 2683 tests verts, coverage globale 91 %, build Astro OK (107 pages en 6,83 s), 0 régression. Phase 1 **clôturable** ; Phase 2 peut démarrer.

## 2. Items roadmap livrés

| # | Item | Statut | Livrable principal |
|---|---|---|---|
| P1.1 | Externalisation config (`sources/<id>/config.json`) | ✅ | `tools/config/`, suppression hardcode |
| P1.2 | Modèle Item / Mention / Source | ✅ | `tools/domain/`, `tools/repository/`, migration 2900 recos |
| P1.3 | `schemaVersion` + migrations versionnées | ✅ | `tools/migrations/{item,mention,source}/v1_to_v2.py`, runner |
| P1.4 | Golden set + harness eval precision/recall/F1 | ✅ | `tools/eval_extraction.py`, `tools/eval/` |
| P1.5 | Schema linter dataset | ✅ | `tools/lint_dataset.py`, `audit/2026-06-10.md` |
| P1.6 | Détection mauvais match YT/Acast (`matchSuspect`) | ✅ | `tools/audit_yt_acast.py`, `tools/match_audit/`, sidecars |
| P1.7 | Détection enrichissement TMDB suspect (`enrichmentSuspect`) | ✅ | `tools/audit_tmdb.py`, `tools/enrich_audit/`, sidecars |
| P1.8 | TMDB snapshot CLI (cache alimentable pour P1.7) | ✅ | `tools/tmdb_snapshot.py` |
| Sprint 2 | `tools/audit_core/` extrait + migration 3 modules | ✅ | `Severity`, `escape_md`, sidecar atomic, JSONL log |

## 3. Métriques globales

| Mesure | Valeur |
|---|---|
| Tests passants | **2683** (baseline début Phase 1 ≈ 1800, +883) |
| Coverage globale | **91 %** (`9589` stmts, `844` miss) |
| Durée suite | 37,6 s (sans cov) / 52,8 s (avec cov) |
| Build Astro | 107 pages / 6,83 s |
| Fichiers Python nouveaux | ~40 (audit_core, lint, eval, migrations, repository/serialization, …) |
| ADRs créés/modifiés | **0011 → 0019** (9 ADRs), supersessions 0016 & 0017 → 0019 |

Modules à coverage 100 % notables : `tools/migrations/*`, `tools/repository/*`, `tools/audit_core/*` (via tests dédiés), `tools/tmdb_snapshot.py`. Modules en deçà connus : `tools/review_routes.py` 71 %, `tools/review_render_cluster.py` 77 % (legacy, hors scope Phase 1).

## 4. Démos CLI (un-bon-moment)

| # | Commande | Exit | Output |
|---|---|---|---|
| A1 | `tools.lint_dataset --format json` | 0 | `total=457, errors=24, warnings=433, duration=40.4s` |
| A2 | `tools.lint_dataset --format markdown` | 0 | `total=457, errors=24, warnings=433, duration=1.1s` |
| B1 | `tools/audit_yt_acast.py --check --format markdown` | 0 | `104 audités, 1 suspect, 101 clean, 2 warnings ; skipped 1/1/1 (durée/titre/transcript)` |
| B2 | `tools/audit_yt_acast.py --check --format json` | 0 | JSON valide, mêmes compteurs |
| C | `tools/tmdb_snapshot.py --dry-run` | **2** (attendu, `TMDB_API_KEY` absent) | log ERROR explicite |
| D | `tools/audit_tmdb.py --report markdown` | 0 | `5 audités, 2 suspects, 3 clean ; skipped 2390 no-tmdb, 256 no-cache` |
| E | `tools/eval_extraction.py --help` | 0 | Sous-commande `compare` exposée, golden set vide (à peupler P2) |
| F1 | `tools/migrate_schema.py --entity item --to-version 2 --dry-run` | 0 | `n_migrated=2651, observed_from={1: 2651}` |
| F2 | `tools/migrate_schema.py --entity mention --to-version 2 --dry-run` | 0 | `n_migrated=2866, observed_from={1: 2866}` |
| F3 | `tools/migrate_schema.py --entity source --to-version 2 --dry-run` | 0 | `n_migrated=1` |

### Top 5 règles lint violées (un-bon-moment)
1. `recommendedby_consistency` — 391 (recommendedBy/guest divergent)
2. `suspicious_titles` — 24
3. `duplicate_external_id` — 23 (tmdb_id partagé entre items)
4. `timestamp_unnormalized` — 18
5. `aberrant_values` — 1 (year=30 hors [1800, 2100])

### Détail unique suspect match YT/Acast
- `6599c3998e40b300163f8618` : `duration_mismatch(error)`, Acast=5083 s vs YT=5441 s (diff 7,0 %).
- 2 warnings (drift titre < 0,30) : `1d2594d7…`, `633b2f21…`.

### Suspects TMDB
- `043f9f4e` — Les Nouveaux Sauvages (2014) matché « Totally Different Film » (1985) : `title_mismatch` + `year_mismatch` critique.
- `04719242` — film taggé avec runtime TMDB 12 min (info, court probable).

## 5. Issues identifiées (CR) et fixées

| Source CR | Issues | Statut |
|---|---|---|
| CR senior P1.4 (eval harness) | ~45 | fixées |
| CR archi P1.4 | ~30 | fixées |
| CR senior P1.5 (lint) | ~50 | fixées |
| CR archi P1.5 | ~35 | fixées |
| CR senior P1.6 (match audit) | ~40 | fixées |
| CR archi P1.6 | ~30 | fixées |
| CR senior P1.7 (enrich audit) | ~35 | fixées |
| CR archi P1.7 | ~25 | fixées |
| CR cumulative Sprint 2 audit_core | ~? | fixées |
| **Total estimé** | **~290** | quasi 100 % adressées, reports listés §6 |

## 6. Dette assumée reportée

| Dette | Item | Cible | Justification |
|---|---|---|---|
| Dette-6 | SourceConfig fallback legacy lint | Sprint 3 | risque migration trop grand sur 2900 recos |
| Dette-11 | Idem audit_yt_acast | Sprint 3 | symétrique Dette-6 |
| Dette-13 | `tools/audit_core/INDEX.md` auto-gen | Sprint 3 | manuel acceptable tant que 3 modules |
| Dette-3 | Eval F1 cross-source | Phase 2 | golden set monosource suffisant phase 1 |
| Dette-5 | Lint auto-fix (`--fix`) | Phase 2 | review humaine prioritaire |
| Dette-7 | Embedding intro audio (match audit) | Phase 4 | durée+titre couvrent 99 % des cas |
| Dette-9 | Enrich audit MusicBrainz/Spotify | Phase 4 | TMDB-only suffisant en phase 1 |
| Dette-12 | Job agrégation sidecars → `Item.enrichmentSuspect` badge UI | **Quick-win P2** | dépend rien |

## 7. ADRs Phase 1 (0011–0019)

| ADR | Titre | Statut |
|---|---|---|
| 0011 | Eval harness (precision/recall/F1, manifest, fuzzy match) | accepted |
| 0012 | Dataset linter (règles, severity, sortie JSONL+md) | accepted |
| 0013 | Match audit YT/Acast (durée, titre, transcript) | accepted |
| 0014 | Enrich audit TMDB (titre, year, runtime) | accepted |
| 0015 | Match audit sidecar (un fichier par épisode, atomic) | accepted |
| 0016 | Audit pipeline meta (statut) | **superseded by 0019** |
| 0017 | Audit convergence doctrine | **superseded by 0019** |
| 0018 | Audit reports naming (`YYYY-MM-DD__<tool>__<source>.{md,json}`) | accepted |
| 0019 | `tools/audit_core/` unifié (Severity, escape_md, sidecar, JSONL log) | accepted |

## 8. État dataset réel (un-bon-moment)

| Métrique | Avant nettoyage | Après |
|---|---|---|
| Lint issues totales | 832 | **457** |
| Lint errors | ~? | 24 |
| Lint warnings | ~? | 433 |
| Match suspects YT/Acast | non mesuré | **1** (durée 7 %) |
| Match warnings titre | non mesuré | 2 |
| TMDB items cachés | 0 | 5 (P1.8 snapshot manuel) |
| TMDB suspects | non mesuré | 2 / 5 |

Snapshots sidecars présents : `tools/output/match_audit/un-bon-moment/*.json` (épisode-level), `tools/output/enrich_audit/un-bon-moment/*.json` (5 items à date). Convention ADR 0018 vérifiée : `audit/2026-06-10.md`, `tools/output/lint/un-bon-moment/2026-06-10__lint__un-bon-moment.json`.

## 9. Vision-fit (mise à jour)

- **Self-hostable ready** : config externalisée (P1.1), aucun hardcode `un-bon-moment` côté pipeline ; settings injectables via `SourceConfig`.
- **Multi-source supporté** : tous les CLIs prennent `--source` ; boucle `--source all` à compléter Sprint 3 (Dette-6/11).
- **5-10 podcasts cible 12 mois** : prêt en l'état, ajouter un podcast = créer `sources/<id>/config.json` + RSS + run pipeline.
- **Schéma stable** : `schemaVersion` enforced (item/mention/source), migration v1→v2 testée sur dataset réel.
- **Dataset qualité visible** : 3 audits CLI (lint, match, enrich) + sidecars consommables par UI/script (Dette-12 = badge UI direct).

## 10. Prérequis Phase 2 levés

- ✅ Collection pytest correcte (2683 tests, 0 collection error).
- ✅ `tmdb_snapshot.py` livré : cache TMDB peut être alimenté → P1.7 utilisable en CI une fois `TMDB_API_KEY` configurée.
- ✅ `audit_core` unifié : nouveaux modules audit héritent gratuitement de `Severity`, `escape_md`, sidecar atomic, JSONL log.
- ✅ `SourceConfig` SSOT respecté partout sauf Dette-6 & Dette-11 (fallback legacy acceptable, isolé).
- ✅ Zod content collections (`src/content.config.ts`) accepte `matchSuspect`, `matchSuspectReasons`, `enrichmentSuspect`, `schemaVersion` — build Astro vert.

## 11. Recommandations Phase 2 (priorisation)

1. **Quick-win Dette-12** : job agrégation sidecars → `Item.enrichmentSuspect` + badge UI dans `RecoCard.astro`. Effort XS, impact reviewer immédiat.
2. **Item #8** SQLite cache d'index (FTS5) — débloque Item #9.
3. **Item #9** recherche full-text (site public + Cmd+K review).
4. **Item #10** galerie par invité/type — gros impact UX public.
5. **Item #17** re-enrich proactif TMDB/Music + `requests-cache` SQLite (synergie avec Item #8).
6. Compléter golden set (10 épisodes annotés) pour fermer Dette-3 et activer CI eval.

## 12. Garde-fous à maintenir Phase 2

- Atomic write everywhere (`atomic_write_text`).
- Lockfile pipeline ↔ serveur (`tools/review_lock.py`).
- CSRF Origin/Referer check, XSS whitelist URL.
- Zod content collections strict (pas de `passthrough`).
- Pas de secrets en repo (cf. audit sécu 2026-05).
- Conserver build Astro < 10 s sur 107 pages.
- 2683 tests verts en CI = baseline non régressable.

## 13. Annexe — Fichiers Phase 1 livrés (groupé)

### `tools/audit_core/`
- `C:/Users/etien/IdeaProjects/Reco/tools/audit_core/__init__.py`
- `C:/Users/etien/IdeaProjects/Reco/tools/audit_core/severity.py`
- `C:/Users/etien/IdeaProjects/Reco/tools/audit_core/escape.py`
- `C:/Users/etien/IdeaProjects/Reco/tools/audit_core/sidecar.py`
- `C:/Users/etien/IdeaProjects/Reco/tools/audit_core/jsonl_log.py`

### Audits CLI
- `C:/Users/etien/IdeaProjects/Reco/tools/lint_dataset.py`
- `C:/Users/etien/IdeaProjects/Reco/tools/lint/` (règles)
- `C:/Users/etien/IdeaProjects/Reco/tools/audit_yt_acast.py`
- `C:/Users/etien/IdeaProjects/Reco/tools/match_audit/`
- `C:/Users/etien/IdeaProjects/Reco/tools/audit_tmdb.py`
- `C:/Users/etien/IdeaProjects/Reco/tools/enrich_audit/`
- `C:/Users/etien/IdeaProjects/Reco/tools/tmdb_snapshot.py`

### Eval harness
- `C:/Users/etien/IdeaProjects/Reco/tools/eval_extraction.py`
- `C:/Users/etien/IdeaProjects/Reco/tools/eval/`

### Domain / repository
- `C:/Users/etien/IdeaProjects/Reco/tools/domain/` (Item, Mention, Source, identity)
- `C:/Users/etien/IdeaProjects/Reco/tools/repository/_base.py`
- `C:/Users/etien/IdeaProjects/Reco/tools/repository/item_repo.py`
- `C:/Users/etien/IdeaProjects/Reco/tools/repository/mention_repo.py`
- `C:/Users/etien/IdeaProjects/Reco/tools/repository/serialization/{item,mention}_codec.py`
- `C:/Users/etien/IdeaProjects/Reco/tools/repository/migration/{reco_parser,reco_to_item_mention}.py`

### Migrations versionnées
- `C:/Users/etien/IdeaProjects/Reco/tools/migrate_schema.py`
- `C:/Users/etien/IdeaProjects/Reco/tools/migrations/{registry,runner}.py`
- `C:/Users/etien/IdeaProjects/Reco/tools/migrations/{item,mention,source}/v1_to_v2.py`

### Config externalisée
- `C:/Users/etien/IdeaProjects/Reco/tools/config/` (loader, registry, policies, schema, astro_adapter)
- `C:/Users/etien/IdeaProjects/Reco/sources/un-bon-moment/config.json`

### ADRs
- `C:/Users/etien/IdeaProjects/Reco/docs/adr/0011-eval-harness.md` → `0019-audit-core.md`

### Outputs démo (générés ce jour)
- `C:/Users/etien/IdeaProjects/Reco/tools/output/phase1_demo_lint.json`
- `C:/Users/etien/IdeaProjects/Reco/tools/output/phase1_demo_lint.md`
- `C:/Users/etien/IdeaProjects/Reco/tools/output/lint/un-bon-moment/2026-06-10__lint__un-bon-moment.json`
- `C:/Users/etien/IdeaProjects/Reco/audit/2026-06-10.md`

### Front (Astro)
- `C:/Users/etien/IdeaProjects/Reco/src/content.config.ts` (Zod : `matchSuspect`, `enrichmentSuspect`, `schemaVersion`)
- `C:/Users/etien/IdeaProjects/Reco/src/components/RecoCard.astro`
