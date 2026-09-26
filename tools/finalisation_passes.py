"""
finalisation_passes.py — les passes d'enrichissement que la chaîne déroule
après la relecture, et RIEN d'autre : chacune n'est qu'un adaptateur vers un
outil existant, limité aux recos de l'épisode par son option `--ids`.

Sorti de `traiter_nouveaux_episodes.py` le 2026-09-26 (règle des 500 lignes) :
la troisième passe faisait déborder le fichier. Les regrouper ici a un second
mérite — l'ORDRE dans lequel elles tournent devient lisible d'un coup d'œil, or
il n'est pas indifférent (cf. `fiches_video`).

Aucune de ces passes n'invente une URL : chaque outil exige qu'une API
corrobore ce qu'il écrit. Les recos qu'aucun outil ne sait servir restent dans
la liste du reste à faire, envoyée à l'éditeur.
"""
from __future__ import annotations

from typing import Any

import common


def liens_musicaux(source_id: str, ids: set[str]) -> Any:
    """Liens d'écoute (Deezer, Apple, Spotify, Qobuz) des recos de l'épisode.

    Aucune invention : l'outil n'écrit une URL que si la plateforme corrobore le
    titre ET l'artiste (cf. enrich_music_links). Les types `artiste` sont
    ouverts, mais leurs homonymes finissent en « ambiguous » — donc dans la
    liste du reste à faire, pas dans le corpus.
    """
    import requests

    from music_links_pipeline import run as run_links
    return run_links(root=common.RECOS_DIR, session=requests.Session(),
                     source=source_id, ids=ids, apply=True, allow_artists=True)


def fiches_tmdb(source_id: str, ids: set[str]) -> Any:
    """« Où regarder » et identifiants TMDB des recos film/série de l'épisode.

    L'outil musical ne connaît que les plateformes d'écoute : les films et
    séries restaient dans la liste du reste à faire alors que TMDB sait les
    servir (mesuré sur S6-E02 : 2 films et 2 séries sur 12 restes). Ce qu'elle
    écrit, ce sont les `watchProviders` et les identifiants TMDB, jamais une URL
    devinée.
    """
    from enrich_tmdb import cle_api
    from enrich_tmdb import run as run_tmdb
    return run_tmdb(source=source_id, api_key=cle_api(), ids=ids, apply=True)


def fiches_video(source_id: str, ids: set[str]) -> Any:
    """Fiches de référence IMDb et TMDB des recos film/série de l'épisode.

    Passe APRÈS `fiches_tmdb`, qui vient de poser `externalIds.tmdb` : cet
    outil traite alors la population « id-existant », un seul appel par reco et
    aucune recherche par titre. C'est pourquoi `allow_search` reste à False —
    la recherche par titre est le seul endroit où cet outil peut se tromper, et
    la chaîne n'en a pas besoin. Les recos que TMDB n'a pas identifiées restent
    dans la liste du reste à faire.

    JustWatch est prévu par l'outil mais sa source est tarie depuis le
    2026-07-31 (TMDB ne rend plus d'URL justwatch.com) : en pratique, deux
    fiches par reco, IMDb et TMDB.
    """
    import requests

    from enrich_creators import load_episode_years
    from enrich_tmdb import cle_api
    from video_links_pipeline import run as run_video
    return run_video(
        root=common.RECOS_DIR, session=requests.Session(), api_key=cle_api(),
        source=source_id, ids=ids, apply=True,
        episode_years=load_episode_years(common.EPISODES_DIR, source_id))
