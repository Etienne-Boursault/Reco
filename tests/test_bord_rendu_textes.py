"""Tests des textes du tableau de bord (revue globale, tranche B2).

Décision : tableau de bord, R2 B du 27/11/2026 ; revue globale du 28/11/2026. Chaque test
vient d'un défaut de libellé vu sur la page : accord, « 1er », durées en jours, jour des
passages, majuscule d'un réseau, bouton d'une PR qui n'existe pas encore.

Le rendu est pur : aucune lecture de disque ni de réseau, fuseau forcé à UTC.
"""
from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta, timezone

import pytest

import bord_afaire as ba
import bord_rendu_blocs as bb
import bord_rendu_systeme as brs
from bord_reseaux import LIBELLES

MAINTENANT = datetime(2026, 11, 29, 10, 51, tzinfo=UTC)  # un dimanche
RUN = "https://github.com/Etienne-Boursault/Reco/actions/runs/42"


@pytest.fixture(autouse=True)
def _utc(monkeypatch):
    monkeypatch.setattr(bb, "_fuseau", lambda: UTC)


# ---- L'accord de la conclusion : « réussi » pour le déploiement, « réussie » pour la CI ----

def _github(conclusion):
    course = {"conclusion": conclusion, "date": "2026-11-28T08:04:00Z", "adresse": RUN}
    return {"etat": "ok", "donnees": {"ci": course, "deploiement": course}, "age": 60}


def _ligne(bloc, nom):
    return re.search(rf"<li[^>]*><span>{nom}</span><span>([^<]*)</span>", bloc).group(1)


@pytest.mark.parametrize("conclusion,ci,deploiement", [
    ("success", "réussie", "réussi"), ("cancelled", "annulée", "annulé"),
    ("failure", "échec", "échec")])
def test_la_conclusion_s_accorde_avec_ce_qu_elle_qualifie(conclusion, ci, deploiement):
    bloc = brs.bloc_sante(_github(conclusion), None)
    assert _ligne(bloc, "CI de main") == ci
    assert _ligne(bloc, "Dernier déploiement") == deploiement


def test_une_conclusion_inconnue_ne_change_pas_selon_la_ligne():
    bloc = brs.bloc_sante(_github("timed_out"), None)
    assert _ligne(bloc, "Dernier déploiement") == "autre : timed_out"
    assert _ligne(bloc, "CI de main") == "autre : timed_out"


# ---- La date du jour : « 1er » ----------------------------------------------

@pytest.mark.parametrize("jour,attendu", [
    (datetime(2026, 12, 1, 9, tzinfo=UTC), "mardi 1er décembre"),
    (datetime(2026, 12, 2, 9, tzinfo=UTC), "mercredi 2 décembre"),
    (datetime(2026, 11, 29, 9, tzinfo=UTC), "dimanche 29 novembre"),
    (datetime(2026, 12, 11, 9, tzinfo=UTC), "vendredi 11 décembre")])
def test_le_premier_du_mois_s_ecrit_1er(jour, attendu):
    assert bb.date_du_jour(jour) == attendu


# ---- Les durées : des jours au-delà de 48 h --------------------------------------

@pytest.mark.parametrize("ecart,attendu", [
    (timedelta(seconds=30), "à l'instant"),
    (timedelta(minutes=12), "il y a 12 min"),
    (timedelta(hours=2, minutes=5), "il y a 2 h 05"),
    (timedelta(hours=47, minutes=59), "il y a 47 h 59"),
    (timedelta(hours=48), "il y a 2 j 0 h"),
    (timedelta(hours=55, minutes=33), "il y a 2 j 7 h"),
    (timedelta(days=10, hours=3, minutes=40), "il y a 10 j 3 h")])
def test_une_duree_passe_aux_jours_au_dela_de_48_h(ecart, attendu):
    assert bb._depuis(ecart) == attendu


def _audience(age, etat="panne"):
    sig = {"etat": "lu", "total": 1, "enAttente": [
        {"id": "r", "recoId": "ubm-0", "categorie": "error", "date": "2026-11-27T10:00:00Z"}]}
    return {"etat": etat, "donnees": {"signalements": sig}, "age": age}


def test_les_signalements_gardes_apres_une_panne_disent_leur_age_sans_tournure_boiteuse():
    bloc = bb.bloc_signalements(_audience(55 * 3600 + 33 * 60))
    assert "Données d'il y a 2 j 7 h : l'audience n'a pas pu être relue." in bloc
    assert "Liste des données" not in bloc


def test_des_signalements_ok_mais_anciens_disent_perime_sans_tournure_boiteuse():
    bloc = bb.bloc_signalements(_audience(3 * 3600, etat="ok"))
    assert "Périmé : données d'il y a 3 h 00." in bloc
    assert "Liste des données" not in bloc


# ---- Les passages disent leur jour quand ce n'est pas aujourd'hui ----------------------

def _chaine(*debuts):
    passages = [{"debut": d, "fin": d, "lancees": [], "echecs": []} for d in debuts]
    return {"episode": None, "etapes": [], "passages": passages, "erreurs": [], "etat_lu": True}


def _textes_passages(contenu):
    return re.findall(r'<li data-echec="\d"><span>(.*?) · ', contenu)


def test_un_passage_d_hier_porte_son_jour_et_celui_d_aujourd_hui_non():
    chaine = _chaine("2026-11-29T10:17:00+00:00", "2026-11-28T23:05:00+00:00",
                     "2026-11-22T10:00:00+00:00", "pas une date")
    contenu = bb.bloc_chaine(chaine, MAINTENANT)
    assert _textes_passages(contenu) == ["10 h 17", "sam. 23 h 05", "dim. 10 h 00", "?"]


def test_le_jour_d_un_passage_se_compte_dans_le_fuseau_de_la_page(monkeypatch):
    monkeypatch.setattr(bb, "_fuseau", lambda: timezone(timedelta(hours=1)))
    # 23 h 30 UTC samedi = 00 h 30 dimanche en heure d'hiver de Paris : le même jour que « maintenant ».
    contenu = bb.bloc_chaine(_chaine("2026-11-28T23:30:00+00:00"), MAINTENANT)
    assert _textes_passages(contenu) == ["00 h 30"]


def test_sans_heure_de_reference_les_passages_ne_portent_pas_de_jour():
    contenu = bb.bloc_chaine(_chaine("2026-11-22T10:00:00+00:00"))
    assert _textes_passages(contenu) == ["10 h 00"]


# ---- Les réseaux : une majuscule partout -------------------------------------------------

def test_chaque_libelle_de_reseau_commence_par_une_majuscule():
    assert all(nom[0].isupper() for nom in LIBELLES.values())
    assert LIBELLES["youtube"] == "Commentaire YouTube"


# ---- Une PR qui n'existe pas encore se crée, elle ne s'ouvre pas ----------------------

def _item(texte, href):
    return {"bloc": "publication", "texte": texte, "guid": None, "inconnu": False, "href": href}


def test_la_ligne_ouvrir_puis_fusionner_porte_un_bouton_creer_la_pr():
    compare = "https://github.com/Etienne-Boursault/Reco/compare/main...contenu/yt-11?expand=1"
    contenu, _ = bb.bloc_afaire([_item("ouvrir puis fusionner la PR de S6·E11", compare)])
    assert f'href="{compare}"' in contenu and ">Créer la PR<" in contenu
    assert "Ouvrir la PR" not in contenu


def test_une_pr_qui_existe_garde_le_bouton_ouvrir_la_pr():
    pr = "https://github.com/Etienne-Boursault/Reco/pull/41"
    contenu, _ = bb.bloc_afaire([_item("fusionner la PR de S6·E11 (#41)", pr),
                                 _item("fusionner la PR #42 : titre", pr)])
    assert contenu.count(">Ouvrir la PR<") == 2 and "Créer la PR" not in contenu


def test_le_texte_de_la_ligne_vient_toujours_de_bord_afaire():
    """Le bouton se règle sur le texte que `lignes_publication` écrit : si l'un change, l'autre suit."""
    recent = {"guid": "yt-11", "fusionne": False,
              "episode": {"guid": "yt-11", "title": "Onze", "season": 6, "number": 11}}
    github = {"etat": "ok", "donnees": {
        "depot": "Etienne-Boursault/Reco", "fusionnees": [],
        "ouvertes": {"episodes": [], "sorties": [], "coupee": False}}}
    lignes = ba.lignes_publication(github, [recent])
    assert lignes and lignes[0][0].startswith(ba.A_CREER)
