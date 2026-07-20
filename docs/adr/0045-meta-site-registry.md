# ADR 0045 — Méta-site `source-internet.fr` : registry JSON public + agrégat de forks

- **Statut** : Accepté
- **Date** : 2026-06-12
- **Auteurs** : Dev P4.24
- **Liens** : ADR 0021 (SEO/OG/sitemap), ADR 0028 (frontière fork),
  ADR 0040 (manifeste éthique), `docs/vision-2026.md` (méta-domaine)

## Contexte

Phase 4 — la vision 2026 prévoit un méta-domaine `source-internet.fr`
qui agrège les forks Reco déployés en production (cible 5–10 podcasts).
Le kit est self-hostable : chaque fork vit sur son propre domaine
(`un-bon-moment.example.com`, etc.), avec ses propres données, son propre
manifeste, ses propres liens éthiques.

Problèmes à résoudre :

1. **Découverte** : comment un méta-agrégateur sait-il qu'un fork existe,
   son volume, sa langue, son flux RSS ?
2. **Décentralisation** : pas de DB centrale (perd l'autonomie des forks).
3. **Effet réseau** : sans index visible, chaque fork reste isolé.
4. **Confiance** : les stats affichées doivent venir du fork lui-même,
   pas d'un crawl invasif.

## Décision

### Registry JSON par fork (SSOT)

Chaque déploiement Reco expose `/.well-known/reco-registry.json` — un
document machine-readable conforme au schema `RegistryDocument`
(`src/lib/registry/types.ts`). Format léger :

```json
{
  "schemaVersion": 1,
  "siteUrl": "https://un-bon-moment.example.com",
  "podcast": { "title": "Un Bon Moment", "hosts": ["..."], "language": "fr" },
  "stats": { "itemsCount": 2651, "mentionsCount": 2866, "episodesCount": 104, "guestsCount": 224, "lastUpdatedAt": "2026-06-12T00:00:00Z" },
  "meta": { "generator": "Reco/0.3.0", "generatedAt": "2026-06-12T07:45:00Z", "manifesto": "..." },
  "endpoints": { "ogImage": "/og/default.png", "sitemap": "/sitemap-index.xml", "search": "/search.json" }
}
```

Le schema est versionné (`schemaVersion: 1`). Toute évolution
non rétro-compatible DOIT bumper le numéro et lister les changements ici.

Le contrat est dupliqué dans deux validateurs :

- **TS / Zod** : `src/lib/registry/types.ts` (parseRegistry).
- **Python** : `tools/meta/validator.py` (validate_registry).

L'endpoint Astro (`src/pages/.well-known/reco-registry.json.ts`) lit les
collections (`sources`, `episodes`, `items`, `mentions`), agrège les
stats, et écrit le JSON au build (compatible `output: 'static'`).

### Méta-site mode opt-in dans le même repo

Le méta-site vit dans le même repo, sous `src/pages/_meta/`. Activation
via la variable d'environnement `META_MODE=1` au build. Sans elle :

- `src/lib/registry/meta-loader.ts` retourne `null`,
- `getStaticPaths` ne yielde rien,
- les pages `/_meta/*` n'apparaissent pas dans `dist/`.

Avec `META_MODE=1`, `tools/build_meta.py` doit avoir préalablement
produit `tools/output/meta/meta_index.json` à partir d'un fichier listant
les URLs des registries à inclure.

```
META_MODE=1 SITE_URL=https://source-internet.fr npm run build
```

### CLI `tools/build_meta.py`

- Lit un fichier YAML/JSON listant les URLs des registries.
- Fetche chaque registry (cache HTTP `requests-cache` TTL 1h).
- Valide chaque document (`validate_registry`).
- Agrège en `meta_index.json` (tri mentions desc + totals globaux).
- Erreurs collectées par URL (jamais bloquant — best-effort).

### Effet réseau

Deux mécanismes :

1. **Inscription via PR** sur le repo méta-site (ajouter son URL dans le
   fichier de registries).
2. **Découverte passive** (future) : crawler des annuaires connus, ou
   webfinger sur `/.well-known/`.

Le format public sous `/.well-known/` est volontairement choisi pour
permettre la découverte automatique par d'autres outils
(podcatchers, agrégateurs RSS, etc.).

## Alternatives évaluées

| Option | Verdict |
|---|---|
| **Méta-site dans un repo séparé** | Rejeté : gestion doublonnée des types/i18n, divergence inévitable. Le mode opt-in dans le même repo préserve la SSOT. |
| **DB centralisée (PostgreSQL / Supabase)** | Rejeté : perte de décentralisation, dépendance d'infra, secret partagé. Garde un point de panne unique. |
| **Pas de méta-site** | Rejeté : perd l'effet réseau, chaque fork reste isolé, contredit la vision 2026. |
| **WebFinger / .well-known/host-meta** | Considéré : plus standard, mais plus rigide. On garde `reco-registry.json` simple. WebFinger pourrait être ajouté plus tard sans rupture. |

## Conséquences positives

- **Standardisation simple** : un seul fichier JSON par fork, format
  versionné, schema validé des deux côtés (Zod + Python).
- **Décentralisation préservée** : chaque fork reste autonome.
- **Decoupling** : le méta-site peut tourner sur n'importe quel host —
  pas de couplage au runtime des forks.
- **Fork-friendly** : aucun setup nécessaire pour un fork standard ; il
  expose automatiquement son registry.
- **A11y / privacy** : pas d'inline JS dans la grille méta, aucun
  tracker, aucune IP visiteur dans le registry.

## Conséquences négatives

- **Pas de sécurité d'authenticité** : n'importe qui peut tricher ses
  stats dans son propre registry. Mitigation : à terme, signature
  cryptographique optionnelle (`meta.signature`), audit manuel par
  le mainteneur du méta-site, ou validation croisée via le sitemap.
- **Latence d'indexation** : le méta-site doit re-fetcher pour voir
  les mises à jour. Mitigation : cache HTTP TTL 1h, build régulier
  (cron quotidien).
- **Pas de notifications push** : un fork qui publie un nouvel
  épisode n'est pas immédiatement visible. Mitigation acceptée pour
  l'échelle cible (5–10 podcasts).

## SSOT comptage (X-P0-32)

Les compteurs (`itemsCount`, `mentionsCount`, `episodesCount`, `guestsCount`)
exposés par `/.well-known/reco-registry.json` viennent EXCLUSIVEMENT de
`computeGlobalCounts` (`src/lib/stats/aggregator.ts`) — la même fonction
qui alimente les pages publiques `/stats`. Conséquences :

| Champ registry | Source SSOT |
|---|---|
| `stats.itemsCount` | `uniqueWorksCount` — items mentionnés (≠ taille du catalogue) |
| `stats.mentionsCount` | `recommendationsCount` (mentions publiques, hors `discarded`) |
| `stats.episodesCount` | `episodesCount` (épisodes de la source courante) |
| `stats.guestsCount` | `uniqueGuestsCount` (recommendedBy hors hosts, case-insensitive) |

Le générateur n'effectue plus aucun comptage local. Toute évolution
des compteurs passe par `computeGlobalCounts` (et reste implicitement
versionnée par `STATS_SCHEMA_VERSION`). Cela évite la double-source de
vérité (ex. `guestsCount` historique calculé depuis `episode.guests`
n'incluait pas la règle d'exclusion des hosts).

Le schema **ne bumpe pas** (`schemaVersion: 1` inchangé) — le format
JSON externe est identique. Seule la sémantique interne a été corrigée.

## Forward-compat — champs réservés (R-P1-05)

Pour absorber Phase 4.5 (multi-source par fork) sans bump majeur, le
schema réserve dès v1 :

- **`podcasts?: RegistryPodcast[]`** — array optionnel. Un fork qui
  agrège plusieurs sources peut publier la liste complète sous cette
  clé ; le `podcast` racine reste alors la source principale (pour
  rétro-compat des agrégateurs v1). Le consumer v1 ignore ce champ.

Tout autre futur champ réservé sera documenté ici avant l'implémentation.

## Architecture — Protocols formels (R-P1-02)

- **Python** : `tools.meta.fetcher.RegistryHttpGet` (`typing.Protocol`,
  `@runtime_checkable`). Tout callable `(url: str) -> (int, str)` est un
  fetcher acceptable.
- **TypeScript** : `MetaIndexLoader` interface (`src/lib/registry/types.ts`).
  Implémenté par `FileMetaIndexLoader` (par défaut). Forks libres
  d'injecter un loader custom (cache, signature, etc.).

## META_MODE — mode opt-in (R-P2-07)

Le namespace `_meta/` est conditionnel : `META_MODE=1` est obligatoire au
build pour le générer. Sans cette variable :

- `meta-loader.ts::loadMetaIndex` retourne `null` ;
- `/_meta/index.astro` répond `404` côté SSR/static (pas de redirect 302
  indexable) ;
- `/_meta/podcast/[slug]` n'enregistre aucun path via `getStaticPaths`.

Un fork qui veut activer le mode méta doit aussi fournir
`tools/output/meta/meta_index.json`, produit en amont par
`python tools/build_meta.py --registries-file <urls.yaml>`.

## Cache-Control & TTL fetcher

- Endpoint Astro : `Cache-Control: public, max-age=3600, must-revalidate`
  (override via `RECO_REGISTRY_CACHE_MAX_AGE`).
- Fetcher Python : `requests-cache` TTL **3600 s** (aligné).

Note : `Cache-Control` est informatif pour les hosts statiques
(Vercel/Netlify ré-écrivent selon leur stratégie). Le TTL effectif côté
méta-agrégateur reste piloté par le cache HTTP de `tools/build_meta.py`.

## Critères de bascule (chiffrés)

| Métrique | Seuil | Action |
|---|---|---|
| Podcasts indexés | **> 50** | Migrer vers DB centralisée + webhooks push (latence d'indexation impraticable avec fetch-all). |
| Taille agrégat `meta_index.json` | **> 5 MB** | Découper par langue ou région, ajouter pagination. |
| Latence build méta-site | **> 5 min** | Activer build incrémental + cache HTTP partagé. |
| Erreurs `payload too large` (H24-4) | **> 1 %** des fetches | Auditer les forks émetteurs, durcir le cap (par défaut 256 KiB). |
| Abus de stats détectés | qualitatif | Activer signature Ed25519 obligatoire (`meta.signature`). |

## Exit codes CLI (M24-17)

`tools/build_meta.py` aligne ses exit codes sur les autres jobs (pattern
`audit_core`) :

| Code | Sens |
|---|---|
| `0` | OK — tous les registries fetchés validés. |
| `1` | Partial — ≥ 1 OK, ≥ 1 erreur. |
| `2` | Total failure — aucun fetch OK alors que ≥ 1 URL déclarée, ou lock serveur occupé. |

## Mise en œuvre (livrable P4.24)

- TS : `src/lib/registry/{types,generator,consumer,meta-loader}.ts`.
- Astro : `src/pages/.well-known/reco-registry.json.ts`,
  `src/pages/_meta/index.astro`, `src/pages/_meta/podcast/[slug].astro`,
  `src/components/MetaPodcastCard.astro`.
- Python : `tools/meta/{validator,aggregator,fetcher}.py`,
  `tools/build_meta.py`.
- i18n : namespace `meta.*` dans `src/i18n/fr.ts`.
- Tests : 35 vitest (`tests/registry/`, `tests/meta/`) +
  46 pytest (`tests/registry/`, `tests/meta/`).
