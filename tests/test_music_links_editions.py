"""Appariement assoupli des liens d'écoute — cas réels de S6-E04.

Trois refus de la chaîne, tous injustifiés, ont coûté neuf liens posés à la
main : un titre enrichi (« reprise française de… »), une réédition prise pour
une ambiguïté (« Roméo kiffe Juliette » sur album ET compilation), et les
pages artiste Apple jamais lues (mauvais champ iTunes). Chaque assouplissement
garde une seconde preuve — l'artiste — et ses limites sont testées ici aussi.
"""
from __future__ import annotations

import pytest

import music_links_clients as clients
import music_links_matching as m
from enrich_creators import any_title_matches
from music_links_editions import same_recording
from title_variants import cores_match, is_other_version, split_suffix, variants

ROMEO = {"title": "Roméo Kiffe Juliette", "creator": "Grand Corps Malade",
         "types": ["musique"], "status": "validated"}
SAUF = {"title": "Sauf si c'est toi (reprise française de Until I Found You)",
        "creator": "Carla de Coignac & Félix Radu", "types": ["musique"],
        "status": "validated"}


def cand(title, artist="Grand Corps Malade", ident="1", **kw):
    return m.Candidate(m.PLATFORM_SPOTIFY, "track", f"https://x/{ident}", artist,
                       title, ident=ident, **kw)


# ===== title_variants ========================================================
@pytest.mark.parametrize("title,expected", [
    ("Acharnés (Beef)", ("Acharnés", "Beef")),
    ("Sauf si c'est toi - Adaptation de Until i found you",
     ("Sauf si c'est toi", "Adaptation de Until i found you")),
    ("Bref (saison 2)", ("", "")),        # une partie de l'œuvre : pas de découpe
    ("Midi 20 (Vol. 2)", ("", "")),
    ("Vu (live)", ("", "")),              # noyau trop court
    ("Fleabag", ("", "")),
    (None, ("", "")),
])
def test_split_suffix(title, expected):
    assert split_suffix(title) == expected


def test_variants_are_normalized_and_unique():
    assert variants("Acharnés (Beef)") == ["acharnes beef", "acharnes", "beef"]
    assert variants("Fleabag") == ["fleabag"]
    assert variants("Bref (saison 2)") == ["bref saison 2"]


def test_other_versions_are_recognized():
    assert is_other_version("Ils s'aimaient toujours", "Ils s'aimaient toujours (Version piano)")
    assert not is_other_version("Love (live)", "Love - Live")   # la reco veut le live
    assert not is_other_version("Love", "Love (Adaptation de X)")
    assert not is_other_version("Love", "Love")


def test_cores_match():
    assert cores_match(SAUF["title"], "Sauf si c'est toi - Adaptation de Until i found you")
    assert cores_match("Fleabag", "Fleabag")
    assert not cores_match("Ils s'aimaient toujours", "Ils s'aimaient toujours (Version piano)")
    assert not cores_match("Vu", "Vu")  # trop court pour prouver quoi que ce soit


# ===== verdict : noyau de titre =============================================
def test_core_title_links_when_the_artist_matches():
    c = cand("Sauf si c'est toi - Adaptation de Until i found you", "Carla De Coignac")
    assert m.verdict(SAUF, [c], want_artist_page=False)[:2] == (c, m.REASON_LINKED)


def test_core_title_never_beats_an_exact_title():
    exact = cand("Roméo kiffe Juliette", ident="a")
    live = cand("Roméo kiffe Juliette (Live à l'Olympia)", ident="b")
    assert m.verdict(ROMEO, [live, exact], want_artist_page=False)[0] is exact


def test_core_title_still_requires_the_artist():
    c = cand("Sauf si c'est toi (Adaptation de Until i found you)", "Quelqu'un d'autre")
    assert m.verdict(SAUF, [c], want_artist_page=False)[1] == m.REASON_ARTIST_MISMATCH


def test_core_title_does_not_slip_to_another_version():
    reco = {**ROMEO, "title": "Ils s'aimaient toujours", "creator": "Carla de Coignac"}
    c = cand("Ils s'aimaient toujours (Version piano)", "Carla de Coignac")
    assert m.verdict(reco, [c], want_artist_page=False)[1] == m.REASON_NO_MATCH


# ===== verdict : rééditions =================================================
def test_same_isrc_on_album_and_compilation_keeps_the_original():
    album = cand("Roméo kiffe Juliette", ident="a", release="2010-10-18", isrc="FRT461080000")
    best_of = cand("Roméo kiffe Juliette", ident="b", release="2019-08-30",
                   isrc="FRT461080000", compilation=True)
    assert m.verdict(ROMEO, [best_of, album], want_artist_page=False)[:2] == (
        album, m.REASON_LINKED)


def test_without_isrc_the_earliest_release_wins():
    """Cas Apple : pas d'ISRC, deux collections — 3ème temps (2010) d'abord."""
    vieux = cand("Roméo kiffe Juliette", ident="a", release="2010-10-18")
    neuf = cand("Roméo kiffe Juliette", ident="b", release="2019-08-30")
    sans_date = cand("Roméo kiffe Juliette", ident="c")
    assert m.verdict(ROMEO, [neuf, sans_date, vieux], want_artist_page=False)[0] is vieux


def test_two_isrc_are_two_recordings_and_stay_ambiguous():
    a = cand("Roméo kiffe Juliette", ident="a", isrc="FR1")
    b = cand("Roméo kiffe Juliette", ident="b", isrc="FR2")
    assert m.verdict(ROMEO, [a, b], want_artist_page=False)[1] == m.REASON_AMBIGUOUS


def test_same_recording_refuses_artist_pages_and_mixed_titles():
    assert same_recording([cand("")]) is None
    assert same_recording([cand("", ident="a"), cand("", ident="b")]) is None
    assert same_recording([cand("Roméo", ident="a"), cand("Juliette", ident="b")]) is None
    assert same_recording([cand("Roméo", "A", ident="a"), cand("Roméo", "B", ident="b")]) is None


def test_artist_pages_still_refuse_two_identities():
    reco = {"title": "Mona", "creator": None, "types": ["artiste"], "status": "validated"}
    a = m.Candidate(m.PLATFORM_SPOTIFY, "artist", "https://x/a", "Mona", ident="a")
    b = m.Candidate(m.PLATFORM_SPOTIFY, "artist", "https://x/b", "Mona", ident="b")
    assert m.verdict(reco, [a, b], want_artist_page=True)[1] == m.REASON_AMBIGUOUS


# ===== clients ===============================================================
def test_itunes_artist_url_is_read_from_artist_link_url():
    payload = {"artistName": "Carla De Coignac", "artistId": 1518253112,
               "artistLinkUrl": "https://music.apple.com/fr/artist/carla-de-coignac/1518253112?uo=4"}
    c = clients.itunes_candidate(payload, "artist")
    assert c is not None and c.url.endswith("1518253112?uo=4") and c.ident == "1518253112"


def test_itunes_track_carries_its_release_date():
    payload = {"trackViewUrl": "https://music.apple.com/x", "artistName": "Grand Corps Malade",
               "trackName": "Roméo kiffe Juliette", "collectionId": 1444206162,
               "releaseDate": "2010-10-18T07:00:00Z"}
    assert clients.itunes_candidate(payload, "track").release == "2010-10-18"


def test_spotify_track_carries_release_isrc_and_compilation_flag():
    payload = {"external_urls": {"spotify": "https://open.spotify.com/track/x"}, "id": "x",
               "name": "Roméo kiffe Juliette", "artists": [{"name": "Grand Corps Malade"}],
               "external_ids": {"isrc": "FRT461080000"},
               "album": {"release_date": "2019-08-30", "album_type": "compilation"}}
    c = clients.spotify_candidate(payload, "track")
    assert (c.release, c.isrc, c.compilation) == ("2019-08-30", "FRT461080000", True)


def test_spotify_album_reads_its_own_release():
    payload = {"external_urls": {"spotify": "https://open.spotify.com/album/y"}, "id": "y",
               "name": "3ème temps", "artists": [{"name": "Grand Corps Malade"}],
               "release_date": "2010-10-18", "album_type": "album"}
    c = clients.spotify_candidate(payload, "album")
    assert (c.release, c.isrc, c.compilation) == ("2010-10-18", "", False)


# ===== passe vidéo : titre VF (titre original) ==============================
def test_video_title_parts_match_when_anchored():
    assert any_title_matches("Acharnés (Beef)", ["Acharnés", "BEEF"])
    assert any_title_matches("Acharnés (Beef)", ["BEEF"])
    assert not any_title_matches("Bref (saison 2)", ["Bref"])
    assert not any_title_matches("Mortel", ["Mortal Kombat"])
