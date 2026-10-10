"""Tests de `tools/invites_titre.py` — les invités d'un épisode, lus dans son titre.

Titres réels du corpus. Mesuré le 2026-10-09 sur les 40 titres des saisons 5 et 6
dont les invités ont été relus : 37 identiques, contre 22 avec l'ancienne
heuristique ; les trois écarts viennent du titre lui-même (« Rosa Burzstein »,
« Paul de St Sernin ») ou d'une phrase (« le gros rein de Camille Combal »).
"""
from __future__ import annotations

import pytest

import extract_recos as er
from invites_titre import invites_du_titre

HOTES = ["Kyan Khojandi", "Navo"]


@pytest.mark.parametrize(("titre", "invites"), [
    # Saisons 5 et 6 : les noms en tête, puis une phrase.
    ("Félix Radu et Carla de Coignac mettent de la poésie partout (Un Bon Moment, S6-E04)",
     ["Félix Radu", "Carla de Coignac"]),
    ("Babor et Jenny Letellier irremplaçables (Un Bon Moment, S6-E03)", ["Babor", "Jenny Letellier"]),
    ("Géraldine Nakache, Clémentine Célarié et des montagnes russes d'émotions (Un Bon Moment, S6-E02)",
     ["Géraldine Nakache", "Clémentine Célarié"]),
    ("Albert Dupontel, ce grand maître du cinéma (Un Bon Moment, S5-E7)", ["Albert Dupontel"]),
    ("Orelsan, c’est lui le boss final de la saison (Un Bon Moment, S5-E37)", ["Orelsan"]),
    ("Cyprien et Fanny La Panny multiplient les talents cachés (Un Bon Moment, S5-E18)",
     ["Cyprien", "Fanny La Panny"]),
    ("Oli et Seb de bon matin et de bonne humeur (Un Bon Moment, S5-E28)", ["Oli", "Seb"]),
    ("Jason Brokerss et AZ, les voilà les vraies stars (Un Bon Moment, S5-E34)", ["Jason Brokerss", "AZ"]),
    ("Alex Ramirès et Thaïs Vauquières plus complices que Navo et moi ??? (Un Bon Moment, S5-E33)",
     ["Alex Ramirès", "Thaïs Vauquières"]),
    ("Doully et David Castello-Lopes en mode confessions (Un Bon Moment, S5-E30)",
     ["Doully", "David Castello-Lopes"]),
    # Ancienne forme, Acast.
    ("avec HAKIM JEMILI", ["Hakim Jemili"]),
    ("avec Laurie et Pablo", ["Laurie", "Pablo"]),
    ("avec JULIEN GRANEL ET CLÉMENT VIKTOROVITCH", ["Julien Granel", "Clément Viktorovitch"]),
    ("avec YVICK (MISTER V) et FREDDY GLADIEUX", ["Yvick", "Freddy Gladieux"]),
    ("avec l'humoriste FADILY CAMARA", ["Fadily Camara"]),
])
def test_les_invites_du_titre(titre, invites):
    assert invites_du_titre(titre, HOTES) == invites


@pytest.mark.parametrize("titre", [
    "Qui est Greg Romano ? Épisode 1 (Un Bon Moment, hors-série)",
    "Épisode spécial",
    "Invité (Un Bon Moment, S6-E1)",
    "",
    None,
])
def test_un_titre_sans_nom_ne_donne_aucun_invite(titre):
    assert invites_du_titre(titre, HOTES) == []


def test_les_animateurs_et_les_doublons_sont_ecartes():
    assert invites_du_titre("Kyan Khojandi, Navo & Orelsan parlent", HOTES) == ["Orelsan"]
    assert invites_du_titre("avec Alice et ALICE", []) == ["Alice"]


def test_un_nom_trop_long_n_en_est_pas_un():
    assert invites_du_titre("Un Deux Trois Quatre Cinq Six sept", []) == []


# ===== consigne de l'extraction ==============================================
def test_l_extraction_connait_les_invites_de_l_episode():
    source = {"hosts": HOTES}
    assert er._intervenants(source, {"guests": ["Orelsan"]}) == (
        "Kyan Khojandi, Navo ; invités de l'épisode : Orelsan")


def test_sans_invites_enregistres_l_extraction_les_lit_dans_le_titre():
    episode = {"guests": [], "title": "Babor et Jenny Letellier irremplaçables (Un Bon Moment, S6-E03)"}
    assert er._intervenants({"hosts": HOTES}, episode) == (
        "Kyan Khojandi, Navo ; invités de l'épisode : Babor, Jenny Letellier")


def test_sans_animateur_ni_invite():
    assert er._intervenants({}, {"title": "Épisode spécial"}) == "inconnus"
