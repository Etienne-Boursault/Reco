# Rapport final — Phase 3 Reco (2026-06-12)

## 1. Résumé exécutif

Phase 3 livrée intégralement : 6 items roadmap (#18 → #23), 6 nouveaux ADRs (0037-0042), kit désormais réellement self-hostable en une commande. Docker compose multistage + wizard `npx reco init` + README/tutoriels (×5) + License MIT/CITATION/CI publique + page À propos / manifeste éthique + cron RSS hebdo avec notification Discord/Slack/Email. **3185 tests pytest verts (+211 vs Phase 2)**, **236 vitest (+19)**, build Astro **5793 pages**, 0 violation a11y. Conflit ADR 0037 (Docker vs Wizard) résolu par renumérotation Wizard → 0038. Phase 3 **clôturable** ; Phase 4 (méta-agrégateur `source-internet.fr`) peut démarrer.

## 2. Items roadmap livrés

| # | Item | Statut | Livrable principal | ADR |
|---|---|---|---|---|
| 18 | Docker compose pipeline + review + site | ✅ | `Dockerfile` multistage, `docker-compose.yml` (3 services), `Makefile`, `.env.example`, `.dockerignore`, `docker/review_launcher.py` | 0037 |
| 19 | Wizard CLI `npx reco init` | ✅ | `bin/reco` (Node ESM dispatcher), `tools/reco_init.py`, `tools/init/{slugify,validators,prompts,writer}.py` | 0038 |
| 20 | Doc + tutorial | ✅ | `README.md` refonte (188 lignes), `docs/index.md`, 5 tutoriels `docs/tutorial/01-05`, `docs/architecture.md`, `docs/screencast-script.md` | 0041 |
| 21 | License MIT + CITATION + CI publique | ✅ | `LICENSE` (MIT + ATTRIBUTION REQUEST), `CITATION.cff`, `NOTICE`, `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, `SECURITY.md`, `CHANGELOG.md`, 3 workflows (`ci`, `release`, `security`), `dependabot.yml`, ISSUE/PR templates | 0039 |
| 22 | À propos + manifeste éthique | ✅ | `docs/manifeste-ethique.md`, `src/pages/a-propos.astro`, `src/pages/manifeste.astro`, `SiteFooter` mis à jour | 0040 |
| 23 | Cron RSS auto + notification | ✅ | `tools/poll_rss.py`, `tools/rss/` (ports/parser/state/detector), `tools/notify/` (discord/slack/email/formatter), `.github/workflows/cron-rss.yml` | 0042 |

**Sous-vagues** : Vague 1 (#18 Docker, #19 Wizard, #20 Doc, #21 License, #22 Manifeste — soft-launch) → Vague 2 (#23 Cron RSS, durcissement CI) → Coordination finale (résolution conflit ADR 0037, CR cumulative, sync architecture/index/fork-guide).

## 3. Métriques globales

| Mesure | Phase 2 (2026-06-11) | Phase 3 (2026-06-12) | Δ |
|---|---|---|---|
| Tests Python | 2974 | **3185** | +211 |
| Tests vitest | 217 | **236** (27 fichiers) | +19 (a-propos / manifeste) |
| Pages buildées | 5791 | **5793** | +2 (`/a-propos`, `/manifeste`) |
| ADRs Phase | 17 (0020-0036) | **6 (0037-0042)** | +6 |
| Workflows CI | 1 (a11y.yml) | **5** (a11y + ci + release + security + cron-rss) | +4 |
| Fichiers gouvernance racine | 0 | **9** (LICENSE, CITATION.cff, NOTICE, CONTRIBUTING.md, CODE_OF_CONDUCT.md, SECURITY.md, CHANGELOG.md, Dockerfile, docker-compose.yml) | +9 |
| `bin/` dispatcher | absent | `bin/reco` (Node ESM) | nouveau |

### Modules nouveaux Phase 3
`tools/init/` (wizard), `tools/rss/` (poll RSS), `tools/notify/` (webhooks), `docker/` (review_launcher).

## 4. Démos (un-bon-moment, 2026-06-12)

| # | Vérification | Statut |
|---|---|---|
| A | `python -m tools.reco_init --ci --slug=demo --name="Demo" --rss-url=https://example.com/rss.xml --dry-run` | ✅ JSON conforme Zod |
| B | `python tools/poll_rss.py --source un-bon-moment --dry-run --notify none --json` | ✅ idempotent, 0 nouvelle notif |
| C | `docker compose config` (validation YAML compose) | ✅ 3 services + profile pipeline |
| D | `make up` / `make ps` / `make down` | ✅ healthcheck OK |
| E | `tests/docker/test_dockerfile_lint.py` (multistage, healthcheck, secrets) | ✅ |
| F | `tests/docker/test_docker_smoke.py` (skipif daemon absent) | ✅ skipped en CI sans Docker |
| G | `pytest tests/ --tb=no` | ✅ **3185 passed, 1 skipped** |
| H | `npm run test:seo` | ✅ **236 passed** (27 fichiers, 4,30 s) |
| I | `/a-propos` (build) | ✅ page rendue, JSON-LD WebPage présent |
| J | `/manifeste` (build) | ✅ ancres + sommaire navigable |
| K | Workflow `cron-rss.yml` (lint YAML + secret `RECO_DISCORD_WEBHOOK`) | ✅ permissions minimales |

## 5. Issues identifiées Phase 3

Sources : CR senior × 6 items + CR archi cross-modules + audit gouvernance OSS + audit cohérence ADR/docs.

| Source CR | Estimation | Statut |
|---|---|---|
| CR Vague 1 (#18-#22) | ~45 | fixées par devs |
| CR Vague 2 (#23) | ~15 | fixées par dev |
| CR coordination finale (conflit ADR 0037, cross-refs) | ~10 | fixées par coord |
| **CR cumulative Phase 3 (ce rapport)** | **8** | **7 fixées ci-dessous, 1 reportée** |
| **Total Phase 3 estimé** | **~78** | ~99 % adressées |

### Issues fixées par ce rapport (Phase B in-process)

1. `bin/reco` : commentaire `Cf. ADR 0037 (roadmap #19 — wizard CLI init)` → `Cf. ADR 0038` (wizard renuméroté).
2. `tools/reco_init.py` : docstring `cf. ADR 0037, roadmap #19` → `cf. ADR 0038, roadmap #19`.
3. `tools/init/__init__.py` : docstring `cf. ADR 0037` → `cf. ADR 0038`.
4. `tools/init/prompts.py` : docstring `cf. ADR 0037, garde-fou …` → `cf. ADR 0038, …`.
5. `tests/init/test_slugify.py` : docstring `cf. ADR 0037` → `cf. ADR 0038`.
6. `docs/fork-guide.md` §0 : `Depuis P3.19 (ADR 0037)` → `ADR 0038` (le §12 Docker reste sur ADR 0037 — correct).
7. `README.md` :
   - `17 ADRs documentent…` → `42 ADRs documentent…` (compteur global).
   - `| 41 ADRs (décisions architecture) |` → `| 42 ADRs |`.
   - `python -m pytest tools/tests -q` → `python -m pytest tests/ -q` (chemin réel).
8. `docs/index.md` :
   - Ligne ADR 0042 ajoutée dans « Sélection structurante ».
   - Placeholder « *(à venir)* phase-3-report-2026-06-12 — Phase 3 vague 1 (P3.18–P3.22) » → lien réel + P3.18-P3.23.
9. `docs/architecture.md` : ADR 0042 ajoutée à la section « Phase 3 — kit self-hostable ».

### Issues reportées Phase 3.5 / Phase 4

| Item | Origine | Cible | Justification |
|---|---|---|---|
| Smoke test Docker réel (build + curl /healthz) | CR cumulative | Phase 3.5 | actuellement skipif daemon absent ; CI sans Docker, manuel local |
| Test E2E wizard → build Astro complet | CR cumulative | Phase 3.5 | les unit tests Python couvrent la génération JSON ; round-trip Zod manuel |
| Screencast vidéo réel (`docs/screencast-script.md` → MP4) | ADR 0041 | Phase 3.5 | script narratif livré, enregistrement studio reporté |
| Publication image Docker GHCR multi-arch | ADR 0037 | Phase 3.5 | `release.yml` prêt mais conditionné, pas exécuté |
| Email domaine réservé (`conduct@`, `security@source-internet.fr`) | ADR 0039 | Phase 4 | placeholders documentés, à réserver avant ouverture dépôt public |
| `tests/lint/test_manifesto_sync.py` (sync `.md` ↔ `.astro`) | ADR 0040 | Phase 4 | divergence faible documentée |
| `npm publish @source-internet/reco` (nom à scoper) | ADR 0039 | Phase 4 | nom non réservé, scope à choisir |
| `INDEX.md` ADR auto-généré | Dette-13 | Phase 4 | manuel acceptable jusqu'à ~50 ADRs |

## 6. Dette assumée reportée

| Item de dette | Origine | Cible | Justification |
|---|---|---|---|
| i18n migration `work`/`report` namespaces | CR P2 final | Phase 3.5 | `fr.ts` existe, clés `work.*`/`report.*` incomplètes |
| `audit_core` convergence finale (Reporter Protocol) | CR Vague 2A | Phase 3.5 | utilisable en l'état |
| Settings unifié (SourceConfig.match_audit promotion) | CR Vague 2A | Phase 3.5 | `extra[...]` couvre 100 % besoins |
| `cli_runner` extraction (helper commun 5 CLIs) | CR Vague 2A | Phase 3.5 | duplication mesurée, plan d'extraction prêt |
| Provider Protocol formel (TMDB/Music) | CR cumulative P2 | Phase 3.5 | duck typing actuel passe les tests |
| Golden set cross-source (Dette-3) | Phase 1 → Phase 2 | Phase 4 | golden set monosource stable |
| `--fix` lint auto-fix (Dette-5) | Phase 2 | Phase 4 | review humaine prioritaire |
| MusicBrainz embeddings audio match (Dette-7) | Phase 2 | Phase 4 | titre+durée couvrent 99 % |
| Image Docker non-root (UID/GID fixe) | ADR 0037 | Phase 3.5 | requis avant publication officielle GHCR |
| Notifications retry/backoff webhook | ADR 0042 | Phase 4 | best-effort acceptable hebdo |

**Volume dette Phase 3 reportée** : ~10 issues structurelles + dette héritée Phase 2.5 non encore résorbée.

## 7. ADRs Phase 3 (0037-0042)

| ADR | Titre | Statut | Notes |
|---|---|---|---|
| 0037 | Docker compose deployment | accepted | multistage Node+Python, 3 services, profiles, secrets via `env_file` |
| 0038 | Wizard CLI `reco init` | accepted | **renuméroté ex-0037** lors de la coordination finale (conflit Docker) |
| 0039 | License MIT + CITATION + CI publique | accepted | MIT + ATTRIBUTION REQUEST non-binding, CITATION.cff, 3 workflows + Dependabot |
| 0040 | Manifeste éthique | accepted | anti-Bolloré sourcé Acrimed/Wikipédia, librairies indés (Place des Libraires, Lalibrairie, Librest) |
| 0041 | Doc + tutorial strategy | accepted | README court + 5 tutos + architecture + script screencast |
| 0042 | Cron RSS auto + notification | accepted | GHA cron lundi 06:00 UTC, Discord/Slack/Email, idempotence via state.json LRU |

### Cross-refs ADR validées
- ADR 0037 ↔ §12 fork-guide (Docker) ✓
- ADR 0038 ↔ §0 fork-guide (Wizard) ✓ *(fixé)*
- ADR 0039 ↔ ADR 0024 (CI a11y existante) ✓
- ADR 0040 ↔ ADR 0029 (fonts RGPD), ADR 0034 (reports IP hash), ADR 0036 (youtube-nocookie) ✓
- ADR 0041 ↔ ADR 0025 (i18n FR), ADR 0040 (sobriété) ✓
- ADR 0042 ↔ ADR 0024 (CI pattern), ADR 0028 (autonomie kit) ✓

## 8. État dataset réel (un-bon-moment, 2026-06-12)

Inchangé vs Phase 2 (Phase 3 n'a touché ni au dataset ni aux enrichments) :

| Métrique | Phase 2 | Phase 3 |
|---|---|---|
| Items | 2651 | 2651 |
| Mentions | 2866 | 2866 |
| Episodes | 104 | 104 |
| Lint issues | 457 (24 err / 433 warn) | 457 (stable) |
| Cache SQLite | 2,13 MB, FTS5 = 2755 lignes | stable |

## 9. Vision-fit (mise à jour Phase 3)

| Critère vision | Statut |
|---|---|
| **Self-hostable en 1 commande** | ✅ `cp .env.example .env && docker compose up` (3-5 min cold build) |
| **Multi-source `--source all`** | ✅ stable Phase 2 |
| **Wizard onboarding `npx reco init`** | ✅ slug/RSS/hosts/thème en < 1 min, validation pré-écriture |
| **Manifeste éthique public** | ✅ `/manifeste` + `docs/manifeste-ethique.md` (Acrimed, Wikipédia sourcés) |
| **License MIT + CITATION** | ✅ ATTRIBUTION REQUEST non-binding + CITATION.cff (CFF 1.2) |
| **CI publique** | ✅ 5 workflows (a11y, ci, release, security, cron-rss), Dependabot |
| **Cron auto + notification** | ✅ GHA cron hebdo + Discord/Slack/Email, idempotent |
| **Documentation progressive** | ✅ README court + 5 tutoriels + architecture + script screencast |
| **Gouvernance contributive** | ✅ CONTRIBUTING + CoC (Contributor Covenant 2.1) + SECURITY + ISSUE/PR templates |

Verdict : **un nouveau fork peut effectivement déployer en 5 minutes** (Docker), ou en 15 minutes natif. Une seule friction restante : enregistrement réel du screencast vidéo (script livré, MP4 reporté Phase 3.5).

## 10. Prérequis Phase 4 — Méta-agrégateur

| Prérequis | Statut |
|---|---|
| Phase 3 clôturée (kit duplicable réel) | ✅ |
| License MIT + CONTRIBUTING (forks légitimes) | ✅ |
| Manifeste éthique public | ✅ |
| Cron RSS auto (forks vivants sans entretien manuel) | ✅ |
| CI publique sur PR | ✅ |
| Registry JSON public `source-internet.fr` | ❌ Phase 4 #24 |
| Tracking clics sortants | ❌ Phase 4 #25 |
| Stats publiques globales | ❌ Phase 4 #26 |

## 11. Recommandations Phase 4

1. **Phase 3.5 préalable courte** (1 semaine) :
   - Migration i18n complète (clés `work`/`report`).
   - Smoke test Docker réel + E2E wizard → build.
   - Enregistrement screencast vidéo (script déjà livré).
   - Image Docker non-root + publication GHCR (1ère release `v0.3.0`).
   - Réserver domaines emails (`conduct@`, `security@source-internet.fr`).
2. **Item #24 Méta-site `source-internet.fr`** (effort L) — registry JSON public + agrégation des sites des hosts (vérification effet réseau).
3. **Item #25 Tracking clics sortants** (effort S) — validation hypothèse audience.
4. **Item #26 Stats publiques globales** (effort S) — X recos, Y podcasts, Z œuvres, top invités.
5. **Soft-launch externe** : poster annonce dépôt public après #24 livré + 1-2 forks démos invités (autre podcast indé partenaire).

## 12. Annexe — Fichiers Phase 3 livrés (groupé)

### Item #18 — Docker compose
- `C:/Users/etien/IdeaProjects/Reco/Dockerfile`
- `C:/Users/etien/IdeaProjects/Reco/docker-compose.yml`
- `C:/Users/etien/IdeaProjects/Reco/.env.example`
- `C:/Users/etien/IdeaProjects/Reco/.dockerignore`
- `C:/Users/etien/IdeaProjects/Reco/Makefile`
- `C:/Users/etien/IdeaProjects/Reco/docker/review_launcher.py`
- `C:/Users/etien/IdeaProjects/Reco/tests/docker/test_dockerfile_lint.py`
- `C:/Users/etien/IdeaProjects/Reco/tests/docker/test_docker_smoke.py`
- `C:/Users/etien/IdeaProjects/Reco/docs/adr/0037-docker-compose-deployment.md`

### Item #19 — Wizard CLI `reco init`
- `C:/Users/etien/IdeaProjects/Reco/bin/reco`
- `C:/Users/etien/IdeaProjects/Reco/tools/reco_init.py`
- `C:/Users/etien/IdeaProjects/Reco/tools/init/__init__.py`
- `C:/Users/etien/IdeaProjects/Reco/tools/init/slugify.py`
- `C:/Users/etien/IdeaProjects/Reco/tools/init/validators.py`
- `C:/Users/etien/IdeaProjects/Reco/tools/init/prompts.py`
- `C:/Users/etien/IdeaProjects/Reco/tools/init/writer.py`
- `C:/Users/etien/IdeaProjects/Reco/tests/init/` (test_slugify, test_validators, test_prompts, test_writer, test_reco_init_e2e)
- `C:/Users/etien/IdeaProjects/Reco/docs/adr/0038-wizard-cli-init.md`

### Item #20 — Doc + tutorial
- `C:/Users/etien/IdeaProjects/Reco/README.md` (refonte, 188 lignes)
- `C:/Users/etien/IdeaProjects/Reco/docs/index.md`
- `C:/Users/etien/IdeaProjects/Reco/docs/tutorial/01-getting-started.md`
- `C:/Users/etien/IdeaProjects/Reco/docs/tutorial/02-add-podcast.md`
- `C:/Users/etien/IdeaProjects/Reco/docs/tutorial/03-pipeline-walkthrough.md`
- `C:/Users/etien/IdeaProjects/Reco/docs/tutorial/04-deploy-static.md`
- `C:/Users/etien/IdeaProjects/Reco/docs/tutorial/05-customize.md`
- `C:/Users/etien/IdeaProjects/Reco/docs/architecture.md`
- `C:/Users/etien/IdeaProjects/Reco/docs/screencast-script.md`
- `C:/Users/etien/IdeaProjects/Reco/docs/adr/0041-doc-tutorial-strategy.md`

### Item #21 — License MIT + CITATION + CI publique
- `C:/Users/etien/IdeaProjects/Reco/LICENSE`
- `C:/Users/etien/IdeaProjects/Reco/CITATION.cff`
- `C:/Users/etien/IdeaProjects/Reco/NOTICE`
- `C:/Users/etien/IdeaProjects/Reco/CONTRIBUTING.md`
- `C:/Users/etien/IdeaProjects/Reco/CODE_OF_CONDUCT.md`
- `C:/Users/etien/IdeaProjects/Reco/SECURITY.md`
- `C:/Users/etien/IdeaProjects/Reco/CHANGELOG.md`
- `C:/Users/etien/IdeaProjects/Reco/.github/workflows/ci.yml`
- `C:/Users/etien/IdeaProjects/Reco/.github/workflows/release.yml`
- `C:/Users/etien/IdeaProjects/Reco/.github/workflows/security.yml`
- `C:/Users/etien/IdeaProjects/Reco/.github/dependabot.yml`
- `C:/Users/etien/IdeaProjects/Reco/.github/ISSUE_TEMPLATE/` (bug, feature, doc, fork_help)
- `C:/Users/etien/IdeaProjects/Reco/.github/PULL_REQUEST_TEMPLATE.md`
- `C:/Users/etien/IdeaProjects/Reco/docs/adr/0039-license-mit-citation.md`

### Item #22 — À propos + manifeste éthique
- `C:/Users/etien/IdeaProjects/Reco/docs/manifeste-ethique.md`
- `C:/Users/etien/IdeaProjects/Reco/src/pages/a-propos.astro`
- `C:/Users/etien/IdeaProjects/Reco/src/pages/manifeste.astro`
- `C:/Users/etien/IdeaProjects/Reco/src/components/SiteFooter.astro` (mis à jour)
- `C:/Users/etien/IdeaProjects/Reco/src/i18n/fr.ts` (namespaces `about.*`, `manifesto.*`)
- `C:/Users/etien/IdeaProjects/Reco/tests/seo/a-propos.spec.ts`
- `C:/Users/etien/IdeaProjects/Reco/tests/seo/manifeste.spec.ts`
- `C:/Users/etien/IdeaProjects/Reco/docs/adr/0040-manifeste-ethique.md`

### Item #23 — Cron RSS + notification
- `C:/Users/etien/IdeaProjects/Reco/tools/poll_rss.py`
- `C:/Users/etien/IdeaProjects/Reco/tools/rss/` (ports, parser, state, detector)
- `C:/Users/etien/IdeaProjects/Reco/tools/notify/` (ports, discord, slack, email, formatter)
- `C:/Users/etien/IdeaProjects/Reco/.github/workflows/cron-rss.yml`
- `C:/Users/etien/IdeaProjects/Reco/tests/rss/` (parser, state, detector)
- `C:/Users/etien/IdeaProjects/Reco/tests/notify/` (discord, slack, email, formatter)
- `C:/Users/etien/IdeaProjects/Reco/tests/test_poll_rss.py`
- `C:/Users/etien/IdeaProjects/Reco/docs/adr/0042-cron-rss-auto-notification.md`

### Coordination finale (ce rapport)
- `C:/Users/etien/IdeaProjects/Reco/docs/phase-3-report-2026-06-12.md` (ce fichier)
- `C:/Users/etien/IdeaProjects/Reco/docs/roadmap-2026.md` (mise à jour clôture Phase 3)
- `C:/Users/etien/IdeaProjects/Reco/docs/fork-guide.md` (§0 ADR ref corrigée)
- `C:/Users/etien/IdeaProjects/Reco/docs/index.md` (ADR 0042 + lien rapport)
- `C:/Users/etien/IdeaProjects/Reco/docs/architecture.md` (ADR 0042 listée)
- `C:/Users/etien/IdeaProjects/Reco/README.md` (compteurs ADR + chemin tests)
