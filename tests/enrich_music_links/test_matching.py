"""Tests de la couche PURE : appariement, garde-fous, choix de stratégie.

Aucun réseau, aucun disque. C'est ici que se joue la règle « zéro invention » :
la plupart de ces tests vérifient un REFUS, pas un succès.
"""
from __future__ import annotations

import pytest

import enrich_music_links as m


# ===== names_match ==========================================================
def test_names_match_exact():
    assert m.names_match("Orelsan", "Orelsan")


def test_names_match_ignores_case_and_accents():
    assert m.names_match("Philémon Cimon", "philemon cimon")


@pytest.mark.parametrize(("a", "b"), [
    # Fautes de transcription réelles relevées dans le corpus.
    ("Yann Tierssen", "Yann Tiersen"),
    ("Corey Wong", "Cory Wong"),
    ("Sophia Bellabès", "Sophia Belabbès"),
])
def test_names_match_absorbs_transcription_typos(a, b):
    assert m.names_match(a, b)


@pytest.mark.parametrize(("a", "b"), [
    ("Orelsan", "Nekfeu"),
    ("Suzane", "Suzanne Vega"),
    ("Gorillaz", "Blur"),
])
def test_names_match_rejects_different_artists(a, b):
    assert not m.names_match(a, b)


@pytest.mark.parametrize(("a", "b"), [(None, "X"), ("X", None), ("", "X"), ("X", "")])
def test_names_match_empty_is_never_a_match(a, b):
    assert not m.names_match(a, b)


def test_names_match_threshold_is_adjustable():
    assert m.names_match("Orelsan", "Nekfeu", threshold=0.0)


# ===== creator_names / artist_matches_creator ===============================
def test_creator_names_splits_on_commas():
    assert m.creator_names("Damon Albarn, Jamie Hewlett") == [
        "Damon Albarn", "Jamie Hewlett"]


@pytest.mark.parametrize("raw", [None, "", "  ", ",, ,"])
def test_creator_names_empty(raw):
    assert m.creator_names(raw) == []


def test_artist_matches_creator_on_any_of_several_names():
    assert m.artist_matches_creator("Jamie Hewlett", "Damon Albarn, Jamie Hewlett")


def test_artist_matches_creator_false_when_none_match():
    assert not m.artist_matches_creator("Thom Yorke", "Damon Albarn, Jamie Hewlett")


def test_artist_matches_creator_false_without_creator():
    assert not m.artist_matches_creator("Orelsan", None)


# ===== titles_match_strict ==================================================
def test_titles_match_strict_normalizes():
    assert m.titles_match_strict("L'Horizon des Événements",
                                 "l horizon des evenements")


def test_titles_match_strict_refuses_inclusion():
    """« Amélie » ⊄ « Amélie Poulain » : c'est tout l'objet de la stricture."""
    assert not m.titles_match_strict("Amélie", "Amélie Poulain")


def test_titles_match_strict_refuses_near_miss():
    assert not m.titles_match_strict("Civilisation", "Civilisation Édition Ultime")


@pytest.mark.parametrize(("a", "b"), [(None, "X"), ("", "X"), ("X", None)])
def test_titles_match_strict_empty(a, b):
    assert not m.titles_match_strict(a, b)


# ===== link_host / existing_hosts / missing_platforms =======================
def test_link_host_strips_www_and_case():
    assert m.link_host("https://WWW.Deezer.com/fr/album/1") == "deezer.com"


def test_link_host_malformed_ipv6_is_empty():
    """Un lien saisi à la main ne doit pas faire tomber la passe."""
    assert m.link_host("https://[::1") == ""


def test_link_host_without_hostname_is_empty():
    assert m.link_host("pas-une-url") == ""


def test_existing_hosts_collects_link_hosts():
    reco = {"links": [{"url": "https://www.deezer.com/album/1"},
                      {"url": "https://qobuz.com/x"}]}
    assert m.existing_hosts(reco) == {"deezer.com", "qobuz.com"}


def test_existing_hosts_ignores_empty_urls():
    assert m.existing_hosts({"links": [{"url": ""}, {}]}) == set()


def test_existing_hosts_without_links():
    assert m.existing_hosts({}) == set()


def test_missing_platforms_all_when_no_links():
    assert set(m.missing_platforms({})) == {m.PLATFORM_DEEZER, m.PLATFORM_APPLE}


def test_missing_platforms_excludes_existing():
    reco = {"links": [{"url": "https://www.deezer.com/album/1"}]}
    assert m.missing_platforms(reco) == [m.PLATFORM_APPLE]


def test_missing_platforms_empty_when_complete():
    reco = {"links": [{"url": "https://www.deezer.com/album/1"},
                      {"url": "https://music.apple.com/fr/album/1"}]}
    assert m.missing_platforms(reco) == []


def test_has_any_listening_link_true_for_qobuz():
    """Qobuz n'est pas remplissable par l'outil, mais compte comme couverture."""
    assert m.has_any_listening_link({"links": [{"url": "https://qobuz.com/a"}]})


def test_has_any_listening_link_false_for_instagram():
    assert not m.has_any_listening_link(
        {"links": [{"url": "https://instagram.com/x"}]})


# ===== primary_type =========================================================
@pytest.mark.parametrize(("types", "expected"), [
    (["album", "autre"], "album"),
    (["autre", "musique"], "musique"),
    (["artiste"], "artiste"),
    (["album", "musique"], "album"),
    (["podcast"], "podcast"),
    ([], "?"),
])
def test_primary_type(types, expected):
    assert m.primary_type({"types": types}) == expected


# ===== parse_deezer_url =====================================================
@pytest.mark.parametrize(("url", "expected"), [
    ("https://www.deezer.com/album/262200072", ("album", "262200072")),
    ("https://www.deezer.com/fr/track/42", ("track", "42")),
    ("https://deezer.com/ARTIST/7", ("artist", "7")),
])
def test_parse_deezer_url_ok(url, expected):
    assert m.parse_deezer_url(url) == expected


@pytest.mark.parametrize("url", [None, "", "https://spotify.com/album/1",
                                 "https://www.deezer.com/album/abc"])
def test_parse_deezer_url_rejects(url):
    assert m.parse_deezer_url(url) is None


# ===== content_kind =========================================================
@pytest.mark.parametrize(("types", "expected"), [
    (["album"], "album"),
    (["album", "musique"], "album"),
    (["musique"], "track"),
    (["musique", "artiste"], "track"),
    (["artiste"], "artist"),
])
def test_content_kind(types, expected):
    assert m.content_kind({"types": types}) == expected


# ===== plan =================================================================
def test_plan_refuses_non_musical_type():
    assert m.plan({"types": ["film"]}).reason == m.REASON_TYPE_UNSUPPORTED


def test_plan_refuses_type_artiste_by_default():
    """Le corpus classe humoristes, acteurs et réalisateurs en `artiste`."""
    p = m.plan({"types": ["artiste"], "title": "Vérino"})
    assert p.strategy is None
    assert p.reason == m.REASON_ARTIST_TYPE_UNPROVEN


def test_plan_opens_type_artiste_with_opt_in():
    p = m.plan({"types": ["artiste"], "title": "Gorillaz"}, allow_artists=True)
    assert (p.strategy, p.kind) == (m.STRATEGY_SEARCH_ARTIST, "artist")


def test_plan_artiste_with_deezer_id_still_refused_without_opt_in():
    """Un identifiant stocké ne prouve PAS le caractère musical de la reco.

    Ces identifiants viennent de l'ancien `enrich_music.py`, qui retenait le
    premier résultat sans vérifier : c'est ainsi qu'un humoriste hérite de la
    page d'un musicien homonyme.
    """
    reco = {"types": ["artiste"], "title": "Vérino",
            "externalIds": {"deezer": "https://www.deezer.com/artist/1"}}
    assert m.plan(reco).reason == m.REASON_ARTIST_TYPE_UNPROVEN


def test_plan_promotes_stored_deezer_id():
    reco = {"types": ["album"], "title": "X",
            "externalIds": {"deezer": "https://www.deezer.com/album/1"}}
    p = m.plan(reco)
    assert (p.strategy, p.kind) == (m.STRATEGY_PROMOTE_DEEZER_ID, "album")


def test_plan_does_not_promote_when_link_already_visible():
    reco = {"types": ["album"], "title": "X",
            "externalIds": {"deezer": "https://www.deezer.com/album/1"},
            "links": [{"url": "https://www.deezer.com/album/1"}]}
    assert m.plan(reco).strategy == m.STRATEGY_SEARCH_ALBUM


def test_plan_search_track_for_musique():
    p = m.plan({"types": ["musique"], "title": "X"})
    assert (p.strategy, p.kind) == (m.STRATEGY_SEARCH_TRACK, "track")


# ===== search_query =========================================================
def test_search_query_joins_title_and_creator():
    assert m.search_query({"title": "Civilisation", "creator": "Orelsan"},
                          want_artist_page=False) == "Civilisation Orelsan"


def test_search_query_without_creator():
    assert m.search_query({"title": "Civilisation"},
                          want_artist_page=False) == "Civilisation"


def test_search_query_artist_page_uses_title_only():
    assert m.search_query({"title": "Gorillaz", "creator": "Damon Albarn"},
                          want_artist_page=True) == "Gorillaz"


# ===== MusicLink ============================================================
def test_music_link_as_link_matches_schema():
    link = m.MusicLink(m.PLATFORM_DEEZER, "Deezer", "https://deezer.com/a", "src")
    assert link.as_link() == {"label": "Deezer", "url": "https://deezer.com/a",
                              "kind": "streaming", "ethics": "neutral"}


# ===== verdict ==============================================================
def _cand(artist, title="", ident="1", platform=m.PLATFORM_DEEZER, kind="album"):
    return m.Candidate(platform, kind, f"https://deezer.com/{ident}", artist,
                       title, ident=ident)


ALBUM_RECO = {"title": "Civilisation", "creator": "Orelsan"}


def test_verdict_accepts_when_title_and_artist_match():
    chosen, reason, _ = m.verdict(
        ALBUM_RECO, [_cand("Orelsan", "Civilisation")], want_artist_page=False)
    assert reason == m.REASON_LINKED
    assert chosen.artist == "Orelsan"


def test_verdict_refuses_homonym_with_matching_title_only():
    """Le cas « Amélie » : bon titre, mauvais artiste ⇒ refus tracé."""
    chosen, reason, detail = m.verdict(
        {"title": "Amélie", "creator": "Alizée"},
        [_cand("Gracie Abrams", "Amélie")], want_artist_page=False)
    assert chosen is None
    assert reason == m.REASON_ARTIST_MISMATCH
    assert "Gracie Abrams" in detail


def test_verdict_no_match_when_no_title_matches():
    chosen, reason, _ = m.verdict(
        ALBUM_RECO, [_cand("Orelsan", "Autre album")], want_artist_page=False)
    assert (chosen, reason) == (None, m.REASON_NO_MATCH)


def test_verdict_no_match_on_empty_candidates():
    chosen, reason, detail = m.verdict(ALBUM_RECO, [], want_artist_page=False)
    assert (chosen, reason, detail) == (None, m.REASON_NO_MATCH, "")


def test_verdict_anchored_title_mismatch_flags_a_wrong_stored_id():
    chosen, reason, _ = m.verdict(
        ALBUM_RECO, [_cand("Orelsan", "Perdu d'avance")],
        want_artist_page=False, anchored=True)
    assert (chosen, reason) == (None, m.REASON_TITLE_MISMATCH)


def test_verdict_ambiguous_when_two_distinct_candidates_survive():
    chosen, reason, detail = m.verdict(
        ALBUM_RECO,
        [_cand("Orelsan", "Civilisation", ident="1"),
         _cand("Orelsan", "Civilisation", ident="2")],
        want_artist_page=False)
    assert (chosen, reason) == (None, m.REASON_AMBIGUOUS)
    assert "2 candidats distincts" in detail


def test_verdict_same_identity_twice_is_not_ambiguous():
    chosen, _, _ = m.verdict(
        ALBUM_RECO,
        [_cand("Orelsan", "Civilisation", ident="1"),
         _cand("Orelsan", "Civilisation", ident="1")],
        want_artist_page=False)
    assert chosen is not None


def test_verdict_falls_back_to_url_when_ident_missing():
    a = m.Candidate(m.PLATFORM_DEEZER, "album", "https://d/1", "Orelsan",
                    "Civilisation", ident="")
    b = m.Candidate(m.PLATFORM_DEEZER, "album", "https://d/2", "Orelsan",
                    "Civilisation", ident="")
    chosen, reason, _ = m.verdict(ALBUM_RECO, [a, b], want_artist_page=False)
    assert (chosen, reason) == (None, m.REASON_AMBIGUOUS)


def test_verdict_artist_page_matches_on_reco_title():
    chosen, reason, _ = m.verdict(
        {"title": "Gorillaz"}, [_cand("Gorillaz", kind="artist")],
        want_artist_page=True)
    assert reason == m.REASON_LINKED
    assert chosen.artist == "Gorillaz"


def test_verdict_artist_page_matches_on_creator():
    chosen, _, _ = m.verdict(
        {"title": "Feel Good", "creator": "Jungle"},
        [_cand("Jungle", kind="artist")], want_artist_page=True)
    assert chosen is not None


def test_verdict_artist_page_refuses_unrelated_name():
    chosen, reason, detail = m.verdict(
        {"title": "Vérino"}, [_cand("Verino Mercury", kind="artist")],
        want_artist_page=True)
    assert (chosen, reason) == (None, m.REASON_NO_MATCH)
    assert "page artiste" in detail
