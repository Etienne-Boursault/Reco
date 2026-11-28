"""Tests de « Sorties à venir », « Graphies apprises » et « Liens morts » (`bord_rendu_systeme`).

Décision : tableau de bord, R2 B du 27/11/2026 ; TB-1 C du 28/11/2026 (plan
`pr-tableau-de-bord.md`, § 2, § 6, § 9 et § 14, tranche 3d-2).

Le rendu est pur : chaque test lui donne l'état de `bord_contenu.lire()` en dictionnaire
(forme de la note 3c du journal), sans disque ni réseau.
"""
from __future__ import annotations

from datetime import UTC, datetime

import pytest

import bord_rendu as br
import bord_rendu_blocs as bb
import bord_rendu_systeme as brs

CHARGE = '"><script>alert(1)</script>'
JS = "javascript:alert(1)"
MAINTENANT = datetime(2026, 11, 29, 10, 51, tzinfo=UTC)


@pytest.fixture(autouse=True)
def _utc(monkeypatch):
    monkeypatch.setattr(bb, "_fuseau", lambda: UTC)


def _sortie(titre="Un film", date="2026-12-01", jours=2, relancee=False):
    return {"id": "r-1", "titre": titre, "date": date, "jours": jours, "relancee": relancee}


def _sorties(liste=None, total=None, illisibles=0):
    liste = [_sortie()] if liste is None else liste
    return {"liste": liste, "total": len(liste) if total is None else total,
            "illisibles": illisibles}


def _graphies(plus_vues=None, total=None, ecartees=0):
    plus_vues = [{"fausse": "Kaffka", "juste": "Kafka", "vu": 7}] if plus_vues is None \
        else plus_vues
    return {"total": len(plus_vues) if total is None else total, "ecartees": ecartees,
            "plus_vues": plus_vues}


def _lien(url="https://exemple.test/a", reponse="404", recos=("r-1",)):
    return {"url": url, "reponse": reponse, "recos": list(recos)}


def _liens(liste=None, morts=None, age=4, ancien=False, date="2026-11-25"):
    liste = [_lien()] if liste is None else liste
    return {"date": date, "age": age, "ancien": ancien,
            "morts": len(liste) if morts is None else morts,
            "nouveaux": 1, "inconnus": 0, "vivants": 10, "liste": liste}


def _contenu(**kw):
    c = {"sorties": _sorties(), "graphies": _graphies(), "liens": _liens()}
    c.update(kw)
    return c


# ---- Chaque bloc inconnu : jamais « aucun » ---------------------------------

@pytest.mark.parametrize("contenu", [None, {}, {"sorties": None, "graphies": None, "liens": None},
                                     {"sorties": "texte", "graphies": [], "liens": 3}])
def test_chaque_bloc_inconnu_dit_inconnu_jamais_aucun(contenu):
    for bloc, nom in ((brs.bloc_sorties, "Sorties à venir"), (brs.bloc_graphies, "Graphies"),
                      (brs.bloc_liens, "Liens morts")):
        rendu = bloc(contenu)
        assert "inconnu" in rendu and nom in rendu
        assert "aucun" not in rendu.lower() and "Aucun" not in rendu


# ---- Sorties à venir ---------------------------------------------------------

def test_une_sortie_a_venir_dit_son_titre_sa_date_et_les_jours_restants():
    bloc = brs.bloc_sorties(_contenu())
    assert "Un film" in bloc and "01/12" in bloc and "dans 2 jours" in bloc


def test_demain_et_une_sortie_deja_passee_en_relance():
    liste = [_sortie("Demain", "2026-11-30", 1), _sortie("Aujourd'hui", "2026-11-29", 0),
             _sortie("Hier", "2026-11-28", -1)]
    bloc = brs.bloc_sorties(_contenu(sorties=_sorties(liste)))
    assert "demain" in bloc
    assert bloc.count("déjà sortie, en relance") == 2


def test_une_date_ou_des_jours_illisibles_ne_cassent_pas_le_bloc():
    liste = [_sortie(date="pas une date", jours="x"), _sortie(date=None, jours=None)]
    bloc = brs.bloc_sorties(_contenu(sorties=_sorties(liste)))
    assert "pas une date" in bloc and "jours inconnus" in bloc


def test_aucune_sortie_est_une_vraie_mesure_et_les_fichiers_illisibles_se_disent():
    bloc = brs.bloc_sorties(_contenu(sorties=_sorties([], illisibles=2)))
    assert "Aucune sortie" in bloc and "2 fichiers de recos illisibles" in bloc
    un = brs.bloc_sorties(_contenu(sorties=_sorties([], illisibles=1)))
    assert "1 fichier de recos illisible" in un and "fichiers" not in un
    assert "illisible" not in brs.bloc_sorties(_contenu(sorties=_sorties([])))


def test_la_liste_des_sorties_coupee_dit_combien_restent():
    liste = [_sortie(f"Film {k}") for k in range(10)]
    bloc = brs.bloc_sorties(_contenu(sorties=_sorties(liste, total=14)))
    assert "+ 4 autres" in bloc
    assert "autres" not in brs.bloc_sorties(_contenu(sorties=_sorties(liste)))


def test_un_titre_de_sortie_piege_est_echappe_et_coupe():
    bloc = brs.bloc_sorties(_contenu(sorties=_sorties([_sortie(CHARGE + "x" * 300)])))
    assert "<script>alert" not in bloc and "&lt;script&gt;" in bloc and "…" in bloc


# ---- Graphies apprises ---------------------------------------------------------

def test_les_graphies_les_plus_vues_avec_leur_nombre():
    bloc = brs.bloc_graphies(_contenu())
    assert "Kaffka" in bloc and "Kafka" in bloc and "7 fois" in bloc
    assert "1 graphie apprise" in bloc


def test_une_graphie_vue_une_fois_et_plusieurs_graphies():
    plus = [{"fausse": "a", "juste": "b", "vu": 1}, {"fausse": "c", "juste": "d", "vu": 3}]
    bloc = brs.bloc_graphies(_contenu(graphies=_graphies(plus, total=8)))
    assert "1 fois" in bloc and "8 graphies apprises" in bloc and "+ 6 autres" in bloc


def test_aucune_graphie_apprise_et_entrees_ecartees():
    bloc = brs.bloc_graphies(_contenu(graphies=_graphies([], ecartees=0)))
    assert "Aucune graphie apprise" in bloc and "ignorée" not in bloc
    bloc = brs.bloc_graphies(_contenu(graphies=_graphies([], ecartees=2)))
    assert "2 entrées mal formées ignorées" in bloc
    assert "1 entrée mal formée ignorée" in brs.bloc_graphies(
        _contenu(graphies=_graphies(ecartees=1)))


def test_une_graphie_piegee_est_echappee():
    plus = [{"fausse": CHARGE, "juste": JS, "vu": 1}]
    bloc = brs.bloc_graphies(_contenu(graphies=_graphies(plus)))
    assert "<script>alert" not in bloc and '"><script>' not in bloc


# ---- Liens morts -----------------------------------------------------------------

def test_les_liens_morts_disent_le_nombre_la_date_et_l_age():
    bloc = brs.bloc_liens(_contenu())
    assert "1 lien mort" in bloc and "rapport du 25/11" in bloc and "il y a 4 jours" in bloc
    assert "ancien" not in bloc
    assert 'href="https://exemple.test/a"' in bloc and "404" in bloc and "1 reco" in bloc


def test_un_rapport_du_jour_et_plusieurs_morts():
    liste = [_lien(recos=("a", "b")), _lien("http://exemple.test/b")]
    bloc = brs.bloc_liens(_contenu(liens=_liens(liste, age=0)))
    assert "2 liens morts" in bloc and "aujourd'hui" in bloc and "2 recos" in bloc
    assert 'href="http://exemple.test/b"' in bloc


def test_un_rapport_de_plus_de_8_jours_est_ancien():
    bloc = brs.bloc_liens(_contenu(liens=_liens(age=9, ancien=True)))
    assert "ancien" in bloc and "il y a 9 jours" in bloc


def test_aucun_lien_mort_dans_un_rapport_lu():
    bloc = brs.bloc_liens(_contenu(liens=_liens([])))
    assert "Aucun lien mort" in bloc and "<ul" not in bloc


def test_la_liste_des_liens_coupee_dit_combien_restent():
    liste = [_lien(f"https://exemple.test/{k}") for k in range(10)]
    bloc = brs.bloc_liens(_contenu(liens=_liens(liste, morts=13)))
    assert "13 liens morts" in bloc and "+ 3 autres" in bloc


def test_une_adresse_qui_n_est_pas_http_reste_du_texte_echappe():
    liste = [_lien(JS), _lien("ftp://exemple.test/x"), _lien(CHARGE)]
    bloc = brs.bloc_liens(_contenu(liens=_liens(liste)))
    assert "<a " not in bloc
    assert 'href="javascript:' not in bloc and "<script>alert" not in bloc
    assert JS in bloc  # le texte reste lisible, sans lien


def test_une_adresse_http_piegee_n_echappe_pas_son_attribut():
    bloc = brs.bloc_liens(_contenu(liens=_liens([_lien('https://x.test/"><script>a</script>')])))
    assert '"><script>' not in bloc and "&quot;&gt;&lt;script&gt;" in bloc


def test_une_reponse_piegee_et_une_adresse_longue_sont_echappees_et_coupees():
    bloc = brs.bloc_liens(_contenu(liens=_liens([_lien("https://x.test/" + "a" * 300,
                                                       reponse=CHARGE)])))
    assert "<script>alert" not in bloc and "…" in bloc


def test_les_recos_qui_ne_sont_pas_une_liste_ne_cassent_pas_le_bloc():
    bloc = brs.bloc_liens(_contenu(liens=_liens([{"url": "https://x.test", "reponse": "404",
                                                  "recos": None}])))
    assert "https://x.test" in bloc and "reco" not in bloc.split("404")[1]


def test_une_date_de_rapport_ou_un_age_illisibles():
    liens = _liens(date="pas une date", age="x")
    bloc = brs.bloc_liens(_contenu(liens=liens))
    assert "pas une date" in bloc and "il y a" not in bloc


# ---- Dans la page ---------------------------------------------------------------

def _page(**kw):
    chaine = {"episode": None, "etapes": [], "passages": [], "erreurs": [], "etat_lu": True}
    args = {"titre": "Un Bon Moment", "afaire": [], "chaine": chaine,
            "recents": [], "coches": {}, "maintenant": MAINTENANT}
    args.update(kw)
    return br.rendre_bord(**args)


def _colonne(page, cle):
    return page.split(f'id="bord-{cle}"', 1)[1].split("</section>", 1)[0]


def test_la_page_place_les_sorties_dans_les_reseaux_et_le_reste_dans_le_systeme():
    page = _page(contenu=_contenu())
    assert "Sorties à venir" in _colonne(page, "reseaux") and "Un film" in _colonne(page, "reseaux")
    systeme = _colonne(page, "systeme")
    assert "Liens morts" in systeme and "Graphies apprises" in systeme
    assert "data-attente" not in page


def test_la_page_sans_contenu_dit_inconnu_pour_les_trois_blocs():
    page = _page()
    assert "Sorties à venir" in page and "data-attente" not in page
    assert page.count("inconnu") >= 3


def test_la_page_piegee_ne_contient_aucune_balise_active():
    contenu = _contenu(sorties=_sorties([_sortie(CHARGE)]),
                       graphies=_graphies([{"fausse": CHARGE, "juste": CHARGE, "vu": 1}]),
                       liens=_liens([_lien(JS, reponse=CHARGE), _lien(CHARGE)]))
    page = _page(contenu=contenu)
    assert "<script>alert" not in page and 'href="javascript:' not in page
    assert '"><script>' not in page
