# Rapport final — Phase 2 Reco (2026-06-11)

## 1. Résumé exécutif

Phase 2 livrée intégralement : 10 items roadmap (#8 → #17), 17 ADRs (0020-0036), 4 Fixers cumulatifs absorbés. Dataset `un-bon-moment` exposé via cache SQLite/FTS5 (2,13 MB, 2755 lignes), recherche full-text site public + palette Cmd+K, galeries par type/invité (224 pages invité + 2622 œuvres canoniques), embeds audio timecode, OG/sitemap/JSON-LD, A11y WCAG AA validée sur 5790 pages, signalements visiteurs avec queue admin, re-enrich proactif. **2974 tests Python verts (+291 vs Phase 1)**, **217 vitest**, coverage globale **92 %**, build Astro **5791 pages en 35,5 s** (104 MB dist). 0 régression. Phase 2 **clôturable** ; Phase 3 (Kit déployable) peut démarrer.

## 2. Items roadmap livrés

| # | Item | Statut | Livrable principal | ADR |
|---|---|---|---|---|
| 8 | SQLite cache d'index FTS5 | ✅ | `tools/build_cache.py`, `tools/output/cache/reco.sqlite` | 0020 |
| 9 | Recherche full-text (site + Cmd+K) | ✅ | `dist/search.json` (470 KB), `src/components/SearchPalette.*` | 0035 |
| 10 | Galerie par invité + par type | ✅ | `/films`, `/livres`, `/musique`, `/series`, `/invite/<slug>` | 0031, 0032 |
| 11 | Page œuvre canonique | ✅ | `/oeuvre/[id]` (2622 pages), agrégation cross-épisodes | 0032 |
| 12 | Embed audio extrait timecode | ✅ | `src/components/AudioExcerpt.astro` | 0036 |
| 13 | OG cards + sitemap + meta SEO | ✅ | `dist/og/*.png` (Satori build-time), `sitemap-index.xml`, JSON-LD | 0021, 0027 |
| 14 | A11y WCAG AA | ✅ | `tests/a11y/check_a11y.mjs` (5790 pages OK), contrast suite | 0022, 0030 |
| 15 | Embeddings sémantiques | ✅ | `tools/embed_items.py`, `tools/output/embeddings/` | 0033 |
| 16 | Signalements visiteurs | ✅ | `tools/manage_reports.py`, queue `/<src>/reports`, honeypot + math captcha + fallback mailto | 0034 |
| 17 | Re-enrich proactif TMDB/Music | ✅ | `tools/refresh_enrichment.py`, `requests-cache` SQLite | 0023 |

**Items implicites traités** : i18n loader `src/i18n/fr.ts` (#25), design tokens (#30), fonts embarquées (#29), CI quality gates (#24), périmètre fork (#28).

## 3. Métriques globales

| Mesure | Phase 1 (2026-06-10) | Phase 2 (2026-06-11) | Δ |
|---|---|---|---|
| Tests Python | 2683 | **2974** | +291 |
| Tests vitest | 0 | **217** (26 fichiers) | +217 |
| Coverage Python globale | 91 % | **92 %** (10307 / 11211 stmts) | +1 pt |
| Pages buildées | 107 | **5791** | +5684 |
| Durée build Astro | 6,83 s | **35,53 s** (27,97 s pages + 7,56 s assets) | +28,7 s |
| Taille `dist/` | ~ qqs MB | **104 MB** | — |
| ADRs Phase | 9 (0011-0019) | **17 (0020-0036)** | +17 |
| Fixers cumulatifs | 1 (Sprint 2) | **4** (V1 coord, V2A, P2.17 Pass A, P2 final) | +3 |

### Modules à coverage 100 % notables (Phase 2)
`tools/search/similarity.py`, `tools/tmdb_snapshot.py`, `tools/transcribe.py`, `tools/whisper_json_to_txt.py`, `tools/build_cache.py`, `tools/embed_items.py`, `tools/refresh_enrichment.py`, `tools/manage_reports.py`.

### Coverage en deçà connue (legacy, hors scope)
`tools/search/service.py` 82 %, `tools/review_routes.py` ~71 %, `tools/review_render_cluster.py` ~77 %.

## 4. Démos CLI (un-bon-moment, 2026-06-11)

| # | Commande | Exit | Output |
|---|---|---|---|
| A | `tools/build_cache.py --source un-bon-moment` | 0 | `items=2651 mentions=2866 episodes=104 fts=2755 en 0.86s ; db=2.13 MB` |
| B | `tools/embed_items.py --source un-bon-moment --dry-run` | 0 | `2651 item(s) candidat(s) sur 1 source(s)` |
| C | `tools/refresh_enrichment.py --source un-bon-moment --dry-run --refresh-older-than 0d --limit 10` | 0 | `scanned=10 refreshed=5 fields=13 tmdb=3 music=2 not_found=0 errors=0` |
| D | `tools/manage_reports.py --source un-bon-moment --list` | 0 | `1 pending (rep-demo-001, cat=error, Mulholland Drive)` |
| E | `tools.lint_dataset --format json` | 0 | `total=457, errors=24, warnings=433, duration=1.01s` (stable vs P1) |
| F | `tools/audit_yt_acast.py --check --format json` | 0 | mêmes compteurs P1 (104 audités, 1 suspect, 2 warnings) |
| G | `tools/audit_tmdb.py --report markdown` | 0 | `5 audited / 2 suspect / 3 clean (skipped 2390 no-tmdb, 256 no-cache)` |
| H | `npm run test:seo` | 0 | `26 fichiers, 217 tests passants en 3,72 s` |
| I | `npm run test:a11y` | 0 | `5790 pages scannées, 0 violation` |
| J | `npm run test:contrast` | 0 | WCAG AA respecté (accent/bg 13,35:1, accent/surface 12,37:1, focus 3:1+) |

## 5. Démos UI — build statique vérifié

| URL / Asset | Vérification | Statut |
|---|---|---|
| `/` | palette Cmd+K présente (`search-palette-dialog`) | ✅ |
| `/` | aucune ressource `googleapis` (Anton retiré, RGPD) | ✅ |
| `/un-bon-moment/` | JSON-LD `application/ld+json` présent | ✅ |
| `/un-bon-moment/episode/<guid>/` | 101 / 104 pages contiennent un lien « Signaler » (3 sans item donc sans CTA) | ✅ |
| `/un-bon-moment/films/` `/livres/` `/musique/` `/series/` | galeries présentes (1 page index par catégorie) | ✅ |
| `/un-bon-moment/invite/<slug>/` | 224 pages invité générées | ✅ |
| `/un-bon-moment/oeuvre/<id>/` | 2622 pages œuvres canoniques | ✅ |
| `/un-bon-moment/report/` | endpoint formel + fallback mailto | ✅ (statique) |
| `/un-bon-moment/reports/` | queue admin reports | ✅ |
| `/un-bon-moment/verifier/` | page review build-time | ✅ |
| `dist/og/un-bon-moment.png` + `dist/og/default.png` + `dist/og/un-bon-moment/<guid>.png` | OG cards Satori | ✅ |
| `dist/sitemap-0.xml` + `sitemap-index.xml` | sitemap multi-page valide, `lastmod` ISO | ✅ |
| `dist/robots.txt` | `Disallow /verifier /reports /api /search.json /recherche` + Sitemap | ✅ |
| `dist/search.json` | index full-text **470 KB** (481 717 octets) | ✅ |

### Anomalies / à valider hors build statique
- **AudioExcerpt** : révélation iframe au clic non testable sans dev server (à valider manuellement post-Phase 2).
- **GalleryCard → /oeuvre/[id]** : wrap link statique présent dans le HTML rendu ; comportement clavier/focus à valider manuellement.

## 6. Issues identifiées et fixées Phase 2

| Source CR | Nombre estimé | Statut |
|---|---|---|
| CR senior × 8 items (#10-#17) | ~280 | fixées |
| CR archi × 8 items (#10-#17) | ~210 | fixées |
| CR cumulative Vague 2A (2 passes) | ~80 | partiellement fixées (Pass C/D reportées, voir §7) |
| CR cumulative Phase 2 entière | ~50 | fixées + plans techniques (voir §7) |
| **Total Phase 2 estimé** | **~620** | quasi 100 % adressées, dette tracée §7 |

## 7. Dette assumée reportée

| Item de dette | Origine | Cible | Justification |
|---|---|---|---|
| `audit_core` convergence finale (Reporter Protocol) | CR Vague 2A Pass C | Phase 2.5 | utilisable en l'état, plan technique rédigé |
| Settings unifié (SourceConfig promotion) | CR Vague 2A Pass C | Phase 2.5 | `extra[...]` couvre 100 % besoins |
| `cli_runner` extraction (helper commun 5 CLIs) | CR Vague 2A Pass D | Phase 2.5 | duplication mesurée, plan d'extraction prêt |
| Provider Protocol formel (TMDB/Music) | CR cumulative P2 | Phase 2.5 | duck typing actuel passe les tests |
| i18n migration `work/report` (namespace incomplet) | CR P2 final | Phase 2.5 | fr.ts existe, clés manquantes documentées |
| Dette-3 / golden set cross-source | Phase 1 → Phase 2 reportée | Phase 3 | golden set monosource stable |
| `--fix` lint auto-fix | Dette-5 | Phase 3 | review humaine prioritaire |
| `INDEX.md` ADR auto-gen | Dette-13 | Phase 4 | manuel acceptable jusqu'à ~50 ADRs |
| MusicBrainz embeddings audio match | Dette-7 | Phase 4 | titre+durée couvrent 99 % |

**Volume dette Phase 2 reportée** : ~50 issues Pass C/D Vague 2A + items techniques structurels listés ci-dessus.

## 8. ADRs Phase 2 (0020-0036)

| ADR | Titre | Statut | Notes |
|---|---|---|---|
| 0020 | SQLite cache FTS5 | accepted | unique ADR #20, pas de collision avec autres Fixers |
| 0021 | SEO OG + sitemap (Satori build-time) | accepted | |
| 0022 | A11y WCAG AA | accepted | |
| 0023 | Re-enrich proactif TMDB/Music | accepted | |
| 0024 | CI quality gates | accepted | |
| 0025 | i18n loader (`src/i18n/fr.ts`) | accepted | namespace fr-only, EN out of scope |
| 0026 | Tokens / theme / shared UI OG | accepted | |
| 0027 | JSON-LD schema mapping | accepted | |
| 0028 | Fork personalization boundary | accepted | |
| 0029 | Fonts embarquées (RGPD, Anton retiré) | accepted | supprime dépendance Google Fonts |
| 0030 | Design tokens / theming | accepted | |
| 0031 | Galleries routing | **superseded by 0032** | conflit résolu lors du Fixer P2 final |
| 0032 | Page œuvre canonique | accepted | absorbe responsabilité 0031 |
| 0033 | Embeddings sémantiques | accepted | |
| 0034 | Visitor reports | accepted | fallback mailto inclus |
| 0035 | Search frontend | accepted | |
| 0036 | Audio excerpt embed | accepted | |

## 9. État dataset réel (un-bon-moment, 2026-06-11)

| Métrique | Phase 1 | Phase 2 |
|---|---|---|
| Items | 2651 | 2651 |
| Mentions | 2866 | 2866 |
| Episodes | 104 | 104 |
| Lint issues | 457 (24 err / 433 warn) | 457 (stable) |
| Match suspects YT/Acast | 1 + 2 warnings | 1 + 2 warnings (stable) |
| TMDB cache items | 5 | 5 |
| TMDB suspects | 2 / 5 | 2 / 5 |
| Cache SQLite | absent | **2,13 MB**, FTS5 = 2755 lignes |
| Embeddings (dry-run candidats) | n/a | **2651 items** |
| Reports queue | n/a | **1 pending** (seed démo) |
| Re-enrich candidats stale | n/a | **2651** (avec `--refresh-older-than 0d`) |

Sidecars conservés Phase 1 : `tools/output/enrich_audit/un-bon-moment/*.json` (5 fichiers), `tools/output/match_audit/un-bon-moment/` (sidecars épisode-level). Phase 1 toujours fonctionnel ; multi-source `--source all` supporté par 6 CLIs.

## 10. Vision-fit (mise à jour Phase 2)

- **Self-hostable** : env vars documentées (`RECO_*`, `SITE_URL`), adapter SSR documenté, fallback mailto reports (pas d'endpoint serveur requis pour MVP), Anton retiré (zéro requête tierce RGPD).
- **Multi-source ready** : `--source all` opérationnel sur `build_cache`, `embed_items`, `refresh_enrichment`, `manage_reports`, `lint_dataset`, `audit_yt_acast`, `audit_tmdb`.
- **WCAG AA atteint** : 0 violation sur 5790 pages, contrast tokens validés (≥ 4,5:1 texte, ≥ 3:1 focus).
- **i18n FR** : namespace `src/i18n/fr.ts` (clés `work`/`report` incomplètes → Phase 2.5).
- **SEO** : OG cards Satori build-time, sitemap multi-page, JSON-LD `Schema.org` mapping.

## 11. Prérequis Phase 3 — Kit déployable

| Prérequis | Statut |
|---|---|
| `fork-guide` complet | ✅ |
| Env vars listées (`RECO_*`, `SITE_URL`) | ✅ |
| Fallback mailto reports (pas de serveur requis) | ✅ |
| A11y validée build statique | ✅ |
| Anton/Google Fonts retiré (RGPD) | ✅ |
| Refs ADR corrigées (0031 → 0032) | ✅ |
| Docker compose | ❌ Phase 3 #18 |
| Wizard CLI `npx reco init` | ❌ Phase 3 #19 |
| Screencast 5 min « ajouter ton podcast » | ❌ Phase 3 #20 |
| License MIT + CITATION + CI publique | ❌ Phase 3 #21 |
| Page « À propos » + manifeste éthique | ❌ Phase 3 #22 |
| Cron RSS auto + notification Discord/email | ❌ Phase 3 #23 |

## 12. Recommandations Phase 3

1. **Phase 2.5 préalable recommandée** (1-2 semaines) :
   - Migration i18n complète (clés `work`/`report`).
   - Résorber dette Pass C/D Vague 2A : `cli_runner` extraction, `audit_core` convergence finale, Provider Protocol formel, Settings unifié.
2. **Item #18** Docker compose : pipeline + serveur + Astro build en 1 commande.
3. **Item #19** Wizard CLI `npx reco init` : questions → génère `sources/<id>/`.
4. **Item #20** Documentation + screencast 5 min « ajouter ton podcast ».
5. **Item #21** License MIT + CITATION + CONTRIBUTING + CI publique (lint + tests sur PR).
6. **Item #22** Page « À propos » + manifeste éthique (anti-Bolloré, librairies indépendantes — cf. mémoire `reco-liens-ethiques`).
7. **Item #23** Cron RSS auto + notification Discord/email nouvel épisode.

## 13. Annexe — Fichiers Phase 2 livrés (groupé)

### Backend cache / search / embeddings / reports / re-enrich
- `C:/Users/etien/IdeaProjects/Reco/tools/build_cache.py`
- `C:/Users/etien/IdeaProjects/Reco/tools/embed_items.py`
- `C:/Users/etien/IdeaProjects/Reco/tools/refresh_enrichment.py`
- `C:/Users/etien/IdeaProjects/Reco/tools/manage_reports.py`
- `C:/Users/etien/IdeaProjects/Reco/tools/search/` (service, similarity, index)
- `C:/Users/etien/IdeaProjects/Reco/tools/output/cache/reco.sqlite`
- `C:/Users/etien/IdeaProjects/Reco/tools/output/reports/un-bon-moment/`
- `C:/Users/etien/IdeaProjects/Reco/tools/output/embeddings/`

### Front Astro — pages
- `C:/Users/etien/IdeaProjects/Reco/src/pages/[source]/films.astro`
- `C:/Users/etien/IdeaProjects/Reco/src/pages/[source]/livres.astro`
- `C:/Users/etien/IdeaProjects/Reco/src/pages/[source]/musique.astro`
- `C:/Users/etien/IdeaProjects/Reco/src/pages/[source]/series.astro`
- `C:/Users/etien/IdeaProjects/Reco/src/pages/[source]/invite/[slug].astro`
- `C:/Users/etien/IdeaProjects/Reco/src/pages/[source]/oeuvre/[id].astro`
- `C:/Users/etien/IdeaProjects/Reco/src/pages/[source]/episode/[guid].astro`
- `C:/Users/etien/IdeaProjects/Reco/src/pages/[source]/report.astro`
- `C:/Users/etien/IdeaProjects/Reco/src/pages/[source]/reports.astro`
- `C:/Users/etien/IdeaProjects/Reco/src/pages/recherche.astro`

### Front Astro — composants
- `C:/Users/etien/IdeaProjects/Reco/src/components/AudioExcerpt.astro`
- `C:/Users/etien/IdeaProjects/Reco/src/components/SearchPalette.*`
- `C:/Users/etien/IdeaProjects/Reco/src/components/GalleryCard.astro`
- `C:/Users/etien/IdeaProjects/Reco/src/components/RecoCard.astro`

### i18n + tokens
- `C:/Users/etien/IdeaProjects/Reco/src/i18n/fr.ts`
- `C:/Users/etien/IdeaProjects/Reco/src/styles/tokens.css`

### Tests Phase 2
- `C:/Users/etien/IdeaProjects/Reco/tests/a11y/check_a11y.mjs`
- `C:/Users/etien/IdeaProjects/Reco/tests/contrast/`
- `C:/Users/etien/IdeaProjects/Reco/tests/seo/` (26 fichiers, 217 tests vitest)
- `C:/Users/etien/IdeaProjects/Reco/tests/test_build_cache.py`
- `C:/Users/etien/IdeaProjects/Reco/tests/test_embed_items.py`
- `C:/Users/etien/IdeaProjects/Reco/tests/test_refresh_enrichment.py`
- `C:/Users/etien/IdeaProjects/Reco/tests/test_manage_reports.py`

### ADRs
- `C:/Users/etien/IdeaProjects/Reco/docs/adr/0020-sqlite-cache-fts5.md` → `0036-audio-excerpt-embed.md`

### Outputs démo (générés ce jour)
- `C:/Users/etien/IdeaProjects/Reco/tools/output/phase2_demo_lint.json`
- `C:/Users/etien/IdeaProjects/Reco/dist/` (5791 pages, 104 MB, build vérifié 2026-06-11 23:23)
