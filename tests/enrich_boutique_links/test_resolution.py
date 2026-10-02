"""Tests des enchaînements : ce que la passe retient, et surtout ce qu'elle refuse.

On remplace les clients (pas `_demander`) pour éprouver la logique de décision
sans dérouler la forme des réponses, déjà couverte par `test_clients`. Les pauses
entre appels sont mises à zéro : ces tests ne doivent pas attendre.
"""
from __future__ import annotations

import boutique_links as bl
import boutique_matching as bm

PAGE = """<html><head>
<title>Les solitudes de Petite Rivière - Kalindi Ramphul - JC Lattès</title>
<link rel="canonical" href="https://www.placedeslibraires.fr/livre/9782709677424-x/">
<script type="application/ld+json">{"isbn":"9782709677424"}</script>
</head></html>"""

JEU = {"id": "a-1", "title": "The Witness", "creator": "Thekla, Inc.",
       "types": ["jeu"], "status": "validated", "links": []}
LIVRE = {"id": "a-2", "title": "Les Solitudes de Petite Rivière",
         "creator": "Kalindi Ramphul", "types": ["livre"],
         "status": "validated", "links": []}


def _fiches(mapping):
    """Double de `steam_fiche` : chaque identifiant rend la fiche voulue."""
    return lambda _session, appid: mapping.get(appid)


def _steam(monkeypatch, items, fiches):
    monkeypatch.setattr(bl, "steam_candidats", lambda _s, _t: items)
    monkeypatch.setattr(bl, "steam_fiche", _fiches(fiches))


# ===== jeux =================================================================
def test_un_jeu_corrobore_par_son_studio_recoit_son_lien(monkeypatch):
    _steam(monkeypatch, [{"id": 210970, "name": "The Witness"}],
           {210970: {"type": "game", "steam_appid": 210970,
                     "developers": ["Thekla, Inc."]}})

    resolution = bl.resoudre_jeu(JEU, session=None, pause=0)

    assert resolution.raison == bm.RAISON_OK
    assert resolution.liens[0].url == "https://store.steampowered.com/app/210970/"
    assert resolution.liens[0].label == "Steam"
    assert resolution.preuve == "Thekla, Inc."


def test_une_bande_son_au_bon_titre_est_refusee(monkeypatch):
    """`storesearch` l'étiquette « app » ; seul `appdetails` dit « music »."""
    _steam(monkeypatch, [{"id": 4943810, "name": "Looking For Fael"}],
           {4943810: {"type": "music", "steam_appid": 4943810,
                      "developers": ["Swing Swing Submarine"]}})
    reco = {**JEU, "title": "Looking For Fael", "creator": "Swing Swing Submarine"}

    assert bl.resoudre_jeu(reco, session=None, pause=0).raison == bm.RAISON_PAS_UN_JEU


def test_un_studio_qui_ne_correspond_pas_fait_refuser(monkeypatch):
    _steam(monkeypatch, [{"id": 210970, "name": "The Witness"}],
           {210970: {"type": "game", "steam_appid": 210970,
                     "developers": ["Un autre studio"]}})

    assert bl.resoudre_jeu(JEU, session=None,
                           pause=0).raison == bm.RAISON_STUDIO_MISMATCH


def test_une_fiche_qui_parle_d_un_autre_jeu_fait_refuser(monkeypatch):
    """Le piège mesuré, vu depuis la résolution : on ne devine pas."""
    _steam(monkeypatch, [{"id": 210970, "name": "The Witness"}], {210970: None})

    assert bl.resoudre_jeu(JEU, session=None,
                           pause=0).raison == bm.RAISON_STEAM_ID_MISMATCH


def test_deux_jeux_au_meme_titre_et_au_meme_studio_restent_ambigus(monkeypatch):
    _steam(monkeypatch,
           [{"id": 1, "name": "The Witness"}, {"id": 2, "name": "The Witness"}],
           {1: {"type": "game", "steam_appid": 1, "developers": ["Thekla, Inc."]},
            2: {"type": "game", "steam_appid": 2, "developers": ["Thekla, Inc."]}})

    resolution = bl.resoudre_jeu(JEU, session=None, pause=0)

    assert resolution.raison == bm.RAISON_AMBIGUOUS
    assert resolution.liens == ()
    assert "1" in resolution.detail and "2" in resolution.detail


def test_aucun_resultat_au_bon_titre_rend_no_match(monkeypatch):
    _steam(monkeypatch, [{"id": 9, "name": "Tout autre chose"}], {})

    assert bl.resoudre_jeu(JEU, session=None, pause=0).raison == bm.RAISON_NO_MATCH


def test_un_jeu_sans_studio_est_refuse_par_defaut(monkeypatch):
    """Sans studio, rien ne corrobore le titre : un homonyme passerait."""
    reco = {**JEU, "creator": ""}

    resolution = bl.resoudre_jeu(reco, session=None, pause=0)

    assert resolution.raison == bm.RAISON_NO_CREATOR


def test_un_jeu_sans_studio_passe_avec_l_option_et_une_seule_fiche(monkeypatch):
    _steam(monkeypatch, [{"id": 210970, "name": "The Witness"}],
           {210970: {"type": "game", "steam_appid": 210970,
                     "developers": ["Thekla, Inc."]}})
    reco = {**JEU, "creator": ""}

    resolution = bl.resoudre_jeu(reco, session=None, permettre_sans_studio=True,
                                 pause=0)

    assert resolution.raison == bm.RAISON_OK


def test_sans_studio_l_option_ne_tranche_pas_entre_deux_fiches(monkeypatch):
    _steam(monkeypatch,
           [{"id": 1, "name": "The Witness"}, {"id": 2, "name": "The Witness"}],
           {1: {"type": "game", "steam_appid": 1, "developers": ["A"]},
            2: {"type": "game", "steam_appid": 2, "developers": ["B"]}})
    reco = {**JEU, "creator": ""}

    resolution = bl.resoudre_jeu(reco, session=None, permettre_sans_studio=True,
                                 pause=0)

    assert resolution.raison == bm.RAISON_AMBIGUOUS


# ===== livres ===============================================================
def _livre(monkeypatch, *, libraire=(), google=(), openlib=(), pages=None,
           pannes=()):
    def source(nom, valeurs, message):
        def chercher(_s, _t, _c):
            if nom in pannes:
                raise bl.BoutiqueInjoignable(message)
            return list(valeurs)
        return chercher

    monkeypatch.setattr(bl, "isbn_libraire",
                        source("libraire", libraire, "injoignable"))
    monkeypatch.setattr(bl, "isbn_google",
                        source("google", google, "limite d'appels atteinte (429)"))
    monkeypatch.setattr(bl, "isbn_openlibrary",
                        source("openlib", openlib, "injoignable"))
    monkeypatch.setattr(bl, "page_libraire",
                        lambda _s, ean: (pages or {}).get(ean))


def test_un_livre_dont_la_fiche_corrobore_recoit_son_lien(monkeypatch):
    _livre(monkeypatch, google=["9782709677424"],
           pages={"9782709677424": (
               "https://www.placedeslibraires.fr/livre/9782709677424-resolue/",
               PAGE)})

    resolution = bl.resoudre_livre(LIVRE, session=None, pause=0)

    assert resolution.raison == bm.RAISON_OK
    assert resolution.isbn == "9782709677424"
    assert resolution.liens[0].label == "Place des Libraires"
    # L'URL écrite est celle que le site déclare, pas celle qu'on a demandée.
    assert resolution.liens[0].url.endswith("9782709677424-x/")


def test_une_panne_de_google_ne_fait_pas_renoncer(monkeypatch):
    """Google Books répond 429 sans prévenir : Open Library doit prendre le relais."""
    _livre(monkeypatch, openlib=["9782709677424"], pannes=("google",),
           pages={"9782709677424": ("https://www.placedeslibraires.fr/livre/x/",
                                    PAGE)})

    assert bl.resoudre_livre(LIVRE, session=None, pause=0).raison == bm.RAISON_OK


def test_deux_sources_en_panne_donnent_une_erreur_http_pas_une_absence(monkeypatch):
    """La distinction qui compte : on n'a pas pu demander, on ne conclut rien."""
    _livre(monkeypatch, pannes=("libraire", "google", "openlib"))

    assert bl.resoudre_livre(LIVRE, session=None,
                             pause=0).raison == bm.RAISON_HTTP_ERROR


def test_aucun_isbn_trouve_est_une_absence(monkeypatch):
    _livre(monkeypatch)

    assert bl.resoudre_livre(LIVRE, session=None, pause=0).raison == bm.RAISON_NO_ISBN


def test_un_ean_sans_fiche_chez_le_libraire_est_trace(monkeypatch):
    _livre(monkeypatch, google=["9780000000000"], pages={})

    assert bl.resoudre_livre(LIVRE, session=None,
                             pause=0).raison == bm.RAISON_EAN_ABSENT


def test_une_edition_etrangere_est_ecartee_et_la_bonne_retenue(monkeypatch):
    """Open Library rend aussi l'édition allemande : c'est la fiche qui tranche."""
    allemande = ("<html><head><title>Salz auf unserer Haut - Benoîte Groult - "
                 "Droemer</title></head></html>")
    _livre(monkeypatch, openlib=["9783426192511", "9782709677424"],
           pages={"9783426192511": ("https://www.placedeslibraires.fr/livre/de/",
                                    allemande),
                  "9782709677424": ("https://www.placedeslibraires.fr/livre/fr/",
                                    PAGE)})

    resolution = bl.resoudre_livre(LIVRE, session=None, pause=0)

    assert resolution.raison == bm.RAISON_OK
    assert resolution.isbn == "9782709677424"


def test_une_page_qui_contredit_l_ean_demande_est_refusee(monkeypatch):
    _livre(monkeypatch, google=["9782253053552"],
           pages={"9782253053552": ("https://www.placedeslibraires.fr/livre/x/",
                                    PAGE)})

    assert bl.resoudre_livre(LIVRE, session=None,
                             pause=0).raison == bm.RAISON_PAGE_MISMATCH


def test_un_livre_sans_auteur_est_refuse(monkeypatch):
    assert bl.resoudre_livre({**LIVRE, "creator": ""}, session=None,
                             pause=0).raison == bm.RAISON_NO_CREATOR


# ===== aiguillage ===========================================================
def test_la_resolution_aiguille_selon_le_type(monkeypatch):
    monkeypatch.setattr(bl, "resoudre_jeu",
                        lambda *_a, **_k: bm.Resolution(raison="jeu-vu"))
    monkeypatch.setattr(bl, "resoudre_livre",
                        lambda *_a, **_k: bm.Resolution(raison="livre-vu"))

    assert bl.resoudre(JEU, session=None).raison == "jeu-vu"
    assert bl.resoudre(LIVRE, session=None).raison == "livre-vu"


def test_un_type_non_servi_est_ecarte():
    assert bl.resoudre({"types": ["album"], "links": []},
                       session=None).raison == bm.RAISON_NO_MATCH


def test_une_reco_deja_liee_n_est_pas_reinterrogee():
    """Aucun appel réseau : le décor du dossier le prouverait en échouant."""
    reco = {**JEU, "links": [{"url": "https://store.steampowered.com/app/210970/"}]}

    assert bl.resoudre(reco, session=None).raison == bm.RAISON_DEJA_SERVIE


# ===== la politesse envers les sources =====================================
def test_une_pause_separe_deux_fiches_steam(monkeypatch):
    """`appdetails` est sévèrement limité : sans pause, Steam nous coupe."""
    pauses = []
    monkeypatch.setattr(bl.time, "sleep", pauses.append)
    _steam(monkeypatch,
           [{"id": 1, "name": "The Witness"}, {"id": 2, "name": "The Witness"}],
           {1: {"type": "game", "steam_appid": 1, "developers": ["Thekla, Inc."]},
            2: {"type": "game", "steam_appid": 2, "developers": ["Autre"]}})

    bl.resoudre_jeu(JEU, session=None, pause=1.5)

    assert pauses == [1.5]  # une seule : avant la DEUXIÈME fiche


def test_une_pause_separe_deux_fiches_libraire(monkeypatch):
    pauses = []
    monkeypatch.setattr(bl.time, "sleep", pauses.append)
    _livre(monkeypatch, google=["9780000000000", "9782709677424"],
           pages={"9782709677424": ("https://www.placedeslibraires.fr/livre/x/",
                                    PAGE)})

    resolution = bl.resoudre_livre(LIVRE, session=None, pause=0.5)

    assert resolution.raison == bm.RAISON_OK
    assert pauses == [0.5]


def test_la_recherche_du_libraire_comble_ce_que_les_autres_ignorent(monkeypatch):
    """Cas réel : les deux livres de 2026 n'existent que chez le libraire."""
    _livre(monkeypatch, libraire=["9782709677424"], pannes=("google",),
           pages={"9782709677424": ("https://www.placedeslibraires.fr/livre/x/",
                                    PAGE)})

    resolution = bl.resoudre_livre(LIVRE, session=None, pause=0)

    assert resolution.raison == bm.RAISON_OK
    assert resolution.isbn == "9782709677424"
