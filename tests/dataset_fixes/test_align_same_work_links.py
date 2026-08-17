"""Tests de tools/align_same_work_links.py.

Le danger de ce module est de FUSIONNER DEUX ŒUVRES HOMONYMES. La majorité des
tests éprouvent donc les refus, pas les alignements.
"""
from __future__ import annotations

import json

import pytest

import align_same_work_links as asw
import dataset_fixes


def _doc(rid, titre, types, urls=(), creator=None, status="validated"):
    return {
        "id": rid, "title": titre, "types": list(types), "status": status,
        "creator": creator,
        "links": [{"url": u, "label": "L", "kind": "info", "ethics": "neutral"}
                  for u in urls],
    }


# ---------------------------------------------------------------------------
# fold_titre
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(("brut", "attendu"), [
    ("The Office", "the office"),
    ("L'homme-dé", "l homme de"),
    ("  Cher   Journal  ", "cher journal"),
    ("Bérengère", "berengere"),
    (None, ""),
])
def test_fold_titre(brut, attendu):
    assert asw.fold_titre(brut) == attendu


# ---------------------------------------------------------------------------
# compatibles — LE garde-fou
# ---------------------------------------------------------------------------
def test_meme_type_et_meme_createur_sont_compatibles():
    g = [_doc("a", "X", ["serie"], creator="Greg Daniels"),
         _doc("b", "X", ["serie"], creator="Greg Daniels")]
    assert asw.compatibles(g) is None


def test_types_disjoints_refuses():
    """« Happy End » : un ALBUM d'Albin de la Simone et un PODCAST de Blandine
    Lehout. Fusionner enverrait l'auditeur d'un podcast vers un album."""
    g = [_doc("a", "Happy End", ["album"]), _doc("b", "Happy End", ["podcast"])]
    assert "homonymes" in (asw.compatibles(g) or "")


def test_types_qui_se_recoupent_partiellement_acceptes():
    """`['film','livre']` et `['livre']` désignent la même œuvre déclinée."""
    g = [_doc("a", "X", ["film", "livre"]), _doc("b", "X", ["livre"])]
    assert asw.compatibles(g) is None


def test_createurs_differents_refuses():
    g = [_doc("a", "X", ["livre"], creator="Untel"),
         _doc("b", "X", ["livre"], creator="Autre")]
    assert "créateurs différents" in (asw.compatibles(g) or "")


def test_un_createur_absent_ne_bloque_pas():
    """Une reco sans créateur n'est pas une reco d'un AUTRE créateur : elle est
    incomplète. La refuser priverait le groupe d'un alignement légitime."""
    g = [_doc("a", "X", ["livre"], creator="Untel"),
         _doc("b", "X", ["livre"], creator=None)]
    assert asw.compatibles(g) is None


def test_un_nom_contenu_dans_un_autre_est_le_meme_createur():
    """« patrick » ⊂ « patrick baud » : une fiche incomplète, pas une autre
    personne. « greg daniels » ⊂ « greg daniels michael schur » : un
    co-créateur ajouté. Refuser ces groupes privait d'alignement des œuvres
    évidentes — Bref, Better Call Saul, The Office."""
    for noms in (("Patrick", "Patrick Baud"),
                 ("Greg Daniels", "Greg Daniels, Michael Schur"),
                 ("Vince Gilligan", "Vince Gilligan, Peter Gould")):
        g = [_doc(f"a{i}", "Un Titre Long", ["serie"], creator=n)
             for i, n in enumerate(noms)]
        assert asw.compatibles(g) is None, noms


def test_deux_noms_sans_recouvrement_restent_refuses():
    """La tolérance à l'inclusion ne doit pas ouvrir la porte aux homonymes."""
    g = [_doc("a", "X", ["livre"], creator="Albin de la Simone"),
         _doc("b", "X", ["livre"], creator="Blandine Lehout")]
    assert "créateurs différents" in (asw.compatibles(g) or "")


def test_trois_noms_dont_un_seul_diverge_sont_refuses():
    g = [_doc("a", "X", ["serie"], creator="Greg Daniels"),
         _doc("b", "X", ["serie"], creator="Greg Daniels, Michael Schur"),
         _doc("c", "X", ["serie"], creator="Quelqu un d autre")]
    assert "créateurs différents" in (asw.compatibles(g) or "")


def test_createurs_differant_par_un_accent_sont_compatibles():
    """Sinon une simple perte d'accent ferait renoncer à un groupe valide."""
    g = [_doc("a", "X", ["livre"], creator="Bérengère Krief"),
         _doc("b", "X", ["livre"], creator="Berengere Krief")]
    assert asw.compatibles(g) is None


def test_deux_identifiants_contradictoires_refusent_le_groupe():
    """LE garde-fou qui manquait, et qui a coûté une régression.

    « Bref » (2011, Canal+) et « Bref.2 » (2025, Disney+) partagent le titre ET
    le créateur : aucun des trois garde-fous existants ne les distinguait. La
    reco de Bref.2 a donc reçu les fiches IMDb et TMDB de la série de 2011.

    Or deux fiches AlloCiné d'identifiants différents désignent forcément deux
    œuvres : c'est un fait, pas une heuristique. Même chose pour IMDb, TMDB,
    Deezer ou Spotify.
    """
    g = [_doc("a", "Bref", ["serie"], creator="Kyan Khojandi",
              urls=["https://www.allocine.fr/series/ficheserie_gen_cserie=10520.html"]),
         _doc("b", "Bref", ["serie"], creator="Kyan Khojandi",
              urls=["https://www.allocine.fr/series/ficheserie_gen_cserie=1000000468.html"])]
    assert "identifiants" in (asw.compatibles(g) or "")


@pytest.mark.parametrize(("a", "b"), [
    ("https://www.imdb.com/title/tt2044128/", "https://www.imdb.com/title/tt31262444/"),
    ("https://www.themoviedb.org/tv/60715", "https://www.themoviedb.org/tv/271593"),
    ("https://www.deezer.com/album/123", "https://www.deezer.com/album/456"),
    ("https://open.spotify.com/album/aaa", "https://open.spotify.com/album/bbb"),
])
def test_le_garde_fou_couvre_les_principaux_hotes(a, b):
    g = [_doc("a", "Un Titre Long", ["film"], urls=[a]),
         _doc("b", "Un Titre Long", ["film"], urls=[b])]
    assert "identifiants" in (asw.compatibles(g) or "")


def test_le_meme_identifiant_ne_bloque_pas():
    """Deux recos de la MÊME œuvre, l'une plus fournie que l'autre : c'est
    exactement le cas que ce module doit traiter, pas refuser."""
    g = [_doc("a", "Un Titre Long", ["film"],
              urls=["https://www.imdb.com/title/tt1/", "https://netflix.com/x"]),
         _doc("b", "Un Titre Long", ["film"], urls=["https://www.imdb.com/title/tt1/"])]
    assert asw.compatibles(g) is None


def test_identifiants_survit_a_un_lien_mal_forme():
    """Le corpus contient de la donnée héritée : une entrée de `links` qui
    n'est pas un objet ne doit pas faire tomber l'extraction."""
    doc = {"id": "a", "links": ["hérité",
                                {"url": "https://www.imdb.com/title/tt42/"},
                                {"pas_d_url": True}]}
    assert asw.identifiants(doc) == {"imdb": {"tt42"}}


def test_identifiants_sur_une_reco_sans_liens():
    assert asw.identifiants({"id": "a"}) == {}


def test_un_hote_sans_identifiant_ne_bloque_jamais():
    """Deux URL Netflix différentes peuvent être deux saisons de la même série,
    ou deux pages du même titre : rien ne permet d'en conclure un conflit."""
    g = [_doc("a", "Un Titre Long", ["serie"], urls=["https://netflix.com/fr/title/1"]),
         _doc("b", "Un Titre Long", ["serie"], urls=["https://netflix.com/fr/title/2"])]
    assert asw.compatibles(g) is None


def test_une_reco_sans_type_refuse_le_groupe():
    g = [_doc("a", "X", ["livre"]), _doc("b", "X", [])]
    assert "sans type" in (asw.compatibles(g) or "")


# ---------------------------------------------------------------------------
# grouper
# ---------------------------------------------------------------------------
def test_grouper_ignore_les_titres_trop_courts():
    """« Vu », « Art », « 60 » se répètent par coïncidence."""
    g = asw.grouper([_doc("a", "Vu", ["video"]), _doc("b", "Vu", ["video"])])
    assert g == {}


def test_grouper_reunit_les_variantes_de_ponctuation_et_daccent():
    g = asw.grouper([_doc("a", "L'homme-dé", ["livre"]),
                     _doc("b", "L homme de", ["livre"])])
    assert len(g) == 1 and len(next(iter(g.values()))) == 2


def test_grouper_ignore_les_titres_uniques():
    assert asw.grouper([_doc("a", "Unique", ["livre"])]) == {}


# ---------------------------------------------------------------------------
# transform
# ---------------------------------------------------------------------------
def test_transform_pose_les_liens_voulus():
    voulus = [{"url": "https://a/", "label": "A", "kind": "info", "ethics": "neutral"},
              {"url": "https://b/", "label": "B", "kind": "info", "ethics": "neutral"}]
    doc = _doc("ubm-1", "X", ["livre"], ["https://a/"])
    ch = asw.transform_factory({"ubm-1": voulus}, {})(doc)
    assert [link["url"] for link in doc["links"]] == ["https://a/", "https://b/"]
    assert len(ch) == 1 and ch[0].field == "links"


def test_transform_est_idempotent():
    voulus = [{"url": "https://a/", "label": "A", "kind": "info", "ethics": "neutral"}]
    doc = _doc("ubm-1", "X", ["livre"], ["https://a/"])
    assert asw.transform_factory({"ubm-1": voulus}, {})(doc) == []


def test_transform_ignore_une_reco_hors_plan():
    doc = _doc("ubm-9", "X", ["livre"], ["https://a/"])
    assert asw.transform_factory({"ubm-1": []}, {})(doc) == []
    assert len(doc["links"]) == 1


# ---------------------------------------------------------------------------
# planifier — bout en bout, sur un corpus temporaire
# ---------------------------------------------------------------------------
@pytest.fixture
def corpus(tmp_path, monkeypatch):
    racine = tmp_path / "recos"
    (racine / "src").mkdir(parents=True)
    monkeypatch.setattr(dataset_fixes, "RECOS_DIR", racine)

    def ecrire(doc):
        (racine / "src" / f"{doc['id']}.json").write_text(
            json.dumps(doc, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8")
    return racine, ecrire


def test_planifier_aligne_sur_lunion(corpus):
    _, ecrire = corpus
    ecrire(_doc("ubm-1", "The Office", ["serie"], ["https://netflix/"]))
    ecrire(_doc("ubm-2", "The Office", ["serie"], ["https://imdb/"]))
    cibles, rapport = asw.planifier()
    assert set(cibles) == {"ubm-1", "ubm-2"}
    for voulus in cibles.values():
        assert [link["url"] for link in voulus] == ["https://netflix/", "https://imdb/"]
    assert rapport["ecartes"] == []


def test_planifier_preserve_lordre_de_premiere_apparition(corpus):
    """L'ordre des liens porte une intention éditoriale — l'indépendant avant
    le grand distributeur. Un tri alphabétique la détruirait."""
    _, ecrire = corpus
    ecrire(_doc("ubm-1", "Un Titre Long", ["livre"], ["https://zzz/", "https://aaa/"]))
    ecrire(_doc("ubm-2", "Un Titre Long", ["livre"], ["https://mmm/"]))
    cibles, _ = asw.planifier()
    assert [link["url"] for link in cibles["ubm-2"]] == [
        "https://zzz/", "https://aaa/", "https://mmm/"]


def test_planifier_ecarte_les_homonymes_et_le_dit(corpus):
    _, ecrire = corpus
    ecrire(_doc("ubm-1", "Happy End", ["album"], ["https://deezer/"]))
    ecrire(_doc("ubm-2", "Happy End", ["podcast"], ["https://acast/"]))
    cibles, rapport = asw.planifier()
    assert cibles == {}
    assert len(rapport["ecartes"]) == 1
    assert "homonymes" in rapport["ecartes"][0]["motif"]


def test_planifier_ignore_les_recos_ecartees(corpus):
    """Aligner une reco `discarded` n'apporte rien : elle ne s'affiche nulle
    part, et la toucher brouillerait le diff."""
    _, ecrire = corpus
    ecrire(_doc("ubm-1", "Un Titre Long", ["livre"], ["https://a/"]))
    ecrire(_doc("ubm-2", "Un Titre Long", ["livre"], ["https://b/"],
                status="discarded"))
    cibles, _ = asw.planifier()
    assert cibles == {}


def test_planifier_ne_touche_pas_un_groupe_deja_aligne(corpus):
    _, ecrire = corpus
    for rid in ("ubm-1", "ubm-2"):
        ecrire(_doc(rid, "Un Titre Long", ["livre"], ["https://a/", "https://b/"]))
    cibles, _ = asw.planifier()
    assert cibles == {}


def test_planifier_ignore_un_groupe_a_un_seul_lien(corpus):
    """Rien à mutualiser : aligner produirait un fichier réécrit pour rien."""
    _, ecrire = corpus
    ecrire(_doc("ubm-1", "Un Titre Long", ["livre"], ["https://a/"]))
    ecrire(_doc("ubm-2", "Un Titre Long", ["livre"], ["https://a/"]))
    cibles, _ = asw.planifier()
    assert cibles == {}


def test_planifier_survit_a_un_json_illisible(corpus):
    racine, ecrire = corpus
    ecrire(_doc("ubm-1", "Un Titre Long", ["livre"], ["https://a/"]))
    ecrire(_doc("ubm-2", "Un Titre Long", ["livre"], ["https://b/"]))
    (racine / "src" / "casse.json").write_text("{pas du json", encoding="utf-8")
    cibles, _ = asw.planifier()
    assert set(cibles) == {"ubm-1", "ubm-2"}


def test_build_parser_dry_run_par_defaut():
    assert asw.build_parser().parse_args([]).apply is False
