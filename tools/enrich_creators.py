"""
enrich_creators.py — Remplit le champ `creator` des recos (réalisateur·rice,
auteur·rice, artiste) à partir d'APIs officielles, et UNIQUEMENT à partir
d'elles.

RÈGLE FONDATRICE — ZÉRO INVENTION
---------------------------------
Un `creator` n'est écrit que s'il provient d'une API interrogée via un
IDENTIFIANT EXTERNE déjà présent dans la reco (`externalIds`). On ne cherche
JAMAIS par titre : les homonymes produisent de vraies fausses données (cf.
`reco-audit-coherence-liens`). Au moindre doute → champ laissé vide, avec une
raison traçable dans le rapport.

Stratégies (choisies par `plan()`, dans cet ordre) :
  - `tmdb-movie` : `externalIds.tmdbType == "movie"` → GET
    `/movie/{id}?append_to_response=credits` → crew, `job == "Director"`.
  - `tmdb-tv`    : `externalIds.tmdbType == "tv"` → GET `/tv/{id}` →
    `created_by[].name` (souvent vide pour docu/téléréalité/anime → skip).
  - `deezer`     : `externalIds.deezer` (URL /track/ ou /album/) → GET
    `https://api.deezer.com/{kind}/{id}` → `artist.name`.
  - `openlibrary`: `externalIds.isbn` → GET `/isbn/{isbn}.json` → `authors[]`
    → `/authors/{key}.json` → `name`.

Un seul appel TMDB par reco (`append_to_response=credits`) : il ramène à la
fois les crédits ET le titre distant, indispensable au garde-fou ci-dessous.

GARDE-FOUS (toute violation ⇒ champ laissé vide)
------------------------------------------------
  1. `title-mismatch` : le titre renvoyé par l'API ne correspond pas au titre
     de la reco → l'identifiant externe est faux, donc le créateur le serait
     aussi. (Les `externalIds` ont été posés automatiquement par recherche de
     titre : ils ne sont PAS de l'or certifié.)
  2. `year-mismatch` : l'année de la reco (quand elle existe) contredit
     l'année de sortie distante (tolérance ±1 an, sorties FR décalées).
  3. `creator-equals-title` : le créateur trouvé répète le titre de la reco
     (typiquement une reco d'ARTISTE typée `musique`) → sans valeur, et
     souvent le signe d'un mauvais match.
  4. `no-tmdb-type` : un id TMDB sans `tmdbType` est ambigu (les espaces d'ids
     `movie` et `tv` sont disjoints : 1396 = « Breaking Bad » en tv mais un
     tout autre film en movie) → on refuse de deviner.

Usage :
    python enrich_creators.py                        # dry-run, toutes sources
    python enrich_creators.py --source un-bon-moment --types film,serie
    python enrich_creators.py --json rapport.json    # détail machine
    python enrich_creators.py --apply                # écrit (prend le verrou)
    python enrich_creators.py --apply --exclude-ids @revue-humaine.txt

Écriture : `creator` + audit trail `enrichedAt["creator"]` UNIQUEMENT, via
`common.write_json_if_changed` (atomique + idempotent). Un `creator` déjà
présent n'est JAMAIS écrasé.
"""
from __future__ import annotations

import argparse
import os
import re
import sys
import time
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Iterable, Sequence

import requests
from dotenv import load_dotenv

from common import (
    EPISODES_DIR,
    RECOS_DIR,
    TOOLS_DIR,
    atomic_write_text,
    log,
    normalize_text,
    read_json,
    write_json_if_changed,
)
from enrichment.field_refresher import EnrichedAtCorruptedError, partial_update
from enrichment.tracker import now_iso
from review_lock import ServerLockBusy, acquire_pipeline_lock

# --- Constantes réseau ------------------------------------------------------
TMDB_BASE = "https://api.themoviedb.org/3"
DEEZER_BASE = "https://api.deezer.com"
OPENLIBRARY_BASE = "https://openlibrary.org"
HTTP_TIMEOUT = 15
RATE_LIMIT_SLEEP = 0.1  # 10 req/s — très en dessous des limites TMDB/Deezer.

# --- Garde-fous -------------------------------------------------------------
TITLE_MATCH_THRESHOLD = 0.82
YEAR_TOLERANCE = 1

# --- Stratégies -------------------------------------------------------------
STRATEGY_TMDB_MOVIE = "tmdb-movie"
STRATEGY_TMDB_TV = "tmdb-tv"
STRATEGY_DEEZER = "deezer"
STRATEGY_OPENLIBRARY = "openlibrary"

_VIDEO_TYPES = ("film", "serie")
_MUSIC_TYPES = ("musique", "album")
_BOOK_TYPES = ("livre", "bd")
SUPPORTED_TYPES = _VIDEO_TYPES + _MUSIC_TYPES + _BOOK_TYPES

# --- Raisons (codes stables : servent d'agrégats dans le rapport) -----------
REASON_FILLED = "filled"
REASON_ALREADY_SET = "already-set"
REASON_EXCLUDED = "excluded"
REASON_UNREADABLE = "unreadable-json"
REASON_TYPE_UNSUPPORTED = "type-not-supported"
REASON_NO_EXTERNAL_ID = "no-external-id"
REASON_NO_TMDB_TYPE = "no-tmdb-type"
REASON_NO_API_KEY = "no-tmdb-api-key"
REASON_HTTP_ERROR = "http-error"
REASON_NO_DIRECTOR = "tmdb-no-director"
REASON_NO_CREATED_BY = "tmdb-no-created-by"
REASON_NO_ARTIST = "deezer-no-artist"
REASON_NO_AUTHOR = "openlibrary-no-author"
REASON_TITLE_MISMATCH = "title-mismatch"
REASON_YEAR_MISMATCH = "year-mismatch"
REASON_RELEASED_AFTER_EPISODE = "released-after-episode"
REASON_CREATOR_EQUALS_TITLE = "creator-equals-title"
REASON_DEEZER_ARTIST_URL = "deezer-artist-url"
REASON_DEEZER_BAD_URL = "deezer-unparsable-url"

#: Raisons qui traduisent un DOUTE (donnée distante contradictoire) et non une
#: simple absence de donnée : ces cas méritent un œil humain.
AMBIGUOUS_REASONS = frozenset({
    REASON_TITLE_MISMATCH,
    REASON_YEAR_MISMATCH,
    REASON_RELEASED_AFTER_EPISODE,
    REASON_CREATOR_EQUALS_TITLE,
    REASON_NO_TMDB_TYPE,
    REASON_DEEZER_BAD_URL,
})

_RE_DEEZER = re.compile(
    r"deezer\.com/(?:[a-z]{2}/)?(track|album|artist)/(\d+)", re.IGNORECASE
)
_RE_YEAR = re.compile(r"^(\d{4})")


# ===========================================================================
# Couche PURE — extraction & garde-fous (aucun réseau, aucun disque)
# ===========================================================================
def is_plausible_name(value: str) -> bool:
    """Filtre les entrées polluées des bases distantes.

    TMDB contient de vraies lignes `created_by` avec `name == "0"` (cf.
    tv/93219). Un nom de personne comporte au moins une lettre.
    """
    return any(ch.isalpha() for ch in value)


def join_names(names: Iterable[str | None]) -> str | None:
    """Joint des noms en préservant l'ordre, sans doublon, vide ni parasite."""
    out: list[str] = []
    for name in names:
        clean = (name or "").strip()
        if clean and is_plausible_name(clean) and clean not in out:
            out.append(clean)
    return ", ".join(out) or None


def titles_match(a: str | None, b: str | None,
                 *, threshold: float = TITLE_MATCH_THRESHOLD) -> bool:
    """True si deux titres désignent vraisemblablement la même œuvre.

    Trois voies, de la plus sûre à la plus permissive :
      1. égalité après normalisation (accents, casse, ponctuation) ;
      2. inclusion de MOTS ENTIERS contigus, à condition que le titre le plus
         court compte au moins 2 mots (« White Lotus » ⊂ « The White Lotus »
         oui ; « Mortal » ⊂ « Mortal Kombat » non — trop faible) ;
      3. similarité de séquence ≥ `threshold` (absorbe les variantes de
         translittération : « Colombo » / « Columbo »).
    """
    na, nb = normalize_text(a), normalize_text(b)
    if not na or not nb:
        return False
    if na == nb:
        return True
    short, long_ = sorted((na, nb), key=len)
    short_tokens, long_tokens = short.split(), long_.split()
    if len(short_tokens) >= 2:
        n = len(short_tokens)
        for i in range(len(long_tokens) - n + 1):
            if long_tokens[i:i + n] == short_tokens:
                return True
    return SequenceMatcher(None, na, nb).ratio() >= threshold


def any_title_matches(reco_title: str | None,
                      candidates: Iterable[str | None]) -> bool:
    """True si au moins un titre distant correspond (titre VF *ou* original)."""
    return any(titles_match(reco_title, c) for c in candidates)


def remote_titles(payload: dict[str, Any]) -> list[str]:
    """Titres exposés par un payload TMDB (movie: title/original_title ; tv: name…)."""
    keys = ("title", "original_title", "name", "original_name")
    return [payload[k] for k in keys if payload.get(k)]


def remote_year(payload: dict[str, Any]) -> int | None:
    """Année de sortie TMDB (`release_date` ou `first_air_date`). None si absente."""
    for key in ("release_date", "first_air_date"):
        m = _RE_YEAR.match(str(payload.get(key) or ""))
        if m:
            return int(m.group(1))
    return None


def year_matches(reco_year: int | None, api_year: int | None) -> bool:
    """True si les années sont compatibles (ou si l'une des deux est inconnue)."""
    if not reco_year or not api_year:
        return True
    return abs(reco_year - api_year) <= YEAR_TOLERANCE


def release_is_plausible(episode_year: int | None, api_year: int | None) -> bool:
    """True si l'œuvre pouvait être connue à la date de l'épisode.

    Une œuvre sortie APRÈS l'épisode ne peut pas y avoir été recommandée :
    l'identifiant externe pointe alors vers un homonyme plus récent (cas réel :
    « Mourir seul », épisode de 2021, id TMDB de « Pour Pas Mourir Seul », 2025).
    Tolérance de +1 an pour les anticipations légitimes (festival,
    avant-première, bande-annonce).
    """
    if not episode_year or not api_year:
        return True
    return api_year <= episode_year + YEAR_TOLERANCE


def director_from_movie(payload: dict[str, Any]) -> str | None:
    """Réalisateur·rice(s) d'un film TMDB (`job == "Director"`).

    Accepte les deux formes de payload : `/movie/{id}?append_to_response=credits`
    (crédits sous `credits`) et `/movie/{id}/credits` (crew à la racine).
    """
    credits = payload.get("credits") or payload
    crew = credits.get("crew") or []
    return join_names(c.get("name") for c in crew if c.get("job") == "Director")


def creators_from_tv(payload: dict[str, Any]) -> str | None:
    """Créateur·rice(s) d'une série TMDB (`created_by[].name`)."""
    return join_names(c.get("name") for c in payload.get("created_by") or [])


def parse_deezer_url(url: str | None) -> tuple[str, str] | None:
    """Extrait (kind, id) d'une URL Deezer. None si la forme est inattendue."""
    m = _RE_DEEZER.search(url or "")
    return (m.group(1).lower(), m.group(2)) if m else None


def artist_from_deezer(payload: dict[str, Any]) -> str | None:
    """Nom de l'artiste d'un track/album Deezer."""
    return join_names([(payload.get("artist") or {}).get("name")])


def deezer_titles(payload: dict[str, Any]) -> list[str]:
    """Titres exposés par un payload Deezer (un seul champ : `title`)."""
    return [payload["title"]] if payload.get("title") else []


def author_keys(payload: dict[str, Any]) -> list[str]:
    """Clés d'auteurs d'une édition OpenLibrary (`/authors/OL…A`)."""
    keys: list[str] = []
    for entry in payload.get("authors") or []:
        key = entry.get("key") or (entry.get("author") or {}).get("key")
        if key:
            keys.append(key)
    return keys


def name_from_author_doc(payload: dict[str, Any]) -> str | None:
    """Nom d'un document auteur OpenLibrary."""
    return join_names([payload.get("name")])


@dataclass(frozen=True)
class Plan:
    """Stratégie retenue pour une reco (ou raison du refus)."""

    strategy: str | None
    reason: str = ""


def plan(reco: dict[str, Any]) -> Plan:
    """Choisit la stratégie d'enrichissement, ou explique pourquoi il n'y en a pas."""
    if (reco.get("creator") or "").strip():
        return Plan(None, REASON_ALREADY_SET)

    types = reco.get("types") or []
    ext = reco.get("externalIds") or {}

    if any(t in _VIDEO_TYPES for t in types):
        if not ext.get("tmdb"):
            return Plan(None, REASON_NO_EXTERNAL_ID)
        kind = ext.get("tmdbType")
        if kind == "movie":
            return Plan(STRATEGY_TMDB_MOVIE)
        if kind == "tv":
            return Plan(STRATEGY_TMDB_TV)
        return Plan(None, REASON_NO_TMDB_TYPE)

    if any(t in _MUSIC_TYPES for t in types):
        if not ext.get("deezer"):
            return Plan(None, REASON_NO_EXTERNAL_ID)
        return Plan(STRATEGY_DEEZER)

    if any(t in _BOOK_TYPES for t in types):
        if not ext.get("isbn"):
            return Plan(None, REASON_NO_EXTERNAL_ID)
        return Plan(STRATEGY_OPENLIBRARY)

    return Plan(None, REASON_TYPE_UNSUPPORTED)


def primary_type(reco: dict[str, Any]) -> str:
    """Type retenu pour l'agrégation du rapport (le 1er type traitable, sinon le 1er)."""
    types = reco.get("types") or []
    for t in types:
        if t in SUPPORTED_TYPES:
            return t
    return types[0] if types else "?"


@dataclass(frozen=True)
class Resolution:
    """Résultat d'une tentative d'enrichissement.

    `creator` non-None ⇔ `reason == REASON_FILLED`. `source` trace l'origine
    exacte de la donnée (ex. `tmdb:movie/597`) ; `detail` porte l'information
    de diagnostic destinée au rapport (titre distant contradictoire…).
    """

    creator: str | None
    reason: str
    source: str | None
    detail: str = ""


# ===========================================================================
# Couche RÉSEAU — clients mockables
# ===========================================================================
def get_json(session: requests.Session, url: str,
             params: dict[str, Any] | None = None) -> dict[str, Any] | None:
    """GET → dict JSON, ou None en cas d'erreur réseau/HTTP/parse.

    Ne journalise pas les `params` (ils portent la clé API TMDB).
    """
    try:
        resp = session.get(url, params=params, timeout=HTTP_TIMEOUT)
    except requests.RequestException as exc:
        log.error("  HTTP %s : %s", url, exc)
        return None
    if resp.status_code != 200:
        log.error("  %s → HTTP %s", url, resp.status_code)
        return None
    try:
        data = resp.json()
    except ValueError:
        log.error("  %s → réponse non-JSON", url)
        return None
    return data if isinstance(data, dict) else None


def fetch_tmdb_movie(session: requests.Session, tmdb_id: str,
                     *, api_key: str) -> dict[str, Any] | None:
    """Fiche film TMDB + crédits en UN appel."""
    return get_json(session, f"{TMDB_BASE}/movie/{tmdb_id}",
                    {"api_key": api_key, "language": "fr-FR",
                     "append_to_response": "credits"})


def fetch_tmdb_tv(session: requests.Session, tmdb_id: str,
                  *, api_key: str) -> dict[str, Any] | None:
    """Fiche série TMDB (contient déjà `created_by`)."""
    return get_json(session, f"{TMDB_BASE}/tv/{tmdb_id}",
                    {"api_key": api_key, "language": "fr-FR"})


def fetch_deezer(session: requests.Session, kind: str,
                 deezer_id: str) -> dict[str, Any] | None:
    """Fiche Deezer (track/album). None si l'API signale une erreur.

    Deezer répond HTTP 200 avec `{"error": …}` pour un id inexistant — d'où
    le contrôle explicite.
    """
    data = get_json(session, f"{DEEZER_BASE}/{kind}/{deezer_id}")
    if not data or data.get("error"):
        return None
    return data


def fetch_openlibrary_edition(session: requests.Session,
                              isbn: str) -> dict[str, Any] | None:
    """Édition OpenLibrary par ISBN."""
    return get_json(session, f"{OPENLIBRARY_BASE}/isbn/{isbn}.json")


def fetch_openlibrary_author(session: requests.Session,
                             key: str) -> dict[str, Any] | None:
    """Document auteur OpenLibrary (`key` = `/authors/OL…A`)."""
    return get_json(session, f"{OPENLIBRARY_BASE}{key}.json")


# ===========================================================================
# Résolution (orchestration d'UNE reco)
# ===========================================================================
def _tmdb_resolution(reco: dict[str, Any], payload: dict[str, Any] | None,
                     *, source: str, extractor, empty_reason: str,
                     episode_year: int | None = None) -> Resolution:
    """Garde-fous communs aux deux branches TMDB (titre, année) puis extraction."""
    if payload is None:
        return Resolution(None, REASON_HTTP_ERROR, source)
    titles = remote_titles(payload)
    if titles and not any_title_matches(reco.get("title"), titles):
        return Resolution(None, REASON_TITLE_MISMATCH, source,
                          detail=f"TMDB répond « {titles[0]} »")
    api_year = remote_year(payload)
    if not year_matches(reco.get("year"), api_year):
        return Resolution(None, REASON_YEAR_MISMATCH, source,
                          detail=f"reco {reco.get('year')} vs TMDB {api_year}")
    if not release_is_plausible(episode_year, api_year):
        return Resolution(None, REASON_RELEASED_AFTER_EPISODE, source,
                          detail=f"sortie {api_year} > épisode {episode_year}")
    creator = extractor(payload)
    if not creator:
        return Resolution(None, empty_reason, source)
    return Resolution(creator, REASON_FILLED, source)


def _resolve_deezer(reco: dict[str, Any], session: requests.Session) -> Resolution:
    parsed = parse_deezer_url((reco.get("externalIds") or {}).get("deezer"))
    if not parsed:
        return Resolution(None, REASON_DEEZER_BAD_URL, None)
    kind, deezer_id = parsed
    if kind == "artist":
        # Le lien pointe sur l'artiste : le « créateur » serait l'œuvre
        # elle-même (reco d'artiste). Rien à en tirer.
        return Resolution(None, REASON_DEEZER_ARTIST_URL, f"deezer:artist/{deezer_id}")
    source = f"deezer:{kind}/{deezer_id}"
    payload = fetch_deezer(session, kind, deezer_id)
    if payload is None:
        return Resolution(None, REASON_HTTP_ERROR, source)
    titles = deezer_titles(payload)
    if titles and not any_title_matches(reco.get("title"), titles):
        return Resolution(None, REASON_TITLE_MISMATCH, source,
                          detail=f"Deezer répond « {titles[0]} »")
    creator = artist_from_deezer(payload)
    if not creator:
        return Resolution(None, REASON_NO_ARTIST, source)
    if titles_match(creator, reco.get("title")):
        return Resolution(None, REASON_CREATOR_EQUALS_TITLE, source,
                          detail=f"artiste « {creator} » = titre de la reco")
    return Resolution(creator, REASON_FILLED, source)


def _resolve_openlibrary(reco: dict[str, Any],
                         session: requests.Session) -> Resolution:
    isbn = (reco.get("externalIds") or {})["isbn"]
    source = f"openlibrary:{isbn}"
    edition = fetch_openlibrary_edition(session, isbn)
    if edition is None:
        return Resolution(None, REASON_HTTP_ERROR, source)
    title = edition.get("title")
    if title and not titles_match(reco.get("title"), title):
        return Resolution(None, REASON_TITLE_MISMATCH, source,
                          detail=f"OpenLibrary répond « {title} »")
    names: list[str | None] = []
    for key in author_keys(edition):
        doc = fetch_openlibrary_author(session, key)
        if doc:
            names.append(name_from_author_doc(doc))
    creator = join_names(names)
    if not creator:
        return Resolution(None, REASON_NO_AUTHOR, source)
    return Resolution(creator, REASON_FILLED, source)


def resolve_creator(reco: dict[str, Any], *, session: requests.Session,
                    api_key: str | None,
                    episode_year: int | None = None) -> Resolution:
    """Tente de déterminer le `creator` d'une reco. Ne modifie RIEN.

    `episode_year` (année de l'épisode où la reco a été prononcée) alimente le
    garde-fou d'anachronisme — cf. `release_is_plausible`.
    """
    chosen = plan(reco)
    if chosen.strategy is None:
        return Resolution(None, chosen.reason, None)

    tmdb_id = (reco.get("externalIds") or {}).get("tmdb")

    if chosen.strategy == STRATEGY_TMDB_MOVIE:
        if not api_key:
            return Resolution(None, REASON_NO_API_KEY, None)
        return _tmdb_resolution(
            reco, fetch_tmdb_movie(session, tmdb_id, api_key=api_key),
            source=f"tmdb:movie/{tmdb_id}", extractor=director_from_movie,
            empty_reason=REASON_NO_DIRECTOR, episode_year=episode_year)

    if chosen.strategy == STRATEGY_TMDB_TV:
        if not api_key:
            return Resolution(None, REASON_NO_API_KEY, None)
        return _tmdb_resolution(
            reco, fetch_tmdb_tv(session, tmdb_id, api_key=api_key),
            source=f"tmdb:tv/{tmdb_id}", extractor=creators_from_tv,
            empty_reason=REASON_NO_CREATED_BY, episode_year=episode_year)

    if chosen.strategy == STRATEGY_DEEZER:
        return _resolve_deezer(reco, session)

    return _resolve_openlibrary(reco, session)


# ===========================================================================
# Écriture
# ===========================================================================
def apply_creator(reco: dict[str, Any], creator: str,
                  *, timestamp: str | None = None) -> dict[str, Any]:
    """Pose `creator` + l'audit trail `enrichedAt["creator"]`, IN-PLACE.

    Délègue à `enrichment.field_refresher.partial_update` : aucun autre champ
    n'est touché, et un `enrichedAt` corrompu (non-dict) lève plutôt que
    d'être écrasé.
    """
    return partial_update(reco, "creator", creator,
                          timestamp=timestamp or now_iso())


# ===========================================================================
# Rapport
# ===========================================================================
@dataclass(frozen=True)
class FilledCase:
    reco_id: str
    title: str
    type_: str
    creator: str
    source: str
    path: Path


@dataclass(frozen=True)
class ReviewCase:
    reco_id: str
    title: str
    type_: str
    reason: str
    detail: str
    source: str | None


@dataclass
class Report:
    """Agrégats d'une passe (`run`)."""

    seen: int = 0
    written: int = 0
    filled: list[FilledCase] = field(default_factory=list)
    review: list[ReviewCase] = field(default_factory=list)
    skipped: Counter = field(default_factory=Counter)
    by_type: dict[str, Counter] = field(
        default_factory=lambda: defaultdict(Counter))
    reasons_by_type: dict[str, Counter] = field(
        default_factory=lambda: defaultdict(Counter))

    def record(self, reco: dict[str, Any], resolution: Resolution,
               path: Path) -> None:
        """Enregistre le sort d'une reco."""
        type_ = primary_type(reco)
        self.skipped[resolution.reason] += 1
        self.reasons_by_type[type_][resolution.reason] += 1
        if resolution.creator:
            self.by_type[type_]["filled"] += 1
            self.filled.append(FilledCase(
                reco.get("id", path.stem), reco.get("title", ""), type_,
                resolution.creator, resolution.source or "?", path))
        else:
            self.by_type[type_]["empty"] += 1
            if resolution.reason in AMBIGUOUS_REASONS:
                self.review.append(ReviewCase(
                    reco.get("id", path.stem), reco.get("title", ""), type_,
                    resolution.reason, resolution.detail, resolution.source))


def _completion_rate(report: Report) -> float:
    """Part des recos VUES qui repartent avec un `creator` (déjà là ou posé)."""
    if not report.seen:
        return 0.0
    already = report.skipped[REASON_ALREADY_SET]
    return 100.0 * (already + len(report.filled)) / report.seen


def format_report(report: Report) -> str:
    """Rapport lisible : par type, rempli / vide + raison dominante."""
    lines = [
        "",
        f"{'type':10} {'vues':>6} {'remplies':>9} {'vides':>6}  raison dominante",
        "-" * 72,
    ]
    for type_ in sorted(report.by_type):
        counts = report.by_type[type_]
        seen = counts["filled"] + counts["empty"]
        reasons = Counter({r: n for r, n in report.reasons_by_type[type_].items()
                           if r != REASON_FILLED})
        top = reasons.most_common(1)
        top_txt = f"{top[0][0]} ({top[0][1]})" if top else "—"
        lines.append(f"{type_:10} {seen:6} {counts['filled']:9} "
                     f"{counts['empty']:6}  {top_txt}")
    lines += [
        "-" * 72,
        f"Recos vues : {report.seen} · déjà pourvues : "
        f"{report.skipped[REASON_ALREADY_SET]} · nouvelles : {len(report.filled)} "
        f"· écrites : {report.written}",
        f"Taux de complétion du champ creator : {_completion_rate(report):.1f} %",
        f"À revoir à la main : {len(report.review)}",
    ]
    return "\n".join(lines)


def report_payload(report: Report) -> dict[str, Any]:
    """Version JSON-sérialisable du rapport (pour vérification manuelle)."""
    return {
        "seen": report.seen,
        "written": report.written,
        "completionRate": round(_completion_rate(report), 2),
        "reasons": dict(report.skipped),
        "byType": {t: dict(c) for t, c in sorted(report.by_type.items())},
        "filled": [
            {"id": c.reco_id, "title": c.title, "type": c.type_,
             "creator": c.creator, "source": c.source, "path": str(c.path)}
            for c in report.filled
        ],
        "review": [
            {"id": c.reco_id, "title": c.title, "type": c.type_,
             "reason": c.reason, "detail": c.detail, "source": c.source}
            for c in report.review
        ],
    }


# ===========================================================================
# Orchestration (passe complète)
# ===========================================================================
def iter_reco_paths(root: Path, source: str | None = None) -> list[Path]:
    """Fichiers JSON de recos, triés (toutes sources ou une seule)."""
    base = root / source if source else root
    if not base.is_dir():
        return []
    return sorted(base.glob("*.json") if source else base.glob("*/*.json"))


def load_episode_years(root: Path, source: str | None = None) -> dict[str, int]:
    """Index `episodeGuid` → année de diffusion, pour le garde-fou d'anachronisme."""
    years: dict[str, int] = {}
    base = root / source if source else root
    if not base.is_dir():
        return years
    for path in sorted(base.glob("*.json") if source else base.glob("*/*.json")):
        try:
            episode = read_json(path)
        except (ValueError, OSError):
            continue
        m = _RE_YEAR.match(str(episode.get("date") or ""))
        if m and episode.get("guid"):
            years[episode["guid"]] = int(m.group(1))
    return years


def run(*, root: Path, session: requests.Session | None, api_key: str | None,
        source: str | None = None, types: Sequence[str] | None = None,
        limit: int | None = None, apply: bool = False,
        exclude_ids: Iterable[str] = (),
        episode_years: dict[str, int] | None = None,
        sleep: float = RATE_LIMIT_SLEEP) -> Report:
    """Passe complète : sélectionne, résout, journalise, écrit si `apply`."""
    excluded = set(exclude_ids)
    wanted = set(types) if types else None
    report = Report()
    resolved = 0

    for path in iter_reco_paths(root, source):
        try:
            reco = read_json(path)
        except (ValueError, OSError) as exc:
            log.warning("  %s illisible (%s) — ignoré", path.name, exc)
            report.skipped[REASON_UNREADABLE] += 1
            continue

        if wanted and not (set(reco.get("types") or []) & wanted):
            continue
        report.seen += 1
        reco_id = reco.get("id", path.stem)

        if reco_id in excluded:
            log.info("  %s · exclu (revue humaine)", reco_id)
            report.record(reco, Resolution(None, REASON_EXCLUDED, None), path)
            continue
        # Idempotence : un creator existant n'est jamais retouché — et on
        # n'appelle même pas l'API.
        if (reco.get("creator") or "").strip():
            report.record(reco, Resolution(None, REASON_ALREADY_SET, None), path)
            continue
        if limit is not None and resolved >= limit:
            continue

        resolution = resolve_creator(
            reco, session=session, api_key=api_key,
            episode_year=(episode_years or {}).get(reco.get("episodeGuid")))
        resolved += 1
        _log_resolution(reco_id, reco, resolution)
        report.record(reco, resolution, path)

        if resolution.creator and apply:
            try:
                apply_creator(reco, resolution.creator)
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
    """Une ligne par reco : rempli (source) ou vide (raison)."""
    title = (reco.get("title") or "")[:45]
    types = ",".join(reco.get("types") or [])
    if resolution.creator:
        log.info("  %s · %s [%s] → « %s » (%s)", reco_id, title, types,
                 resolution.creator, resolution.source)
    else:
        detail = f" — {resolution.detail}" if resolution.detail else ""
        log.info("  %s · %s [%s] → vide : %s%s", reco_id, title, types,
                 resolution.reason, detail)


def parse_exclude_ids(raw: str | None) -> set[str]:
    """`--exclude-ids` : liste CSV, ou `@fichier` (un id par ligne, `#` = commentaire)."""
    if not raw:
        return set()
    if raw.startswith("@"):
        lines = Path(raw[1:]).read_text(encoding="utf-8").splitlines()
        return {ln.strip() for ln in lines if ln.strip() and not ln.startswith("#")}
    return {part.strip() for part in raw.split(",") if part.strip()}


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Remplit `creator` depuis TMDB / Deezer / OpenLibrary "
                    "via les identifiants externes déjà présents (jamais par "
                    "recherche de titre).")
    p.add_argument("--source", default=None,
                   help="Limiter à une source (défaut : toutes).")
    p.add_argument("--types", default=None,
                   help="Filtrer par types, séparés par des virgules "
                        "(ex. film,serie).")
    p.add_argument("--limit", type=int, default=None,
                   help="Nombre maximum de recos réellement interrogées.")
    p.add_argument("--apply", action="store_true",
                   help="Écrire les creators trouvés (défaut : dry-run).")
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

    load_dotenv(TOOLS_DIR / ".env")
    api_key = os.getenv("TMDB_API_KEY")
    if not api_key:
        log.warning("TMDB_API_KEY absent : films et séries seront ignorés "
                    "(Deezer et OpenLibrary fonctionnent sans clé).")

    types = tuple(t.strip() for t in args.types.split(",")) if args.types else None
    kwargs = dict(
        root=RECOS_DIR, session=requests.Session(), api_key=api_key,
        source=args.source, types=types, limit=args.limit, apply=args.apply,
        exclude_ids=parse_exclude_ids(args.exclude_ids),
        episode_years=load_episode_years(EPISODES_DIR, args.source),
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
        import json as _json  # noqa: PLC0415 — sérialisation ponctuelle.
        atomic_write_text(Path(args.json_path),
                          _json.dumps(report_payload(report),
                                      ensure_ascii=False, indent=2) + "\n")
        log.info("Rapport détaillé : %s", args.json_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
