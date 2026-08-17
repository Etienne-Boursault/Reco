"""
enrich_music_links.py — Pose les liens d'écoute (`links`) des recos musicales
à partir d'APIs interrogées, et UNIQUEMENT à partir d'elles.

RÈGLE FONDATRICE — ZÉRO INVENTION
---------------------------------
Une URL n'est écrite que si elle a été RENVOYÉE par une API dont la réponse
corrobore à la fois le TITRE et l'ARTISTE. Jamais d'URL fabriquée à partir
d'un titre, jamais de « premier résultat » retenu par défaut. Au moindre
doute → aucun lien, avec une raison traçable dans le rapport.

Ce dépôt s'est déjà fait piéger deux fois par la recherche par titre seul :
« Amélie » ramène un homonyme obscur (l'API en propose trois, tous faux),
« Suzane de Sagazan » ramenait un morceau sans rapport. D'où le garde-fou
central de ce module, plus sévère que celui d'`enrich_creators` :

    en musique, le titre seul ne prouve RIEN.

Un titre de morceau ou d'album n'identifie une œuvre qu'associé à son
artiste. Les recos dépourvues de `creator` sont donc refusées d'office
(`no-creator-to-verify`) : il n'y a rien contre quoi vérifier.

SOURCES
-------
  - **Deezer** — API publique, sans clé. `/search/{track,album,artist}` puis
    `/{kind}/{id}` pour re-vérifier un identifiant déjà stocké. La réponse
    porte `title`, `artist.name` et `album.title` : de quoi corroborer.
  - **Apple Music** — API iTunes Search, publique, sans clé. Second avis
    INDÉPENDANT de Deezer, et seule façon d'homogénéiser vers `music.apple.com`.

  - **Spotify** — NON UTILISÉ. Les identifiants de `tools/.env` sont valides
    (le token Client Credentials s'obtient en HTTP 200) mais TOUS les endpoints
    répondent 403 « Active premium subscription required for the owner of the
    app » (politique Spotify 2025). Bâtir dessus produirait du code mort. Le
    jour où le compte repasse Premium, la stratégie s'ajoute ici.

STRATÉGIES (choisies par `plan()`)
----------------------------------
  - `promote-deezer-id` : la reco porte déjà un `externalIds.deezer` mais aucun
    lien Deezer VISIBLE. L'identifiant est re-téléchargé et repasse par tous
    les garde-fous avant d'être promu en lien. Ces identifiants ont été posés
    par l'ancien `enrich_music.py`, qui retenait le premier résultat sans rien
    vérifier : ce ne sont PAS des données certifiées.
  - `search-album`  : type `album`   → `/search/album`, cible = la page album.
  - `search-track`  : type `musique` → `/search/track`, cible = le morceau.
  - `search-artist` : type `artiste` → `/search/artist`, cible = la page
    ARTISTE (jamais un morceau). **Opt-in `--artists`** — cf. ci-dessous.

POURQUOI `artiste` EST OPT-IN
-----------------------------
Mesure du 2026-07-31 sur les 275 recos musicales actives : 155 portent le type
`artiste` SEUL, et l'immense majorité ne sont pas des musiciens — ce sont des
humoristes, acteurs et réalisateurs (Vérino, Paul Mirabel, Ricky Gervais,
Takeshi Kitano, Truffaut, Richard Linklater…), le type `artiste` désignant ici
l'artiste au sens large. Les leur chercher une page d'écoute revient à demander
à Deezer de trouver un musicien nommé « Truffaut » — et Deezer en trouvera un.
Le type `artiste` seul n'est donc PAS une preuve de caractère musical : sans
`--artists`, ces recos sont refusées (`artist-type-unproven`).

GARDE-FOUS (toute violation ⇒ aucun lien)
-----------------------------------------
  1. `no-creator-to-verify` : pas de `creator` → rien contre quoi corroborer.
  2. `title-mismatch`  : le titre distant ne correspond pas à celui de la reco.
  3. `artist-mismatch` : l'artiste distant ne correspond pas au `creator`.
  4. `ambiguous`       : plusieurs candidats distincts survivent aux filtres →
     arbitrage humain, on ne tranche pas.
  5. `no-match`        : aucun candidat ne passe.

Usage :
    python enrich_music_links.py                     # dry-run, tout
    python enrich_music_links.py --types album
    python enrich_music_links.py --artists           # ouvre le type `artiste`
    python enrich_music_links.py --json rapport.json
    python enrich_music_links.py --apply             # écrit (prend le verrou)

Écriture : AJOUT dans `links` + audit trail `enrichedAt["links"]`, via
`common.write_json_if_changed` (atomique + idempotent). Un lien déjà présent
sur une plateforme n'est JAMAIS écrasé ni dupliqué.

INTERFACE EN LIGNE DE COMMANDE ET FAÇADE
----------------------------------------
Le travail lui-même est réparti en quatre modules — ce fichier en réunissait
quatre responsabilités et dépassait 500 lignes :

    music_links_matching  décide SI un candidat correspond (aucun réseau)
    music_links_clients   interroge Deezer et iTunes
    music_links_pipeline  résout une reco, écrit, déroule la passe
    music_links_report    compte, classe, met en forme

Tout est RÉ-EXPORTÉ ici : `enrich_music_links` reste la façade publique de
l'outil, et ni les tests ni les scripts n'ont à connaître ce découpage.
"""
from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

import requests

from common import RECOS_DIR, atomic_write_text, log
from music_links_clients import (
    _ITUNES_URL_FIELD,
    ITUNES_ENTITY,
    deezer_by_id,
    deezer_candidate,
    deezer_search,
    get_json,
    itunes_candidate,
    itunes_search,
    search_query,
)
from music_links_matching import (
    _RE_DEEZER_URL,
    _SEARCH_STRATEGY,
    AMBIGUOUS_REASONS,
    ARTIST_MATCH_THRESHOLD,
    DEEZER_BASE,
    HTTP_TIMEOUT,
    HTTP_TOO_MANY_REQUESTS,
    ITUNES_BASE,
    KNOWN_LISTENING_HOSTS,
    LINK_ETHICS,
    LINK_KIND,
    PLATFORM_APPLE,
    PLATFORM_DEEZER,
    PLATFORMS,
    RATE_LIMIT_SLEEP,
    REASON_ALREADY_COMPLETE,
    REASON_AMBIGUOUS,
    REASON_ARTIST_MISMATCH,
    REASON_ARTIST_TYPE_UNPROVEN,
    REASON_BAD_DEEZER_URL,
    REASON_EXCLUDED,
    REASON_HTTP_ERROR,
    REASON_LINKED,
    REASON_NO_CREATOR,
    REASON_NO_MATCH,
    REASON_NOT_VALIDATED,
    REASON_STORED_KIND_MISMATCH,
    REASON_TITLE_MISMATCH,
    REASON_TYPE_UNSUPPORTED,
    REASON_UNREADABLE,
    RETRY_AFTER_SLEEP,
    SEARCH_LIMIT,
    STRATEGY_PROMOTE_DEEZER_ID,
    STRATEGY_SEARCH_ALBUM,
    STRATEGY_SEARCH_ARTIST,
    STRATEGY_SEARCH_TRACK,
    STRONG_MUSIC_TYPES,
    SUPPORTED_TYPES,
    TYPE_ALBUM,
    TYPE_ARTISTE,
    TYPE_MUSIQUE,
    Candidate,
    MusicLink,
    Plan,
    RecoOutcome,
    Resolution,
    _first_detail,
    artist_matches_creator,
    content_kind,
    creator_names,
    existing_hosts,
    has_any_listening_link,
    link_host,
    missing_platforms,
    names_match,
    parse_deezer_url,
    plan,
    primary_type,
    titles_match_strict,
    verdict,
)
from music_links_pipeline import (
    _collect,
    _log_outcome,
    _resolve_promote_deezer,
    _resolve_search,
    apply_links_to_reco,
    iter_reco_paths,
    parse_exclude_ids,
    resolve_reco,
    run,
)
from music_links_report import (
    LinkedCase,
    Report,
    ReviewCase,
    format_report,
    report_payload,
)
from review_lock import ServerLockBusy, acquire_pipeline_lock

#: Façade publique. Ce `__all__` n'est pas décoratif : sans lui, `ruff --fix`
#: prend les ré-exports pour des imports inutilisés et les SUPPRIME — ce qui
#: est arrivé, et a cassé la collecte des tests d'un coup.
__all__ = [
    "AMBIGUOUS_REASONS",
    "ARTIST_MATCH_THRESHOLD",
    "DEEZER_BASE",
    "HTTP_TIMEOUT",
    "HTTP_TOO_MANY_REQUESTS",
    "ITUNES_BASE",
    "ITUNES_ENTITY",
    "KNOWN_LISTENING_HOSTS",
    "LINK_ETHICS",
    "LINK_KIND",
    "PLATFORMS",
    "PLATFORM_APPLE",
    "PLATFORM_DEEZER",
    "RATE_LIMIT_SLEEP",
    "REASON_ALREADY_COMPLETE",
    "REASON_AMBIGUOUS",
    "REASON_ARTIST_MISMATCH",
    "REASON_ARTIST_TYPE_UNPROVEN",
    "REASON_BAD_DEEZER_URL",
    "REASON_EXCLUDED",
    "REASON_HTTP_ERROR",
    "REASON_LINKED",
    "REASON_NOT_VALIDATED",
    "REASON_NO_CREATOR",
    "REASON_NO_MATCH",
    "REASON_STORED_KIND_MISMATCH",
    "REASON_TITLE_MISMATCH",
    "REASON_TYPE_UNSUPPORTED",
    "REASON_UNREADABLE",
    "RETRY_AFTER_SLEEP",
    "SEARCH_LIMIT",
    "STRATEGY_PROMOTE_DEEZER_ID",
    "STRATEGY_SEARCH_ALBUM",
    "STRATEGY_SEARCH_ARTIST",
    "STRATEGY_SEARCH_TRACK",
    "STRONG_MUSIC_TYPES",
    "SUPPORTED_TYPES",
    "TYPE_ALBUM",
    "TYPE_ARTISTE",
    "TYPE_MUSIQUE",
    "_ITUNES_URL_FIELD",
    "_RE_DEEZER_URL",
    "_SEARCH_STRATEGY",
    "Candidate",
    "LinkedCase",
    "MusicLink",
    "Plan",
    "RecoOutcome",
    "Report",
    "Resolution",
    "ReviewCase",
    "_collect",
    "_first_detail",
    "_log_outcome",
    "_resolve_promote_deezer",
    "_resolve_search",
    "apply_links_to_reco",
    "artist_matches_creator",
    "build_parser",
    "content_kind",
    "creator_names",
    "deezer_by_id",
    "deezer_candidate",
    "deezer_search",
    "existing_hosts",
    "format_report",
    "get_json",
    "has_any_listening_link",
    "iter_reco_paths",
    "itunes_candidate",
    "itunes_search",
    "link_host",
    "main",
    "missing_platforms",
    "names_match",
    "parse_deezer_url",
    "parse_exclude_ids",
    "plan",
    "primary_type",
    "report_payload",
    "resolve_reco",
    "run",
    "search_query",
    "titles_match_strict",
    "verdict",
]

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Pose les liens d'écoute (Deezer, Apple Music) des recos "
                    "musicales, uniquement à partir d'APIs interrogées dont la "
                    "réponse corrobore titre ET artiste.")
    p.add_argument("--source", default=None,
                   help="Limiter à une source (défaut : toutes).")
    p.add_argument("--types", default=None,
                   help="Filtrer par types, séparés par des virgules "
                        "(ex. album,musique).")
    p.add_argument("--limit", type=int, default=None,
                   help="Nombre maximum de recos réellement interrogées.")
    p.add_argument("--apply", action="store_true",
                   help="Écrire les liens trouvés (défaut : dry-run).")
    p.add_argument("--artists", action="store_true",
                   help="Ouvre le type `artiste` seul. Opt-in : ce type "
                        "désigne aussi des humoristes, acteurs et "
                        "réalisateurs, pour qui une page d'écoute n'a pas de "
                        "sens et dont l'API renverra un homonyme.")
    p.add_argument("--only-missing", action="store_true",
                   help="Ne traiter que les recos sans AUCUN lien d'écoute.")
    p.add_argument("--exclude-ids", default=None,
                   help="Ids à ne PAS enrichir : « a,b,c » ou « @fichier ».")
    p.add_argument("--json", dest="json_path", default=None,
                   help="Écrit le rapport détaillé (JSON) à ce chemin.")
    p.add_argument("--ignore-server-lock", action="store_true",
                   help="Ignore le verrou review_server (écritures "
                        "concurrentes possibles).")
    return p


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    types = tuple(t.strip() for t in args.types.split(",")) if args.types else None
    kwargs = dict(
        root=RECOS_DIR, session=requests.Session(), source=args.source,
        types=types, limit=args.limit, apply=args.apply,
        exclude_ids=parse_exclude_ids(args.exclude_ids),
        allow_artists=args.artists, only_missing=args.only_missing,
    )

    if args.apply:
        # Écriture : coordination avec review_server (cf. tools/review_lock.py).
        try:
            lock = acquire_pipeline_lock(force=args.ignore_server_lock)
        except ServerLockBusy as exc:
            log.error("%s", exc)
            return 1
        with lock:
            report = run(**kwargs)
    else:
        log.info("DRY-RUN — aucune écriture (ajoute --apply pour écrire).")
        report = run(**kwargs)

    log.info("%s", format_report(report))
    if args.json_path:
        import json as _json
        atomic_write_text(Path(args.json_path),
                          _json.dumps(report_payload(report),
                                      ensure_ascii=False, indent=2) + "\n")
        log.info("Rapport détaillé : %s", args.json_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
