"""Corpus de calibration — CR senior H11.

20+ cas étiquetés (suspects ET clean, FR/EN, films/séries/courts) qui
valident que les seuils par défaut tiennent. Si on bouge un seuil et qu'un
cas bascule, le test échoue : c'est l'effet recherché. **Bloquant prod**.

NB : on charge le `default_service()` exactement comme le CLI le ferait,
pour que la calibration capture la *composition* (et pas juste les checks
isolés). Le score attendu n'est pas le ratio brut mais "suspect / clean".
"""
from __future__ import annotations

from dataclasses import dataclass

import pytest

from domain.item import ExternalIds, Item, ItemType
from enrich_audit.cli_runner import default_service


@dataclass(frozen=True)
class Case:
    name: str
    item: Item
    tmdb_data: dict
    expected_suspect: bool
    expected_kinds: tuple[str, ...] = ()
    notes: str = ""


def _movie(item_id: str, title: str, year: int | None = None,
           tmdb_type: str = "movie") -> Item:
    return Item(
        id=item_id,
        types=(ItemType.FILM,),
        title=title,
        year=year,
        external_ids=ExternalIds(tmdb=1, tmdb_type=tmdb_type),
    )


def _series(item_id: str, title: str, year: int | None = None,
            tmdb_type: str = "tv") -> Item:
    return Item(
        id=item_id,
        types=(ItemType.SERIES,),
        title=title,
        year=year,
        external_ids=ExternalIds(tmdb=1, tmdb_type=tmdb_type),
    )


# ===== Corpus ==============================================================
# Convention id : "cor" + 5 chars unique
CORPUS: tuple[Case, ...] = (
    # --- Clean (films FR/EN) ---
    Case("inception-clean", _movie("cor00001", "Inception", 2010),
         {"original_title": "Inception", "release_date": "2010-07-16",
          "runtime": 148},
         expected_suspect=False),
    Case("godfather-clean", _movie("cor00002", "Le Parrain", 1972),
         {"original_title": "The Godfather", "title": "Le Parrain",
          "release_date": "1972-03-24", "runtime": 175},
         expected_suspect=False, notes="Titre FR via `title`, original EN."),
    Case("amelie-clean", _movie("cor00003", "Amélie", 2001),
         {"original_title": "Le Fabuleux Destin d'Amélie Poulain",
          "title": "Amélie", "release_date": "2001-04-25", "runtime": 122},
         expected_suspect=False, notes="Alias court."),
    Case("relatos-fr-en", _movie("cor00004", "Les Nouveaux Sauvages", 2014),
         {"original_title": "Relatos salvajes",
          "title": "Les Nouveaux Sauvages",
          "release_date": "2014-08-21", "runtime": 122},
         expected_suspect=False,
         notes="CR senior H1 : original ES, titre FR via `title`."),
    Case("rrr-original-non-latin",
         _movie("cor00005", "RRR", 2022),
         {"original_title": "RRR", "title": "RRR",
          "release_date": "2022-03-25", "runtime": 187},
         expected_suspect=False),
    # --- Clean (séries) ---
    Case("severance-clean", _series("cor00006", "Severance", 2022),
         {"name": "Severance", "first_air_date": "2022-02-18",
          "episode_run_time": [55]},
         expected_suspect=False),
    Case("breakingbad-clean", _series("cor00007", "Breaking Bad", 2008),
         {"name": "Breaking Bad", "first_air_date": "2008-01-20",
          "episode_run_time": [49]},
         expected_suspect=False),
    Case("kassos-clean", _series("cor00008", "Kassos", 2017),
         {"name": "Kassos", "first_air_date": "2017-03-15",
          "episode_run_time": [10]},
         expected_suspect=False,
         notes="Animation courte 10min — pas suspect (>= seuil MIN)."),
    # --- Suspect (titre quasi-different) ---
    Case("title-mismatch-bad",
         _movie("cor00009", "Inception", 2010),
         {"original_title": "The Godfather", "release_date": "1972-03-24",
          "runtime": 175},
         expected_suspect=True,
         expected_kinds=("title_mismatch", "year_mismatch")),
    # --- Suspect (year only) ---
    Case("year-mismatch-only",
         _movie("cor00010", "Heat", 1995),
         {"original_title": "Heat", "release_date": "2022-01-01",
          "runtime": 170},
         expected_suspect=True, expected_kinds=("year_mismatch",)),
    # --- Suspect (court flag INFO mais suspect=True) ---
    Case("short-suspected",
         _movie("cor00011", "Mortel", 2020),
         {"original_title": "Mortel", "release_date": "2020-01-01",
          "runtime": 8},
         expected_suspect=True, expected_kinds=("runtime_short_film",),
         notes="< 20 min → court probable."),
    # --- Suspect critique (tmdb_type_mismatch — bug principal) ---
    Case("film-but-tv-payload",
         _movie("cor00012", "Vice", 2018),
         {"name": "Vice", "first_air_date": "2018-12-25",
          "episode_run_time": [50]},
         expected_suspect=True, expected_kinds=("tmdb_type_mismatch",),
         notes="CR senior C5 : LE check critique."),
    Case("series-but-movie-payload",
         _series("cor00013", "Friends", 1994),
         {"original_title": "Friends", "release_date": "1994-09-22",
          "runtime": 22},
         expected_suspect=True, expected_kinds=("tmdb_type_mismatch",)),
    # --- Suspect (long episode runtime — TV movie matché série) ---
    Case("series-tv-movie",
         _series("cor00014", "MiniDoc", 2020),
         {"name": "MiniDoc", "first_air_date": "2020-01-01",
          "episode_run_time": [220]},
         expected_suspect=True, expected_kinds=("runtime_long_series",)),
    # --- Clean court-métrage explicitement taggé (no suspicion) ---
    # NB : on n'a pas de SHORT_FILM dans ItemType ; on tolère un film court
    #     long (45 min) sans suspicion.
    Case("midlength-clean",
         _movie("cor00015", "Le Court", 2019),
         {"original_title": "Le Court", "release_date": "2019-01-01",
          "runtime": 45},
         expected_suspect=False),
    # --- Clean ponctuation/accents ---
    Case("punct-accents-clean",
         _movie("cor00016", "L'Auberge espagnole", 2002),
         {"original_title": "L'auberge espagnole",
          "release_date": "2002-06-19", "runtime": 122},
         expected_suspect=False),
    Case("oe-ligature-clean",
         _movie("cor00017", "Cœur de pirate", 2008),
         {"original_title": "Coeur de pirate", "release_date": "2008-01-01",
          "runtime": 90},
         expected_suspect=False,
         notes="CR senior L1 : œ ↔ oe."),
    # --- Multi-year tolerance edge cases ---
    Case("year-edge-+1",
         _movie("cor00018", "Edge", 2015),
         {"original_title": "Edge", "release_date": "2016-01-01",
          "runtime": 100},
         expected_suspect=False, notes="Delta = 1 → dans tolérance."),
    Case("year-edge-+2",
         _movie("cor00019", "EdgeBis", 2015),
         {"original_title": "EdgeBis", "release_date": "2017-01-01",
          "runtime": 100},
         expected_suspect=True, expected_kinds=("year_mismatch",)),
    # --- Pas de tmdb_data utile (cache absent) → skip côté caller ---
    # On ne le teste pas ici (le service est appelé via provider).
    # --- Clean en cas d'absence de toute info date / runtime ---
    Case("no-info-clean",
         _movie("cor00020", "SansInfo"),
         {"original_title": "SansInfo"},
         expected_suspect=False, notes="Aucune signal → no-op."),
    # --- Clean série hybride film+série (tolérée) ---
    Case("hybrid-multi-type-clean",
         Item(id="cor00021", types=(ItemType.FILM, ItemType.SERIES),
              title="Anthologie",
              external_ids=ExternalIds(tmdb=1, tmdb_type="tv")),
         {"name": "Anthologie", "first_air_date": "2020-01-01",
          "episode_run_time": [60]},
         expected_suspect=False,
         notes="CR : multi-type FILM+SERIES → tmdb_type_mismatch tolère."),
)


@pytest.mark.parametrize("case", CORPUS, ids=lambda c: c.name)
def test_corpus_default_thresholds(case: Case):
    svc = default_service()
    result = svc.audit_item(case.item, lambda _id: case.tmdb_data)
    assert result is not None, f"{case.name} : provider devrait renvoyer une donnée"
    actual_kinds = tuple(sorted({s.kind for s in result.suspicions}))
    expected_kinds = tuple(sorted(case.expected_kinds))
    assert result.is_suspect == case.expected_suspect, (
        f"{case.name} : attendu suspect={case.expected_suspect}, "
        f"reçu={result.is_suspect}, kinds={actual_kinds} "
        f"(notes: {case.notes})"
    )
    if case.expected_suspect and expected_kinds:
        assert actual_kinds == expected_kinds, (
            f"{case.name} : kinds attendus={expected_kinds}, reçus={actual_kinds}"
        )


def test_corpus_has_enough_cases():
    """Garde-fou : on garde au moins 20 cas pour calibration significative."""
    assert len(CORPUS) >= 20
