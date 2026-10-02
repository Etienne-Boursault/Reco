"""Tests de la couche qui DÉCIDE : aucun réseau, aucun disque.

Chaque test vise un garde-fou précis, et les plus importants portent sur les
pièges mesurés le 2026-09-27 et le 2026-09-28 (cf. l'en-tête de
`boutique_matching`) : la fiche Steam renvoyée sous la clé d'un autre
identifiant, les bandes-son étiquetées comme des jeux, et l'URL que le libraire
résout lui-même.
"""
from __future__ import annotations

import boutique_matching as bm

PAGE_LIBRAIRE = """<html><head>
<title>Les solitudes de Petite Rivière - Kalindi Ramphul - JC Lattès</title>
<link rel="canonical" href="https://www.placedeslibraires.fr/livre/9782709677424-les-solitudes-de-petite-riviere-kalindi-ramphul/">
<script type="application/ld+json">{"@type":"Book","isbn":"9782709677424"}</script>
</head><body></body></html>"""


# ===== le piège Steam : la fiche revient sous une autre clé =================
def test_la_fiche_est_reconnue_meme_sous_la_cle_d_un_autre_identifiant():
    """Mesuré : appdetails(2521170) répond sous la clé 4943810, sa bande-son.

    Lire `payload[str(appid)]` rendait None — un faux négatif silencieux.
    """
    payload = {"4943810": {"success": True,
                           "data": {"type": "game", "name": "Looking For Fael",
                                    "steam_appid": 2521170,
                                    "developers": ["Swing Swing Submarine"]}}}

    fiche = bm.fiche_demandee(payload, 2521170)

    assert fiche is not None
    assert fiche["name"] == "Looking For Fael"


def test_une_fiche_qui_parle_d_un_autre_jeu_est_refusee():
    """Seul `data.steam_appid` dit de quel jeu Steam parle vraiment."""
    payload = {"2521170": {"success": True,
                           "data": {"type": "game", "steam_appid": 999,
                                    "name": "Autre chose"}}}

    assert bm.fiche_demandee(payload, 2521170) is None


def test_une_fiche_en_echec_est_refusee():
    assert bm.fiche_demandee({"210970": {"success": False}}, 210970) is None


# ===== la recherche Steam étiquette tout en « app » ========================
def test_la_bande_son_et_les_homonymes_sont_ecartes_par_le_titre():
    """« The Witness » ramène quatre « City Legends », « Fael » sa bande-son."""
    items = [{"id": 210970, "type": "app", "name": "The Witness"},
             {"id": 2926180, "type": "app",
              "name": "City Legends: Le Témoin Dans le Seigle Édition Collector"},
             {"id": 4943810, "type": "app", "name": "Looking For Fael Soundtrack"}]

    gardes = bm.candidats_au_bon_titre(items, "The Witness")

    assert gardes == [(210970, "The Witness")]


def test_le_titre_se_compare_sans_casse_ni_accent():
    items = [{"id": 2521170, "name": "Looking For Fael"}]

    assert bm.candidats_au_bon_titre(items, "looking for faël") == [
        (2521170, "Looking For Fael")]


def test_le_nombre_de_fiches_interrogees_est_borne():
    items = [{"id": i, "name": "Même nom"} for i in range(10)]

    assert len(bm.candidats_au_bon_titre(items, "Même nom")) == bm.MAX_FICHES_STEAM


def test_un_resultat_sans_identifiant_entier_est_ignore():
    items = [{"id": "210970", "name": "The Witness"}, {"name": "The Witness"}]

    assert bm.candidats_au_bon_titre(items, "The Witness") == []


# ===== studios ==============================================================
def test_le_studio_correspond_par_le_developpeur_ou_par_l_editeur():
    """Steam rend les deux, et le corpus peut nommer l'un ou l'autre."""
    studios = ["Swing Swing Submarine", "La Poule Noire", "ARTE France"]

    assert bm.studio_correspond(studios, "ARTE France")
    assert bm.studio_correspond(studios, "Swing Swing Submarine, La Poule Noire")
    assert not bm.studio_correspond(studios, "Ubisoft")


def test_deux_societes_ne_correspondent_pas_par_leur_seul_suffixe():
    """« Inc. » ne désigne personne : sans ce garde, le découpage sur les
    virgules faisait correspondre n'importe quelles raisons sociales."""
    assert bm.studio_correspond(["Thekla, Inc."], "Thekla, Inc.")
    assert not bm.studio_correspond(["Autre chose, Inc."], "Thekla, Inc.")
    assert not bm.studio_correspond(["Bidule Studios"], "Machin Studios")


def test_un_studio_entier_est_essaye_avant_ses_fragments():
    """Une virgule sépare deux studios chez nous, mais vit aussi dans une
    raison sociale."""
    assert bm.studio_correspond(["Thekla, Inc."], "Thekla, Inc.")
    assert bm.studio_correspond(["La Poule Noire"],
                                "Swing Swing Submarine, La Poule Noire")


def test_les_studios_sont_dedoublonnes_et_sans_trous():
    data = {"developers": ["Dogubomb", "", "Dogubomb"], "publishers": ["Raw Fury", None]}

    assert bm.studios_de(data) == ["Dogubomb", "Raw Fury"]


# ===== la fiche libraire, qui tranche =======================================
def test_la_page_libraire_livre_titre_auteur_et_editeur():
    titre, auteur, editeur = bm.fiche_libraire(PAGE_LIBRAIRE)

    assert titre == "Les solitudes de Petite Rivière"
    assert auteur == "Kalindi Ramphul"
    assert editeur == "JC Lattès"


def test_une_page_sans_titre_ne_corrobore_rien():
    assert bm.fiche_libraire("<html><body>rien</body></html>") == ("", "", "")
    assert not bm.page_corrobore("<html></html>", "Un titre", "Un auteur")


def test_la_page_corrobore_le_bon_livre():
    assert bm.page_corrobore(PAGE_LIBRAIRE, "Les Solitudes de Petite Rivière",
                             "Kalindi Ramphul")


def test_un_auteur_qui_ne_correspond_pas_fait_refuser_la_page():
    """Le cas qui compte : la redirection peut mener à une autre œuvre."""
    assert not bm.page_corrobore(PAGE_LIBRAIRE, "Les Solitudes de Petite Rivière",
                                 "Caroline Laurent")


def test_un_titre_different_fait_refuser_la_page():
    assert not bm.page_corrobore(PAGE_LIBRAIRE, "Les Jours mauves",
                                 "Kalindi Ramphul")


def test_une_page_qui_ne_nomme_pas_son_auteur_est_refusee():
    page = "<html><head><title>Un titre seul</title></head></html>"

    assert not bm.page_corrobore(page, "Un titre seul", "Quelqu'un")


# ===== l'URL vient du site, jamais de nous =================================
def test_l_url_canonique_declaree_par_le_site_est_preferee():
    url = bm.url_canonique(PAGE_LIBRAIRE,
                           "https://www.placedeslibraires.fr/livre/9782709677424/")

    assert url.endswith("9782709677424-les-solitudes-de-petite-riviere-kalindi-ramphul/")


def test_sans_canonique_on_garde_l_url_que_le_site_a_resolue():
    resolue = "https://www.placedeslibraires.fr/livre/9782253053552-x/"

    assert bm.url_canonique("<html></html>", resolue) == resolue


def test_l_isbn_du_jsonld_doit_concorder_avec_l_ean_demande():
    assert bm.jsonld_isbn_coherent(PAGE_LIBRAIRE, "9782709677424")
    assert not bm.jsonld_isbn_coherent(PAGE_LIBRAIRE, "9782253053552")


def test_une_page_sans_isbn_declare_ne_contredit_rien():
    """Absence n'est pas contradiction : le titre et l'auteur corroborent déjà."""
    assert bm.jsonld_isbn_coherent("<html></html>", "9782709677424")


# ===== EAN ==================================================================
def test_seuls_les_isbn_13_sont_retenus_et_normalises():
    """Un ISBN-10 donnerait un 404 trompeur chez le libraire."""
    assert bm.eans_valides(["978-2-253-05355-2", "2246399513", "", None,
                            "9782253053552"]) == ["9782253053552"]


def test_le_nombre_d_ean_essayes_est_borne():
    bruts = [f"97820000000{i:02d}"[:13] for i in range(10)]

    assert len(bm.eans_valides(bruts)) <= bm.MAX_EAN_ESSAYES


def test_google_books_doit_corroborer_titre_et_auteur():
    volume = {"volumeInfo": {
        "title": "Les solitudes de Petite Rivière",
        "authors": ["Kalindi Ramphul"],
        "industryIdentifiers": [{"type": "ISBN_13", "identifier": "9782709677424"},
                                {"type": "ISBN_10", "identifier": "2709677424"}]}}

    assert bm.volume_corrobore(volume, "Les Solitudes de Petite Rivière",
                               "Kalindi Ramphul") == ["9782709677424"]
    assert bm.volume_corrobore(volume, "Les Solitudes de Petite Rivière",
                               "Caroline Laurent") == []
    assert bm.volume_corrobore(volume, "Un autre livre", "Kalindi Ramphul") == []


def test_open_library_rend_des_candidats_des_editions_corroborees():
    """Ses ISBN mêlent les éditions — y compris l'allemande, mesuré."""
    docs = [{"title": "Les vaisseaux du coeur", "author_name": ["Benoîte Groult"],
             "isbn": ["9783426192511", "9782253053552"]},
            {"title": "Un homonyme", "author_name": ["Quelqu'un"],
             "isbn": ["9780000000001"]},
            # Même titre, autre auteur : écarté par l'auteur, pas par le titre.
            {"title": "Les vaisseaux du coeur", "author_name": ["Un imposteur"],
             "isbn": ["9780000000002"]}]

    trouves = bm.documents_corrobores(docs, "Les vaisseaux du cœur", "Benoîte Groult")

    assert trouves == ["9783426192511", "9782253053552"]


# ===== sélection et absence d'écrasement ===================================
def test_la_source_depend_du_type():
    assert bm.source_pour({"types": ["jeu"]}) is bm.SOURCE_STEAM
    assert bm.source_pour({"types": ["livre"]}) is bm.SOURCE_LIBRAIRE
    assert bm.source_pour({"types": ["album"]}) is None


def test_une_reco_deja_liee_a_la_boutique_est_reconnue():
    """On ne remplace jamais : la passe ne comble qu'une absence."""
    jeu = {"types": ["jeu"], "links": [
        {"url": "https://store.steampowered.com/app/210970/"}]}
    livre = {"types": ["livre"], "links": [
        {"url": "https://www.placedeslibraires.fr/livre/9782709677424-x/"}]}

    assert bm.deja_servie(jeu, bm.SOURCE_STEAM)
    assert bm.deja_servie(livre, bm.SOURCE_LIBRAIRE)
    assert not bm.deja_servie({"types": ["jeu"], "links": []}, bm.SOURCE_STEAM)


def test_un_lien_d_une_autre_boutique_ne_compte_pas_comme_servi():
    jeu = {"types": ["jeu"], "links": [{"url": "https://www.nintendo.com/x"}]}

    assert not bm.deja_servie(jeu, bm.SOURCE_STEAM)


def test_le_type_servi_est_le_premier_reconnu():
    assert bm.type_servi({"types": ["autre", "livre"]}) == "livre"
    assert bm.type_servi({"types": ["album"]}) is None


def test_l_hote_ignore_www_et_la_casse():
    assert bm.hote("https://WWW.PlaceDesLibraires.fr/livre/x/") == "placedeslibraires.fr"
    assert bm.hote("pas une url") == "pas une url"


def test_la_forme_des_liens_suit_le_corpus():
    """18 liens Steam en buy/neutral, 67 Place des Libraires en buy/indie."""
    assert (bm.SOURCE_STEAM.kind, bm.SOURCE_STEAM.ethics) == ("buy", "neutral")
    assert (bm.SOURCE_LIBRAIRE.kind, bm.SOURCE_LIBRAIRE.ethics) == ("buy", "indie")
    lien = bm.Lien(bm.SOURCE_STEAM.nom, bm.SOURCE_STEAM.kind, bm.SOURCE_STEAM.ethics,
                   bm.SOURCE_STEAM.label, bm.url_steam(210970))
    assert lien.as_link() == {"kind": "buy", "ethics": "neutral", "label": "Steam",
                              "url": "https://store.steampowered.com/app/210970/"}


def test_la_resolution_se_resume_en_json_pour_le_journal():
    resolution = bm.Resolution(raison=bm.RAISON_OK, isbn="9782709677424")

    assert "9782709677424" in bm.resolution_json(resolution)


def test_la_normalisation_est_celle_des_comparaisons():
    assert bm._normalise("Les Solitudes, de Petite Rivière !") == (
        "les solitudes de petite riviere")


# ===== la recherche du libraire =============================================
def test_les_ean_sont_extraits_d_une_page_de_resultats():
    """Seule source qui connaisse les parutions françaises récentes."""
    html = ('<a href="/livre/9782709677424-les-solitudes-de-petite-riviere-x/">A</a>'
            '<a href="/livre/9782709677639-bref-2-le-livre/">B</a>'
            '<a href="/livre/9782709677424-doublon/">A encore</a>'
            '<a href="/auteur/kalindi-ramphul/">pas une fiche</a>')

    assert bm.eans_de_resultats(html) == ["9782709677424", "9782709677639"]


def test_une_page_de_resultats_vide_ne_rend_rien():
    assert bm.eans_de_resultats("<html>aucun résultat</html>") == []


def test_le_nombre_de_resultats_retenus_est_borne():
    html = "".join(f'<a href="/livre/978200000000{i}-x/">x</a>' for i in range(9))

    assert len(bm.eans_de_resultats(html)) <= bm.MAX_EAN_ESSAYES


def test_l_auteur_se_compare_des_deux_cotes():
    """La fiche d'un livre à quatre mains nomme ses auteurs d'un bloc.

    « Bruno Muschio, Kyan Khojandi » contre « Kyan Khojandi, Navo » : comparer
    les chaînes entières donnait 0,65 pour 0,88 requis, un refus injustifié.
    """
    assert bm.auteur_correspond(["Bruno Muschio, Kyan Khojandi"],
                                "Kyan Khojandi, Navo")
    assert not bm.auteur_correspond(["Bruno Muschio, Marianne Chaillan"],
                                    "Benoîte Groult")
