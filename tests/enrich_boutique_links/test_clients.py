"""Tests des clients : la forme des réponses, et la frontière entre « pas pu
demander » et « ça n'existe pas ».

Le réseau est simulé au seul point de sortie (`boutique_links._demander`), que le
décor du dossier interdit par défaut : un test qui oublierait de le remplacer
échouerait au lieu de partir sur Internet.
"""
from __future__ import annotations

import pytest
import requests

import boutique_links as bl

#: La VRAIE fonction, capturée à l'import — donc avant que le décor du dossier
#: ne la remplace par son double interdit. Les tests qui éprouvent le point de
#: sortie lui-même ont besoin de l'originale, pas du garde-fou.
VRAI_DEMANDER = bl._demander


class FausseReponse:
    """Le minimum qu'attendent les clients d'une réponse `requests`."""

    def __init__(self, charge=None, *, status_code=200, text="", url=""):
        self._charge = charge
        self.status_code = status_code
        self.text = text
        self.url = url

    def json(self):
        if isinstance(self._charge, Exception):
            raise self._charge
        return self._charge


def _repondre(reponses, journal=None):
    """Double de `_demander` : rend la réponse préparée pour chaque URL."""
    def demander(_session, url, params=None):
        if journal is not None:
            journal.append((url, dict(params or {})))
        for motif, reponse in reponses.items():
            if motif in url:
                return reponse
        raise AssertionError(f"URL non prévue par le test : {url}")
    return demander


# ===== le point de sortie unique ===========================================
def test_une_limite_d_appels_n_est_pas_une_absence():
    """429 doit lever : conclure « pas d'ISBN » un jour de limitation salirait
    le rapport et ferait renoncer à la main pour rien."""
    class Session:
        def get(self, *_a, **_k):
            return FausseReponse(status_code=429)

    with pytest.raises(bl.BoutiqueInjoignable, match="429"):
        VRAI_DEMANDER(Session(), bl.GOOGLE_BOOKS, {})


def test_une_panne_reseau_leve_la_meme_exception():
    class Session:
        def get(self, *_a, **_k):
            raise requests.ConnectionError("câble débranché")

    with pytest.raises(bl.BoutiqueInjoignable, match="injoignable"):
        VRAI_DEMANDER(Session(), bl.STEAM_RECHERCHE, {})


def test_une_erreur_serveur_leve():
    class Session:
        def get(self, *_a, **_k):
            return FausseReponse(status_code=503)

    with pytest.raises(bl.BoutiqueInjoignable, match="503"):
        VRAI_DEMANDER(Session(), bl.STEAM_FICHE, {})


def test_un_404_est_une_reponse_pas_une_derobade():
    """Il revient à l'appelant : « cette fiche n'existe pas » est un fait."""
    class Session:
        def get(self, *_a, **_k):
            return FausseReponse(status_code=404)

    reponse = VRAI_DEMANDER(Session(),
                            bl.LIBRAIRE_FICHE.format(ean="9780000000000"))

    assert reponse.status_code == 404


def test_un_corps_illisible_leve():
    with pytest.raises(bl.BoutiqueInjoignable, match="illisible"):
        bl._json(FausseReponse(ValueError("pas du json")))


def test_un_corps_qui_n_est_pas_un_objet_rend_un_dict_vide():
    assert bl._json(FausseReponse([1, 2, 3])) == {}


# ===== Steam ================================================================
def test_la_recherche_steam_rend_les_items(monkeypatch):
    journal = []
    monkeypatch.setattr(bl, "_demander", _repondre(
        {"storesearch": FausseReponse({"items": [{"id": 1, "name": "A"}, "bruit"]})},
        journal))

    items = bl.steam_candidats(None, "A")

    assert items == [{"id": 1, "name": "A"}]
    assert journal[0][1]["term"] == "A"
    assert journal[0][1]["cc"] == "fr"


def test_une_recherche_sans_items_rend_une_liste_vide(monkeypatch):
    monkeypatch.setattr(bl, "_demander",
                        _repondre({"storesearch": FausseReponse({})}))

    assert bl.steam_candidats(None, "Rien") == []


def test_la_fiche_steam_est_trouvee_sous_la_cle_d_un_autre_identifiant(monkeypatch):
    """Bout en bout du piège mesuré : le client doit la rendre quand même."""
    payload = {"4943810": {"success": True,
                           "data": {"type": "game", "name": "Looking For Fael",
                                    "steam_appid": 2521170,
                                    "developers": ["Swing Swing Submarine"]}}}
    monkeypatch.setattr(bl, "_demander",
                        _repondre({"appdetails": FausseReponse(payload)}))

    fiche = bl.steam_fiche(None, 2521170)

    assert fiche["name"] == "Looking For Fael"


def test_une_fiche_steam_absente_rend_none(monkeypatch):
    monkeypatch.setattr(bl, "_demander", _repondre(
        {"appdetails": FausseReponse({"210970": {"success": False}})}))

    assert bl.steam_fiche(None, 210970) is None


# ===== ISBN =================================================================
def test_google_books_rend_l_isbn_corrobore(monkeypatch):
    journal = []
    charge = {"items": [{"volumeInfo": {
        "title": "Les solitudes de Petite Rivière",
        "authors": ["Kalindi Ramphul"],
        "industryIdentifiers": [{"type": "ISBN_13", "identifier": "9782709677424"}]}}]}
    monkeypatch.setattr(bl, "_demander",
                        _repondre({"books/v1": FausseReponse(charge)}, journal))

    trouves = bl.isbn_google(None, "Les Solitudes de Petite Rivière",
                             "Kalindi Ramphul")

    assert trouves == ["9782709677424"]
    assert 'inauthor:"Kalindi Ramphul"' in journal[0][1]["q"]


def test_google_books_refuse_un_auteur_qui_ne_correspond_pas(monkeypatch):
    charge = {"items": [{"volumeInfo": {
        "title": "Les solitudes de Petite Rivière",
        "authors": ["Quelqu'un d'autre"],
        "industryIdentifiers": [{"type": "ISBN_13", "identifier": "9782709677424"}]}}]}
    monkeypatch.setattr(bl, "_demander",
                        _repondre({"books/v1": FausseReponse(charge)}))

    assert bl.isbn_google(None, "Les Solitudes de Petite Rivière",
                          "Kalindi Ramphul") == []


def test_google_books_sans_resultat_rend_une_liste_vide(monkeypatch):
    monkeypatch.setattr(bl, "_demander",
                        _repondre({"books/v1": FausseReponse({"totalItems": 0})}))

    assert bl.isbn_google(None, "Introuvable", "Personne") == []


def test_open_library_rend_les_candidats(monkeypatch):
    journal = []
    charge = {"docs": [{"title": "Les vaisseaux du coeur",
                        "author_name": ["Benoîte Groult"],
                        "isbn": ["9783426192511", "9782253053552"]}, "bruit"]}
    monkeypatch.setattr(bl, "_demander",
                        _repondre({"openlibrary": FausseReponse(charge)}, journal))

    trouves = bl.isbn_openlibrary(None, "Les vaisseaux du cœur", "Benoîte Groult")

    assert trouves == ["9783426192511", "9782253053552"]
    assert journal[0][1]["author"] == "Benoîte Groult"


def test_open_library_sans_docs_rend_une_liste_vide(monkeypatch):
    monkeypatch.setattr(bl, "_demander",
                        _repondre({"openlibrary": FausseReponse({})}))

    assert bl.isbn_openlibrary(None, "Rien", "Personne") == []


# ===== la fiche libraire ====================================================
def test_la_fiche_libraire_rend_l_url_resolue_et_la_page(monkeypatch):
    """C'est le site qui donne son URL : la redirection EST la réponse."""
    resolue = ("https://www.placedeslibraires.fr/livre/"
               "9782709677424-les-solitudes-de-petite-riviere-kalindi-ramphul/")
    monkeypatch.setattr(bl, "_demander", _repondre(
        {"placedeslibraires": FausseReponse(text="<html></html>", url=resolue)}))

    url, html = bl.page_libraire(None, "9782709677424")

    assert url == resolue
    assert html == "<html></html>"


def test_un_ean_inconnu_rend_none(monkeypatch):
    monkeypatch.setattr(bl, "_demander", _repondre(
        {"placedeslibraires": FausseReponse(status_code=404)}))

    assert bl.page_libraire(None, "9780000000000") is None


def test_la_recherche_du_libraire_rend_les_ean(monkeypatch):
    journal = []
    page = '<a href="/livre/9782709677639-bref-2-le-livre/">Bref. 2</a>'
    monkeypatch.setattr(bl, "_demander",
                        _repondre({"listeliv": FausseReponse(text=page)}, journal))

    trouves = bl.isbn_libraire(None, "Bref. 2, le livre", "Kyan Khojandi")

    assert trouves == ["9782709677639"]
    assert journal[0][1]["MOTS"] == "Bref. 2, le livre Kyan Khojandi"


def test_une_recherche_libraire_en_404_rend_une_liste_vide(monkeypatch):
    monkeypatch.setattr(bl, "_demander",
                        _repondre({"listeliv": FausseReponse(status_code=404)}))

    assert bl.isbn_libraire(None, "Rien", None) == []


def test_la_recherche_libraire_n_envoie_que_le_premier_nom_d_auteur(monkeypatch):
    """Mesuré : « … Kyan Khojandi, Navo » ne rend AUCUN résultat chez eux."""
    journal = []
    page = '<a href="/livre/9782709677639-bref-2-le-livre/">Bref. 2</a>'
    monkeypatch.setattr(bl, "_demander",
                        _repondre({"listeliv": FausseReponse(text=page)}, journal))

    bl.isbn_libraire(None, "Bref. 2, le livre", "Kyan Khojandi, Navo")

    assert journal[0][1]["MOTS"] == "Bref. 2, le livre Kyan Khojandi"


def test_le_titre_seul_sert_de_repli(monkeypatch):
    """Élargir ne relâche rien : c'est la fiche qui tranche ensuite."""
    journal = []
    page = '<a href="/livre/9782709677639-bref-2-le-livre/">Bref. 2</a>'

    def demander(_session, url, params=None):
        journal.append(dict(params or {}))
        vide = FausseReponse(text="<html>aucun résultat</html>")
        return vide if len(journal) == 1 else FausseReponse(text=page)

    monkeypatch.setattr(bl, "_demander", demander)
    trouves = bl.isbn_libraire(None, "Bref. 2, le livre", "Kyan Khojandi, Navo")

    assert trouves == ["9782709677639"]
    assert [j["MOTS"] for j in journal] == ["Bref. 2, le livre Kyan Khojandi",
                                            "Bref. 2, le livre"]
