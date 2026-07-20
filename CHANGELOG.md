# Changelog

Tous les changements notables de Reco sont documentés ici.
Format basé sur [Keep a Changelog](https://keepachangelog.com/fr/1.1.0/) ; ce projet suit [Semver](https://semver.org/lang/fr/).

## [Non publié]

### Ajouté
- Phase 4 « Méta-agrégateur » (sem 11-13 roadmap) : méta-site `/meta/*` (ADR 0045) + endpoint `.well-known/reco-registry.json`, tracking clics sortants privacy-first (ADR 0046), stats publiques globales (ADR 0047) avec sidecar `stats.json` et JSON-LD Dataset.
- ADRs 0045, 0046, 0047 + extension 0028 (frontière fork-vs-méta).
- Helper `src/lib/stats/page.ts::loadStatsForPage` (DRY pages stats).
- SSRF guard `tools/meta/url_safety.py` (whitelist HTTPS + bloque IPs privées/link-local).
- Phase 3 « Kit déployable » (sem 8-10 roadmap) : Docker compose, wizard CLI `reco init`, README + tutoriels, LICENSE MIT + CITATION + CI publique, page À propos + manifeste éthique, poll RSS hebdo + notification webhook Discord/Slack/Email.
- ADRs 0037 (Docker), 0038 (Wizard), 0039 (License), 0040 (Manifeste), 0041 (Doc strategy), 0042 (Cron RSS).

### Sécurité
- Phase 4 V2 — 111 issues corrigées (11 CRITICAL, 22 HIGH, 40 MEDIUM, 28 LOW, 20 NIT) : SSRF `build_meta` fix, leak chemin serveur 500, fuite IP DuckDuckGo retirée, `_meta/` renommé `meta/` (Astro exclut préfixe `_`), validation Zod registry avant émission, HMAC IP+salt rate-limiter, cap POST body 8 KiB, normalisation slug FS lowercase, JSON-LD `PodcastSeries`.

## [0.2.0] — 2026-06-11

### Ajouté
- Phase 2 (10 items #8-#17) : SQLite cache + FTS5, recherche full-text MiniSearch + Cmd+K, galeries par invité/type, page œuvre canonique, embed audio timecode, OG cards Satori + sitemap, A11y WCAG AA strict, embeddings sémantiques fastembed, signalements visiteurs, re-enrich proactif TMDB/Music.
- 17 ADRs Phase 2 (0020-0036), incluant audit_core, design tokens, fork-guide, i18n single-locale.
- `docs/fork-guide.md` complet (env vars, modules, adapter SSR, multi-source).

### Modifié
- Layout.astro : SearchPalette globale, fallback mailto reports, retrait Google Fonts (Anton via Inter system).
- 5 cross-références ADR vers ADR 0030 (tokens) corrigées.

### Sécurité
- Captcha durci (hash payload sha256, jti UUID LRU, TTL 4h), Anton retiré (RGPD), assertSlug path traversal, isSafeHttpUrl XSS DOM.

## [0.1.0] — 2026-06-10

### Ajouté
- Phase 1 « Fondations critiques » (sem 1-4 roadmap) : config externe, modèle Item/Mention/Source + migration 2866 recos, schemaVersion + migrations, golden set + eval harness, schema linter dataset, détection match YT/Acast suspect, détection enrichissement TMDB incorrect.
- ADRs 0001-0019, dont audit_core unifié.
- 2683 tests Python, build Astro initial 107 pages.

[Non publié]: https://github.com/etienneboursault/reco/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/etienneboursault/reco/releases/tag/v0.2.0
[0.1.0]: https://github.com/etienneboursault/reco/releases/tag/v0.1.0
