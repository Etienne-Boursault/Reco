# Roadmap Reco — 2026

> **Statut** : roadmap vivante, à mettre à jour après chaque phase.
> Découle de [`vision-2026.md`](./vision-2026.md) (kit open-source self-hostable, multi-podcast, agrégateur méta-site).
> Voir [`yagni.md`](./yagni.md) pour les principes de priorisation.

---

## Vision rappel

**Reco = kit open-source self-hostable pour curation de recommandations issues de podcasts.** N'importe qui peut le déployer pour SON podcast favori. Les sites générés s'agrègent sous un méta-domaine (probable `source-internet.fr`). Volume cible 12 mois : 5-10 podcasts, 1000+ épisodes, 20k+ recos.

---

## Couverture des 165 propositions (synthèse 6 panels)

| Status | Items | % |
|---|---|---|
| ✅ Déjà livré (vagues 1-6) | ~30 | 18% |
| 🎯 Plan explicite (26 items ci-dessous) | ~30 | 18% |
| 📋 Implicite dans les phases | ~20 | 12% |
| 🟡 Polish reviewer reporté (post-Phase 4) | ~15 | 9% |
| ❌ Out of scope (vision-driven) | ~25 | 15% |
| Distillation (doublons cross-panels) | ~40 | 24% |
| **Couvert total** | **~125** | **76%** |

---

## Phase 1 — Fondations critiques (sem 1-4)

Objectif : **dataset propre, schéma stable, multi-source prête.** Sans ça, tout le reste est fragile.

| # | Item | Statut | Effort | Démarré | Terminé |
|---|---|---|---|---|---|
| 1 | Externaliser la config : `sources/<id>/config.json`, suppression hardcode "un-bon-moment" | ✅ | M | 2026-06-10 | 2026-06-10 |
| 2 | Modèle Item / Mention / Source : refactor data model + migration ~2900 recos | ✅ | L | 2026-06-10 | 2026-06-10 |
| 3 | Versioning `schemaVersion` + migrations versionnées (`tools/migrations/`) | ✅ | S | 2026-06-10 | 2026-06-10 |
| 4 | Golden set : 10 épisodes annotés + harness eval precision/recall/F1 | ✅ | M | 2026-06-10 | 2026-06-10 |
| 5 | Schema linter dataset : audit auto des recos (champs requis, valeurs aberrantes, recommendedBy incohérent, titres louches) → `audit/<date>.md` | ✅ | S | 2026-06-10 | 2026-06-10 |
| 6 | Détection mauvais match YT/Acast : durée + embedding intro → flag `matchSuspect=true` | ✅ | S | 2026-06-10 | 2026-06-10 |
| 7 | Détection enrichissement TMDB incorrect : Levenshtein titre + year mismatch + runtime cohérence → flag `enrichmentSuspect=true` | ✅ | S | 2026-06-10 | 2026-06-10 |
| 7.8 | TMDB snapshot CLI (`tools/tmdb_snapshot.py`) alimente le cache pour P1.7 | ✅ | S | 2026-06-10 | 2026-06-10 |
| Sprint 2 | Extraction `tools/audit_core/` (Severity, escape_md, sidecar safety) + migration 3 modules | ✅ | M | 2026-06-10 | 2026-06-10 |

**Phase 1 clôturée le 2026-06-10** — voir [`phase-1-report-2026-06-10.md`](./phase-1-report-2026-06-10.md).

**Items implicites Phase 1** (livrés en chemin) :
- JSON Schema strict (tool use Anthropic + structured outputs OpenAI)
- Logs structurés JSONL + métriques par étape
- Endpoint `/health`
- Validation Zod côté Astro content collections

---

## Phase 2 — Site public + qualité dataset visible (sem 5-7)

Objectif : **site public minimum viable, dataset enrichi auto-corrigé, contributions visiteurs.**

| # | Item | Statut | Effort | Démarré | Terminé |
|---|---|---|---|---|---|
| 8 | SQLite cache d'index (read-through depuis JSON, FTS5) | ✅ | M | 2026-06-11 | 2026-06-11 |
| 9 | Recherche full-text (site public + outil review Cmd+K) | ✅ | M | 2026-06-11 | 2026-06-11 |
| 10 | Galerie par invité + par type (`/invite/<name>`, `/films`, `/livres`...) | ✅ | M | 2026-06-11 | 2026-06-11 |
| 11 | Page œuvre canonique (mentions cross-épisodes, trending) | ✅ | M | 2026-06-11 | 2026-06-11 |
| 12 | Embed audio extrait timecode (différenciateur) | ✅ | M | 2026-06-11 | 2026-06-11 |
| 13 | OG cards + sitemap + meta SEO (Satori build-time) | ✅ | S | 2026-06-11 | 2026-06-11 |
| 14 | A11y WCAG AA (contraste, focus-visible, aria, empty/loading states) | ✅ | M | 2026-06-11 | 2026-06-11 |
| 15 | Embeddings sémantiques (dédup cross-épisode + recos similaires) | ✅ | M | 2026-06-11 | 2026-06-11 |
| 16 | Signalements visiteurs : form + endpoint + storage JSON + queue admin `/reports` + anti-spam (honeypot + math captcha) + crédit contributeurs | ✅ | M | 2026-06-11 | 2026-06-11 |
| 17 | Re-enrich proactif TMDB/Music : flag `enrichedAt` par champ + CLI `--refresh-older-than 90d` + cache `requests-cache` SQLite + refresh sous-champs uniquement | ✅ | S | 2026-06-11 | 2026-06-11 |

**Phase 2 clôturée le 2026-06-11** — voir [`phase-2-report-2026-06-11.md`](./phase-2-report-2026-06-11.md).

Sous-items livrés en chemin : Vague 1 (coord finale), Vague 2A (Pass A/B), Phase 2.17 Pass A, Fixer cumulatif Phase 2 final. ADRs 0020-0036 (17 ADRs, supersession 0031 → 0032).

**Items implicites Phase 2** :
- Idempotence POST (`client_request_id`)
- JSON-first POST partout (vs 303 reload)
- Cache-Control + gzip + ETag fragments
- Tests via `tmp_path` au lieu de Mock
- Type-checking pyright strict sur les fichiers cibles

---

## Phase 3 — Kit déployable (sem 8-10)

Objectif : **n'importe quel non-codeur peut héberger son propre Reco en 1 commande.**

| # | Item | Statut | Effort | Démarré | Terminé |
|---|---|---|---|---|---|
| 18 | Docker compose : pipeline + serveur + Astro build = 1 commande | ✅ | M | 2026-06-12 | 2026-06-12 |
| 19 | Wizard setup CLI : `npx reco init` → questions → génère `sources/<id>/` | ✅ | M | 2026-06-12 | 2026-06-12 |
| 20 | Doc + tutorial : README + screencast 5min "ajouter ton podcast" | ✅ | M | 2026-06-12 | 2026-06-12 |
| 21 | License (MIT + citation) + CONTRIBUTING + CI publique (lint + tests sur PR) | ✅ | S | 2026-06-12 | 2026-06-12 |
| 22 | Page "À propos" + manifeste éthique (anti-Bolloré, librairies indés) | ✅ | XS | 2026-06-12 | 2026-06-12 |
| 23 | Cron RSS auto + notification nouvel épisode : poll RSS hebdo + pipeline auto + webhook Discord/email | ✅ | M | 2026-06-12 | 2026-06-12 |

**Phase 3 clôturée le 2026-06-12** — voir [`phase-3-report-2026-06-12.md`](./phase-3-report-2026-06-12.md).

Sous-vagues livrées : Vague 1 (#18 Docker, #19 Wizard, #20 Doc, #21 License, #22 Manifeste), Vague 2 (#23 Cron RSS + durcissement CI), coordination finale (résolution conflit ADR 0037 → renumérotation Wizard 0038, CR cumulative, sync architecture/index/fork-guide). 6 ADRs (0037-0042).

**Items implicites Phase 3** :
- Config via env vars (`RECO_*`)
- Rotation backups (garder N=50 + <7j)
- Audit trail `change_log` (humain vs LLM vs migration)
- Hot-reload watchdog (dev)
- **P1.2.D** Migrer callsites legacy `Reco`/`Episode` → `Item`/`Mention` puis
  supprimer `tools/domain/_legacy.py` (cf. CR 2026-06-10).

---

## Phase 4 — Méta-agrégateur (sem 11-13)

Objectif : **valider l'hypothèse audience publique + créer l'effet réseau via `source-internet.fr`.**

| # | Item | Statut | Effort | Démarré | Terminé |
|---|---|---|---|---|---|
| 24 | Méta-site `source-internet.fr` : registry JSON public + agrège sites des hosts | ✅ | L | 2026-06-12 | 2026-06-12 |
| 25 | Tracking clics sortants (validation "les gens cliquent") | ✅ | S | 2026-06-12 | 2026-06-12 |
| 26 | Stats publiques globales (X recos, Y podcasts, Z œuvres, top invités) | ✅ | S | 2026-06-12 | 2026-06-12 |

**Phase 4 ✅ Clôturée 2026-06-12 — 111 issues corrigées** (Vague 1 fixers spécialisés + Vague 2 CR exhaustive 5 Fixers parallèles). Voir [`phase-4-report-2026-06-12.md`](./phase-4-report-2026-06-12.md). ADRs 0045 (méta-site), 0046 (tracking), 0047 (stats) + extension 0028 (frontière fork-vs-méta).

---

## 🟡 Polish reviewer reporté (post-Phase 4, optionnel)

À faire **seulement si** la qualité du dataset pose problème ET que tu as le temps. Ces items te servent À TOI comme reviewer mais ne servent pas le kit/public.

- Vue `/drafts` cross-épisode
- Mini-transcript ±15s autour du timecode
- Autosave form édition (localStorage)
- Hover preview YT (thumbnail)
- Pastilles denses sur carte (👤 ⚠ 🎬 🔗)
- Bulk actions sur sélection multi
- Mode focus 1 reco plein écran
- Recherche cross-épisode review (Cmd+K)
- Notes personnelles privées par reco
- Compteur d'actions session
- Marquer épisode complet
- Mode audit rapide
- Distinction seen/unseen sur cards
- Durée écoutée sur timecodes
- Raccourcis numériques cluster (1-9)

---

## ❌ Out of scope (vision-driven)

**Refusés par vision** :
- Newsletter (explicite, non)
- Multi-rôles complexes (chaque host gère)
- Comptes utilisateurs / modération
- App mobile dédiée (Astro responsive suffit)
- i18n EN (FR-only initial)
- Système commentaires / social
- Notifications push

**Overkill / YAGNI** :
- Diarization pyannote
- Embeddings vocaux (invité-récurrent)
- Embeddings hyperboliques (taxonomie)
- Classifier intent LLM
- Active learning rejets humains
- Prefect / Dagster orchestration (cron + makefile suffit pour 5-10 podcasts)
- LLM local pré-filtre vLLM/Ollama
- FastAPI + auth multi-rôles
- MicroLoRA / Sona / Neural-everything

**Différé Phase 5+** (si traction publique le justifie) :
- MusicBrainz / Deezer fallback (Spotify suffit)
- OpenLibrary livres
- IGDB jeux / BDGest BD
- Comparaison cross-podcast "consensus" (besoin 2+ podcasts d'abord)
- Tags libres + tags LLM auto
- Timeline année (`/2024`, `/saison-5`)
- Mode lecture distraction-free public
- Recos similaires "continue le voyage"
- Bookmark visiteur localStorage
- Listes partageables "mes 10 préférées"
- **Font display custom libre** (identité visuelle propre, alternative à Bebas Neue) :
  fork d'une base OFL (Antonio / Steelfish) retouchée dans Birdfont (gratuit) ou
  Glyphs Mini (49 €), ~50-150 glyphes, hinting via ttfautohint, publication sous
  OFL 1.1 dans un repo dédié `bref-condensed-libre` (sources `.glyphs` + builds
  `woff2` + `OFL.txt`). Effort estimé 2-6 sem. solo. Déclencheur : si l'accord
  pour la font de Bref n'est pas obtenu ET qu'on veut signer le projet avec une
  identité unique. Sinon Bebas Neue (OFL, déjà en place 2026-06-12) suffit.
  Cf. ADR 0029 §Bebas Neue.

---

## ✅ Déjà livré (vagues 1-6, historique)

**Backend & sécu** : atomic write everywhere (`atomic_write_text`), lockfile pipeline ↔ serveur (`tools/review_lock.py`), cache `_load_groups` mtime-based, CSRF Origin/Referer check, XSS whitelist URL (`_safe_url`), validation guid/Content-Length, path containment, port check, anti-DNS-rebinding

**Architecture** : split god-object review_server → `review_handler_base.py` + `review_routes.py` + `review_render.py`, extraction `review_render_common.py`, `reco_dedup_merge.py` extrait de `reco_dedup.py`, single-thread by design documenté

**UX reviewer** : 14 raccourcis clavier (J/K/V/C/D/E/R/Espace/T/[/]//?/Esc), carte active + auto-scroll, auto-play YT IFrame API, overlay aide `?`, recherche `/` filtrage, validated vert turquoise (vs grisé), bouton ✕ retirer cluster, undo merge

**UI** : touch-action mobile, pointer events, cluster cuivre distinct, tri chronologique par timestamp, focus visible, contraste WCAG amélioré sur certains items

**Pipeline & qualité** : tri par timestamp, validation cluster compatibility, kind keep_id (vs majoritaire), helper `_yt_timecode_link_parts`, helper `_extractors_badge`, helper `_strip_french_quotes`

**Invités** : 3 champs (`guests` / `guestsParsed` / `guestsExcluded`), source unique `collect_guests`, garde-fou host protégé, harmonisation `casefold()`, 104 épisodes migrés

**Tests** : 953 tests, bs4 helpers (`tests/_html_helpers.py`), 25 tests migrés DOM-based, tests lockfile, tests atomic write, tests crash recovery

---

## Ordre de démarrage suggéré

**Phase 1.A — `C → A → B`** :
1. ⏳ **C** : Golden set + détection YT/Acast (items #4, #5, #6, #7) — ~3-4 jours, consensus 3 panels, nettoyage dataset utile dans tous les cas
2. ⏳ **A** : Externaliser config (item #1) — 1-2 jours, fait émerger les vrais points de couplage
3. ⏳ **B** : Item / Mention / Source (item #2) + versioning (item #3) — 4-5 jours, gros morceau préparé par A

**Phase 1.B** : après audit dataset (étape C), tu sauras combien de recos corrompues / suspects → décider si re-extraction nécessaire.

---

## Garde-fous

1. **Relire `vision-2026.md` avant toute décision structurelle.** Si on dérive vers une feature qui sert "le perso" ou "à voir plus tard" → STOP.
2. **Anti-YAGNI strict** : aucune abstraction "au cas où". Voir [`yagni.md`](./yagni.md).
3. **Re-trancher OK** : si la vision évolue, mettre à jour `vision-2026.md` ET cette roadmap, documenter la bascule.

---

## Historique des phases

| Date | Phase | Items terminés | Notes |
|---|---|---|---|
| 2026-06-10 | Phase 1 | #1-#7 + P1.8 + Sprint 2 (`audit_core`) | 2683 tests verts, coverage 91 %, ADRs 0011-0019. Rapport `phase-1-report-2026-06-10.md` |
| 2026-06-11 | Phase 2 | #8-#17 + Vague 1 / 2A / 2B + Fixer P2 final | 2974 pytest (+291) + 217 vitest, coverage 92 %, build 5791 pages, ADRs 0020-0036. Rapport `phase-2-report-2026-06-11.md` |
| 2026-06-12 | Phase 3 | #18-#23 + Vague 1 / Vague 2 + coord finale | 3185 pytest (+211) + 236 vitest (+19), build 5793 pages, ADRs 0037-0042 (conflit 0037 Docker/Wizard résolu → Wizard 0038). Rapport `phase-3-report-2026-06-12.md` |
| 2026-06-12 | Phase 4 | #24-#26 + Vague 1 fixers spécialisés + Vague 2 (5 Fixers parallèles, 111 issues) | 3528 pytest (+343) + 528 vitest (+292), build 5795 pages, ADRs 0045-0047 + extension 0028. Rapport `phase-4-report-2026-06-12.md` |

### Démarrage Phase 5 (à définir)

Phase 4 clôturée. Prochaine étape conditionnée à demande utilisateur / traction publique. Items reportés potentiels : agrégateur réel (réservation domaine `source-internet.fr` + curation `meta-index.json`), comparaison cross-podcast "consensus" (nécessite 2+ podcasts hébergés), MusicBrainz / OpenLibrary fallback enrichissement.

---

## Dette technique reportée — backlog Phase 2+ (CR cumulative 2026-06-10)

Issues identifiées par la CR cross-modules, **documentées comme reports**
(pas implémentées dans le Fixer cumulatif Phase 1) :

### Phase 1.B / 2

- **Dette-12 / D-03** : job d'agrégation `tools/output/enrich_audit/<src>/<item>.json`
  → `Item.enrichmentSuspect: bool`. Périmètre : ~30 LOC + 1 CLI.
  Côté Astro : `RecoCard.astro` lit déjà conditionnellement (forward-compat
  via Zod). Aucun ADR dédié (cf. note ADR 0014).
- **Dette-9 / item #15 roadmap** : `IntroSimilarityStrategy` embedding réel
  (passage du heuristique titre → embedding audio/transcript). Coût élevé,
  ROI conditionné à la finalisation du golden set.

### Sprint 2 (fin Phase 1) — **LIVRÉ 2026-06-10**

- **C-01..C-05 / Dette-14 / ADR 0019** : extraction `tools/audit_core/`
  (Severity unifié, Reporter Protocol, `escape_md`, `_safe_segment`,
  `from_source_extra`, `RunOptionsBase[Ctx, Report]`, `JsonlAuditTrail`).
  **LIVRÉ** — 7 modules, 100% coverage (88 tests), 0 régression.
- **C-06 / C-07** : convergence `cli_runner` + `Reporter` Protocol —
  **LIVRÉ** via `audit_core`.
- **R-01 / S-01 / S-03** : sidecar `match_audit` versionné
  (`schemaVersion: 1`), `_safe_segment` strict, `escape_md` union.
  **LIVRÉ** + rétro-compat lecture sidecars v0 (warning log).
- **T-02 / T-04** : tests rétro-compat severity legacy + Zod schema
  élargi 4-niveaux. **LIVRÉ** (`tests/test_severity_legacy_sidecars.py`,
  `src/content.config.ts`).
- **D-01 / V-01** : `tools/enrich_audit/settings.py:EnrichAuditSettings`
  + lecture `SourceConfig.extra["enrich_audit"]` par défaut + wire
  dans `cli_runner.default_service(settings=...)`. **LIVRÉ** (12 tests
  dédiés).
- **S-02** : wrapper `_ensure_output_within(base, path)` anti
  path-traversal. **LIVRÉ** (`audit_core.sidecar.ensure_output_within`).
  Wiring dans les CLIs lint/match/enrich = Sprint 3.
- **Dette-6 / Dette-11** : promotion `SourceConfig.match_audit` /
  `enrich_audit` first-class. **REPORTÉ Sprint 3** — risque cross-stack
  Astro/Zod, lecture via `extra[…]` couvre déjà tous les cas (compromis
  acceptable).
- **V-02 / V-04 / Dette-7** : non couverts Sprint 2 — reportés Sprint 3.

### Phase 2

- **Dette-5** : `AutoFixableRule` (linter rules avec fixer attaché).
  Permettrait `tools/lint_dataset.py --fix`.
- **Dette-3 / Phase 4** : `MetaLintReport` cross-modules — agrégation des
  4 rapports (lint + 2 audits + tmdb_snapshot) en un seul tableau de bord.

### Phase 3

- **V-03** : tutoriel « ajouter une source » (1 doc, pas de README dédié).

### Phase 4

- **A-04 / Dette-13** : générateur `INDEX.md` des ADRs. Trivial mais
  reporté (aucune urgence éditoriale).

### Notes diverses

- **R-03** : préférer l'ordre `lint → migrate` dans les runs pipeline
  (le lint capture des incohérences que la migration camouflerait sinon).
- **P-01** : inline du calcul `audit_source` (double allocation). Couvert
  lors de la migration audit_core.
- **P-02** : `tools/bench_audit.py` — micro-bench des 4 CLIs sur
  `un-bon-moment`. Baseline Phase 2 ; pas critique.
- **S-04** : `write_jsonl_log` append sans `flock` — toléré tant que la
  contrainte « single-writer pipeline » tient (lockfile global protège déjà).
  Documenter explicitement « single-writer » si on libère le lock.
- **Reports lointains — Dette-2/4/8** : reformatés lors de la migration
  audit_core ; pas de tracking séparé pour l'instant.
