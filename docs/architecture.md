# Architecture — vue d'ensemble système

> Vue système synthétique du projet Reco. Détails techniques par couche
> dans les ADRs référencés en fin de page.

## Pipeline end-to-end

```
   ┌─────────────┐    ┌─────────────┐    ┌─────────────┐
   │ RSS Acast   │    │  YouTube    │    │  TMDB /     │
   │ feedparser  │    │  yt-dlp     │    │  Spotify /  │
   │             │    │             │    │  MusicBrainz│
   └──────┬──────┘    └──────┬──────┘    └──────┬──────┘
          │                  │                  │
          ▼                  ▼                  │
   ┌─────────────────────────────────┐          │
   │ fetch_episodes  +  match_youtube│          │
   └─────────────────┬───────────────┘          │
                     ▼                          │
              ┌──────────────┐                  │
              │ transcribe   │ Whisper          │
              │              │ (CPU / CUDA)     │
              └──────┬───────┘                  │
                     ▼                          │
              ┌──────────────┐                  │
              │ extract_recos│ Anthropic +      │
              │              │ OpenAI ⭐         │
              └──────┬───────┘                  │
                     ▼                          ▼
              ┌──────────────────────────────────┐
              │ enrich_* (tmdb, spotify, music)  │
              └──────┬───────────────────────────┘
                     ▼
              ┌──────────────┐
              │ review_server│ port 8000 (humain valide)
              └──────┬───────┘
                     ▼
              ┌──────────────┐
              │ build_cache  │ → tools/output/cache.json
              └──────┬───────┘
                     ▼
              ┌──────────────┐
              │  Astro build │ → dist/ (5793 pages)
              └──────────────┘
```

## Persistence — 3 SQLite séparés

| DB | Rôle | Pourquoi séparé ? |
|---|---|---|
| `tools/output/cache.sqlite` | Cache enrichments (TMDB, Spotify…) | Reset enrichments sans toucher embeddings. |
| `tools/output/embeddings.sqlite` | Vecteurs sémantiques (search, dédup) | Reset coûteux (regénération) — isolé. |
| `tools/output/http_cache.sqlite` | Cache HTTP brut (requests-cache) | TTL court (24 h) ; ne doit pas faire bouger les autres. |

Séparation justifiée : invalidations différentes, taux de croissance
différent, opérations de maintenance indépendantes
(`vacuum`, `--reset-cache`).

## Frontend Astro

- **Build statique par défaut** (`astro build` → `dist/`).
- **Mode hybride opt-in** (reports POST) : `astro add @astrojs/node` +
  `output: 'hybrid'`. Cf. [ADR 0034 — Visitor reports](adr/0034-visitor-reports.md).
- **Multi-source** : `getStaticPaths` génère `/[source]/…` pour chaque
  `src/content/sources/<slug>.json`.
- **Search** : minisearch côté client, index pré-buildé. Cf. [ADR 0035](adr/0035-search-frontend.md).
- **Tokens design** : `src/lib/tokens.ts` — contrast WCAG AA vérifié en CI.
  Cf. [ADR 0030 — Design tokens theming](adr/0030-design-tokens-theming.md).

## Multi-source

```
src/content/sources/
├── un-bon-moment.json
├── mon-podcast.json        # nouveau fork
└── autre-podcast.json
```

Tous les CLIs Python supportent `--source all` :

```bash
python tools/extract_recos.py --source all --provider anthropic
python tools/audit_tmdb.py --source all
python tools/build_cache.py --source all
```

## ADRs structurants

### Phase 1 — fondations
- [0001](adr/0001-source-config-ssot.md) — Source config SSOT
- [0019](adr/0019-audit-core.md) — Pipeline audit (`build_cache`, `lint_dataset`, `audit_tmdb`)
- [0022](adr/0022-a11y-wcag-aa.md) — A11y WCAG AA
- [0024](adr/0024-ci-quality-gates.md) — CI quality gates

### Phase 2 — qualité + extension
- [0025](adr/0025-locales-i18n.md) — i18n single-locale
- [0028](adr/0028-fork-personalization-boundary.md) — Frontière fork-perso / kit
- [0029](adr/0029-fonts-embedded-licenses.md) — Fonts auto-hébergées
- [0030](adr/0030-design-tokens-theming.md) — Design tokens theming
- [0033](adr/0033-semantic-embeddings.md) — Embeddings sémantiques
- [0034](adr/0034-visitor-reports.md) — Visitor reports (POST hybride)
- [0035](adr/0035-search-frontend.md) — Search frontend minisearch
- [0036](adr/0036-audio-excerpt-embed.md) — Audio excerpt embed

### Phase 3 — kit self-hostable
- [0037](adr/0037-docker-compose-deployment.md) — Docker compose deployment
- [0038](adr/0038-wizard-cli-init.md) — Wizard CLI `reco init`
- [0039](adr/0039-license-mit-citation.md) — License MIT + CITATION
- [0040](adr/0040-manifeste-ethique.md) — Manifeste éthique
- [0041](adr/0041-doc-tutorial-strategy.md) — Doc + tutorial strategy
- [0042](adr/0042-cron-rss-auto-notification.md) — Cron RSS auto + notification

Liste complète : [`adr/`](adr/).
