"""
tmdb_providers.py — nom de plateforme renvoyé par TMDB → lien de recherche
et marqueur éthique.

Sorti de `enrich_tmdb.py` le 2026-09-25 : ce sont 100 lignes de TABLE, que la
règle des 500 lignes par fichier ne laissait plus cohabiter avec la logique
d'appel d'API. Deux outils s'en servent — `enrich_tmdb` à l'enrichissement, et
`refresh_watch_provider_urls` quand la table change.
"""
from __future__ import annotations

from urllib.parse import quote

# Mapping nom-affiché-par-TMDB → URL de recherche directe + marqueur éthique.
# Recherche d'abord par correspondance EXACTE, puis par PATTERN (substring) pour
# couvrir les nombreuses variantes que TMDB renvoie (« Apple TV Store »,
# « Netflix Standard with Ads », « X Amazon Channel », « Canal VOD », …).
# Quand un provider ne match aucune règle, on retombe sur une recherche
# DuckDuckGo neutre.
PROVIDER_RULES: dict[str, dict[str, str]] = {
    # --- Plateformes mainstream (neutres) ---
    "Netflix":              {"url": "https://www.netflix.com/search?q={q}",                     "ethics": "neutral"},
    "Apple TV":             {"url": "https://tv.apple.com/fr/search?term={q}",                  "ethics": "neutral"},
    "Disney Plus":          {"url": "https://www.disneyplus.com/fr-fr/search?q={q}",            "ethics": "neutral"},
    "Paramount Plus":       {"url": "https://www.paramountplus.com/fr/search/?q={q}",           "ethics": "neutral"},
    "Max":                  {"url": "https://play.max.com/search?q={q}",                       "ethics": "neutral"},
    "Crunchyroll":          {"url": "https://www.crunchyroll.com/fr/search?q={q}",              "ethics": "neutral"},
    "YouTube":              {"url": "https://www.youtube.com/results?search_query={q}",         "ethics": "neutral"},
    "Filmo TV":             {"url": "https://www.filmotv.fr/?txtsearch={q}",                    "ethics": "neutral"},
    "Google Play Movies":   {"url": "https://play.google.com/store/search?q={q}&c=movies",      "ethics": "neutral"},
    "Orange VOD":           {"url": "https://video.orange.fr/search?q={q}",                     "ethics": "neutral"},
    "Sooner":               {"url": "https://www.sooner.fr/recherche?q={q}",                    "ethics": "neutral"},
    "Pathé Home":           {"url": "https://www.pathehome.com/recherche?text={q}",             "ethics": "neutral"},
    "Rakuten TV":           {"url": "https://rakuten.tv/fr/search?q={q}",                       "ethics": "neutral"},
    "Molotov TV":           {"url": "https://www.molotov.tv/search?q={q}",                      "ethics": "neutral"},
    "SFR Play":             {"url": "https://www.sfrplay.fr/recherche?q={q}",                   "ethics": "neutral"},
    "TF1+":                 {"url": "https://www.tf1.fr/recherche?q={q}",                       "ethics": "neutral"},
    "M6+":                  {"url": "https://www.6play.fr/recherche?q={q}",                     "ethics": "neutral"},
    "VIVA by videofutur":   {"url": "https://www.videofutur.fr/recherche?q={q}",                "ethics": "neutral"},
    "Premiere Max":         {"url": "https://www.premieremax.com/search?q={q}",                 "ethics": "neutral"},
    "Animation Digital Network": {"url": "https://animationdigitalnetwork.com/search?q={q}",    "ethics": "neutral"},
    "Cinemas a la Demande": {"url": "https://www.cinemasalademande.com/?s={q}",                 "ethics": "neutral"},
    "Plex":                 {"url": "https://watch.plex.tv/search?q={q}",                       "ethics": "neutral"},
    "Plex Channel":         {"url": "https://watch.plex.tv/search?q={q}",                       "ethics": "neutral"},
    "Filmzie":              {"url": "https://www.filmzie.com/search?q={q}",                     "ethics": "indie"},
    # --- Plateformes « indé » / culturelles ---
    "Arte":                 {"url": "https://www.arte.tv/fr/search/?q={q}",                     "ethics": "indie"},
    "ARTE Boutique":        {"url": "https://boutique.arte.tv/search?q={q}",                    "ethics": "indie"},
    "Mubi":                 {"url": "https://mubi.com/fr/films?q={q}",                          "ethics": "indie"},
    "MUBI":                 {"url": "https://mubi.com/fr/films?q={q}",                          "ethics": "indie"},
    "Universcine":          {"url": "https://www.universcine.com/?query={q}",                   "ethics": "indie"},
    "Tenk":                 {"url": "https://www.tenk.tv/search?q={q}",                         "ethics": "indie"},
    "La Cinetek":           {"url": "https://www.lacinetek.com/fr/?text={q}",                   "ethics": "indie"},
    "LaCinetek":            {"url": "https://www.lacinetek.com/fr/?text={q}",                   "ethics": "indie"},
    "Artiflix":             {"url": "https://www.artiflix.com/search?q={q}",                    "ethics": "indie"},
    "Shadowz":              {"url": "https://shadowz.fr/search?q={q}",                          "ethics": "indie"},
    # --- ⚠️ Plateformes à éviter (Amazon, Bolloré) ---
    "Amazon Prime Video":   {"url": "https://www.primevideo.com/-/fr/search/?phrase={q}",       "ethics": "avoid"},
    "Amazon Video":         {"url": "https://www.primevideo.com/-/fr/search/?phrase={q}",       "ethics": "avoid"},
    "Canal+":               {"url": "https://www.canalplus.com/cmd/searchOnsite?query={q}",     "ethics": "avoid"},
    "myCANAL":              {"url": "https://www.canalplus.com/cmd/searchOnsite?query={q}",     "ethics": "avoid"},
    "Canal+ Series":        {"url": "https://www.canalplus.com/cmd/searchOnsite?query={q}",     "ethics": "avoid"},
    "Canal+ Séries":        {"url": "https://www.canalplus.com/cmd/searchOnsite?query={q}",     "ethics": "avoid"},
    "Canal VOD":            {"url": "https://www.canalplus.com/cmd/searchOnsite?query={q}",     "ethics": "avoid"},
}

# Patterns appliqués DANS L'ORDRE quand le nom du provider ne match aucune
# entrée exacte. La 1ère règle qui matche gagne.
# (substring insensible à la casse → règle exacte du dict ci-dessus)
PROVIDER_PATTERNS: list[tuple[str, dict[str, str]]] = [
    # Tout ce qui contient « Amazon » (channels, Prime Video with Ads, etc.).
    ("amazon",         {"url": "https://www.primevideo.com/-/fr/search/?phrase={q}",   "ethics": "avoid"}),
    # Toute variante de Canal (groupe Bolloré).
    ("canal",          {"url": "https://www.canalplus.com/cmd/searchOnsite?query={q}",  "ethics": "avoid"}),
    # Variantes Apple TV (« Apple TV Store », « Apple TV Plus », …).
    ("apple tv",       {"url": "https://tv.apple.com/fr/search?term={q}",               "ethics": "neutral"}),
    # Variantes Netflix (« Netflix Standard with Ads », « Netflix basic »).
    ("netflix",        {"url": "https://www.netflix.com/search?q={q}",                  "ethics": "neutral"}),
    # Variantes Disney+ / Paramount+ / HBO Max / Max.
    ("disney",         {"url": "https://www.disneyplus.com/fr-fr/search?q={q}",         "ethics": "neutral"}),
    ("paramount",      {"url": "https://www.paramountplus.com/fr/search/?q={q}",        "ethics": "neutral"}),
    ("hbo max",        {"url": "https://play.max.com/search?q={q}",                     "ethics": "neutral"}),
    # MUBI peut apparaître avec d'autres suffixes (« MUBI Amazon Channel »
    # est déjà capté par "amazon channel" plus haut → avoid).
    ("mubi",           {"url": "https://mubi.com/fr/films?q={q}",                       "ethics": "indie"}),
    # ARTE et ses variantes.
    ("arte",           {"url": "https://www.arte.tv/fr/search/?q={q}",                  "ethics": "indie"}),
]


def _provider_link(provider_name: str, title: str) -> dict:
    """Construit un lien { label, url, ethics } pour un nom de provider TMDB.

    Cascade : 1) règle exacte, 2) pattern substring (1er match), 3) fallback
    DuckDuckGo. On garde toujours le `provider_name` original comme `label`
    pour l'affichage (≠ de l'URL cible).
    """
    q = quote(title)
    # 1) règle exacte
    rule = PROVIDER_RULES.get(provider_name)
    if rule:
        return {"label": provider_name, "url": rule["url"].format(q=q), "ethics": rule["ethics"]}
    # 2) pattern substring (premier match gagne)
    name_lc = provider_name.lower()
    for needle, r in PROVIDER_PATTERNS:
        if needle in name_lc:
            return {"label": provider_name, "url": r["url"].format(q=q), "ethics": r["ethics"]}
    # 3) fallback : recherche neutre (DuckDuckGo, pas Google).
    return {
        "label": provider_name,
        "url": f"https://duckduckgo.com/?q={quote(title + ' ' + provider_name)}",
        "ethics": "neutral",
    }
