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
from pathlib import Path
from urllib.parse import quote

import requests
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).parent))
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
# Quand un provider n'est pas dans cette table, on retombe sur une recherche
# Google neutre (cf. _provider_link).
PROVIDER_RULES: dict[str, dict[str, str]] = {
    # Plateformes mainstream (neutres)
    "Netflix":              {"url": "https://www.netflix.com/search?q={q}",                     "ethics": "neutral"},
    "Apple TV":             {"url": "https://tv.apple.com/fr/search?term={q}",                  "ethics": "neutral"},
    "Apple TV Plus":        {"url": "https://tv.apple.com/fr/search?term={q}",                  "ethics": "neutral"},
    "Disney Plus":          {"url": "https://www.disneyplus.com/fr-fr/search?q={q}",            "ethics": "neutral"},
    "Paramount Plus":       {"url": "https://www.paramountplus.com/fr/search/?q={q}",           "ethics": "neutral"},
    "Max":                  {"url": "https://play.max.com/search?q={q}",                       "ethics": "neutral"},
    "HBO Max":              {"url": "https://play.max.com/search?q={q}",                       "ethics": "neutral"},
    "Crunchyroll":          {"url": "https://www.crunchyroll.com/fr/search?q={q}",              "ethics": "neutral"},
    "YouTube":              {"url": "https://www.youtube.com/results?search_query={q}",         "ethics": "neutral"},
    "YouTube Premium":      {"url": "https://www.youtube.com/results?search_query={q}",         "ethics": "neutral"},
    "Filmo":                {"url": "https://www.filmotv.fr/?txtsearch={q}",                    "ethics": "neutral"},
    "Filmo TV":             {"url": "https://www.filmotv.fr/?txtsearch={q}",                    "ethics": "neutral"},
    "Google Play Movies":   {"url": "https://play.google.com/store/search?q={q}&c=movies",      "ethics": "neutral"},
    # Plateformes "indé" / culturelles
    "Arte":                 {"url": "https://www.arte.tv/fr/search/?q={q}",                     "ethics": "indie"},
    "ARTE":                 {"url": "https://www.arte.tv/fr/search/?q={q}",                     "ethics": "indie"},
    "Mubi":                 {"url": "https://mubi.com/fr/films?q={q}",                          "ethics": "indie"},
    "Universcine":          {"url": "https://www.universcine.com/?query={q}",                   "ethics": "indie"},
    "Tenk":                 {"url": "https://www.tenk.tv/search?q={q}",                         "ethics": "indie"},
    "La Cinetek":           {"url": "https://www.lacinetek.com/fr/?text={q}",                   "ethics": "indie"},
    "Spicee":               {"url": "https://www.spicee.com/search?query={q}",                  "ethics": "neutral"},
    # ⚠️ À éviter selon la politique éditoriale (Amazon, Bolloré)
    "Amazon Prime Video":   {"url": "https://www.primevideo.com/-/fr/search/?phrase={q}",       "ethics": "avoid"},
    "Amazon Video":         {"url": "https://www.primevideo.com/-/fr/search/?phrase={q}",       "ethics": "avoid"},
    "Canal+":               {"url": "https://www.canalplus.com/cmd/searchOnsite?query={q}",     "ethics": "avoid"},
    "myCANAL":              {"url": "https://www.canalplus.com/cmd/searchOnsite?query={q}",     "ethics": "avoid"},
    "Canal+ Series":        {"url": "https://www.canalplus.com/cmd/searchOnsite?query={q}",     "ethics": "avoid"},
}


def _provider_link(provider_name: str, title: str) -> dict:
    """Construit un lien { label, url, ethics } pour un nom de provider TMDB."""
    rule = PROVIDER_RULES.get(provider_name)
    q = quote(title)
    if rule:
        return {
            "label": provider_name,
            "url": rule["url"].format(q=q),
            "ethics": rule["ethics"],
        }
    # Fallback : recherche Google neutre quand on ne connaît pas le provider.
    return {
        "label": provider_name,
        "url": f"https://www.google.com/search?q={quote(title + ' ' + provider_name)}",
        "ethics": "neutral",
    }


def _tmdb_get(session: requests.Session, path: str, params: dict | None = None) -> dict | None:
    """GET TMDB avec auth, journalise les erreurs."""
    full = {"api_key": os.environ["TMDB_API_KEY"], **(params or {})}
    try:
        r = session.get(f"{TMDB_BASE}{path}", params=full, timeout=15)
    except requests.RequestException as e:
        log.error("  HTTP : %s", e)
        return None
    if r.status_code != 200:
        log.error("  TMDB %s → %s : %s", path, r.status_code, r.text[:200])
        return None
    return r.json()


def tmdb_search(
    session: requests.Session, reco_type: str, title: str, creator: str | None = None
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
            data = _tmdb_get(session, f"/search/{kind}", {"query": q, **extra})
            results = (data or {}).get("results") or []
            if results:
                return str(results[0]["id"]), kind
    return None


def tmdb_watch_providers(session: requests.Session, tmdb_id: str, kind: str, title: str) -> list[dict]:
    """Récupère les watch providers FR + mappe en liens éthiques."""
    data = _tmdb_get(session, f"/{kind}/{tmdb_id}/watch/providers")
    fr = ((data or {}).get("results") or {}).get("FR") or {}
    seen: set[str] = set()
    links: list[dict] = []
    # On parcourt dans l'ordre de préférence : streaming inclus > free > rent > buy.
    for slot in ("flatrate", "free", "ads", "rent", "buy"):
        for prov in fr.get(slot, []) or []:
            name = (prov.get("provider_name") or "").strip()
            if not name or name in seen:
                continue
            seen.add(name)
            links.append(_provider_link(name, title))
    return links


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
    if not os.getenv("TMDB_API_KEY"):
        log.error("TMDB_API_KEY absent de tools/.env. "
                  "Crée un compte sur https://www.themoviedb.org/ → Settings → API.")
        sys.exit(1)

    recos_dir = recos_dir_for(args.source)
    targets = []
    for p in sorted(recos_dir.glob("*.json")):
        d = read_json(p)
        if d.get("type") not in ("film", "serie"):
            continue
        if not args.force and (d.get("externalIds") or {}).get("tmdb"):
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
        found = tmdb_search(session, d["type"], title, creator)
        if not found:
            log.info("  → TMDB : pas trouvé")
            not_found += 1
            time.sleep(RATE_LIMIT_SLEEP)
            continue
        tmdb_id, kind = found
        providers = tmdb_watch_providers(session, tmdb_id, kind, d["title"])
        ids = dict(d.get("externalIds") or {})
        ids["tmdb"] = tmdb_id
        ids["tmdbType"] = kind
        d["externalIds"] = ids
        if providers:
            d["watchProviders"] = providers
        elif "watchProviders" in d:
            # Pas de provider FR : on retire l'éventuel cache obsolète.
            del d["watchProviders"]
        if write_json_if_changed(p, d):
            enriched += 1
        log.info("  → tmdb_id=%s (%s) · %d providers", tmdb_id, kind, len(providers))
        time.sleep(RATE_LIMIT_SLEEP)

    log.info("Terminé : %d enrichis · %d non trouvés · %d inchangés.",
             enriched, not_found, len(targets) - enriched - not_found)


if __name__ == "__main__":
    main()
