"""Résolution d'une reco et déroulé d'une passe complète.

C'est la couche qui ORCHESTRE : elle appelle les clients, soumet leurs réponses
aux garde-fous d'appariement, écrit les liens retenus et alimente le rapport.
Elle ne décide d'aucun appariement elle-même — cette responsabilité appartient
à `music_links_matching`, et les mélanger rendrait l'une comme l'autre
impossibles à éprouver isolément.

Extraite de `enrich_music_links.py` (cf. `music_links_matching`).
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
from enrichment.field_refresher import EnrichedAtCorruptedError, partial_update
from enrichment.tracker import now_iso
from music_links_clients import (
    ITUNES_ENTITY,
    deezer_by_id,
    deezer_candidate,
    deezer_search,
    itunes_candidate,
    itunes_search,
    search_query,
)
from music_links_matching import (
    PLATFORM_DEEZER,
    PLATFORMS,
    RATE_LIMIT_SLEEP,
    REASON_ALREADY_COMPLETE,
    REASON_BAD_DEEZER_URL,
    REASON_EXCLUDED,
    REASON_HTTP_ERROR,
    REASON_LINKED,
    REASON_NO_CREATOR,
    REASON_NO_MATCH,
    REASON_NOT_VALIDATED,
    REASON_STORED_KIND_MISMATCH,
    REASON_UNREADABLE,
    STRATEGY_PROMOTE_DEEZER_ID,
    SUPPORTED_TYPES,
    MusicLink,
    RecoOutcome,
    Resolution,
    creator_names,
    has_any_listening_link,
    link_host,
    missing_platforms,
    parse_deezer_url,
    plan,
    verdict,
)
from music_links_report import Report


def _resolve_search(reco: dict[str, Any], session: requests.Session,
                    *, platform: str, kind: str) -> Resolution:
    """Recherche sur une plateforme, puis garde-fous."""
    want_artist_page = kind == "artist"
    query = search_query(reco, want_artist_page=want_artist_page)

    if platform == PLATFORM_DEEZER:
        raw = deezer_search(session, kind, query)
        candidates = [c for c in (deezer_candidate(p, kind) for p in raw) if c]
    else:
        raw = itunes_search(session, ITUNES_ENTITY[kind], query)
        candidates = [c for c in (itunes_candidate(p, kind) for p in raw) if c]

    chosen, reason, detail = verdict(reco, candidates,
                                     want_artist_page=want_artist_page)
    if chosen is None:
        return Resolution(None, reason, detail)
    return Resolution(
        MusicLink(platform, PLATFORMS[platform]["label"], chosen.url,
                  f"{platform}:{kind}/{chosen.ident or '?'}"),
        REASON_LINKED)


def _resolve_promote_deezer(reco: dict[str, Any], session: requests.Session,
                            *, expected_kind: str) -> Resolution:
    """Re-vérifie un `externalIds.deezer` existant avant de le promouvoir.

    L'identifiant a été posé par l'ancien `enrich_music.py`, qui retenait le
    premier résultat sans rien corroborer. Il repasse donc par les garde-fous
    au même titre qu'un candidat de recherche.

    `expected_kind` verrouille la NATURE de la cible : une reco d'album doit
    mener à une page d'album, pas à la page de l'artiste. Un identifiant
    stocké qui ne s'accorde pas au type de la reco est refusé plutôt que
    promu — c'est le signe que l'ancienne passe a rabattu sa recherche sur un
    autre type de contenu, et l'arbitrage revient à l'humain.
    """
    parsed = parse_deezer_url((reco.get("externalIds") or {}).get("deezer"))
    if not parsed:
        return Resolution(None, REASON_BAD_DEEZER_URL)
    kind, deezer_id = parsed
    if kind != expected_kind:
        return Resolution(None, REASON_STORED_KIND_MISMATCH,
                          f"identifiant stocké de type « {kind} » pour une "
                          f"reco qui appelle « {expected_kind} »")
    payload = deezer_by_id(session, kind, deezer_id)
    if payload is None:
        return Resolution(None, REASON_HTTP_ERROR)
    candidate = deezer_candidate(payload, kind)
    if candidate is None:
        return Resolution(None, REASON_NO_MATCH)
    chosen, reason, detail = verdict(reco, [candidate], anchored=True,
                                     want_artist_page=kind == "artist")
    if chosen is None:
        return Resolution(None, reason, detail)
    return Resolution(
        MusicLink(PLATFORM_DEEZER, PLATFORMS[PLATFORM_DEEZER]["label"],
                  chosen.url, f"deezer:{kind}/{deezer_id}"),
        REASON_LINKED)


def resolve_reco(reco: dict[str, Any], *, session: requests.Session,
                 allow_artists: bool = False) -> RecoOutcome:
    """Cherche les liens manquants d'UNE reco. Ne modifie RIEN.

    Chaque plateforme absente est traitée indépendamment : trouver Deezer
    n'empêche pas de chercher Apple Music, c'est même tout l'objet de
    l'homogénéisation.
    """
    chosen = plan(reco, allow_artists=allow_artists)
    if chosen.strategy is None:
        return RecoOutcome((), (), chosen.reason)

    targets = missing_platforms(reco)
    if not targets:
        return RecoOutcome((), (), REASON_ALREADY_COMPLETE)

    # Le titre seul ne prouve rien en musique : sans `creator`, aucune
    # corroboration n'est possible pour un morceau ou un album. Une page
    # ARTISTE fait exception — le titre de la reco EST le nom recherché.
    if chosen.kind != "artist" and not creator_names(reco.get("creator")):
        return RecoOutcome((), (), REASON_NO_CREATOR)

    links: list[MusicLink] = []
    refusals: list[tuple[str, str, str]] = []

    if chosen.strategy == STRATEGY_PROMOTE_DEEZER_ID:
        _collect(PLATFORM_DEEZER,
                 _resolve_promote_deezer(reco, session,
                                         expected_kind=chosen.kind),
                 links, refusals)
        targets = [p for p in targets if p != PLATFORM_DEEZER]

    for platform in targets:
        _collect(platform,
                 _resolve_search(reco, session, platform=platform,
                                 kind=chosen.kind),
                 links, refusals)

    reason = REASON_LINKED if links else refusals[0][1]
    return RecoOutcome(tuple(links), tuple(refusals), reason)


def _collect(platform: str, resolution: Resolution, links: list[MusicLink],
             refusals: list[tuple[str, str, str]]) -> None:
    """Range une résolution du bon côté."""
    if resolution.link is not None:
        links.append(resolution.link)
    else:
        refusals.append((platform, resolution.reason, resolution.detail))


# ===========================================================================
# Écriture
# ===========================================================================
def apply_links_to_reco(reco: dict[str, Any], links: Sequence[MusicLink],
                        *, timestamp: str | None = None) -> dict[str, Any]:
    """AJOUTE les liens à `reco["links"]` + l'audit trail, IN-PLACE.

    Les liens existants sont conservés dans leur ordre ; un lien dont l'hôte
    est déjà présent n'est jamais ajouté (garde-fou de dernier recours, la
    sélection ayant déjà écarté ces plateformes).
    """
    existing = list(reco.get("links") or [])
    hosts = {link_host(str(entry.get("url") or "")) for entry in existing}
    added = [link.as_link() for link in links
             if link_host(link.url) not in hosts]
    if not added:
        return reco
    return partial_update(reco, "links", existing + added,
                          timestamp=timestamp or now_iso())



def iter_reco_paths(root: Path, source: str | None = None) -> list[Path]:
    """Fichiers JSON de recos, triés (toutes sources ou une seule)."""
    base = root / source if source else root
    if not base.is_dir():
        return []
    return sorted(base.glob("*.json") if source else base.glob("*/*.json"))


def parse_exclude_ids(raw: str | None) -> set[str]:
    """`--exclude-ids` : liste CSV, ou `@fichier` (un id par ligne, `#` = commentaire)."""
    if not raw:
        return set()
    if raw.startswith("@"):
        lines = Path(raw[1:]).read_text(encoding="utf-8").splitlines()
        return {ln.strip() for ln in lines if ln.strip() and not ln.startswith("#")}
    return {part.strip() for part in raw.split(",") if part.strip()}


def run(*, root: Path, session: requests.Session | None,
        source: str | None = None, types: Sequence[str] | None = None,
        limit: int | None = None, apply: bool = False,
        exclude_ids: Iterable[str] = (),
        allow_artists: bool = False,
        only_missing: bool = False,
        sleep: float = RATE_LIMIT_SLEEP) -> Report:
    """Passe complète : sélectionne, résout, journalise, écrit si `apply`.

    `only_missing` restreint aux recos DÉPOURVUES de tout lien d'écoute — le
    gisement où le gain est réel, à traiter avant l'homogénéisation.
    """
    excluded = set(exclude_ids)
    wanted = set(types) if types else None
    report = Report()
    resolved = 0

    for path in iter_reco_paths(root, source):
        try:
            reco = read_json(path)
        except (ValueError, OSError) as exc:
            log.warning("  %s illisible (%s) — ignoré", path.name, exc)
            report.reasons[REASON_UNREADABLE] += 1
            continue

        if not any(t in SUPPORTED_TYPES for t in (reco.get("types") or [])):
            continue
        if wanted and not (set(reco.get("types") or []) & wanted):
            continue
        report.seen += 1
        reco_id = str(reco.get("id", path.stem))

        if reco.get("status") != "validated":
            report.record(reco, RecoOutcome((), (), REASON_NOT_VALIDATED))
            continue
        if reco_id in excluded:
            report.record(reco, RecoOutcome((), (), REASON_EXCLUDED))
            continue
        if only_missing and has_any_listening_link(reco):
            report.record(reco, RecoOutcome((), (), REASON_ALREADY_COMPLETE))
            continue
        if limit is not None and resolved >= limit:
            continue

        outcome = resolve_reco(reco, session=session,
                               allow_artists=allow_artists)
        resolved += 1
        _log_outcome(reco_id, reco, outcome)
        report.record(reco, outcome)

        if outcome.links and apply:
            try:
                apply_links_to_reco(reco, outcome.links)
            except EnrichedAtCorruptedError as exc:
                log.error("  %s · audit trail corrompu (%s) — non écrit",
                          reco_id, exc)
                continue
            if write_json_if_changed(path, reco):
                report.written += 1
        if sleep:
            time.sleep(sleep)

    return report


def _log_outcome(reco_id: str, reco: dict[str, Any],
                 outcome: RecoOutcome) -> None:
    """Une ligne par reco : liens posés, ou raison du refus."""
    title = (reco.get("title") or "")[:40]
    creator = (reco.get("creator") or "")[:28]
    if outcome.links:
        for link in outcome.links:
            log.info("  %s · %s — %s → %s (%s)", reco_id, title, creator,
                     link.url, link.source)
    else:
        log.info("  %s · %s — %s → aucun lien : %s", reco_id, title, creator,
                 outcome.reason)
