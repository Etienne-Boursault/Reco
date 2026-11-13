"""Tests de tools/carrousel_scenes.py : le HTML des pages du carrousel avec visuels."""
from __future__ import annotations

import carrousel_scenes as cs

R = {"type": "Film", "titre": "The Father", "createur": "Florian Zeller",
     "citation": "« <b> » exceptionnel", "qui": "Kyan Khojandi", "moment": "1:19:20"}
IMG = [("file:///a.jpg", "Affiche de The Father")]


def test_taille_du_titre_tient_en_deux_lignes():
    assert cs.taille("Rebelle") == 150
    assert cs.taille("Menteuse, menteuse") == 132
    assert cs.taille("Eternal Sunshine of the Spotless Mind") == 116
    assert cs.taille("Anticonstitutionnellement anticonstitutionnellement") == 88


def test_page_avec_affiche_floute_le_fond_et_echappe_le_texte():
    page = cs.page_reco(R, 15, 18, IMG, "affiche")
    assert page.count("file:///a.jpg") == 2 and "blur(46px)" in page
    assert "height: 460px" in page and "15 / 18" in page
    assert "&lt;b&gt;" in page and "<b>" not in page
    assert 'alt="Affiche de The Father"' in page and "Florian Zeller" in page


def test_chaque_mise_en_scene_a_son_cadre():
    assert "border-radius: 50%" in cs.page_reco(R, 1, 2, IMG, "rond")
    assert "width: 440px; height: 440px" in cs.page_reco(R, 1, 2, IMG, "carre")
    assert "width: 660px" in cs.page_reco(R, 1, 2, IMG, "cadre")
    assert "#f6f4ee" in cs.page_reco(R, 1, 2, IMG, "tuile")
    photo = cs.page_reco(R, 1, 2, IMG, "photo")
    assert "margin-top: -60px" in photo and "blur(" not in photo
    double = cs.page_reco(R, 1, 2, IMG + [("file:///b.jpg", "Autre")], "double")
    assert "file:///b.jpg" in double and double.count("width: 400px") == 2


def test_page_sans_image_garde_le_rythme():
    sans = cs.page_reco({**R, "type": "Album", "createur": ""}, 9, 18, [], "sans")
    assert "<img" not in sans and "<circle" in sans and "Florian" not in sans
    autre = cs.page_reco({**R, "type": "Autre"}, 1, 18, [], "sans")
    assert "<circle" not in autre and "<path" in autre


def test_couverture_avec_et_sans_vignette():
    ep = {"numero": "S6 · E09", "titre": "Un & deux", "invites": ["Miki", "Adèle Castillon"]}
    avec = cs.couverture(ep, 18, "file:///v.jpg")
    assert "file:///v.jpg" in avec and "Un &amp; deux" in avec and ">18<" in avec and "Adèle Castillon" in avec
    assert "<img" not in cs.couverture(ep, 18, None)


def test_fin_nomme_les_sources():
    fin = cs.fin({"numero": "S6 · E09"}, 18, "Images : affiches TMDB")
    assert "Les 18 recos" in fin and "Images : affiches TMDB" in fin
    assert "Images" not in cs.fin({"numero": "S6 · E09"}, 18, "")


def test_un_titre_long_et_une_citation_longue_tiennent_dans_la_page():
    """Revue de la PR #204 : sinon « Reco de … » sort de la page, coupé sans avertissement."""
    long = {**R, "titre": "Eternal Sunshine of the Spotless Mind", "createur": "Michel Gondry et Charlie Kaufman",
            "citation": "Non, c’était un film de Charlie Kaufman qui s’appelle Synecdoche New York, et qui est "
                        "trop bien, parce que c’est que des mises en abîme de trucs, et moi j’adore ça, vraiment."}
    titre, citation = cs.ajuster(long, "affiche")
    assert cs.hauteur_du_texte(long, titre, citation) <= cs.place("affiche")
    assert citation < 42
    assert cs.ajuster(R, "affiche") == (cs.taille("The Father"), 42)
    page = cs.page_reco(long, 1, 2, IMG, "affiche")
    assert f"font-size: {citation}px" in page and f"font-size: {titre}px" in page


def test_une_citation_demesuree_prend_les_tailles_minimales():
    enorme = {**R, "citation": "mot " * 400}
    assert cs.ajuster(enorme, "sans") == (cs.TITRES[-1], cs.CITATIONS[-1])


def test_place_par_mise_en_scene():
    assert cs.place("photo") == 690 and cs.place("sans") == 566 and cs.place("affiche") == cs.place("rond") == 606


def test_un_mot_trop_long_passe_a_la_ligne_au_lieu_de_sortir_de_la_page():
    page = cs.page_reco({**R, "titre": "Anticonstitutionnellementissimement"}, 1, 2, IMG, "affiche")
    assert page.count("overflow-wrap: anywhere") >= 2


def test_le_navigateur_reduit_encore_le_texte_s_il_deborde():
    """L'estimation ne voit pas la police réelle : Edge mesure et réduit, une fois les polices chargées."""
    page = cs.page_reco(R, 1, 2, IMG, "affiche")
    assert "document.fonts.ready" in page and "scrollHeight" in page
    assert 'data-bas' in page and 'data-titre' in page and 'data-citation' in page


def test_trop_long_signale_un_texte_qui_deborde_meme_au_plus_petit():
    assert cs.trop_long({**R, "citation": "mot " * 400}, "sans")
    assert not cs.trop_long(R, "affiche")
