"""
refresh_watch_provider_urls.py — Re-map les URLs des watchProviders existants
sans rappeler l'API TMDB.

Quand on enrichit (ou améliore) la table de mapping PROVIDER_RULES /
PROVIDER_PATTERNS dans enrich_tmdb.py, les recos déjà enrichies ont des URLs
basées sur l'ancienne table. Ce script lit chaque reco ayant des
`watchProviders`, ré-applique `_provider_link()` sur chaque label, et écrit
les nouvelles URLs / ethics. Idempotent.

Usage :
    python refresh_watch_provider_urls.py --source un-bon-moment
"""
from __future__ import annotations

import argparse

from common import log, read_json, recos_dir_for, write_json_if_changed
from enrich_tmdb import _provider_link


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True)
    args = parser.parse_args()

    updated = 0
    seen = 0
    for p in sorted(recos_dir_for(args.source).glob("*.json")):
        d = read_json(p)
        providers = d.get("watchProviders")
        if not providers:
            continue
        seen += 1
        title = d["title"]
        new_providers = [_provider_link(prov["label"], title) for prov in providers]
        d["watchProviders"] = new_providers
        if write_json_if_changed(p, d):
            updated += 1

    log.info("Terminé : %d recos avec providers vues, %d mises à jour.", seen, updated)


if __name__ == "__main__":
    main()
