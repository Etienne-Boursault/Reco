# Schéma de données — contrat site ⇄ pipeline

Le site (Astro) lit trois collections de fichiers **JSON**. Le pipeline de
collecte (`tools/`) doit produire des fichiers conformes. La source de vérité
exécutable est `src/content.config.ts` (schémas Zod) — ce document en est la
version lisible.

Arborescence des données :

```
src/content/
├─ sources/   un fichier .json par podcast      (ex: un-bon-moment.json)
├─ episodes/  un fichier .json par épisode       (ex: un-bon-moment/ep-312.json)
└─ recos/     un fichier .json par recommandation (ex: un-bon-moment/0001.json)
```

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

## 3. Reco (recommandation) — l'objet central

```jsonc
{
  "id": "ubm-0001",                      // unique tous podcasts confondus
  "sourceId": "un-bon-moment",
  "episodeGuid": "acast-…",              // relie à episodes[].guid
  "title": "Le Bureau des légendes",
  "creator": "Éric Rochant",
  "type": "serie",                       // film|serie|livre|bd|musique|album|podcast|jeu|spectacle|lieu|autre
  "year": 2015,
  "recommendedBy": "Navo",               // qui recommande
  "quote": "Une série d'espionnage incroyable, vraiment.",
  "timestamp": "01:12:30",
  "note": "…",
  "links": [
    { "label": "JustWatch", "url": "https://…", "kind": "streaming", "ethics": "neutral" }
  ],
  "externalIds": { "tmdb": "62560" },
  "status": "draft"                      // draft | validated | discarded (écarté)
}
```

## Règles d'or pour le pipeline

1. **`status: "draft"`** par défaut : toute reco extraite par IA est un brouillon
   tant qu'un humain ne l'a pas validée (`validated`).
2. **`episodeGuid`** doit correspondre exactement au `guid` de l'épisode.
3. **Liens éthiques** : ne JAMAIS générer de lien Amazon ni vers une entité du
   groupe Bolloré (voir `src/data/merchants.ts`). Privilégier l'`ethics: "indie"`.
   Le pipeline peut laisser `links: []` ; le site sait générer des liens de
   recherche éthiques à partir de `type` + `title` + `creator`.
4. **Ne rien inventer** : si un champ est incertain, l'omettre plutôt que halluciner.
5. Encodage **UTF-8**, accents français corrects (« Éric », pas « Eric »).
