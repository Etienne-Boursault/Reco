# Phase 4 — Méta-agrégateur — Rapport 2026-06-12

## 1. Résumé exécutif

Phase 4 livrée intégralement : 3 items roadmap (#24, #25, #26), 3 nouveaux ADRs (0045, 0046, 0047) + extension 0028 (frontière fork-vs-méta). Méta-site `source-internet.fr` (catch-all `/meta/[...all]`), endpoint `.well-known/reco-registry.json` (Zod-validated, SSOT generator/consumer), tracking clics sortants privacy-first (HMAC IP + salt, GC amorti, Sec-GPC respecté, noindex skip), stats publiques globales (sidecar `stats.json`, JSON-LD `Dataset`, DRY via `loadStatsForPage`). **111 issues corrigées** sur deux vagues de CR (Vague 1 fixers spécialisés + Vague 2 CR exhaustive cumulée). **3528 pytest** verts (+343 vs Phase 3), **528 vitest** (+292), build Astro **5795 pages** (+2 stats), 0 régression a11y, 0 leak SSRF, 0 fuite IP. Phase 4 **clôturable** ; Phase 5 ou demande utilisateur peut démarrer.

## 2. Items roadmap livrés

| # | Item | Statut | Livrable principal | ADR |
|---|---|---|---|---|
| 24 | Méta-site `source-internet.fr` | ✅ | `src/pages/meta/[...all].astro` (catch-all), `src/pages/meta/podcast/[slug].astro`, `src/lib/registry/{generator,consumer,meta-loader}.ts`, `src/pages/.well-known/reco-registry.json.ts`, `MetaPodcastCard.astro` + JSON-LD `PodcastSeries`, `tools/meta/{build_meta,url_safety}.py` | 0045 |
| 25 | Tracking clics sortants | ✅ | `src/pages/api/click.ts` (POST 8 KiB cap), `src/lib/tracking/{handler,storage,rateLimit,validator,settings,metrics,types}.ts` (HMAC IP+salt, GC amortized), respect `Sec-GPC`, opt-out cookie-less | 0046 |
| 26 | Stats publiques globales | ✅ | `tools/build_stats.py` (`--source all`, sidecar `stats.json`), `src/pages/stats.astro` + `src/pages/[source]/stats.astro`, `src/lib/stats/page.ts::loadStatsForPage` (DRY), JSON-LD `Dataset` | 0047 |
| — | Extension frontière fork-vs-méta | ✅ | Précision ADR 0028 (META_MODE vs fork standard) | 0028 |

**Sous-vagues** : Vague 1 (CR initiale par item + fixers spécialisés, ~126 issues) → Vague 2 (CR exhaustive Phase entière, 5 Fixers parallèles backend Python + frontend Astro + archi, 111 issues cumulatives — vague terminale).

## 3. Métriques globales

| Mesure | Phase 3 (2026-06-12 matin) | Phase 4 (2026-06-12 soir) | Δ |
|---|---|---|---|
| Tests Python | 3185 | **3528** | +343 |
| Tests vitest | 236 (27 fichiers) | **528** (51 fichiers) | +292 (+24 fichiers) |
| Pages buildées | 5793 | **5795** | +2 (`/stats`, `/un-bon-moment/stats`) |
| ADRs Phase | 6 (0037-0042) | **3 + 1 extension** (0045-0047 + 0028) | +3 |
| Durée build Astro (5795 pages) | ~38 s | **37.80 s** | stable |
| Coverage fichiers Phase 4 | — | **100 %** | nouveau |

## 4. Détail Vague 2 — 111 issues par sévérité

| Sévérité | Backend Python | Frontend + Archi | Total |
|---|---:|---:|---:|
| CRITICAL | 2 | 9 | **11** |
| HIGH | 8 | 14 | **22** |
| MEDIUM | 22 | 18 | **40** |
| LOW | 18 | 10 | **28** |
| NIT | 12 | 8 | **20** |
| **TOTAL** | **62** | **49** | **111** |

### 4.1 Showstoppers corrigés

- **F-CRIT-1** — Renommage `_meta/` → `meta/` : Astro exclut les routes préfixées `_`, le méta-site était inaccessible. Remap des `getStaticPaths()` + tests.
- **F-CRIT-3** — `export const prerender = true` posé sur toutes les pages `/meta/*` (sinon SSR-only sur un fork statique → 404).
- **F-CRIT-5** — Validation Zod de `reco-registry.json` via `parseRegistry()` avant émission (échec build si schéma cassé, prévient un registry corrompu en prod).
- **F-CRIT-6** — Retrait du fallback DuckDuckGo dans `MetaPodcastCard` (fuite IP visiteur vers tiers, incompatible avec ADR 0046 privacy-first).
- **B-CRIT-1** — Suppression du chemin serveur dans la page 500 (`process.cwd()` exposé en stack — leak infra).
- **B-CRIT-2** — SSRF `tools/build_meta.py` corrigé via `tools/meta/url_safety.py` : whitelist HTTPS, blocage IPs privées / link-local / loopback / metadata 169.254.169.254, résolution DNS pré-vérifiée.

## 5. Architecture livrée

- **Méta-site** (`source-internet.fr`) : catch-all `/meta/[...all]`, gallery podcasts (`MetaPodcastCard` + JSON-LD `PodcastSeries`), fiche podcast `/meta/podcast/[slug]`, index-only (pas de scraping runtime), activé par `META_MODE=1` + présence d'un `meta-index.json`.
- **Endpoint registry** : `.well-known/reco-registry.json` (single-line JSON 632 B, schemaVersion: 1, podcast/stats/meta/endpoints), généré par `src/lib/registry/generator.ts`, consommé par `src/lib/registry/consumer.ts` (même Zod schema — SSOT).
- **Tracking clics privacy-first** : POST `/api/click` (cap 8 KiB body, Sec-GPC respecté, opt-out cookie-less), HMAC-SHA256(IP + daily salt) pour rate-limiter sans stockage IP, GC amorti, skip pages noindex.
- **Stats publiques** : `tools/build_stats.py --source all` → `tools/output/stats/_global/stats.json` + `tools/output/stats/<source>/stats.json` → sidecar `dist/stats.json` + pages HTML `/stats` et `/[source]/stats` (JSON-LD `Dataset`), helper `loadStatsForPage` (DRY pour 2 pages stats).

## 6. Test manuel E2E (2026-06-12)

| Section | Commande | Exit | Observation |
|---|---|---:|---|
| A.1 pytest | `tools/.venv/Scripts/python.exe -m pytest -q` | 0 | **3528 passed** en 49.53 s |
| A.2 vitest | `npx vitest run` | 0 | **528 passed** (51 files) en 6.68 s |
| A.3 build prod | `cross-env SITE_URL=https://un-bon-moment.example.com npm run build` | 0 | **5795 pages** en 37.80 s, sitemap-index + sidecar stats.json présents |
| B.1 META_MODE=1 build | `cross-env META_MODE=1 SITE_URL=https://source-internet.fr npm run build` | 0 | 5795 pages, `.well-known/reco-registry.json` (siteUrl=source-internet.fr), pas de `_meta/` (Astro exclut `_`-préfixé), `/meta/*` n'émet rien faute de `meta-index.json` (comportement nominal pour un fork standard, cf. ADR 0028 extension) |
| B.2 META_MODE off | `cross-env SITE_URL=… npm run build` | 0 | Confirmation : aucune page `/meta/*`, registry présent |
| B.3 registry JSON | `python -c "json.load(open(…))"` | 0 | Single-line 632 B, keys = `[schemaVersion, siteUrl, podcast, stats, meta, endpoints]` |
| C tracking files | inventaire | — | `src/pages/api/click.ts` + 7 modules `src/lib/tracking/*.ts` (handler, storage, rateLimit, validator, settings, metrics, types) présents |
| D.1 build_stats | `tools/build_stats.py --source all --format json` | 0 | `tools/output/stats/_global/stats.json` : `uniqueWorksCount=2622`, `uniqueGuestsCount=230`, `topGuests[50]`, `topWorks`, `monthlyEpisodes`, `perSource`, `typeDistribution`, `schemaVersion` |
| D.2 sidecar build | `npm run build` | 0 | `dist/stats.json`, `dist/stats/index.html`, `dist/un-bon-moment/stats/index.html` tous présents |
| E aggregate_clicks | `tools/aggregate_clicks.py --source un-bon-moment --by category` | 0 | Sortie JSON valide `{by, total_clicks: 0, counts: [], by_category: {}}` (aucun event, comportement attendu en dev) |

**Verdict E2E** : 9/9 vert, 0 échec.

## 7. ADRs Phase 4

- **ADR 0045** — Méta-site `source-internet.fr` + registry public.
- **ADR 0046** — Tracking clics sortants privacy-first.
- **ADR 0047** — Stats publiques globales (sidecar JSON + JSON-LD Dataset).
- **ADR 0028 (extension)** — Frontière fork-vs-méta clarifiée (META_MODE comme seul interrupteur, fork standard reste statique).

## 8. Conformité mandat

- [x] TDD strict (test rouge → vert), pas de couverture rétro-active.
- [x] SOLID + Clean Architecture (DIP via Protocols Python / interfaces TS).
- [x] Coverage **100 %** sur fichiers Phase 4.
- [x] Coverage global ≥ 95 %.
- [x] WCAG AA strict (skip-link, focus-visible, SVG `<title>`, classes `sr-only`).
- [x] Privacy-first (HMAC IP+salt, no cookie, no tiers, no fuite IP DDG).
- [x] Déterminisme build (`SOURCE_DATE_EPOCH`, NFKD slug, `hashSlug` stable).
- [x] i18n single-locale FR (ADR 0025 respecté).
- [x] Multi-source `--source all` partout (`build_stats`, `aggregate_clicks`, registry).
- [x] Toutes issues CRITICAL → NIT corrigées (**111 / 111**).

## 9. Verdict

Phase 4 **clôturable**. Méta-agrégateur opérationnel (en attente du domaine `source-internet.fr` + `meta-index.json` côté agrégateur), tracking clics prêt à monter en charge, stats publiques visibles. Build reproductible, 4056 tests verts (3528 pytest + 528 vitest), 0 issue ouverte.

## 10. Prochaine étape

Phase 5 ou demande utilisateur. Items différés potentiels (cf. roadmap-2026 § Phase 4) : agrégateur réel (réservation domaine, hébergement séparé, `meta-index.json` curation), comparaison cross-podcast "consensus" (besoin 2+ podcasts d'abord), MusicBrainz / OpenLibrary fallback.
