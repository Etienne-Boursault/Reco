"""Tests des fonctions PURES de `tools/enrich_creators.py`.

Aucun réseau, aucun disque : extraction du créateur depuis un payload API +
garde-fous (correspondance de titre, d'année) + choix de stratégie.
"""
from __future__ import annotations

import pytest

import enrich_creators as ec


# ===== join_names ===========================================================
def test_join_names_single():
    assert ec.join_names(["Jacques Audiard"]) == "Jacques Audiard"


def test_join_names_multiple_preserves_order():
    assert ec.join_names(["Joel Coen", "Ethan Coen"]) == "Joel Coen, Ethan Coen"


def test_join_names_dedupes_and_strips():
    assert ec.join_names([" Ava DuVernay ", "Ava DuVernay"]) == "Ava DuVernay"


def test_join_names_ignores_empty_and_none():
    assert ec.join_names(["", None, "   ", "Agnès Varda"]) == "Agnès Varda"


def test_join_names_all_empty_returns_none():
    assert ec.join_names(["", None]) is None


@pytest.mark.parametrize("junk", ["0", "42", "-", "—", "  0  ", "###"])
def test_join_names_rejects_names_without_a_letter(junk):
    """TMDB contient des entrées polluées (`created_by` avec `name == "0"`)."""
    assert ec.join_names([junk]) is None


def test_join_names_keeps_valid_names_next_to_junk():
    assert ec.join_names(["Brian Volk-Weiss", "0"]) == "Brian Volk-Weiss"


def test_join_names_accepts_non_ascii_and_digits_in_real_names():
    assert ec.join_names(["Éric Rochant"]) == "Éric Rochant"
    assert ec.join_names(["Tetsuya Nomura 2"]) == "Tetsuya Nomura 2"


def test_join_names_empty_iterable_returns_none():
    assert ec.join_names([]) is None


# ===== titles_match =========================================================
@pytest.mark.parametrize(
    "a,b",
    [
        ("Breaking Bad", "Breaking Bad"),
        ("Le Bureau des Légendes", "Le Bureau des legendes"),  # accents
        ("Mr. & Mrs. Smith", "Mr and Mrs Smith"),              # ponctuation
        ("White Lotus", "The White Lotus"),                    # containment mots
        ("Charlie (All Dogs Go to Heaven)", "All Dogs Go to Heaven"),
        ("What We Do In The Shadows", "What We Do in the Shadows"),
    ],
)
def test_titles_match_true(a, b):
    assert ec.titles_match(a, b) is True


@pytest.mark.parametrize(
    "a,b",
    [
        ("Aka", "Akira"),            # containment de SOUS-CHAÎNE interdit
        ("Titanic", "Le Titan"),
        ("Vice", "Vice-versa"),
        ("Mortal", "Mortal Kombat"), # 1 mot court ≠ suffisant
        ("", "Breaking Bad"),
        ("Breaking Bad", None),
    ],
)
def test_titles_match_false(a, b):
    assert ec.titles_match(a, b) is False


def test_titles_match_threshold_is_tunable():
    assert ec.titles_match("Colombo", "Columbo") is True          # typo tolérée
    assert ec.titles_match("Colombo", "Columbo", threshold=0.99) is False


def test_any_title_matches_scans_candidates():
    assert ec.any_title_matches("Charlie", ["Charlie, mon héros", "Charlie"]) is True


def test_any_title_matches_none_match():
    assert ec.any_title_matches("Charlie", ["Bambi", None, ""]) is False


# ===== remote_titles / remote_year ==========================================
def test_remote_titles_movie():
    payload = {"title": "Will Hunting", "original_title": "Good Will Hunting"}
    assert ec.remote_titles(payload) == ["Will Hunting", "Good Will Hunting"]


def test_remote_titles_tv():
    payload = {"name": "Le Bureau des Légendes", "original_name": "Le Bureau des Légendes"}
    assert ec.remote_titles(payload) == ["Le Bureau des Légendes"] * 2


def test_remote_titles_empty_payload():
    assert ec.remote_titles({}) == []


@pytest.mark.parametrize(
    "payload,expected",
    [
        ({"release_date": "1997-12-19"}, 1997),
        ({"first_air_date": "2008-01-20"}, 2008),
        ({"release_date": ""}, None),
        ({"release_date": "n/a"}, None),
        ({}, None),
    ],
)
def test_remote_year(payload, expected):
    assert ec.remote_year(payload) == expected


@pytest.mark.parametrize(
    "reco_year,api_year,expected",
    [
        (1997, 1997, True),
        (1997, 1998, True),    # tolérance ±1 (sortie FR décalée)
        (1997, 2001, False),
        (None, 1997, True),    # pas d'année côté reco → pas de contrainte
        (1997, None, True),    # pas d'année côté API → pas de contrainte
    ],
)
def test_year_matches(reco_year, api_year, expected):
    assert ec.year_matches(reco_year, api_year) is expected


@pytest.mark.parametrize(
    "episode_year,api_year,expected",
    [
        (2021, 2019, True),    # œuvre antérieure : normal
        (2021, 2021, True),
        (2021, 2022, True),    # anticipation légitime (avant-première, festival)
        (2021, 2025, False),   # anachronisme : le film n'existait pas encore
        (None, 2025, True),    # date d'épisode inconnue → pas de contrainte
        (2021, None, True),
    ],
)
def test_release_is_plausible(episode_year, api_year, expected):
    assert ec.release_is_plausible(episode_year, api_year) is expected


# ===== Extraction TMDB ======================================================
def test_director_from_movie_append_to_response():
    payload = {"credits": {"crew": [
        {"job": "Producer", "name": "X"},
        {"job": "Director", "name": "James Cameron"},
    ]}}
    assert ec.director_from_movie(payload) == "James Cameron"


def test_director_from_movie_bare_credits_endpoint():
    payload = {"crew": [{"job": "Director", "name": "Orson Welles"}]}
    assert ec.director_from_movie(payload) == "Orson Welles"


def test_director_from_movie_multiple_directors():
    payload = {"credits": {"crew": [
        {"job": "Director", "name": "Joel Coen"},
        {"job": "Director", "name": "Ethan Coen"},
    ]}}
    assert ec.director_from_movie(payload) == "Joel Coen, Ethan Coen"


def test_director_from_movie_no_director():
    payload = {"credits": {"crew": [{"job": "Writer", "name": "X"}]}}
    assert ec.director_from_movie(payload) is None


def test_director_from_movie_empty():
    assert ec.director_from_movie({}) is None


def test_creators_from_tv():
    payload = {"created_by": [{"name": "Vince Gilligan"}]}
    assert ec.creators_from_tv(payload) == "Vince Gilligan"


def test_creators_from_tv_multiple():
    payload = {"created_by": [{"name": "A"}, {"name": "B"}]}
    assert ec.creators_from_tv(payload) == "A, B"


def test_creators_from_tv_empty_is_none():
    """Cas fréquent : téléréalité, docu-série, anime → aucun `created_by`."""
    assert ec.creators_from_tv({"created_by": []}) is None
    assert ec.creators_from_tv({}) is None


# ===== Deezer ===============================================================
@pytest.mark.parametrize(
    "url,expected",
    [
        ("https://www.deezer.com/track/142704126", ("track", "142704126")),
        ("https://deezer.com/album/942466201", ("album", "942466201")),
        ("https://www.deezer.com/fr/artist/201875", ("artist", "201875")),
        ("https://www.deezer.com/en/album/12?utm=x", ("album", "12")),
    ],
)
def test_parse_deezer_url(url, expected):
    assert ec.parse_deezer_url(url) == expected


@pytest.mark.parametrize(
    "url",
    ["https://www.deezer.com/", "https://example.com/track/1", "", None,
     "https://www.deezer.com/playlist/123"],
)
def test_parse_deezer_url_invalid(url):
    assert ec.parse_deezer_url(url) is None


def test_artist_from_deezer():
    assert ec.artist_from_deezer({"artist": {"name": "Daft Punk"}}) == "Daft Punk"


def test_artist_from_deezer_missing():
    assert ec.artist_from_deezer({}) is None
    assert ec.artist_from_deezer({"artist": {}}) is None


def test_deezer_titles():
    assert ec.deezer_titles({"title": "Around the World"}) == ["Around the World"]
    assert ec.deezer_titles({}) == []


# ===== OpenLibrary ==========================================================
def test_author_keys_direct():
    payload = {"authors": [{"key": "/authors/OL34184A"}]}
    assert ec.author_keys(payload) == ["/authors/OL34184A"]


def test_author_keys_nested_form():
    """Certaines éditions imbriquent la clé sous `author`."""
    payload = {"authors": [{"author": {"key": "/authors/OL1A"}}]}
    assert ec.author_keys(payload) == ["/authors/OL1A"]


def test_author_keys_none():
    assert ec.author_keys({}) == []
    assert ec.author_keys({"authors": [{}]}) == []


def test_name_from_author_doc():
    assert ec.name_from_author_doc({"name": "Alan Moore"}) == "Alan Moore"
    assert ec.name_from_author_doc({}) is None


# ===== Choix de stratégie (plan) ===========================================
def _reco(**kw):
    base = {"id": "x-0001", "title": "T", "types": ["film"]}
    base.update(kw)
    return base


def test_plan_already_set_is_skipped():
    p = ec.plan(_reco(creator="Déjà là", externalIds={"tmdb": "1", "tmdbType": "movie"}))
    assert p.strategy is None and p.reason == ec.REASON_ALREADY_SET


def test_plan_blank_creator_is_not_already_set():
    p = ec.plan(_reco(creator="   ", externalIds={"tmdb": "1", "tmdbType": "movie"}))
    assert p.strategy == ec.STRATEGY_TMDB_MOVIE


def test_plan_tmdb_movie():
    p = ec.plan(_reco(types=["film"], externalIds={"tmdb": "597", "tmdbType": "movie"}))
    assert p.strategy == ec.STRATEGY_TMDB_MOVIE


def test_plan_tmdb_tv():
    p = ec.plan(_reco(types=["serie"], externalIds={"tmdb": "1396", "tmdbType": "tv"}))
    assert p.strategy == ec.STRATEGY_TMDB_TV


def test_plan_tmdb_type_wins_over_reco_type():
    """`tmdbType` fait autorité : l'id appartient à l'espace movie OU tv."""
    p = ec.plan(_reco(types=["serie"], externalIds={"tmdb": "21575", "tmdbType": "movie"}))
    assert p.strategy == ec.STRATEGY_TMDB_MOVIE


def test_plan_tmdb_without_type_is_refused():
    """Sans `tmdbType`, l'id est ambigu (espaces movie/tv disjoints) → skip."""
    p = ec.plan(_reco(types=["film"], externalIds={"tmdb": "1396"}))
    assert p.strategy is None and p.reason == ec.REASON_NO_TMDB_TYPE


def test_plan_deezer():
    p = ec.plan(_reco(types=["musique"],
                      externalIds={"deezer": "https://www.deezer.com/track/1"}))
    assert p.strategy == ec.STRATEGY_DEEZER


def test_plan_openlibrary():
    p = ec.plan(_reco(types=["livre"], externalIds={"isbn": "9782070360024"}))
    assert p.strategy == ec.STRATEGY_OPENLIBRARY


def test_plan_supported_type_without_id():
    p = ec.plan(_reco(types=["film"], externalIds={}))
    assert p.strategy is None and p.reason == ec.REASON_NO_EXTERNAL_ID


@pytest.mark.parametrize("types", [["musique"], ["album"], ["livre"], ["bd"]])
def test_plan_music_and_book_without_their_id(types):
    p = ec.plan(_reco(types=types, externalIds={"tmdb": "1", "tmdbType": "movie"}))
    assert p.strategy is None and p.reason == ec.REASON_NO_EXTERNAL_ID


def test_plan_supported_type_no_external_ids_key():
    p = ec.plan(_reco(types=["livre"]))
    assert p.strategy is None and p.reason == ec.REASON_NO_EXTERNAL_ID


@pytest.mark.parametrize("t", ["artiste", "chaine", "video", "podcast",
                               "spectacle", "lieu", "jeu", "autre"])
def test_plan_unsupported_types(t):
    p = ec.plan(_reco(types=[t], externalIds={"tmdb": "1", "tmdbType": "movie"}))
    assert p.strategy is None and p.reason == ec.REASON_TYPE_UNSUPPORTED


def test_plan_no_types_at_all():
    p = ec.plan({"id": "x", "title": "T"})
    assert p.strategy is None and p.reason == ec.REASON_TYPE_UNSUPPORTED


def test_plan_priority_video_over_music_when_both_typed():
    """`['film','serie','autre']` → la branche TMDB gagne."""
    p = ec.plan(_reco(types=["musique", "film"],
                      externalIds={"tmdb": "1", "tmdbType": "movie",
                                   "deezer": "https://www.deezer.com/track/1"}))
    assert p.strategy == ec.STRATEGY_TMDB_MOVIE
