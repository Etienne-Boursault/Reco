# Schéma de données — contrat site ⇄ pipeline

Le site (Astro) lit cinq collections de fichiers **JSON**. Le pipeline de
collecte (`tools/`) doit produire des fichiers conformes. La source de vérité
exécutable est `src/content.config.ts` (schémas Zod) — ce document en est la
version lisible.

Arborescence des données :

```
src/content/
├─ sources/   un fichier .json par podcast                 (ex: un-bon-moment.json)
├─ episodes/  un fichier .json par épisode                  (ex: un-bon-moment/<guid>.json)
├─ recos/     un fichier .json par carte de recommandation  (ex: un-bon-moment/0001.json)
├─ items/     un fichier .json par œuvre (fiche)            (ex: un-bon-moment/a1b2c3d4.json)
├─ mentions/  un fichier .json par citation d'une œuvre     (ex: un-bon-moment/ubm-0001.json)
└─ redirections-oeuvres.json   anciennes adresses des fiches fusionnées (ADR 0053)
```

Une même citation existe aujourd'hui **en deux copies** : la reco, que lisent
les cartes des pages d'épisode, et la mention, que lisent les fiches d'œuvre.
Chaque reco recopie aussi le titre, le créateur, les types et les liens de son
œuvre. Le modèle canonique (ADR 0055, proposé) garde chaque champ à un seul
endroit ; la reco y devient une vue calculée.

## 1. Source (un podcast)

```jsonc
{
  "id": "un-bon-moment",                 // slug unique
  "title": "Un Bon Moment",
  "tagline": "Les recos de Kyan & Navo",
  "hosts": ["Kyan Khojandi", "Navo"],
  "description": "…",
  "rssUrl": "https://feeds.acast.com/public/shows/81a0b207-…",
  "youtubeChannel": "https://www.youtube.com/@KyanKhojandi",
  "website": "https://…",
  "theme": {
    "fontDisplay": "Reco Display",
    "fontBody": "Reco Body",
    "colors": {
      "bg": "#0e0e10", "surface": "#1a1a1f", "text": "#f5f5f0",
      "muted": "#9a9aa2", "accent": "#ffd23f", "accentText": "#0e0e10"
    }
  }
}
```

## 2. Episode

```jsonc
{
  "sourceId": "un-bon-moment",           // référence à une source
  "guid": "acast-…",                     // identifiant stable (RSS <guid>)
  "number": 312,
  "title": "Avec Florence Foresti",
  "date": "2026-04-13",
  "audioUrl": "https://…/episode.mp3",
  "youtubeUrl": "https://youtu.be/…",
  "description": "…",
  "guests": ["Florence Foresti"],
  "transcriptStatus": "auto"             // none | auto | validated
}
```

## 3. Reco (carte de recommandation)

```jsonc
{
  "id": "ubm-0001",                      // unique tous podcasts confondus
  "sourceId": "un-bon-moment",
  "episodeGuid": "acast-…",              // relie à episodes[].guid
  "title": "Le Bureau des légendes",
  "creator": "Éric Rochant",
  "types": ["serie"],                    // un ou plusieurs types, cf. ci-dessous
  "year": 2015,
  "recommendedBy": "Navo",               // qui recommande
  "quote": "Une série d'espionnage incroyable, vraiment.",
  "timestamp": "01:12:30",
  "transcriptSource": "youtube",         // youtube | acast : origine du minutage
  "kind": "reco",                        // reco | citation (simple mention)
  "links": [
    { "label": "JustWatch", "url": "https://…", "kind": "streaming", "ethics": "neutral" }
  ],
  "externalIds": { "tmdb": "62560" },
  "status": "draft"                      // draft | validated | discarded (écarté)
}
```

Types de reco : `film`, `serie`, `livre`, `bd`, `musique`, `album`, `podcast`,
`jeu`, `spectacle`, `lieu`, `artiste`, `video`, `chaine`, `application`,
`autre`. Champs facultatifs non montrés : `guestWork` (`true` pour une œuvre
d'un invité ou d'un animateur, badge « Leur œuvre » ; absent sinon), `note`,
`aliases`, `linkOverrides` (remplace l'URL d'un lien par libellé),
`customLinks`, `watchProviders`, `enrichedAt`, `extractors`,
`extractionHistory`.

## 4. Item (œuvre, la fiche)

```jsonc
{
  "id": "a1b2c3d4",                      // 8 caractères hexadécimaux, permanent ; suffixe -n en cas de collision
  "schemaVersion": 1,
  "title": "Le Bureau des légendes",
  "creator": "Éric Rochant",
  "types": ["serie"],                    // un ou plusieurs types
  "year": 2015,
  "aliases": ["Bureau des légendes"],
  "externalIds": { "tmdb": 62560, "tmdbType": "tv" },  // tmdb est un entier ici, une chaîne sur la reco
  "watchProviders": [{ "name": "Canal+", "url": "https://…" }]
}
```

Types d'œuvre : ceux de la reco, plus `article`. Clés de `externalIds` :
`tmdb`, `tmdbType`, `spotify`, `musicbrainz`, `openlibrary`, `isbn`,
`watchPage`, `youtubeChannelId`, `instagram`, `tiktok`. Champs facultatifs non
montrés : `customLinks`, `linkOverrides`, `enrichedAt`.

## 5. Mention (citation d'une œuvre dans un épisode)

```jsonc
{
  "id": "ubm-0001",                      // même identifiant que la reco correspondante
  "schemaVersion": 1,
  "itemId": "a1b2c3d4",                  // l'œuvre citée
  "sourceRef": {
    "sourceId": "un-bon-moment",
    "episodeGuid": "acast-…",
    "timestamp": "01:12:30",             // HH:MM:SS
    "transcriptSource": "youtube"        // youtube | acast
  },
  "recommendedBy": "Navo",
  "quote": "Une série d'espionnage incroyable, vraiment.",
  "kind": "reco",                        // reco | citation
  "status": "validated"                  // draft | validated | discarded
}
```

`guestWork` est facultatif, miroir de celui de la reco. Une œuvre peut être
citée plusieurs fois dans un même épisode, à des minutages différents.

## Règles d'or pour le pipeline

1. **`status: "draft"`** par défaut : toute reco extraite par IA est un brouillon
   tant qu'un humain ne l'a pas validée (`validated`).
2. **`episodeGuid`** doit correspondre exactement au `guid` de l'épisode.
3. **Liens éthiques** : ne JAMAIS générer de lien Amazon ni vers une entité du
   groupe Bolloré (voir `src/data/merchants.ts`). Privilégier l'`ethics: "indie"`.
   Le pipeline peut laisser `links: []` ; le site sait générer des liens de
   recherche éthiques à partir de `types` + `title` + `creator`.
4. **Ne rien inventer** : si un champ est incertain, l'omettre plutôt que halluciner.
5. Encodage **UTF-8**, accents français corrects (« Éric », pas « Eric »).
