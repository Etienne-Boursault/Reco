"""Résolution d'une reco et déroulé d'une passe complète — vidéo.

La couche qui ORCHESTRE : elle interroge TMDB, soumet les réponses aux
garde-fous d'extraction, écrit les liens retenus et alimente le rapport. Elle
ne décide d'aucun appariement elle-même — cette responsabilité appartient à
`video_links_matching`.

Extraite de `enrich_video_links.py` (cf. `video_links_matching`).
"""
from __future__ import annotations

import time
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any

import requests

from common import (
    log,
    read_json,
    write_json_if_changed,
)

# Les garde-fous de recherche par titre sont CALIBRÉS SUR MESURE RÉELLE dans
# `enrich_creators` (cf. `obscurity_verdict`). On les importe : en écrire
# d'autres reviendrait à recalibrer à l'aveugle.
from enrich_creators import (
    TMDB_BASE,
    any_title_matches,
    exact_title_candidates,
    fetch_tmdb_search,
    get_json,
    iter_reco_paths,
    obscurity_verdict,
    popularity,
    release_is_plausible,
    remote_titles,
    remote_year,
    search_kind,
    year_matches,
)
from enrichment.field_refresher import EnrichedAtCorruptedError, partial_update
from enrichment.tracker import now_iso
from video_links_matching import (
    _VIDEO_TYPES,
    ALL_SITES,
    POPULATION_ID,
    POPULATION_SEARCH,
    RATE_LIMIT_SLEEP,
    REASON_EXCLUDED,
    REASON_FILLED,
    REASON_HTTP_ERROR,
    REASON_NO_API_KEY,
    REASON_NO_NEW_LINK,
    REASON_NOT_VALIDATED,
    REASON_RELEASED_AFTER_EPISODE,
    REASON_SEARCH_AMBIGUOUS,
    REASON_SEARCH_NO_MATCH,
    REASON_SEARCH_UNDATED,
    REASON_TITLE_MISMATCH,
    REASON_UNREADABLE,
    REASON_YEAR_MISMATCH,
    STRATEGY_TMDB_ID,
    Resolution,
    candidate_links,
    merge_links,
    missing_links,
    plan,
)
from video_links_report import Report


def fetch_tmdb_detail(session: requests.Session, kind: str, tmdb_id: str,
                      *, api_key: str) -> dict[str, Any] | None:
    """Fiche TMDB + identifiants externes + offres FR, en UN SEUL appel.

    `append_to_response` ramène aussi le titre et l'année distants, sans quoi
    les garde-fous ne pourraient pas s'exercer.
    """
    return get_json(session, f"{TMDB_BASE}/{kind}/{tmdb_id}",
                    {"api_key": api_key, "language": "fr-FR",
                     "append_to_response": "external_ids,watch/providers"})

def _links_from_detail(reco: dict[str, Any], payload: dict[str, Any] | None, *,
                       kind: str, tmdb_id: str, source: str, population: str,
                       episode_year: int | None,
                       sites: Sequence[str]) -> Resolution:
    """Garde-fous (titre, années) puis extraction des liens fondés."""
    if payload is None:
        return Resolution((), REASON_HTTP_ERROR, source, population)

    titles = remote_titles(payload)
    if titles and not any_title_matches(reco.get("title"), titles):
        return Resolution((), REASON_TITLE_MISMATCH, source, population,
                          detail=f"TMDB répond « {titles[0]} »")
    api_year = remote_year(payload)
    if not year_matches(reco.get("year"), api_year):
        return Resolution((), REASON_YEAR_MISMATCH, source, population,
                          detail=f"reco {reco.get('year')} vs TMDB {api_year}")
    if not release_is_plausible(episode_year, api_year):
        return Resolution((), REASON_RELEASED_AFTER_EPISODE, source, population,
                          detail=f"sortie {api_year} > épisode {episode_year}")

    fresh = missing_links(reco, candidate_links(payload, kind=kind,
                                                tmdb_id=tmdb_id, sites=sites))
    if not fresh:
        return Resolution((), REASON_NO_NEW_LINK, source, population)
    return Resolution(tuple(fresh), REASON_FILLED, source, population)


def _resolve_from_id(reco: dict[str, Any], session: requests.Session, *,
                     api_key: str, episode_year: int | None,
                     sites: Sequence[str]) -> Resolution:
    """Population sûre : l'identifiant TMDB est déjà dans la reco.

    « Sûre » ne veut pas dire « crue » — l'id a été posé automatiquement par
    recherche de titre, donc le titre distant est re-vérifié comme ailleurs.
    """
    ext = reco.get("externalIds") or {}
    kind, tmdb_id = ext["tmdbType"], str(ext["tmdb"])
    payload = fetch_tmdb_detail(session, kind, tmdb_id, api_key=api_key)
    return _links_from_detail(reco, payload, kind=kind, tmdb_id=tmdb_id,
                              source=f"tmdb:{kind}/{tmdb_id}",
                              population=POPULATION_ID,
                              episode_year=episode_year, sites=sites)


def _resolve_from_search(reco: dict[str, Any], session: requests.Session, *,
                         api_key: str, episode_year: int | None,
                         sites: Sequence[str]) -> Resolution:
    """Population à relire : aucun id, on recherche par titre.

    Les trois filtres sont ceux d'`enrich_creators._resolve_tmdb_search`, dans
    le même ordre et avec les mêmes seuils : titre strictement égal, année et
    antériorité, puis unicité. Rien n'est recalibré ici.
    """
    kind = search_kind(reco)
    source = f"tmdb-search:{kind}"
    payload = fetch_tmdb_search(session, kind, reco.get("title") or "",
                                api_key=api_key, year=reco.get("year"))
    if payload is None:
        return Resolution((), REASON_HTTP_ERROR, source, POPULATION_SEARCH)

    results = payload.get("results") or []
    candidates = [
        c for c in exact_title_candidates(reco.get("title"), results)
        if year_matches(reco.get("year"), remote_year(c))
        and release_is_plausible(episode_year, remote_year(c))
    ]
    if not candidates:
        return Resolution((), REASON_SEARCH_NO_MATCH, source, POPULATION_SEARCH)

    ids = sorted({str(c["id"]) for c in candidates})
    if len(ids) > 1:
        return Resolution((), REASON_SEARCH_AMBIGUOUS, source, POPULATION_SEARCH,
                          detail=f"{len(ids)} œuvres au même titre : "
                                 f"{', '.join(ids[:5])}")

    # Une fiche SANS date n'a franchi aucune des deux gardes d'année : toutes
    # deux passent quand la date manque. L'identité ne tiendrait alors qu'au
    # titre — et un titre suffit rarement (« Definition », jeu télévisé
    # canadien de 1974, contre « Définition », série stand-up française).
    if remote_year(candidates[0]) is None:
        return Resolution((), REASON_SEARCH_UNDATED, source, POPULATION_SEARCH,
                          detail="fiche TMDB sans date de sortie")

    refus = obscurity_verdict(candidates[0], results)
    if refus:
        return Resolution((), refus, source, POPULATION_SEARCH,
                          detail=f"popularité {popularity(candidates[0]):.2f}")

    tmdb_id = ids[0]
    payload = fetch_tmdb_detail(session, kind, tmdb_id, api_key=api_key)
    return _links_from_detail(reco, payload, kind=kind, tmdb_id=tmdb_id,
                              source=f"tmdb:{kind}/{tmdb_id}",
                              population=POPULATION_SEARCH,
                              episode_year=episode_year, sites=sites)


def resolve_video_links(reco: dict[str, Any], *, session: requests.Session,
                        api_key: str | None, episode_year: int | None = None,
                        allow_search: bool = False,
                        sites: Sequence[str] = ALL_SITES) -> Resolution:
    """Tente de déterminer les fiches d'une reco. Ne modifie RIEN."""
    chosen = plan(reco, allow_search=allow_search)
    if chosen.strategy is None:
        return Resolution((), chosen.reason, None, chosen.population)
    if not api_key:
        return Resolution((), REASON_NO_API_KEY, None, chosen.population)

    if chosen.strategy == STRATEGY_TMDB_ID:
        return _resolve_from_id(reco, session, api_key=api_key,
                                episode_year=episode_year, sites=sites)
    return _resolve_from_search(reco, session, api_key=api_key,
                                episode_year=episode_year, sites=sites)


# ===========================================================================
# Écriture
# ===========================================================================
def apply_video_links(reco: dict[str, Any], links: Sequence[dict[str, Any]],
                      *, timestamp: str | None = None) -> dict[str, Any]:
    """Ajoute `links` à la fin de `reco["links"]` + audit trail, IN-PLACE."""
    return partial_update(reco, "links", merge_links(reco, links),
                          timestamp=timestamp or now_iso())

def run(*, root: Path, session: requests.Session | None, api_key: str | None,
        source: str | None = None, limit: int | None = None,
        apply: bool = False, exclude_ids: Iterable[str] = (),
        episode_years: dict[str, int] | None = None,
        allow_search: bool = False, sites: Sequence[str] = ALL_SITES,
        sleep: float = RATE_LIMIT_SLEEP) -> Report:
    """Passe complète : sélectionne, résout, journalise, écrit si `apply`."""
    excluded = set(exclude_ids)
    report = Report()
    resolved = 0

    for path in iter_reco_paths(root, source):
        try:
            reco = read_json(path)
        except (ValueError, OSError) as exc:
            log.warning("  %s illisible (%s) — ignoré", path.name, exc)
            report.skipped[REASON_UNREADABLE] += 1
            continue

        if not any(t in _VIDEO_TYPES for t in reco.get("types") or []):
            continue
        reco_id = reco.get("id", path.stem)

        # `seen` compte le PÉRIMÈTRE réel : une reco écartée par la relecture
        # humaine n'a pas à peser sur les taux du rapport.
        if reco.get("status") != "validated":
            report.skipped[REASON_NOT_VALIDATED] += 1
            continue
        report.seen += 1
        if reco_id in excluded:
            log.info("  %s · exclu (revue humaine)", reco_id)
            report.record(reco, Resolution((), REASON_EXCLUDED, None), path, 0)
            continue
        if limit is not None and resolved >= limit:
            continue

        resolution = resolve_video_links(
            reco, session=session, api_key=api_key,
            episode_year=(episode_years or {}).get(reco.get("episodeGuid")),
            allow_search=allow_search, sites=sites)
        resolved += 1
        _log_resolution(reco_id, reco, resolution)
        total_after = len(merge_links(reco, resolution.links))
        report.record(reco, resolution, path, total_after)

        if resolution.links and apply:
            try:
                apply_video_links(reco, resolution.links)
            except EnrichedAtCorruptedError as exc:
                log.error("  %s · audit trail corrompu (%s) — non écrit",
                          reco_id, exc)
                continue
            if write_json_if_changed(path, reco):
                report.written += 1
        if sleep:
            time.sleep(sleep)

    return report


def _log_resolution(reco_id: str, reco: dict[str, Any],
                    resolution: Resolution) -> None:
    """Une ligne par reco : liens posés (source) ou raison du refus."""
    title = (reco.get("title") or "")[:45]
    if resolution.links:
        labels = ", ".join(link["label"] for link in resolution.links)
        log.info("  %s · %s [%s] → %s (%s)", reco_id, title,
                 resolution.population, labels, resolution.source)
    else:
        detail = f" — {resolution.detail}" if resolution.detail else ""
        log.info("  %s · %s [%s] → rien : %s%s", reco_id, title,
                 resolution.population, resolution.reason, detail)
