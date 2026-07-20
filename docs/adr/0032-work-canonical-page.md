# ADR 0032 — Page canonique d'œuvre (cross-épisodes)

- Statut : Accepté
- Date : 2026-06-11 (renuméroté 2026-06-11 — collision avec ADR 0031 galleries)
- Auteur : Dev #11 (Phase 2.11)
- Roadmap : item #11 — Page œuvre canonique (mentions cross-épisodes, trending)

> **Note de renumérotation** : initialement publié sous `0031-work-canonical-page.md`,
> ce document a été renuméroté en `0032` pour lever la collision avec
> `0031-galleries-routing.md` (CR archi cumulative Vague 2A, issue C-X-1).

## Contexte

La couche `Item` / `Mention` introduite en Phase 1 (ADRs 0001-0004) déduplique
chaque œuvre référencée dans le catalogue : un même film peut être recommandé
dans plusieurs épisodes via N `Mention`s qui pointent toutes vers le même
`Item`. Jusqu'ici cette dédup n'était exploitée que par le pipeline (audit,
enrichissement TMDB partagé). Côté site public, l'œuvre n'avait pas d'URL
propre — on la voyait uniquement sous forme de `RecoCard` dans chaque page
d'épisode.

Cette absence pénalise :

- **le SEO** : pas de page indexable « parasite (Bong Joon-ho, 2019) » qui
  agrégerait les passages où l'œuvre est citée ;
- **la découverte** : impossible pour un·e visiteur·euse de répondre à la
  question « combien de fois ce film a-t-il été recommandé, et par qui ? » ;
- **les méta-agrégateurs futurs** (Phase 4) qui voudront pivoter de la
  perspective podcast vers la perspective œuvre.

## Décision

1. **Une route Astro statique par œuvre** :
   `/<source>/oeuvre/<itemId>`. Générée via `getStaticPaths()` à partir des
   collections `items`, `mentions`, `episodes`. Une page est émise pour
   chaque item ayant au moins une mention visible (statut ≠ `discarded`)
   dans la source courante.

2. **Aggrégation pure** dans `src/lib/work/aggregator.ts` (zéro dépendance
   Astro/fs) : `buildWorkIndex({sourceId, items, mentions, episodes})`
   renvoie un `Map<itemId, WorkAggregate>` avec mentions jointes aux
   épisodes et triées par date DESC. Permet un test unitaire `vitest` sans
   builder le site.

3. **Trending** : `isTrending(mentions, now, windowMonths=12)` retourne
   true si ≥2 mentions visibles dans la fenêtre des 12 derniers mois.
   Rendu par `<TrendingBadge>` (pastille `🔥`) à côté du compteur de
   recommandations.

4. **Timeline mentions** : `<MentionsTimeline>` rend une `<ol>` ordonnée
   chronologiquement DESC, avec lien vers l'épisode, `<time datetime>`,
   `recommendedBy`, citation et lien YouTube horodaté quand applicable
   (politique transcript YouTube respectée — pas d'offset en cas de
   transcript Acast, cf. mémoire `reco-transcript-source-policy.md`).

5. **JSON-LD typé** : `recoToSchema` (ADR 0027) mappe le premier
   `item.types` vers `Movie` / `Book` / `MusicAlbum` / `TVSeries`. Fallback
   `CreativeWork` pour les types inconnus (ex. `article`).

6. **Œuvres similaires** : interface `SimilarWorksProvider` (cf. W1) avec
   implémentation par défaut `creatorBasedProvider` — exact match (insensible
   à la casse) sur `creator`. Un `embeddingsBasedProvider` (placeholder lit
   `dist/_embeddings_similar.json` si présent) sera branché en P2.15+ pour la
   similarité sémantique.

## Alternatives écartées

- **Pas de page dédiée, garder uniquement les fiches épisode** : perte
  SEO sèche, pas de signal de récurrence.
- **SSR pour la page œuvre** : casserait le modèle statique et imposerait
  un adapter pour un kit duplicable. Rejeté.
- **Index global d'œuvres cross-sources** : reportée à Phase 4
  (méta-agrégateur multi-podcasts). Pour l'instant chaque source garde son
  propre namespace `/<source>/oeuvre/<itemId>`.

## Conséquences

### Positives

- SEO : 2 622 pages canoniques émises pour `un-bon-moment` (sur 2 651
  items — 29 sans mention visible). Chacune indexable, sitemap
  auto-ramassé par `@astrojs/sitemap` (limite 45 000, encore très loin).
- Découverte : compteur « Recommandée N fois » + badge tendance.
- Réutilisable : `aggregator.ts` est pur, exporte les types utiles
  (`WorkAggregate`, `JoinedMention`) — re-consommé par tout futur index.

### Négatives

- Volume build : ~2 600 routes additionnelles par source. La build Astro
  reste en-deçà de 1 min sur le poste dev en l'état actuel. À surveiller
  quand on dépassera 10 000 items.
- Pas d'image OG dédiée (la carte Satori `/og/oeuvre/<id>.png` n'est pas
  encore générée — la zone est gérée par Dev #15/#16, hors-périmètre).
  Fallback `/og/default.png` via le mécanisme `ogSlug` existant.

## Critères de bascule

- Si la durée de build dépasse 5 min → pagination par lettre /
  type, ou skip des items à 1 mention seule (filtrer
  `mentionCount >= 2`). Voir W3 : items à `mentionCount=1` peuvent recevoir
  `<meta name="robots" content="noindex">` pour économiser le budget de crawl
  sans casser les liens entrants.
- Si le sitemap dépasse 45 000 URLs → bump `entryLimit` dans
  `astro.config.mjs` (limite RFC 50 000).

## Tests (vitest, `tests/work/`)

- `test_mentions_aggregation.test.ts` — agrégation, tri, jointure,
  filtres `discarded`, helpers `workExternalLinks`,
  `youtubeDeepLink`, `similarByCreator`.
- `test_trending.test.ts` — fenêtre 12 mois, frontière, mentions sans
  date, `windowMonths` paramétré.
- `test_work_route.test.ts` — post-build : page contient `<h1>` unique,
  `<main id="main">`, skip-link, canonical absolue, JSON-LD schema.org,
  `<time datetime>` sur timeline. Skip en local sans `dist/`, fail
  explicite en CI.

## Références

- ADR 0001 — SSOT source config
- ADR 0002 — Multi-types Item
- ADR 0021 — SEO/OG/sitemap
- ADR 0022 — A11y WCAG AA
- ADR 0027 — Mapping JSON-LD schema.org
- ADR 0031 — Galleries routing (sibling, distinct concern)
