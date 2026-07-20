"""Adaptateur Astro (camelCase) ↔ schéma Python (snake_case).

SRP : sortir la traduction de format hors du domaine. Le ``schema.py``
n'a aucune raison de connaître les conventions camelCase d'Astro ni la
liste des champs « purement front » (theme, tagline) ignorés côté pipeline.

Ce module n'a aucune dépendance sur ``schema.py`` ni ``loader.py`` (il ne
sait pas non plus à quoi ressemble une ``SourceConfig`` — il ne fait que
massacrer un dict).
"""

from __future__ import annotations

from typing import Any, Mapping

__all__ = ["ALIASES", "ASTRO_ONLY_FIELDS", "normalize_payload"]

# Alias d'entrée (Astro / JSON camelCase) → champs Python (snake_case).
# SSOT : `src/content/sources/<id>.json` reste camelCase pour Astro.
ALIASES: dict[str, str] = {
    "rssUrl": "rss_url",
    "youtubeChannel": "youtube_channel_url",
    "spotifyShowId": "spotify_show_id",
    "website": "site_url",
    "recoPrefix": "reco_prefix",
    "transcriptDefaultSource": "transcript_default_source",
    "extractionAnchorPatterns": "extraction_anchor_patterns",
    "siteColorAccent": "site_color_accent",
    "avoidBrands": "avoid_brands",
    "youtubeTitleSuffixPatterns": "youtube_title_suffix_patterns",
    "schemaVersion": "schema_version",
}

# Champs spécifiques à la couche Astro (site public) — ignorés silencieusement
# côté Python. C'est de la « UI/branding only » : aucun script du pipeline
# n'en a besoin.
ASTRO_ONLY_FIELDS: frozenset[str] = frozenset(
    {
        "theme",
        "tagline",
        # Anticipation : champs envisagés dans la roadmap (variants visuels).
        # Les lister ici évite un warning à chaque load tant que le schéma
        # Python ne les expose pas explicitement.
        "coverImage",
    }
)


def normalize_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Traduit un payload Astro (camelCase + champs front) en dict
    snake_case consommable par ``SourceConfig.from_dict``.

    - Renomme les clés via ``ALIASES``.
    - Drop silencieusement les champs purement Astro.
    - Ne touche pas aux valeurs (la coercition tuple/strict reste au domaine).
    """
    out: dict[str, Any] = {}
    for k, v in payload.items():
        if k in ASTRO_ONLY_FIELDS:
            continue
        out[ALIASES.get(k, k)] = v
    return out
