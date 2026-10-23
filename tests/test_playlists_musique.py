"""Tests pour `tools/playlists_musique.py` — briques pures, sans reseau."""
from __future__ import annotations

import playlists_musique as pm


class FauxEmbed:
    """Pages embed simulees : (genre, id) -> [(id_titre, titre)]."""

    def __init__(self, pistes, artistes=None, infos=None):
        self._pistes = pistes
        self._artistes = artistes or {}
        self._infos = infos or {}

    def titre_artiste(self, tid):
        return self._infos.get(tid, (tid, ""))

    def pistes(self, genre, sid):
        return self._pistes.get((genre, sid), [])

    def artiste_de_album(self, sid):
        return self._artistes.get(sid)


def entree(url, type_="album", titre="X", playlist="Saison 5"):
    return {"item": titre, "titre": titre, "url": url, "type": type_, "playlist": playlist, "date": ""}


def test_forme_accepte_le_prefixe_de_langue():
    assert pm.forme("https://open.spotify.com/intl-fr/album/abc123") == ("album", "abc123")
    assert pm.forme("https://www.deezer.com/album/1") == (None, None)


def test_morceau_donne_son_titre():
    assert pm.titres(entree("https://open.spotify.com/track/t1", "musique"), FauxEmbed({})) == ["t1"]


def test_artiste_donne_ses_trois_titres_phares():
    embed = FauxEmbed({("artist", "a"): [("t1", "A"), ("t2", "B"), ("t3", "C"), ("t4", "D")]})
    assert pm.titres(entree("https://open.spotify.com/artist/a", "artiste"), embed) == ["t1", "t2", "t3"]


def test_album_prend_le_top_de_l_artiste_puis_les_premiers_titres():
    embed = FauxEmbed({("album", "al"): [("t1", "A"), ("t2", "B"), ("t3", "C"), ("t4", "D")],
                       ("artist", "ar"): [("t4", "D"), ("x", "Y")]}, {"al": "ar"})
    assert pm.titres(entree("https://open.spotify.com/album/al"), embed) == ["t4", "t1", "t2"]


def test_morceau_avec_un_lien_d_album_prend_le_titre_du_meme_nom():
    embed = FauxEmbed({("album", "al"): [("t1", "Intro"), ("t2", "L’anxiété (live)")]})
    e = entree("https://open.spotify.com/album/al", "musique", titre="L'anxiété")
    assert pm.titres(e, embed) == ["t2"]


def test_playlists_dedoublonne_et_cumule_dans_l_ordre():
    embed = FauxEmbed({})
    liste = [entree("https://open.spotify.com/track/t1", "musique", "A", pm.AVANT_SAISONS),
             entree("https://open.spotify.com/track/t2", "musique", "B", "Saison 5"),
             entree("https://open.spotify.com/track/t1", "musique", "C", "Saison 5")]
    sortie = pm.playlists(liste, embed)
    assert sortie[pm.TOUT] == ["t1", "t2"]
    assert sortie["Saison 5"] == ["t2", "t1"]


def test_playlists_ne_garde_qu_une_version_d_une_chanson():
    embed = FauxEmbed({}, infos={"t1": ("Le prochain rêve", "Grand Corps Malade, Styleto"),
                                 "t2": ("Le prochain rêve (feat. Styleto)", "Grand Corps Malade, Styleto"),
                                 "t3": ("Le prochain rêve", "Autre Artiste")})
    liste = [entree(f"https://open.spotify.com/track/{t}", "musique", t) for t in ("t1", "t2", "t3")]
    assert pm.playlists(liste, embed)["Saison 5"] == ["t1", "t3"]


def test_a_ajouter_en_fin_de_liste():
    assert pm.a_ajouter(["a", "b"], ["a", "b", "c"]) == (["c"], True)


def test_a_ajouter_signale_une_insertion_au_milieu():
    nouveaux, en_fin = pm.a_ajouter(["a", "c"], ["a", "b", "c"])
    assert nouveaux == ["b"] and not en_fin
