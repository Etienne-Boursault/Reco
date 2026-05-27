"""
enrich_tmdb.py — Enrichit les recos film/série avec leurs « watch providers »
FR (plateformes de streaming) en interrogeant l'API TMDB.

Pour chaque reco de type `film` ou `serie` sans `externalIds.tmdb` :
  1. Recherche TMDB par titre (+ créateur si dispo), langue FR.
  2. Si non trouvé en `movie`, essai en `tv` (et inversement) — robustesse face
     au mauvais typage par le LLM (un docu peut être tagué film alors qu'il
     est en TV, etc.).
  3. Récupère les watch providers FR (`/<kind>/{id}/watch/providers`).
  4. Mappe chaque provider à une URL de recherche dédiée + marqueur éthique :
     - Amazon Prime Video → `ethics='avoid'` (politique anti-Amazon).
     - Canal+ / myCANAL    → `ethics='avoid'` (groupe Bolloré).
     - Arte / Mubi / Universcine / Tenk → `ethics='indie'`.
     - Tout le reste → `ethics='neutral'`.
  5. Sauvegarde `externalIds.tmdb`, `externalIds.tmdbType`, `watchProviders`
     dans le JSON de la reco (idempotent : write_json_if_changed).

Usage :
    python enrich_tmdb.py --source un-bon-moment
    python enrich_tmdb.py --source un-bon-moment --limit 10
    python enrich_tmdb.py --source un-bon-moment --force   # re-traiter même
                                                            # celles déjà enrichies
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from urllib.parse import quote

import requests
from dotenv import load_dotenv

from common import (
    TOOLS_DIR,
    log,
    read_json,
    recos_dir_for,
    write_json_if_changed,
)

TMDB_BASE = "https://api.themoviedb.org/3"
RATE_LIMIT_SLEEP = 0.1  # 10 req/sec, bien sous la limite TMDB (50 req/sec).

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


def _tmdb_get(
    session: requests.Session,
    path: str,
    params: dict | None = None,
    api_key: str | None = None,
) -> dict | None:
    """GET TMDB avec auth, journalise les erreurs.

    La clé API est passée à `session.get` via `params=` (jamais via header
    custom) pour rester compatible avec l'API v3 de TMDB.

    `api_key` est explicite quand fourni par `main()` ; sinon on retombe sur
    `os.environ` pour rester compatible avec les appels directs (tests).
    """
    if api_key is None:
        api_key = os.environ.get("TMDB_API_KEY", "")
    full = {"api_key": api_key, **(params or {})}
    try:
        r = session.get(f"{TMDB_BASE}{path}", params=full, timeout=15)
    except requests.RequestException as e:
        log.error("  HTTP : %s", e)
        return None
    if r.status_code != 200:
        # On n'inclut pas `params` dans le log d'erreur : il contient la clé API.
        log.error("  TMDB %s → %s : %s", path, r.status_code, r.text[:200])
        return None
    return r.json()


def tmdb_search(
    session: requests.Session, reco_type: str, title: str,
    creator: str | None = None, api_key: str | None = None,
) -> tuple[str, str] | None:
    """Cherche le titre sur TMDB. Retourne (tmdb_id, kind in {'movie','tv'}) ou None.

    Stratégie de recherche (premier hit gagne) :
      1. titre + creator (si fourni), langue FR, type primaire (film→movie / serie→tv).
      2. titre seul, langue FR, type primaire.
      3. titre seul, sans contrainte de langue (include_adult=false), type primaire.
      4. mêmes étapes mais sur le type secondaire (cas de mauvais typage par le LLM).
    """
    primary = "movie" if reco_type == "film" else "tv"
    secondary = "tv" if primary == "movie" else "movie"

    queries: list[tuple[str, dict]] = []
    if creator:
        queries.append((f"{title} {creator}", {"language": "fr-FR"}))
    queries.append((title, {"language": "fr-FR"}))
    queries.append((title, {}))  # toutes langues

    for kind in (primary, secondary):
        for q, extra in queries:
            data = _tmdb_get(session, f"/search/{kind}",
                             {"query": q, **extra}, api_key=api_key)
            results = (data or {}).get("results") or []
            if results:
                return str(results[0]["id"]), kind
    return None


def tmdb_watch_providers(
    session: requests.Session, tmdb_id: str, kind: str, title: str,
    api_key: str | None = None,
) -> tuple[str | None, list[dict]]:
    """Récupère le `link` JustWatch du film + les watch providers FR.

    Retourne (justwatch_url, providers). Le justwatch_url est l'URL EXACTE de la
    page JustWatch du film (renvoyée par TMDB) — c'est là qu'on trouve les vrais
    deeplinks « Watch on Netflix » etc. C'est notre lien streaming principal.
    Les providers sont conservés à titre informatif (debug / évolutions futures).
    """
    data = _tmdb_get(session, f"/{kind}/{tmdb_id}/watch/providers", api_key=api_key)
    fr = ((data or {}).get("results") or {}).get("FR") or {}
    justwatch_url = fr.get("link") or None
    seen: set[str] = set()
    providers: list[dict] = []
    for slot in ("flatrate", "free", "ads", "rent", "buy"):
        for prov in fr.get(slot, []) or []:
            name = (prov.get("provider_name") or "").strip()
            if not name or name in seen:
                continue
            seen.add(name)
            providers.append(_provider_link(name, title))
    return justwatch_url, providers


def main():
    parser = argparse.ArgumentParser(
        description="Enrichit les recos film/série avec leurs watch providers FR via TMDB."
    )
    parser.add_argument("--source", required=True)
    parser.add_argument("--limit", type=int, default=None,
                        help="Limiter le nombre de recos traitées (utile pour tester).")
    parser.add_argument("--force", action="store_true",
                        help="Re-traiter même les recos qui ont déjà un externalIds.tmdb.")
    args = parser.parse_args()

    load_dotenv(TOOLS_DIR / ".env")
    api_key = os.getenv("TMDB_API_KEY")
    if not api_key:
        log.error("TMDB_API_KEY absent de tools/.env. "
                  "Crée un compte sur https://www.themoviedb.org/ → Settings → API.")
        sys.exit(1)

    recos_dir = recos_dir_for(args.source)
    targets = []
    for p in sorted(recos_dir.glob("*.json")):
        d = read_json(p)
        if d.get("type") not in ("film", "serie"):
            continue
        ext = d.get("externalIds") or {}
        if not args.force and ext.get("tmdb") and ext.get("justwatch"):
            # Déjà enrichi complètement.
            continue
        targets.append((p, d))

    if args.limit:
        targets = targets[: args.limit]
    log.info("%d reco(s) film/série à enrichir TMDB.", len(targets))
    if not targets:
        return

    session = requests.Session()
    enriched = 0
    not_found = 0
    for i, (p, d) in enumerate(targets, 1):
        title = d["title"]
        creator = d.get("creator")
        label = f"{title} ({creator})" if creator else title
        log.info("[%d/%d] %s [%s]", i, len(targets), label[:60], d["type"])
        # On réutilise le tmdb_id déjà connu si possible — économise 1 appel API.
        ext = d.get("externalIds") or {}
        if ext.get("tmdb") and ext.get("tmdbType"):
            tmdb_id, kind = ext["tmdb"], ext["tmdbType"]
            log.info("  ↻ TMDB id déjà connu : %s (%s)", tmdb_id, kind)
        else:
            found = tmdb_search(session, d["type"], title, creator, api_key=api_key)
            if not found:
                log.info("  → TMDB : pas trouvé")
                not_found += 1
                time.sleep(RATE_LIMIT_SLEEP)
                continue
            tmdb_id, kind = found
        justwatch_url, providers = tmdb_watch_providers(
            session, tmdb_id, kind, d["title"], api_key=api_key)
        ids = dict(d.get("externalIds") or {})
        ids["tmdb"] = tmdb_id
        ids["tmdbType"] = kind
        if justwatch_url:
            ids["justwatch"] = justwatch_url
        elif "justwatch" in ids:
            del ids["justwatch"]
        d["externalIds"] = ids
        if providers:
            d["watchProviders"] = providers
        elif "watchProviders" in d:
            del d["watchProviders"]
        if write_json_if_changed(p, d):
            enriched += 1
        log.info("  → tmdb_id=%s (%s) · JustWatch=%s · %d providers info",
                 tmdb_id, kind, "OK" if justwatch_url else "—", len(providers))
        time.sleep(RATE_LIMIT_SLEEP)

    log.info("Terminé : %d enrichis · %d non trouvés · %d inchangés.",
             enriched, not_found, len(targets) - enriched - not_found)


if __name__ == "__main__":
    main()
