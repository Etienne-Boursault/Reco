"""
enrich_boutique_links.py — Pose les liens « où se le procurer » des jeux et des
livres, à partir de sources interrogées, et UNIQUEMENT à partir d'elles.

Deux passes, un seul outil : un jeu se trouve sur Steam, un livre chez le
libraire, mais la mécanique est la même — sélectionner, corroborer, n'écrire
qu'une source absente, rendre une raison traçable sinon. Les séparer en deux
commandes aurait dupliqué la boucle, le rapport et l'interface.

RÈGLE FONDATRICE — ZÉRO INVENTION
---------------------------------
Cf. l'en-tête d'`enrich_music_links`, et `boutique_matching` pour les pièges
mesurés : Steam qui répond sous la clé d'un autre identifiant, `storesearch` qui
étiquette les bandes-son comme des jeux, et Place des Libraires dont on écrit
l'URL QU'IL RÉSOUT plutôt qu'un slug fabriqué.

CE QUE LA PASSE REFUSE DE FAIRE
-------------------------------
  - deviner un jeu sans studio pour le corroborer (`--jeux-sans-studio` ouvre ce
    cas sous responsabilité humaine, et seulement si une seule fiche survit) ;
  - retenir un ISBN qu'aucune fiche libraire ne confirme ;
  - remplacer un lien existant : elle ne comble qu'une absence.

Usage :
    python enrich_boutique_links.py                       # simulation, tout
    python enrich_boutique_links.py --types jeu
    python enrich_boutique_links.py --ids @episode.txt
    python enrich_boutique_links.py --jeux-sans-studio
    python enrich_boutique_links.py --apply               # écrit (prend le verrou)

Écriture : AJOUT dans `links`, `externalIds.isbn` pour les livres, et l'audit
trail `enrichedAt` — via `common.write_json_if_changed` (atomique, idempotent).

FAÇADE
------
Le travail est réparti en deux modules, pour tenir sous les 500 lignes :
`boutique_matching` décide (aucun réseau), `boutique_links` interroge et écrit.
Tout est ré-exporté ici, qui reste le point d'entrée public de l'outil.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence

import requests

from boutique_links import (
    GOOGLE_BOOKS,
    HTTP_NOT_FOUND,
    HTTP_TIMEOUT,
    HTTP_TOO_MANY_REQUESTS,
    LIBRAIRE_FICHE,
    LIBRAIRE_RECHERCHE,
    OPEN_LIBRARY,
    PAUSE,
    PAUSE_STEAM,
    STEAM_FICHE,
    STEAM_RECHERCHE,
    USER_AGENT,
    BoutiqueInjoignable,
    appliquer,
    isbn_google,
    isbn_libraire,
    isbn_openlibrary,
    page_libraire,
    resoudre,
    resoudre_jeu,
    resoudre_livre,
    run,
    steam_candidats,
    steam_fiche,
)
from boutique_matching import (
    MAX_EAN_ESSAYES,
    MAX_FICHES_STEAM,
    RAISON_AMBIGUOUS,
    RAISON_DEJA_SERVIE,
    RAISON_EAN_ABSENT,
    RAISON_HTTP_ERROR,
    RAISON_NO_CREATOR,
    RAISON_NO_ISBN,
    RAISON_NO_MATCH,
    RAISON_NOT_VALIDATED,
    RAISON_OK,
    RAISON_PAGE_MISMATCH,
    RAISON_PAS_UN_JEU,
    RAISON_STEAM_ID_MISMATCH,
    RAISON_STUDIO_MISMATCH,
    RAISON_TYPE_UNSUPPORTED,
    RAISON_UNREADABLE,
    RAISONS_A_ARBITRER,
    SOURCE_LIBRAIRE,
    SOURCE_STEAM,
    TYPE_JEU,
    TYPE_LIVRE,
    TYPE_STEAM_JEU,
    TYPES_SERVIS,
    Lien,
    Resolution,
    Source,
    auteur_correspond,
    candidats_au_bon_titre,
    deja_servie,
    documents_corrobores,
    eans_de_resultats,
    eans_valides,
    fiche_demandee,
    fiche_libraire,
    hote,
    isbn_de_page,
    jsonld_isbn_coherent,
    page_corrobore,
    source_pour,
    studio_correspond,
    studios_de,
    titres_correspondent,
    type_servi,
    url_canonique,
    url_steam,
    volume_corrobore,
)
from boutique_report import Cas, RapportBoutique, format_rapport, rapport_payload
from common import RECOS_DIR, atomic_write_text, log, parse_ids_option
from review_lock import ServerLockBusy, acquire_pipeline_lock

#: Façade publique. Ce `__all__` n'est pas décoratif : sans lui, `ruff --fix`
#: prend les ré-exports pour des imports inutilisés et les SUPPRIME (c'est arrivé
#: sur `enrich_music_links`, et la collecte des tests a cassé d'un coup).
__all__ = [
    "GOOGLE_BOOKS",
    "HTTP_NOT_FOUND",
    "HTTP_TIMEOUT",
    "HTTP_TOO_MANY_REQUESTS",
    "LIBRAIRE_FICHE",
    "LIBRAIRE_RECHERCHE",
    "MAX_EAN_ESSAYES",
    "MAX_FICHES_STEAM",
    "OPEN_LIBRARY",
    "PAUSE",
    "PAUSE_STEAM",
    "RAISONS_A_ARBITRER",
    "RAISON_AMBIGUOUS",
    "RAISON_DEJA_SERVIE",
    "RAISON_EAN_ABSENT",
    "RAISON_HTTP_ERROR",
    "RAISON_NOT_VALIDATED",
    "RAISON_NO_CREATOR",
    "RAISON_NO_ISBN",
    "RAISON_NO_MATCH",
    "RAISON_OK",
    "RAISON_PAGE_MISMATCH",
    "RAISON_PAS_UN_JEU",
    "RAISON_STEAM_ID_MISMATCH",
    "RAISON_STUDIO_MISMATCH",
    "RAISON_TYPE_UNSUPPORTED",
    "RAISON_UNREADABLE",
    "SOURCE_LIBRAIRE",
    "SOURCE_STEAM",
    "STEAM_FICHE",
    "STEAM_RECHERCHE",
    "TYPES_SERVIS",
    "TYPE_JEU",
    "TYPE_LIVRE",
    "TYPE_STEAM_JEU",
    "USER_AGENT",
    "BoutiqueInjoignable",
    "Cas",
    "Lien",
    "RapportBoutique",
    "Resolution",
    "Source",
    "appliquer",
    "auteur_correspond",
    "build_parser",
    "candidats_au_bon_titre",
    "deja_servie",
    "documents_corrobores",
    "eans_de_resultats",
    "eans_valides",
    "fiche_demandee",
    "fiche_libraire",
    "format_rapport",
    "hote",
    "isbn_de_page",
    "isbn_google",
    "isbn_libraire",
    "isbn_openlibrary",
    "jsonld_isbn_coherent",
    "main",
    "page_corrobore",
    "page_libraire",
    "rapport_payload",
    "resoudre",
    "resoudre_jeu",
    "resoudre_livre",
    "run",
    "source_pour",
    "steam_candidats",
    "steam_fiche",
    "studio_correspond",
    "studios_de",
    "titres_correspondent",
    "type_servi",
    "url_canonique",
    "url_steam",
    "volume_corrobore",
]


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Pose les liens d'achat des jeux (Steam) et des livres "
                    "(Place des Libraires), uniquement à partir de sources "
                    "interrogées dont la réponse corrobore titre ET "
                    "studio/auteur.")
    p.add_argument("--source", default=None,
                   help="Limiter à une source de recos (défaut : toutes).")
    p.add_argument("--types", default=None,
                   help="Filtrer par types, séparés par des virgules "
                        "(ex. jeu,livre).")
    p.add_argument("--ids", default=None,
                   help="N'enrichir QUE ces ids : « a,b,c » ou « @fichier » "
                        "(un id par ligne).")
    p.add_argument("--limit", type=int, default=None,
                   help="Nombre maximum de recos réellement interrogées.")
    p.add_argument("--apply", action="store_true",
                   help="Écrire les liens trouvés (défaut : simulation).")
    p.add_argument("--jeux-sans-studio", action="store_true",
                   help="Accepte un jeu dont la reco ne nomme pas le studio, "
                        "si UNE seule fiche Steam survit aux garde-fous. "
                        "Opt-in : sans studio, rien ne corrobore le titre, et "
                        "un jeu de société homonyme passerait pour le jeu "
                        "vidéo.")
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
                  apply=args.apply,
                  permettre_sans_studio=args.jeux_sans_studio)

    if args.apply:
        # Écriture : coordination avec review_server (cf. tools/review_lock.py).
        try:
            verrou = acquire_pipeline_lock(force=args.ignore_server_lock)
        except ServerLockBusy as exc:
            log.error("%s", exc)
            return 1
        with verrou:
            rapport = run(**kwargs)
    else:
        log.info("SIMULATION — aucune écriture (ajoute --apply pour écrire).")
        rapport = run(**kwargs)

    log.info("%s", format_rapport(rapport))
    if args.json_path:
        from pathlib import Path
        atomic_write_text(Path(args.json_path),
                          json.dumps(rapport_payload(rapport),
                                     ensure_ascii=False, indent=2) + "\n")
        log.info("Rapport détaillé : %s", args.json_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
