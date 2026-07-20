# Documentation Reco — table des matières

> Point d'entrée unique de la documentation. Pour démarrer en 5 minutes,
> aller directement à [tutorial/01-getting-started](tutorial/01-getting-started.md).

## Démarrage

- [README](../README.md) — pitch + quick start + features.
- [tutorial/01-getting-started](tutorial/01-getting-started.md) — premier déploiement (5 min).
- [tutorial/02-add-podcast](tutorial/02-add-podcast.md) — ajouter ton podcast (équivalent screencast).
- [tutorial/03-pipeline-walkthrough](tutorial/03-pipeline-walkthrough.md) — pipeline complet pas-à-pas.
- [tutorial/04-deploy-static](tutorial/04-deploy-static.md) — déployer (Netlify, Vercel, Pages, nginx).
- [tutorial/05-customize](tutorial/05-customize.md) — theme, fonts, i18n, branding.

## Référence

- [architecture](architecture.md) — vue d'ensemble système (pipeline, DBs, frontend).
- [fork-guide](fork-guide.md) — guide pour forker et adapter à son podcast.
- [manifeste-ethique](manifeste-ethique.md) — principes éthiques (liens, vie privée, IA).
- [screencast-script](screencast-script.md) — script narratif du screencast 5 min.
- [yagni](yagni.md) — décisions "you ain't gonna need it".

## ADRs (Architecture Decision Records)

Index complet dans [`adr/`](adr/). Sélection structurante :

| ADR | Sujet |
|---|---|
| [0001](adr/0001-source-config-ssot.md) | Source config SSOT (un JSON par podcast) |
| [0019](adr/0019-audit-core.md) | Pipeline audit (cache, lint, audit_tmdb) |
| [0024](adr/0024-ci-quality-gates.md) | CI quality gates (pytest, vitest, pa11y) |
| [0025](adr/0025-locales-i18n.md) | i18n single-locale par fork |
| [0028](adr/0028-fork-personalization-boundary.md) | Frontière fork-perso / kit |
| [0029](adr/0029-fonts-embedded-licenses.md) | Fonts auto-hébergées (pas de Google Fonts) |
| [0033](adr/0033-semantic-embeddings.md) | Embeddings sémantiques (search) |
| [0034](adr/0034-visitor-reports.md) | Reports visiteurs (signalements) |
| [0035](adr/0035-search-frontend.md) | Search frontend (minisearch) |
| [0037](adr/0037-docker-compose-deployment.md) | Docker compose deployment |
| [0038](adr/0038-wizard-cli-init.md) | Wizard CLI `reco init` |
| [0039](adr/0039-license-mit-citation.md) | License MIT + CITATION.cff |
| [0040](adr/0040-manifeste-ethique.md) | Manifeste éthique |
| [0041](adr/0041-doc-tutorial-strategy.md) | Stratégie doc + tutorial |
| [0042](adr/0042-cron-rss-auto-notification.md) | Cron RSS auto + notification |

## Rapports de phase

- [phase-1-report-2026-06-10](phase-1-report-2026-06-10.md) — Phase 1 (P1.1–P1.10).
- [phase-2-report-2026-06-11](phase-2-report-2026-06-11.md) — Phase 2 (P2.11–P2.17).
- [phase-3-report-2026-06-12](phase-3-report-2026-06-12.md) — Phase 3 (P3.18–P3.23).

## Vision & roadmap

- [vision-2026](vision-2026.md) — vision 12 mois.
- [roadmap-2026](roadmap-2026.md) — roadmap trimestrielle.

## Opérations

- [inventaire-un-bon-moment](inventaire-un-bon-moment.md) — tableau de bord épisodes (généré).
- [llm-local](llm-local.md) — setup multi-machine LLM/GPU.
- [session-2026-05-28](session-2026-05-28.md) — CR session.
