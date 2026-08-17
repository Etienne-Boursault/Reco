"""Tests de tools/fix_duplicate_links.py.

L'enjeu de ce module n'est pas de supprimer, c'est de NE PAS supprimer ce qui
est complémentaire. La moitié des tests vérifient donc qu'il ne touche à rien.
"""
from __future__ import annotations

import pytest

import fix_duplicate_links as fdl

FICHE = "https://www.allocine.fr/film/fichefilm_gen_cfilm=6608.html"
ONGLET = "https://www.allocine.fr/film/fichefilm-6608/telecharger-vod/"
FICHE_SERIE = "https://www.allocine.fr/series/ficheserie_gen_cserie=19344.html"
ONGLET_SERIE = "https://www.allocine.fr/series/ficheserie-19344/streaming/"
PDL = "https://www.placedeslibraires.fr/livre/{}-un-titre-un-auteur/"


def _doc(urls, rid="ubm-1"):
    return {"id": rid, "title": "T",
            "links": [{"url": u, "label": "L", "kind": "info", "ethics": "neutral"}
                      for u in urls]}


def _urls(doc):
    return [link["url"] for link in doc["links"]]


# ---------------------------------------------------------------------------
# allocine_key
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(("url", "attendu"), [
    (FICHE, ("fiche", "6608")),
    (ONGLET, ("onglet", "6608")),
    (FICHE_SERIE, ("fiche", "19344")),
    (ONGLET_SERIE, ("onglet", "19344")),
])
def test_allocine_key_distingue_fiche_et_onglet(url, attendu):
    assert fdl.allocine_key(url) == attendu


@pytest.mark.parametrize("url", [
    "https://www.allocine.fr/",
    "https://www.allocine.fr/article/fichearticle_gen_carticle=1000.html",
    "https://www.allocine.fr/rechercher/?q=dune",
    "https://www.imdb.com/title/tt0068646/",
    "",
])
def test_allocine_key_ignore_le_reste_du_site(url):
    """Page d'accueil, article, recherche : rien à dédoublonner."""
    assert fdl.allocine_key(url) is None


# ---------------------------------------------------------------------------
# Règle allocine
# ---------------------------------------------------------------------------
def test_retire_longlet_quand_la_fiche_est_la():
    doc = _doc([ONGLET, FICHE])
    changes = fdl.transform_factory(["allocine"])(doc)
    assert _urls(doc) == [FICHE]
    assert len(changes) == 1 and changes[0].after is None


def test_fonctionne_aussi_pour_les_series():
    doc = _doc([FICHE_SERIE, ONGLET_SERIE])
    fdl.transform_factory(["allocine"])(doc)
    assert _urls(doc) == [FICHE_SERIE]


def test_garde_un_onglet_ORPHELIN():
    """Sans la fiche correspondante, l'onglet est le SEUL accès à l'œuvre :
    le supprimer perdrait le lien au lieu de le dédoublonner."""
    doc = _doc([ONGLET])
    assert fdl.transform_factory(["allocine"])(doc) == []
    assert _urls(doc) == [ONGLET]


def test_ne_rapproche_PAS_deux_identifiants_differents():
    autre = "https://www.allocine.fr/film/fichefilm-99999/telecharger-vod/"
    doc = _doc([FICHE, autre])
    assert fdl.transform_factory(["allocine"])(doc) == []
    assert len(doc["links"]) == 2


# ---------------------------------------------------------------------------
# Règle editions
# ---------------------------------------------------------------------------
def test_ne_garde_que_ledition_retenue():
    doc = _doc([PDL.format("9782234092525"), PDL.format("9782253907824")],
               rid="ubm-1158")
    fdl.transform_factory(["editions"])(doc)
    assert _urls(doc) == [PDL.format("9782253907824")]


def test_une_reco_absente_de_la_table_nest_pas_touchee():
    """`ubm-1145` (Tao Te King) en est ABSENTE à dessein : deux traductions,
    pas deux formats. La table est curée, pas déduite."""
    assert "ubm-1145" not in fdl.EDITIONS
    doc = _doc([PDL.format("9782070465255"), PDL.format("9782130878414")],
               rid="ubm-1145")
    assert fdl.transform_factory(["editions"])(doc) == []
    assert len(doc["links"]) == 2


def test_ne_supprime_rien_si_lisbn_attendu_a_disparu():
    """La donnée a changé depuis la vérification : la table doit être revue
    AVANT d'agir, pas appliquée sur une base qu'on ne reconnaît plus."""
    doc = _doc([PDL.format("9782234092525"), PDL.format("9999999999999")],
               rid="ubm-1158")
    assert fdl.transform_factory(["editions"])(doc) == []
    assert len(doc["links"]) == 2


def test_ne_touche_rien_avec_un_seul_lien_libraire():
    doc = _doc([PDL.format("9782253907824")], rid="ubm-1158")
    assert fdl.transform_factory(["editions"])(doc) == []


def test_ne_touche_pas_les_liens_non_libraires_de_la_meme_reco():
    autre = "https://www.babelio.com/livres/x/123"
    doc = _doc([PDL.format("9782234092525"), PDL.format("9782253907824"), autre],
               rid="ubm-1158")
    fdl.transform_factory(["editions"])(doc)
    assert autre in _urls(doc)


# ---------------------------------------------------------------------------
# Ce qui doit rester INTACT — le vrai risque de ce module
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(("nom", "urls"), [
    ("page artiste + album (Deezer)",
     ["https://www.deezer.com/artist/7733482", "https://www.deezer.com/album/287075802"]),
    ("morceau + album (Spotify)",
     ["https://open.spotify.com/track/6d0", "https://open.spotify.com/album/0a5"]),
    ("série + tome 1 (Glénat)",
     ["https://www.glenat.com/manga/series/tokyo-revengers",
      "https://www.glenat.com/shonen/tokyo-revengers-tome-01-9782344035290"]),
    ("deux spectacles distincts (Netflix)",
     ["https://www.netflix.com/fr/title/81665820",
      "https://www.netflix.com/fr/title/82662593"]),
    ("recherche auteur + un livre (Place des Libraires)",
     ["https://www.placedeslibraires.fr/listeliv.php?auteurs=Fabien+Olicard",
      PDL.format("9782412022917")]),
    ("deux chaînes YouTube différentes",
     ["https://www.youtube.com/@Squeezie", "https://www.youtube.com/@SqueezieGaming"]),
])
def test_les_paires_complementaires_survivent(nom, urls):
    """Ces paires ont toutes été vues dans le corpus le 2026-08-15. Les
    supprimer appauvrirait la carte — c'est le risque que ce module doit
    éviter, davantage que celui de laisser un doublon."""
    doc = _doc(urls, rid="ubm-9999")
    assert fdl.transform_factory(list(fdl.RULES))(doc) == [], nom
    assert len(doc["links"]) == len(urls), nom


# ---------------------------------------------------------------------------
# Composition et robustesse
# ---------------------------------------------------------------------------
def test_les_deux_regles_se_composent():
    doc = _doc([ONGLET, FICHE, PDL.format("9782234092525"),
                PDL.format("9782253907824")], rid="ubm-1158")
    changes = fdl.transform_factory(list(fdl.RULES))(doc)
    assert len(changes) == 2
    assert _urls(doc) == [FICHE, PDL.format("9782253907824")]


def test_une_regle_seule_nactive_pas_lautre():
    doc = _doc([ONGLET, FICHE, PDL.format("9782234092525"),
                PDL.format("9782253907824")], rid="ubm-1158")
    fdl.transform_factory(["allocine"])(doc)
    assert PDL.format("9782234092525") in _urls(doc)


def test_est_idempotent():
    t = fdl.transform_factory(list(fdl.RULES))
    doc = _doc([ONGLET, FICHE])
    t(doc)
    assert t(doc) == []


def test_reco_sans_liens():
    assert fdl.transform_factory(list(fdl.RULES))({"id": "ubm-1"}) == []


def test_preserve_une_entree_de_links_qui_nest_pas_un_objet():
    """Le corpus contient de la donnée héritée mal formée : elle doit survivre
    au correctif, pas disparaître au passage."""
    doc = {"id": "ubm-1", "links": ["hérité", {"url": ONGLET}, {"url": FICHE}]}
    fdl.transform_factory(["allocine"])(doc)
    assert "hérité" in doc["links"]
    assert [link["url"] for link in doc["links"] if isinstance(link, dict)] == [FICHE]


def test_build_parser_defaut_dry_run_et_toutes_les_regles():
    args = fdl.build_parser().parse_args([])
    assert args.apply is False
    assert args.rule is None          # None → toutes les règles, cf. main
    assert fdl.build_parser().parse_args(["--rule", "allocine"]).rule == ["allocine"]
