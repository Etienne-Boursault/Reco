"""Tests de `tools/bord_afaire.py` — la liste « À faire d'abord » du tableau de bord.

Le module est pur : chaque test lui donne ses données en dictionnaires, sans
disque ni réseau.
"""
from __future__ import annotations

import pytest

import bord_afaire as ba

EP10 = {"guid": "yt-10", "title": "Dix (Un Bon Moment, S6-E10)", "season": 6, "number": 10}
EP11 = {"guid": "yt-11", "title": "Onze", "season": 6, "number": 11}
EP12 = {"guid": "yt-12", "title": "Douze", "season": 6, "number": 12}
TOUT_COCHE = dict.fromkeys(("instagram", "threads", "spotify", "deezer", "senscritique",
                            "youtube"), "2026-11-28T09:30:00+00:00")


def _appel(**kw):
    """Tout connu et rien à faire, sauf ce que le test change."""
    args = {"episodes": {}, "groups": {}, "recents": [], "coches": {},
            "signalements": [], "liens": [], "sorties": []}
    args.update(kw)
    return ba.a_faire(**args)


def _textes(items):
    return [i["texte"] for i in items]


def test_la_liste_vide_quand_tout_est_connu_et_fait():
    assert _appel() == []
    recent = {"guid": "yt-11", "fusionne": True, "episode": EP11}
    assert _appel(episodes={"yt-11": EP11}, recents=[recent],
                  coches={"yt-11": TOUT_COCHE}) == []


def test_une_reco_ni_validee_ni_ecartee_compte_a_relire():
    groups = {"yt-12": [{"status": "draft"}, {}, {"status": "pending"},
                        {"status": "validated"}, {"status": "discarded"}],
              "yt-11": [{"status": "draft"}]}
    items = _appel(episodes={"yt-11": EP11, "yt-12": EP12}, groups=groups)
    # Le plus récent d'abord, comme l'accueil de la relecture.
    assert _textes(items) == ["relire S6·E12 (3 recos)", "relire S6·E11 (1 reco)"]
    assert [i["guid"] for i in items] == ["yt-12", "yt-11"]
    assert all(i["bloc"] == "relecture" and not i["inconnu"] for i in items)


def test_un_episode_entierement_relu_ne_compte_pas():
    groups = {"yt-12": [{"status": "validated"}, {"status": "discarded"}]}
    assert _appel(episodes={"yt-12": EP12}, groups=groups) == []


def test_publie_pas_encore_fusionne_donne_la_pr_a_fusionner():
    recents = [{"guid": "yt-11", "fusionne": False, "episode": EP11},
               {"guid": "yt-9", "fusionne": False, "episode": None}]
    items = _appel(recents=recents, coches={"yt-11": TOUT_COCHE, "yt-9": TOUT_COCHE})
    assert _textes(items) == ["fusionner la PR de S6·E11", "fusionner la PR de yt-9"]
    assert [i["bloc"] for i in items] == ["publication", "publication"]


def test_les_reseaux_qui_manquent_dans_l_ordre_fixe():
    recents = [{"guid": "yt-11", "fusionne": True, "episode": EP11}]
    coches = {"yt-11": {k: v for k, v in TOUT_COCHE.items()
                        if k not in ("deezer", "senscritique")}}
    items = _appel(episodes={"yt-11": EP11}, recents=recents, coches=coches)
    assert _textes(items) == ["réseaux de S6·E11 : Deezer, SensCritique"]
    assert items[0]["guid"] == "yt-11"


def test_le_libelle_retombe_sur_le_titre_court_puis_le_guid():
    sans_numero = {"guid": "yt-x", "title": "Hors série (Un Bon Moment, S6-E99)"}
    recents = [{"guid": "yt-x", "fusionne": True, "episode": sans_numero},
               {"guid": "yt-y", "fusionne": True, "episode": None}]
    items = _appel(recents=recents, coches={"yt-x": {}, "yt-y": {}})
    assert _textes(items)[0].startswith("réseaux de Hors série : Instagram")
    assert _textes(items)[1].startswith("réseaux de yt-y : ")
    assert _textes(items)[0].endswith("commentaire YouTube")


def test_l_ordre_des_blocs():
    groups = {"yt-12": [{"status": "draft"}]}
    recents = [{"guid": "yt-11", "fusionne": False, "episode": EP11}]
    items = _appel(episodes={"yt-12": EP12}, groups=groups, recents=recents,
                   coches={"yt-11": {"instagram": "x"}},
                   signalements=["1 signalement"], liens=["3 liens morts"],
                   sorties=["fusionner les sorties de décembre"])
    assert [i["bloc"] for i in items] == ["relecture", "publication", "reseaux",
                                          "signalements", "liens", "sorties"]
    assert _textes(items)[3:] == ["1 signalement", "3 liens morts",
                                  "fusionner les sorties de décembre"]


def test_une_source_inconnue_est_dite_inconnue_jamais_rien_a_faire():
    items = ba.a_faire(episodes={}, groups={}, recents=None, coches=None)
    assert [i["bloc"] for i in items] == ["publication", "reseaux", "signalements",
                                          "liens", "sorties"]
    assert all(i["inconnu"] and "inconnu" in i["texte"] for i in items)
    assert items[0]["texte"] == "publication : inconnu"


def test_des_cases_illisibles_rendent_les_reseaux_inconnus_pas_la_publication():
    recents = [{"guid": "yt-11", "fusionne": False, "episode": EP11}]
    items = _appel(recents=recents, coches=None)
    assert [(i["bloc"], i["inconnu"]) for i in items] == [("publication", False),
                                                          ("reseaux", True)]
    assert items[1]["texte"] == "réseaux : inconnu"


# ---- Les signalements, lus par l'audience (tranche 2c) --------------------

def _audience(etat="ok", signalements=None):
    sig = {"etat": "lu", "enAttente": []} if signalements is None else signalements
    return {"etat": etat, "donnees": {"signalements": sig}}


def _en_attente(n):
    return {"etat": "lu", "enAttente": [{"id": f"rep-{k}", "recoId": "r", "categorie": "error",
                                          "date": "2026-11-27T10:00:00.000Z"} for k in range(n)]}


def test_la_ligne_des_signalements_passe_d_inconnu_a_un_nombre():
    avant = _appel(signalements=ba.lignes_signalements(None))
    assert _textes(avant) == ["signalements : inconnu"] and avant[0]["inconnu"]
    apres = _appel(signalements=ba.lignes_signalements(_audience(signalements=_en_attente(3))))
    assert _textes(apres) == ["3 signalements en attente"] and not apres[0]["inconnu"]
    un = ba.lignes_signalements(_audience(signalements=_en_attente(1)))
    assert un == ["1 signalement en attente"]


def test_aucun_signalement_en_attente_ne_fait_aucune_ligne():
    assert ba.lignes_signalements(_audience()) == []


def test_les_signalements_restent_inconnus_si_l_audience_n_est_pas_a_jour():
    # Des données gardées après une panne ne disent pas ce qui attend maintenant.
    assert ba.lignes_signalements(_audience("panne", _en_attente(2))) is None
    assert ba.lignes_signalements({"etat": "ok", "donnees": None}) is None
    assert ba.lignes_signalements(_audience(signalements={"etat": "inconnu",
                                                          "enAttente": []})) is None


@pytest.mark.parametrize("sig", [
    {"etat": "lu", "enAttente": "pas une liste"},
    {"etat": "lu", "enAttente": {"id": "x"}},
    {"etat": "lu", "enAttente": [{"id": "x"}, "texte"]},
    ["pas", "un", "objet"],
    "texte",
])
def test_une_forme_inattendue_de_signalements_reste_inconnue(sig):
    """Tour 1, M3 : jamais une exception, jamais un compte inventé."""
    assert ba.lignes_signalements(_audience(signalements=sig)) is None
    assert ba.signalements_en_attente(_audience(signalements=sig)) is None


def test_signalements_en_attente_rend_la_liste_lue():
    assert ba.signalements_en_attente(_audience(signalements=_en_attente(2))) ==         _en_attente(2)["enAttente"]
    assert ba.signalements_en_attente(_audience()) == []
    assert ba.signalements_en_attente(None) is None
