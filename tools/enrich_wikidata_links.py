"""
enrich_wikidata_links.py — pose sur les recos `artiste` les liens que Wikidata
peut PROUVER : site officiel, Instagram, AlloCiné, IMDb et Wikipédia.

Comble le trou laissé par les autres passes : `enrich_music_links` sert les pages
d'écoute, `enrich_tmdb` et `enrich_video_links` les films et séries. Personne ne
servait les artistes, acteurs et réalisateurs — c'est le travail que l'éditeur
faisait encore à la main.

RÈGLE FONDATRICE — ZÉRO INVENTION
---------------------------------
Une URL n'est écrite que si une source l'a RENVOYÉE et que la réponse corrobore
la personne. Les adresses Instagram, AlloCiné et IMDb sont construites à partir
d'un IDENTIFIANT rendu par Wikidata (P2003, P1266, P345) selon le schéma public
du site — jamais à partir d'un nom. Au moindre doute : aucun lien, avec une
raison traçable. Mieux vaut zéro lien qu'un lien faux : ce dépôt s'est déjà fait
polluer par des URL plausibles.

DEUX CHEMINS, TOUS DEUX EXACTS
------------------------------
`wbsearchentities` — la recherche libre — est écartée : elle CLASSE des résultats
au lieu d'identifier. Mesuré le 2026-09-27, « Fabe » y rend d'abord un village
indonésien, puis une maison d'édition ; le rappeur français n'est pas dans les
trois premiers. On ne s'en sert donc jamais. À la place :

  1. **Par identifiant déjà porté par la reco** (`haswbstatement`) — la preuve la
     plus forte, parce qu'un identifiant est un FAIT et non une ressemblance. La
     reco porte un identifiant Deezer (`externalIds.deezer` ou un lien
     `deezer.com/artist/<id>`) ou Spotify (lien `open.spotify.com/artist/<id>`) :
     on demande à Wikidata quelle entité déclare le même (P2722, P1902).
  2. **Par titre d'article frwiki** (`wbgetentities&sites=frwiki&titles=…`) — un
     titre d'article est une CLÉ EXACTE, pas un classement, et 50 titres passent
     en un seul appel, d'où pas de 429 à redouter.

Le chemin 2 ne prouve toutefois pas l'identité, et le corpus en fournit le
contre-exemple : `fr.wikipedia.org/wiki/Yoa` est un **village du Cameroun**
(Q28041053, P31 = Q486972 « établissement humain »), pas la chanteuse recommandée
dans S6-E01. C'est le contrôle de la NATURE (P31) qui l'arrête. La chanteuse, elle,
est retrouvée par le chemin 1 grâce à l'identifiant Spotify que la reco porte
déjà : Q124961805, dont l'article s'intitule « Yoa (artiste) » — un titre que le
chemin 2 ne devinerait pas.

POURQUOI SEUL LE TYPE `artiste`
-------------------------------
Mesuré sur les recos réelles des deux épisodes publiés : les quatre entités de
type `lieu` et `autre` sont ABSENTES de Wikidata — l'exposition « Plumes du
paradis », les associations « Sourire à la vie » et « Linkee », et même le musée
du quai Branly (dont l'article porte un tiret cadratin que le titre de la reco n'a
pas). Écrire pour ces types une liste de natures admises serait de la devinette
non testable : on s'abstient, et c'est dit plutôt que caché. Leur site officiel,
lui, se trouve à la main en une recherche.

GARDE-FOUS (toute violation ⇒ aucun lien)
-----------------------------------------
  `id-mismatch`       la reco et l'entité déclarent des identifiants DIFFÉRENTS
                      sur la même propriété → deux personnes distinctes.
  `type-incompatible` nature hors liste (le village pour un artiste).
  `label-mismatch`    l'entité trouvée par titre ne porte ni ce libellé ni cet
                      alias.
  `ambiguous`         deux entités distinctes survivent → arbitrage humain.
  `no-entity`         aucun des deux chemins ne trouve.
  `no-new-link`       entité corroborée, mais toutes ses sources sont déjà là.
  `http-error`        Wikidata injoignable — distinct d'une absence d'entité.

Un lien déjà présent n'est JAMAIS remplacé : on ne comble qu'un hôte absent.

DÉCOUPAGE
---------
    wikidata_matching  décide SI c'est la bonne personne (aucun réseau)
    wikidata_links     interroge, résout, déroule la passe, écrit
Tout est ré-exporté ici : cette façade reste l'entrée publique de l'outil.

Usage :
    python enrich_wikidata_links.py                        # simulation, tout
    python enrich_wikidata_links.py --source un-bon-moment
    python enrich_wikidata_links.py --ids @episode.txt     # un épisode relu
    python enrich_wikidata_links.py --json rapport.json
    python enrich_wikidata_links.py --apply                # écrit (prend le verrou)

Écriture : AJOUT dans `links` + audit trail `enrichedAt["links"]`, via
`common.write_json_if_changed` (atomique et idempotent).
"""
from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

import requests

from common import RECOS_DIR, atomic_write_text, log, parse_ids_option
from review_lock import ServerLockBusy, acquire_pipeline_lock
from wikidata_links import (
    API,
    RATE_LIMIT_SLEEP,
    USER_AGENT,
    Cas,
    RapportWikidata,
    WikidataInjoignable,
    appliquer,
    entite_depuis_json,
    entites_par_identifiant,
    entites_par_titres,
    format_rapport,
    resoudre,
    run,
)
from wikidata_matching import (
    NATURES_ADMISES,
    PREUVE_IDENTIFIANT,
    PREUVE_TITRE,
    PROPS_PREUVE,
    RAISON_AMBIGUOUS,
    RAISON_HTTP_ERROR,
    RAISON_ID_MISMATCH,
    RAISON_LABEL_MISMATCH,
    RAISON_NO_ENTITY,
    RAISON_NO_NEW_LINK,
    RAISON_NOT_VALIDATED,
    RAISON_OK,
    RAISON_TYPE_INCOMPATIBLE,
    RAISON_TYPE_UNSUPPORTED,
    RAISONS_A_ARBITRER,
    SOURCES_PAR_PROP,
    TYPES_SERVIS,
    Entite,
    Lien,
    Resolution,
    hote,
    identifiants_portes,
    liens_offerts,
    type_servi,
    url_wikipedia,
    verdict,
)

__all__ = [
    "API",
    "NATURES_ADMISES",
    "PREUVE_IDENTIFIANT",
    "PREUVE_TITRE",
    "PROPS_PREUVE",
    "RAISONS_A_ARBITRER",
    "RAISON_AMBIGUOUS",
    "RAISON_HTTP_ERROR",
    "RAISON_ID_MISMATCH",
    "RAISON_LABEL_MISMATCH",
    "RAISON_NOT_VALIDATED",
    "RAISON_NO_ENTITY",
    "RAISON_NO_NEW_LINK",
    "RAISON_OK",
    "RAISON_TYPE_INCOMPATIBLE",
    "RAISON_TYPE_UNSUPPORTED",
    "RATE_LIMIT_SLEEP",
    "SOURCES_PAR_PROP",
    "TYPES_SERVIS",
    "USER_AGENT",
    "Cas",
    "Entite",
    "Lien",
    "RapportWikidata",
    "Resolution",
    "WikidataInjoignable",
    "appliquer",
    "build_parser",
    "entite_depuis_json",
    "entites_par_identifiant",
    "entites_par_titres",
    "format_rapport",
    "hote",
    "identifiants_portes",
    "liens_offerts",
    "main",
    "rapport_payload",
    "resoudre",
    "run",
    "type_servi",
    "url_wikipedia",
    "verdict",
]


def rapport_payload(rapport: RapportWikidata) -> dict:
    """Rapport sérialisable, pour `--json` et pour comparer deux passes."""
    return {
        "vues": rapport.vues,
        "ecrites": rapport.ecrites,
        "liens": rapport.liens_poses,
        "servies": sorted(rapport.servies),
        "cas": [{"id": c.reco_id, "titre": c.titre, "raison": c.raison,
                 "preuve": c.preuve, "liens": c.liens, "detail": c.detail}
                for c in rapport.cas],
    }


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Pose les liens (site officiel, Instagram, AlloCiné, IMDb, "
                    "Wikipédia) des recos artiste, uniquement quand Wikidata "
                    "prouve l'identité de la personne.")
    p.add_argument("--source", default=None,
                   help="Limiter à une source (défaut : toutes).")
    p.add_argument("--types", default=None,
                   help=f"Filtrer par types (servis : {','.join(TYPES_SERVIS)}).")
    p.add_argument("--ids", default=None,
                   help="N'enrichir QUE ces ids : « a,b,c » ou « @fichier » "
                        "(un id par ligne).")
    p.add_argument("--limit", type=int, default=None,
                   help="Nombre maximum de recos réellement interrogées.")
    p.add_argument("--apply", action="store_true",
                   help="Écrire les liens trouvés (défaut : simulation).")
    p.add_argument("--json", dest="json_path", default=None,
                   help="Écrit le rapport détaillé (JSON) à ce chemin.")
    p.add_argument("--ignore-server-lock", action="store_true",
                   help="Ignore le verrou review_server (écritures "
                        "concurrentes possibles).")
    return p


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    types = tuple(t.strip() for t in args.types.split(",")) if args.types else None
    kwargs = dict(root=RECOS_DIR, session=requests.Session(), source=args.source,
                  types=types, ids=parse_ids_option(args.ids), limit=args.limit,
                  apply=args.apply)

    if args.apply:
        # Écriture : coordination avec review_server (cf. tools/review_lock.py).
        try:
            lock = acquire_pipeline_lock(force=args.ignore_server_lock)
        except ServerLockBusy as exc:
            log.error("%s", exc)
            return 1
        with lock:
            rapport = run(**kwargs)
    else:
        log.info("SIMULATION — aucune écriture (ajoute --apply pour écrire).")
        rapport = run(**kwargs)

    log.info("%s", format_rapport(rapport))
    if args.json_path:
        atomic_write_text(Path(args.json_path),
                          json.dumps(rapport_payload(rapport),
                                     ensure_ascii=False, indent=2) + "\n")
        log.info("Rapport détaillé : %s", args.json_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
