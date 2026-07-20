# Sources (podcasts)

Ce dossier est la **source unique de vérité** (SSOT) de toutes les sources
exploitées par le projet :

- Astro (site public) y lit le titre, le thème, l'URL RSS.
- Le pipeline Python (`tools/`) y lit le préfixe des recos, les hôtes,
  l'URL YouTube, les patterns d'ancrage du prompt LLM, etc.

## Ajouter un nouveau podcast (3 étapes)

1. **Choisir un slug** (minuscules, tirets) — ex. `mon-podcast`.
2. **Créer** `src/content/sources/mon-podcast.json` à partir du gabarit
   ci-dessous.
3. **Lancer** :
   ```bash
   python tools/run_pipeline.py --source mon-podcast --steps fetch
   ```
   Le pipeline crée automatiquement les dossiers
   `src/content/episodes/mon-podcast/` et `src/content/recos/mon-podcast/`.

## Champs

### Minimum requis (4 lignes)

```json
{
  "id": "mon-podcast",
  "title": "Mon Podcast",
  "recoPrefix": "mp",
  "hosts": ["Alice", "Bob"]
}
```

### Recommandé (pour le pipeline complet)

```json
{
  "id": "mon-podcast",
  "title": "Mon Podcast",
  "recoPrefix": "mp",
  "hosts": ["Alice", "Bob"],
  "description": "Description courte du podcast.",
  "rssUrl": "https://exemple.com/feed.rss",
  "youtubeChannel": "https://www.youtube.com/@mon-podcast",
  "website": "https://exemple.com",
  "extractionAnchorPatterns": [
    "ta reco",
    "qu'est-ce que tu nous recommandes"
  ],
  "siteColorAccent": "#ffd23f",
  "transcriptDefaultSource": "youtube",
  "avoidBrands": ["Amazon", "Bolloré"],
  "theme": {
    "fontDisplay": "Reco Display",
    "fontBody": "Reco Body",
    "colors": {
      "bg": "#0e0e10",
      "surface": "#17171c",
      "text": "#f6f4ee",
      "muted": "#9a99a3",
      "accent": "#ffd23f",
      "accentText": "#0e0e10"
    }
  }
}
```

### Tableau récapitulatif

| Champ | Type | Requis | Utilisé par |
|-------|------|--------|-------------|
| `id` | slug | oui | Astro, pipeline |
| `title` | string | oui | Astro, pipeline |
| `recoPrefix` | string | oui (pipeline) | `tools.review_routes`, IDs de recos |
| `hosts` | string[] | oui (pipeline) | prompt LLM, dédup, review |
| `description` | string | non | Astro |
| `tagline` | string | non | Astro |
| `rssUrl` | URL | non | `tools.fetch_episodes` |
| `youtubeChannel` | URL | non | `tools.match_youtube` |
| `website` | URL | non | Astro (lien externe) |
| `extractionAnchorPatterns` | string[] | non | `tools.extract_recos` (prompt) |
| `siteColorAccent` | couleur hex | non | thème de repli |
| `transcriptDefaultSource` | `youtube`/`acast` | non | `tools.transcribe` |
| `avoidBrands` | string[] | non | `tools.review_links` |
| `theme` | objet | oui (Astro) | Astro CSS |

## Validation

Au démarrage de tout script `tools/*.py` :

```python
from tools.config.registry import get_source

cfg = get_source("mon-podcast")   # → SourceConfig immuable
print(cfg.reco_prefix, cfg.hosts)
```

Toute incohérence (champ manquant, JSON cassé, id de fichier différent
de `id` dans le payload) est levée immédiatement avec un message clair.
