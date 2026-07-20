# ADR 0027 — JSON-LD schema.org : factories & mapping `recoType`

- Statut : Acceptée (factories livrées) — câblage pages reporté
- Date : 2026-06-10
- Décideurs : équipe Reco
- ADRs liés : ADR 0021 (SEO/OG), ADR 0002 (item multi-types)

## Contexte

ADR 0021 a livré une prop `jsonLd` sur `MetaTags.astro` mais sans
consommateur réel — aucune page ne construit son objet schema.org.
La conséquence : la prop dormait, et chaque page qui voudrait
l'utiliser réinventerait la roue (mapping `recoType → @type`,
encodage anti-XSS du `</script>`, structure `partOfSeries`, etc.).

## Décision

`src/lib/seo/jsonld.ts` expose :

1. **`safeJsonLd(data)`** — sérialise en échappant tout `<` en `<`.
   `MetaTags.astro` l'appelle obligatoirement, ce qui ferme la classe
   CR senior C2 (XSS via `</script>` dans un titre d'épisode).
2. **`RECO_TYPE_TO_SCHEMA`** — `Readonly<Record<...>>` figé qui mappe
   les 13 valeurs de `recoType` (cf. `src/content.config.ts`) vers les
   types schema.org :

   | recoType   | @type            |
   |------------|------------------|
   | film       | Movie            |
   | serie      | TVSeries         |
   | livre      | Book             |
   | bd         | Book             |
   | musique    | MusicRecording   |
   | album      | MusicAlbum       |
   | podcast    | PodcastSeries    |
   | jeu        | VideoGame        |
   | spectacle  | Event            |
   | lieu       | Place            |
   | artiste    | Person           |
   | video      | VideoObject      |
   | autre      | CreativeWork     |

3. **Factories typées** — `recoToSchema`, `episodeToSchema`,
   `sourceToPodcastSchema`. Chaque factory produit un nœud
   `@context: schema.org` + `@type` + champs requis (name, url,
   `partOfSeries` pour les épisodes, `publisher` pour les sources).

## Reporté

Le **câblage** dans `Layout.astro` et les pages
(`src/pages/[source]/episode/[guid].astro`,
`src/pages/[source]/index.astro`) appartient à la zone Fixer P2.14 /
coordination finale Vague 1. Quand cette zone redeviendra disponible :

```astro
import { recoToSchema, episodeToSchema } from '../lib/seo/jsonld';
const jsonLd = [
  episodeToSchema({ ... }),
  ...recos.map(recoToSchema),
];
<MetaTags ... jsonLd={jsonLd} />
```

## Conséquences

- Les futurs ajouts de pages n'ont qu'à appeler une factory : pas de
  duplication d'objets JSON-LD à la main.
- Le mapping `recoType → @type` est testé (tous les types couverts).
- Le `safeJsonLd` est utilisé par défaut dans `MetaTags.astro` — aucune
  régression XSS possible même si une page passe un payload exotique.
