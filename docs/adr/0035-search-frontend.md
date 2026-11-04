# ADR 0035 — Recherche full-text frontend (site public + palette Cmd+K)

- **Statut** : Accepté
- **Date** : 2026-06-11
- **Auteurs** : Dev P2.9
- **Issue roadmap** : item #9 — Recherche full-text

## Contexte

Le site Reco affiche des milliers d'œuvres, d'épisodes et d'invités. Les
visiteurs ont besoin :

1. d'une page `/recherche` accessible (URL bookmarkable `?q=`) ;
2. d'une palette **Cmd+K** style Algolia DocSearch, montable n'importe où
   sur le site.

Le kit est **statique** (`output: 'static'`) et doit rester self-hostable
sans serveur (un hébergement de fichiers + CDN suffit). Pas de Node SSR,
pas de service externe payant.

La Phase 2 Vague 1 a déjà livré un cache SQLite + FTS5 dans
`tools/search/`, mais c'est **côté Python**, utilisable seulement pour le
review_server et le pipeline. Le site public n'a pas accès à SQLite à
l'exécution.

## Options envisagées

### A. Index JSON client-side + MiniSearch (**retenue**)

- Au build, un endpoint statique `src/pages/search.json.ts` lit les
  collections Astro et écrit `dist/search.json`.
- Côté navigateur, MiniSearch (~10 KB gzipped, BM25 natif, TypeScript)
  charge l'index en lazy au premier focus de la palette / au premier
  caractère de la page `/recherche`, puis indexe en mémoire.
- Filtrage par `kind` (item | episode | guest) groupé côté UI.

### B. Endpoint serveur `/api/search?q=` consommant `tools/search/service.py`

- Nécessite un adapter Node (Astro hybrid), un runtime Python collé, et
  une infra plus lourde. Casse l'argument « self-hostable kit » et fait
  fuiter la stack Python côté visiteur.

### C. Algolia DocSearch / MeiliSearch externe

- Excellent UX mais : compte tiers, requête sortante chaque keystroke
  (privacy), dépendance contractuelle (DocSearch est gratuit pour de
  l'open-source mais demande validation manuelle Algolia).
- Garde-fou : bascule envisageable si l'index dépasse plusieurs MB.

## Décision

**Option A** : MiniSearch côté client + endpoint JSON statique au build.

Architecture :

```
tools/  (Python)            src/lib/search/          src/pages/
─────────                  ───────────────          ──────────
                            build-index.ts  ─────►  search.json.ts (GET)
                            normalize.ts                 │ build-time
                            client.ts                    ▼
                                ▲                  dist/search.json
                                │                        │
                                │  fetch lazy            │
                                └────────────────────────┘
                            src/components/SearchPalette.astro
                            src/pages/recherche.astro
```

- **Tokenizer / processTerm FR** : NFD + strip diacritiques + lowercase
  (cf. `src/lib/search/normalize.ts`). Garantit que `Kaâmelott` matche
  `kaamelott`, `Étienne` matche `etienne`.
- **Boost** : `title` ×3, `subtitle` ×2, `text` ×1. Préfixe + fuzzy 0.2
  par défaut (matches partiels « para… » → Parasite).
- **Format index** versionné (`SEARCH_INDEX_VERSION = 1`) pour pouvoir
  régénérer après évolution sans piéger un client.

## Conséquences

### Positives

- Zéro serveur, zéro service externe, RGPD trivial.
- Recherche locale : aucune requête réseau par keystroke.
- Self-hostable sans config (un `nginx`/CDN servant `dist/`).
- ~10 KB gzipped pour MiniSearch ; build-time stable (1 endpoint, O(n)).

### Négatives / limites

- L'index est téléchargé **une fois** par client. Mesure 2026-06-11 :
  `dist/search.json` = **≈ 471 KB** brut (2 727 documents) pour la source
  `un-bon-moment`. Gzip réduit à ~80-120 KB sur la wire — tolérable.
- Charge mémoire : MiniSearch construit l'index in-memory à chaque page
  qui monte la palette. Mitigation : 1 instance partagée par onglet,
  construite au premier open (lazy).
- Pas d'analytics de recherche (volontaire — privacy).

### Critères de bascule

- Si `dist/search.json` dépasse **5 MB** brut → migrer vers DocSearch
  Algolia (gratuit projet open-source) OU split par source (un index par
  podcast, chargé selon la page).
- Si on ajoute un index sémantique (embeddings P2.8/#15), une 2ᵉ couche
  pourra venir en sus (HNSW client comme `usearch-wasm`) mais reste hors
  scope de ce ticket.

## Notes d'implémentation

- **Endpoint statique** : `src/pages/search.json.ts`. Astro 5 émet
  l'asset à `/search.json` (et donc `dist/search.json`).
- **Bypass robots / sitemap** : `robots.txt` ajoute `Disallow: /search.json`
  et `/recherche`, et `astro.config.mjs` filtre ces deux URLs hors du
  sitemap. La page `/recherche` est `noindex` (utilitaire).
- **A11y** : `<dialog>` virtuel via `role=dialog`, `aria-modal`, focus
  trap minimaliste (focus sur input + restore au close), `aria-live=polite`
  sur les résultats, raccourcis Cmd/Ctrl+K et `/`.
- **CSP** : tous les scripts passent par `<script>` Astro bundlé (pas
  d'inline), compatible CSP strict.

## Liens

- Code : `src/lib/search/`, `src/components/SearchPalette.astro`,
  `src/pages/recherche.astro`, `src/pages/search.json.ts`.
- Tests : `tests/search-frontend/`.
- Dépendance ajoutée : `minisearch` (MIT).
