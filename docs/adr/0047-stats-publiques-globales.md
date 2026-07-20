# ADR 0047 — Stats publiques globales (`/stats`)

- **Statut** : Acceptée
- **Date** : 2026-06-12
- **Décideurs** : équipe Reco (P4.26)
- **Liens** : ADR 0021 (SEO / OG / sitemap), ADR 0022 (a11y WCAG AA),
  ADR 0026 (i18n), ADR 0027 (mapping JSON-LD), ADR 0031 (galleries),
  ADR 0040 (manifeste éthique), ADR 0045 (méta-site), ADR 0046 (tracking
  clics sortants — vague séparée)

## Contexte

Phase 4 du projet (méta-agrégateur). Item #26 du roadmap : exposer
publiquement les compteurs agrégés du catalogue Reco pour :

1. **Transparence** — un kit qui prétend être éthique doit rendre visibles
   ses propres mesures (combien de sources, combien d'œuvres, qui revient
   le plus souvent).
2. **Effet réseau** — la page `/stats` est un signal communauté (le
   catalogue grossit, la qualité monte) cohérent avec le manifeste.
3. **Référencement** — un `Dataset` schema.org bien câblé est un signal
   SEO honnête (vs. les fermes de pages SEO « top 10 » sans data).

Contraintes :

- Output statique (`output: 'static'`) — pas de SSR, pas de DB runtime.
- Pas de tracker, pas de cookie (cf. ADR 0040). Les chiffres doivent être
  calculés au build, jamais côté visiteur.
- A11y WCAG AA (ADR 0022) — un graphique doit avoir une alternative
  textuelle / tabulaire.
- Build deterministe — tri stable, ISO 8601, pas de `Date.now()` non
  paramétrable côté CLI.
- Vague 1 Phase 4 ne livre pas le tracking clics (cf. dev #25 en parallèle,
  ADR 0046) ; donc pas de stats clics sortants dans cette vague.

## Décision

### Architecture

```
src/lib/stats/                # côté Astro (pures fonctions)
  types.ts        # zod + types StatsSnapshot
  aggregator.ts   # buildStatsSnapshot (façade) + computes
  formatter.ts    # formatCompact / formatCount / formatPercent
  page.ts         # statsDatasetSchema (JSON-LD Dataset)
  slug.ts         # slug ASCII des noms d'invités

tools/stats/                  # miroir Python (pipeline CLI)
  __init__.py
  models.py       # dataclasses
  aggregator.py   # build_snapshot + computes

tools/build_stats.py          # CLI (--source / --format / --output-dir)

src/components/
  StatCard.astro
  TopList.astro   # <table> sémantique (a11y)
  StatChart.astro # SVG inline + table cachée alternative

src/pages/
  stats.astro
  [source]/stats.astro
```

### Schéma `stats.json` (versionné — `STATS_SCHEMA_VERSION = 1`)

```json
{
  "schemaVersion": 1,
  "generatedAt": "2026-06-12T07:45:00Z",
  "global": {
    "podcastsCount": 1, "episodesCount": 104,
    "recommendationsCount": 2866, "uniqueWorksCount": 2651,
    "uniqueGuestsCount": 224
  },
  "perSource": { "un-bon-moment": { ... } },
  "topGuests": [{ "name": "...", "slug": "...", "count": 12 }, ...],
  "topWorks": [{ "id": "...", "title": "...", "type": "film", "mentionsCount": 3 }, ...],
  "typeDistribution": { "film": 437, "livre": 225, ... },
  "monthlyEpisodes": [{ "month": "2024-01", "count": 4 }, ...]
}
```

### Invariants pure-fonctions

- **Filtrage des mentions** : `status='discarded'` → exclues. Cohérent
  avec `src/lib/gallery/aggregate.ts::publicMentions`.
- **Invités vs. hôtes** : `recommendedBy` ∈ `source.hosts` (casefold)
  est exclu du décompte des invités uniques (un host n'est pas un
  « invité »).
- **Œuvres uniques** : item présent dans le catalogue ET mentionné.
- **Tri stable** : `count DESC` puis `name ASC` (locale FR insensible).
- **Mois** : ISO `YYYY-MM` en UTC. Ordre lexicographique = ordre temporel.

### JSON-LD

`statsDatasetSchema` émet un objet `https://schema.org/Dataset` avec
`variableMeasured` (PropertyValue) listant les 5 compteurs globaux.
`distribution` (DataDownload) optionnel pour exposer un export
`stats.json` téléchargeable si on l'héberge.

### A11y

- `<table>` sémantique pour `TopList` (rang / nom / valeur).
- `StatChart` : `<svg role="img" aria-label="…">` + `<title>` SVG par
  barre + table cachée `sr-only` (linéarisation lecteurs d'écran et
  fallback print).
- Pas de lib JS de chart — SVG inline minimaliste, `viewBox` responsive.

### CLI

```
python tools/build_stats.py --source un-bon-moment
python tools/build_stats.py --source all --format csv
```

- Lockfile pipeline (réutilise `review_lock.acquire_pipeline_lock`).
- Écriture atomique (`tools.common.atomic_write_text`).
- Exit codes alignés `audit_core` (M26-22) :
  - `0` — OK.
  - `1` — erreur fonctionnelle (lock pris, source inconnue, source au
    nom non sûr en chemin — cf. M26-23).
  - `2` — exception non rattrapée.
- `--generated-at` pour la reproductibilité des tests.
- Filtrage : les dossiers `__cross_stack_fixture__/`, `_legacy/` et
  `.archived/` sont exclus du scan `getCollection`-like (M26-24).

### Settings (R-P1-25)

`tools/stats/settings.py::StatsSettings` factorise les seuils (top guests,
top works, statuts cachés) en pattern Phase 3.5 (ADR 0033) — délègue à
`audit_core.settings.from_source_extra`. Un fork peut ajuster par source
via `SourceConfig.extra["stats"]` sans patcher le CLI :

```jsonc
{
  "extra": {
    "stats": {
      "top_guests_limit": 25,
      "top_works_limit": 25,
      "hidden_statuses": ["discarded", "flagged"]
    }
  }
}
```

### Sidecar pré-calculé (R-P1-24)

Les pages `/stats` et `/[source]/stats` tentent d'abord la lecture du
sidecar `tools/output/stats/<source|_global>/stats.json` produit par
`build_stats.py`. Si présent + valide (Zod `statsSnapshotSchema.strict()`),
il est utilisé directement ; sinon fallback compute via `getCollection`.

Bénéfice : forks dont le catalogue franchit ~100 000 recommandations
peuvent éviter le coût `getCollection` au build Astro en industrialisant
`build_stats.py` en amont (pattern cohérent ADR 0020 — vues matérialisées).

### SSOT compteurs

`HIDDEN_STATUS` côté TS et `_HIDDEN_STATUSES` côté Python définissent la
SSOT des statuts exclus du compte « public ». La `StatsSettings`
`hidden_statuses` permet à un fork d'élargir cette liste par source sans
toucher au code agrégateur.

### JSON-LD enrichi (M26-16/M26-18)

`statsDatasetSchema` émet désormais :

- `keywords[]` (défaut : podcast, recommandations, statistiques…) ;
- `license` (défaut : MIT — fork peut surcharger) ;
- `publisher` paramétrable depuis `siteConfig` (ADR 0028) ;
- `temporalCoverage` dérivé de `monthlyEpisodes` (ISO 8601 intervalle
  `YYYY-MM/YYYY-MM`) ;
- `distribution[DataDownload]` pointant vers `/stats.json` (M26-17,
  endpoint statique `src/pages/stats.json.ts`).

### Cross-stack golden (R-P1-23)

Fixture commune `tests/fixtures/stats/golden/{input,snapshot}.json`
consommée à la fois par `test_golden.test.ts` (vitest) et
`test_golden_py.py` (pytest). Garantit que `buildStatsSnapshot` (TS) ≡
`build_snapshot` (Py) — couvre la ligature `Œ`/`OEuvre` (M26-21), les
collisions slug (`Léa Martin`/`Lea-Martin` → `lea-martin` / `lea-martin-2`
— M26-19) et le remplissage des trous mensuels (R-P3-30).

## Alternatives évaluées

1. **Endpoint SSR avec query DB live** — incompatible kit static ; overkill
   pour un catalogue de l'ordre du millier d'œuvres ; introduit une
   surface runtime à monitorer. **Rejeté**.
2. **Stats dans la homepage seulement** — déjà partiellement présent
   (`/a-propos`), mais dilue le signal et empêche le `Dataset` schema.org
   dédié. **Rejeté**.
3. **Pas de stats du tout** — manque un livrable Phase 4 et un signal
   communauté ; va à l'encontre du manifeste de transparence. **Rejeté**.
4. **Lib charting (Chart.js, D3, ApexCharts)** — viole le principe « kit
   minimal, build deterministe ». Ajoute du JS bloquant et un poids
   bundle injustifié pour ≤ 50 barres. **Rejeté** au profit du SVG inline.

## Conséquences

- **Positives** : transparence + effet réseau, page additionnelle
  indexable, structure prête à exposer un CSV si besoin, schéma versionné
  (forward-compat).
- **Négatives** : données agrégées publiquement (counts visibles → un
  acteur curieux peut les comparer à d'autres podcasts). Mitigation :
  on n'expose que des comptes et des noms publics (déjà visibles sur les
  pages podcast/galeries).
- **Notes** :
  - Pas de stats clics sortants dans cette vague (cf. ADR 0046, dev #25
    en parallèle) — pourront être ajoutés Phase 4.5 quand `tools/aggregate_clicks.py`
    livre.
  - **Bascule** : si le catalogue franchit ~100 000 recommandations, le
    `getCollection` build-time deviendra lent. Bascule prévue vers des
    vues matérialisées SQLite (cf. ADR 0020) lues côté Astro via un
    JSON sidecar pré-calculé par `build_stats.py`.
