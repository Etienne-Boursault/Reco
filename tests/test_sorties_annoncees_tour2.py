"""Tests de `tools/sorties_annoncees.py` ajoutés au tour 2 de revue de la PR #227.

Même banc que `test_sorties_annoncees.py` (git réel, `origin` nu local ; passes, publication,
Matrix et horloge remplacés).
"""
from __future__ import annotations

from datetime import timedelta

import pytest

import sorties_annoncees as sa
import sorties_plan as sp
import test_sorties_annoncees as base
from publication import ErreurGit
from test_sorties_annoncees import CLE, Banc, Passe

depot, banc, paris = base.depot, base.banc, base.paris


# --- le message 🗓️ qui n'est pas parti est retenté ----------------------------------------

def _matrix_coupe(_texte):
    raise OSError("Matrix coupé")


def test_un_message_de_pr_non_parti_est_retente_au_passage_suivant(banc):
    banc.lancer(notify=_matrix_coupe)
    proposition = banc.etat()["propositions"][CLE]
    assert "pull/1" in proposition["annonce"]  # le lien de la PR est gardé
    banc.maintenant += timedelta(days=1)
    banc.lancer([("musique", Passe())])
    [message] = banc.messages
    assert "🗓️" in message and "pull/1" in message
    assert "annonce" not in banc.etat()["propositions"][CLE]
    banc.maintenant += timedelta(days=1)
    banc.lancer([("musique", Passe())])
    assert len(banc.messages) == 1  # une seule fois


def test_un_message_de_pr_parti_ne_laisse_rien_a_retenter(banc):
    banc.lancer()
    assert "annonce" not in banc.etat()["propositions"][CLE]


def test_un_message_de_pr_retente_garde_les_avertissements(banc):
    banc.publieur.resultat.avertissements.append("PR non ouverte (URLError)")
    banc.lancer(notify=_matrix_coupe)
    banc.maintenant += timedelta(days=1)
    banc.lancer([("musique", Passe())])
    assert banc.messages[0].endswith("PR non ouverte (URLError)")


def test_l_etat_d_avant_sans_annonce_reste_lisible(banc):
    etat = sp.noter_proposition(sp.etat_vide(), CLE, "b", "s", ["u"])
    assert sp.annonces_en_attente(etat) == {}
    etat = sp.noter_proposition(etat, CLE, "b", "s", ["u"], annonce="texte")
    assert sp.annonces_en_attente(etat) == {CLE: "texte"}
    assert sp.annonces_en_attente(sp.noter_annonce_envoyee(etat, CLE)) == {}


# --- git grep : seuls les codes 0 et 1 sont admis ---------------------------------------------

def test_un_git_grep_qui_echoue_n_est_pas_lu_comme_aucune_reco(banc, depot):
    _git = base._git
    _git(depot, "update-ref", "-d", "refs/remotes/origin/main")  # git grep rend 128
    with pytest.raises(ErreurGit):
        sa._recos_sur_origin(sa.Git(depot), "un-bon-moment")
    assert banc.lancer(apercu=True) == 1  # la panne git déjà en place, sans envoi ni état


def test_un_git_grep_sans_resultat_rend_aucune_reco(depot):
    assert sa._recos_sur_origin(sa.Git(depot), "source-inconnue") == ({}, [])
