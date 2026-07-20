# ADR 0031 — Galeries par invité et par type

- Statut : Acceptée
- Date : 2026-06-11
- Décideurs : équipe Reco (P2.10)

## Contexte

Le site expose deux dimensions d'exploration historiques :

- `/[source]/` — toutes les recos d'un podcast (tabs « toutes les recos » +
  « par épisode »).
- `/[source]/episode/<guid>` — détail d'un épisode.

L'item #10 du roadmap Phase 2 demande deux nouvelles dimensions
transverses :

- **Par invité** — toutes les œuvres recommandées par une personne donnée,
  toutes sources et épisodes confondus pour cette personne dans la source
  courante. Exemple : `/un-bon-moment/invite/bong-joon-ho`.
- **Par type** — toutes les œuvres d'un type (films, livres, musique,
  séries) au sein d'une source. Exemple : `/un-bon-moment/films`.

Contraintes :

- Le kit doit rester **self-hostable statique** (`astro build`). Pas de SSR.
- Volumétrie réelle (`un-bon-moment`) au moment de l'ADR : 2651 items,
  ~3500 mentions, ~220 invités distincts.
- La piste « recherche dynamique uniquement » (item #9) couvre déjà la
  recherche libre ; les galeries servent un usage différent :
  navigation/exploration + indexabilité SEO + partages de liens lisibles.
- Les routes `/[source]/oeuvre/` et `/[source]/report/` sont gérées par
  d'autres agents : la galerie n'enveloppe pas les cartes dans un `<a>`
  vers `/oeuvre/` pour éviter le couplage non coordonné (à câbler par la
  coordination finale Vague 2).

## Décision

On crée 5 nouveaux types de routes statiques, générées au build via
`getStaticPaths` à partir des content collections Astro :

| Route                                | Cardinalité (par source) | Source de données        |
| ------------------------------------ | ------------------------ | ------------------------ |
| `/[source]/films`                    | 1                        | items.types ∋ `film`     |
| `/[source]/livres`                   | 1                        | items.types ∋ `livre`/`bd` |
| `/[source]/musique`                  | 1                        | `musique`/`album`/`artiste` |
| `/[source]/series`                   | 1                        | items.types ∋ `serie`    |
| `/[source]/invite/<slug>`            | N (= nb invités)         | mentions.recommendedBy   |

Pipeline interne :

1. `slugify(name)` (NFD → strip diacritics → lowercase → non-alnum → `-`)
   dans `src/lib/gallery/slug.ts`. Tests : `tests/gallery/test_slug.test.ts`.
2. `selectByType`, `selectByGuest`, `listGuests`, `sortGalleryEntries`
   (pures, testables) dans `src/lib/gallery/aggregate.ts`. Tests :
   `tests/gallery/test_aggregate.test.ts`.
3. Composants UI isolés : `GalleryCard.astro` (carte minimaliste, pas de
   dropdown marchand) + `GalleryGrid.astro` (grid responsive auto-fill 220px).
4. JSON-LD `ItemList` + `BreadcrumbList` (Accueil → Source → Galerie) via
   `src/lib/gallery/page.ts` qui s'appuie sur les factories existantes
   `src/lib/seo/jsonld.ts`. Limite `ItemList` à 100 items embarqués pour
   éviter des payloads JSON-LD démesurés (les autres restent indexables
   via le sitemap qui ramasse l'URL canonique).
5. Tri par défaut : `mentionCount DESC, title ASC` (locale FR).
6. Filtrage par source : on s'appuie sur `mentions.sourceRef.sourceId`
   pour découvrir les `itemId` mentionnés, puis on filtre la collection
   `items` par appartenance à ce set. Cette voie reste correcte si à
   terme un item devient partagé entre sources.

Slugification :

- Cas connu projet : "Kyan Khojandi" → `kyan-khojandi`.
- Sécurité : retourne `''` si entrée ne contient aucun caractère
  alphanumérique → empêche `/invite//` (route vide ignorée par
  `buildGuestIndex`).
- Collision : premier nom rencontré gagne (déterministe pour
  `getStaticPaths`).

## Alternatives évaluées

- **Page SSR avec query string** (`?type=film`, `?invite=…`) — rejeté :
  casse le contrat self-hostable static + SEO moins bon (URLs non
  partageables/canonisables).
- **Catch-all `/[source]/[…dim]/[val]`** — rejeté : URLs moins lisibles,
  collision possible avec `/episode/`, `/oeuvre/`, `/report/` déjà routés.
- **Galerie reposant uniquement sur la recherche dynamique de l'item #9**
  — rejeté : pas indexable par les moteurs, pas partageable, n'offre pas
  d'écran d'accueil thématique.
- **Pagination obligatoire** — rejeté pour l'instant : les volumes par
  galerie restent gérables (max 696 items pour `/musique` sur
  `un-bon-moment`) et `auto-fill minmax(220px, 1fr)` reste fluide. La
  pagination sera réintroduite quand un seuil de douleur sera observé
  (voir Critères de bascule).

## Conséquences

- **Positives** :
  - URLs propres, partageables, indexables. Sitemap auto-ramassé par
    `@astrojs/sitemap`.
  - JSON-LD `ItemList` + `BreadcrumbList` ajoute de la donnée structurée
    schema.org sans toucher aux routes existantes.
  - Logique d'agrégation pure, 100 % couverte par 22 tests vitest.
  - Cohérent avec le design tokens existant (`--bg`, `--accent`,
    `--surface`, `--radius`, `--gap`) — aucune nouvelle dépendance UI.
  - A11y : check `tests/a11y/check_a11y.mjs` passe sur les 2956 pages
    générées (skip-link, h1 unique, hiérarchie h1→h2→h3).
- **Négatives** :
  - Rebuild complet pour ajouter un nouvel invité (déjà le cas pour
    `/episode/`, on hérite simplement de la même contrainte).
  - Nombre de pages générées augmente sensiblement (107 → 2957 sur
    `un-bon-moment`). NB : cette explosion ne vient pas que des galeries
    (les pages `/oeuvre/<itemId>` ont déjà augmenté le volume — voir
    autres agents). Galeries ajoutent ~228 pages = 4 type + 224 invités.
- **Notes / risques résiduels** :
  - Coordination finale Vague 2 : enrober `GalleryCard` d'un `<a>` vers
    `/[source]/oeuvre/<itemId>` quand cette route sera stable (touche
    `GalleryCard.astro` uniquement, pas la logique d'agrégation).
  - `recommendedBy` est aujourd'hui une chaîne libre (pas d'identifiant
    canonique d'invité) ; deux orthographes produisent deux pages. Une
    future réconciliation invité (item à scoper) pourra muter en
    redirections.

## Critères de bascule

- > 2000 invités sur une source → grouper par initiale (`/invite/a/…`).
- > 1500 items par galerie de type → paginer par tranches de 250 ou
  introduire un filtre côté client (la recherche libre #9 couvre déjà
  partiellement ce besoin).
