# ADR 0001 — Single Source of Truth pour la configuration des sources (podcasts)

- Statut : Acceptée
- Date : 2026-06-10
- Décideurs : équipe Reco

## Contexte

Le pipeline Reco doit ingérer plusieurs podcasts (« sources ») et chaque
source a des métadonnées :
- identité (id, titre, hôtes) ;
- flux de données (RSS, YouTube, Spotify) ;
- réglages pipeline (préfixe reco, patterns d'extraction, suffixes YT à
  retirer avant matching) ;
- branding site public (couleur d'accent, thème).

Historique : ces métadonnées étaient :
1. partiellement codées en dur dans `tools/common.py` (`reco_prefix`
   heuristique) ;
2. partiellement dans des constantes regex (`_SUFFIX_RE` de
   `match_youtube.py` taillé pour « Un Bon Moment ») ;
3. partiellement dans `src/content/sources/<id>.json` (consommé par
   Astro pour le site public).

Résultat : ajouter une nouvelle source = patcher 3 fichiers Python +
1 JSON, avec un risque de drift silencieux entre Astro et Python.

## Options envisagées

### A. JSON Schema unique généré (Zod → JSON Schema → Python jsonschema)

- ✅ formellement « SSOT mécanique »
- ❌ surdimensionné pour 1-2 sources actives
- ❌ nécessite un build step Node ↔ Python à maintenir
- ❌ dégrade l'ergonomie (les contributeurs lisent du JSON Schema)

### B. SSOT côté Astro + couche Python pure de mapping

- ✅ contrat unique : `src/content/sources/<id>.json` valide Zod
- ✅ `tools/config/` (Python pur) traduit camelCase → snake_case
- ✅ Tests cross-stack qui valident que chaque JSON SSOT charge sans
  warning côté Python (preuve qu'il n'y a pas de drift)
- ❌ duplication soft du schéma (Zod + dataclass), mais structurée par
  des tests

### C. SSOT côté Python + génération du schéma TypeScript

- ❌ inverse les couples acteur/observateur (Astro est l'app principale)
- ❌ build step Python → TS plus exotique que B

## Décision

**Option B**. SSOT = `src/content/sources/<id>.json`, validée par :
- Zod (Astro `src/content.config.ts`) au build du site ;
- `SourceConfig.from_dict` (Python `tools/config/schema.py`) au boot des
  scripts pipeline ;
- un test pytest qui charge **tous** les fichiers SSOT via `SourceConfig`
  et échoue si un champ est inconnu côté Python — voir
  `tests/test_config_cross_stack.py`.

## Conséquences

### Positives

- Ajouter une source = 1 fichier JSON, zéro modif Python.
- Drift Astro↔Python détecté à la première CI (test cross-stack).
- Le schéma Python expose `SourceConfig.extra` pour absorber sans warning
  les champs front (`theme`, `tagline`, `coverImage`) ou des champs
  futurs en attente de mapping.
- `tools/config/astro_adapter.py` isole la connaissance camelCase ↔
  snake_case hors du domaine pur (`schema.py`).

### Négatives

- Deux schémas à maintenir (Zod TypeScript + dataclass Python). Mitigé
  par le test cross-stack.
- Les regex de validation doivent rester en miroir entre `_RE_ID`,
  `_RE_PREFIX`, `_RE_HEX_COLOR` côté Python et leurs équivalents Zod.
  Mitigé par des commentaires croisés et l'ADR.

### Évolutions prévues

- `schemaVersion: int` réservé pour permettre des migrations futures
  sans casser les forks (cf. item #3 roadmap).
- `enabled: bool` permet de désactiver une source sans la supprimer.
- `extra: dict` peut accueillir des champs forks/expérimentaux sans
  patcher le schéma.
