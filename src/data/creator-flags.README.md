# Signalements « situation de l'artiste »

Ce fichier (`creator-flags.json`) est **curé à la main**. Il permet d'afficher une
info-bulle ⚠️ à côté d'un créateur dont la situation (accusation, condamnation…)
justifie de contextualiser la mise en avant de son œuvre.

**Règle de sûreté** : n'ajoute une entrée que si tu peux la **sourcer**. Le champ
`source` (lien vers un article de presse fiable, une décision de justice, etc.)
est obligatoire. Formule la `situation` de façon **factuelle et neutre**
(« mis en examen pour… », « condamné en 2023 pour… »), au présent de l'état connu.

Le code ne fait qu'**afficher** ce que contient ce fichier — il n'invente rien.

## Format

```json
{
  "flags": [
    {
      "names": ["Nom Exact", "Variante d'orthographe éventuelle"],
      "situation": "Mis en examen en 2024 pour… (enquête en cours).",
      "source": "https://exemple-media.fr/article",
      "severity": "accusation"
    }
  ]
}
```

- **names** : liste des orthographes à faire correspondre au champ `creator`
  d'une reco. La comparaison ignore la casse et les accents ; ajoute toutes les
  variantes que tu veux couvrir (« Gérard X », « Gerard X »…).
- **situation** : texte affiché dans la bulle. Court, factuel, sourcé.
- **source** : URL obligatoire (ouverte dans un nouvel onglet).
- **severity** : `"accusation"` (présomption d'innocence — teinte orange) ou
  `"condamnation"` (teinte rouge). Facultatif, défaut `"accusation"`.

## Où ça s'affiche

- Site public : page œuvre, cartes (galerie, reco, œuvres similaires).
- Outil de relecture (`/doutes`, `/ep`) : à côté du créateur, pour t'aider à
  décider quoi garder.

Le même fichier est lu par le site Astro (`src/data/creatorFlags.ts`) et par le
serveur de relecture Python (`tools/creator_flags.py`).
