"""Tests de `sorties_plan` : le plan du jour de la relance des sorties annoncées (R4 B, 27/11/2026).

Pur : « aujourd'hui », les recos, l'état et les faits de git (branche présente, commit
ancêtre, fichier modifié) sont passés en paramètres. Seule l'écriture de l'état touche au
disque, dans un dossier temporaire.
"""
from __future__ import annotations

import copy
import json
import os
from datetime import date

import pytest

import sorties_plan as sp

AUJOURDHUI = date(2026, 11, 27)


def reco(num: int = 3348, **champs) -> dict:
    doc = {"id": f"ubm-{num}", "sourceId": "un-bon-moment", "status": "validated",
           "types": ["album"], "title": "(Re)belle", "releaseDate": "2026-11-20"}
    doc.update(champs)
    return doc


def plan(recos, etat=None, *, sur_origin=None, modifiees=(), en_attente=(), jour=AUJOURDHUI):
    recos = list(recos)
    if sur_origin is None:
        sur_origin = {sp.cle_de(r) for r in recos}
    return sp.plan_du_jour(recos, jour, etat or sp.etat_vide(), sur_origin=set(sur_origin),
                           modifiees=set(modifiees), en_attente=set(en_attente))


# --- la clé -----------------------------------------------------------------------

def test_la_cle_joint_la_source_et_l_identifiant():
    assert sp.cle_de(reco()) == "un-bon-moment/ubm-3348"


# --- la sélection -----------------------------------------------------------------

def test_une_reco_dans_la_fenetre_est_a_relancer():
    r = reco()
    assert plan([r]).a_relancer == [r]


@pytest.mark.parametrize("statut", ["draft", "discard", None])
def test_seule_une_reco_validee_est_retenue(statut):
    r = reco(status=statut)
    assert plan([r]).a_relancer == []


@pytest.mark.parametrize("types", [["film"], ["serie"], ["artiste"], []])
def test_un_type_hors_de_la_v1_est_ignore(types):
    assert plan([reco(types=types)]).a_relancer == []


@pytest.mark.parametrize("type_", ["album", "musique", "livre", "jeu"])
def test_les_types_de_la_v1_sont_retenus(type_):
    assert len(plan([reco(types=[type_])]).a_relancer) == 1


def test_un_type_servi_parmi_d_autres_suffit():
    assert len(plan([reco(types=["film", "album"])]).a_relancer) == 1


@pytest.mark.parametrize("sortie,attendu", [
    ("2026-11-28", False),  # veille de la sortie
    ("2026-11-27", True),   # le jour même
    ("2026-10-28", True),   # J+30
    ("2026-10-27", False),  # J+31
])
def test_la_fenetre_va_du_jour_de_la_sortie_a_j_plus_30(sortie, attendu):
    assert bool(plan([reco(releaseDate=sortie)]).a_relancer) is attendu


@pytest.mark.parametrize("valeur", [None, "", "2026-02-30", "20261120", 20261120])
def test_une_date_absente_ou_fausse_est_ignoree_sans_erreur(valeur):
    r = reco(releaseDate=valeur)
    assert plan([r]).a_relancer == []
    sans = {k: v for k, v in r.items() if k != "releaseDate"}
    assert plan([sans]).a_relancer == []


def test_une_reco_absente_d_origin_main_est_ignoree():
    r = reco()
    p = plan([r], sur_origin=set(), modifiees={sp.cle_de(r)})
    assert p.a_relancer == [] and p.modifiees == []


def test_une_reco_modifiee_dans_le_clone_est_sautee_et_a_signaler():
    r = reco()
    p = plan([r], modifiees={sp.cle_de(r)})
    assert p.a_relancer == [] and p.modifiees == [r]


def test_la_reco_modifiee_n_est_signalee_qu_une_fois_par_cle():
    r = reco()
    etat = sp.noter_signal(sp.etat_vide(), "sautee", sp.cle_de(r))
    p = plan([r], etat, modifiees={sp.cle_de(r)})
    assert p.a_relancer == [] and p.modifiees == []
    autre = reco(9999)
    p = plan([r, autre], etat, modifiees={sp.cle_de(r), sp.cle_de(autre)})
    assert p.modifiees == [autre]


def test_une_reco_modifiee_hors_fenetre_n_est_pas_signalee():
    r = reco(releaseDate="2026-01-01")
    assert plan([r], modifiees={sp.cle_de(r)}).modifiees == []


def test_une_proposition_en_attente_saute_la_reco_sans_signal():
    r = reco()
    p = plan([r], en_attente={sp.cle_de(r)})
    assert p.a_relancer == [] and p.modifiees == []


def test_les_autres_recos_passent_malgre_une_proposition_en_attente():
    a, b = reco(1), reco(2)
    assert plan([a, b], en_attente={sp.cle_de(a)}).a_relancer == [b]


# --- la proposition en attente ----------------------------------------------------

@pytest.mark.parametrize("branche,ancetre,attendu", [
    (True, False, True),    # PR ouverte
    (True, True, False),    # fusionnée, branche pas encore supprimée
    (False, False, False),  # PR refermée, branche supprimée
    (False, True, False),
])
def test_on_saute_tant_que_la_branche_existe_et_n_est_pas_fusionnee(branche, ancetre, attendu):
    assert sp.proposition_en_attente(branche, ancetre) is attendu


# --- la non-reproposition des mêmes adresses ---------------------------------------

def test_une_adresse_deja_proposee_n_est_pas_reproposee():
    cle = sp.cle_de(reco())
    etat = sp.noter_proposition(sp.etat_vide(), cle, "contenu/sorties-2026-11-27", "abc123",
                                ["https://a/1", "https://a/2"])
    assert sp.adresses_nouvelles(etat, cle, ["https://a/1", "https://a/3", "https://a/2"]) == [
        "https://a/3"]


def test_sans_proposition_toutes_les_adresses_sont_nouvelles():
    assert sp.adresses_nouvelles(sp.etat_vide(), "x/y", ["u1", "u2"]) == ["u1", "u2"]


def test_les_adresses_s_accumulent_d_une_proposition_a_l_autre():
    cle = "x/y"
    etat = sp.noter_proposition(sp.etat_vide(), cle, "b1", "s1", ["u1"])
    etat = sp.noter_proposition(etat, cle, "b2", "s2", ["u2", "u1"])
    assert etat["propositions"][cle] == {"branche": "b2", "sha": "s2", "adresses": ["u1", "u2"],
                                         "derniere": ["u2", "u1"], "externalIds": {}}


# --- le signal ⏳ -----------------------------------------------------------------

def test_aucun_signal_pour_une_reco_jamais_relancee_meme_vieille_de_deux_ans():
    vieille = reco(releaseDate="2024-11-20")
    assert sp.sabliers([vieille], AUJOURDHUI, sp.etat_vide()) == []


def test_le_signal_part_a_la_fermeture_de_la_fenetre_d_une_reco_relancee():
    r = reco(releaseDate="2026-10-27")  # J+31
    etat = sp.noter_relance(sp.etat_vide(), [sp.cle_de(r)])
    assert sp.sabliers([r], AUJOURDHUI, etat) == [r]


def test_pas_de_signal_tant_que_la_fenetre_est_ouverte():
    r = reco(releaseDate="2026-10-28")  # J+30
    etat = sp.noter_relance(sp.etat_vide(), [sp.cle_de(r)])
    assert sp.sabliers([r], AUJOURDHUI, etat) == []


def test_pas_de_signal_si_la_relance_a_pose_un_lien():
    r = reco(releaseDate="2026-10-27")
    etat = sp.noter_relance(sp.etat_vide(), [sp.cle_de(r)])
    etat = sp.noter_proposition(etat, sp.cle_de(r), "b", "s", ["https://a/1"])
    assert sp.sabliers([r], AUJOURDHUI, etat) == []


def test_le_signal_ne_part_qu_une_fois():
    r = reco(releaseDate="2026-10-27")
    etat = sp.noter_relance(sp.etat_vide(), [sp.cle_de(r)])
    assert sp.sabliers([r], AUJOURDHUI, etat) == [r]
    etat = sp.noter_signal(etat, "sablier", sp.cle_de(r))
    assert sp.sabliers([r], AUJOURDHUI, etat) == []


@pytest.mark.parametrize("champs", [{"status": "draft"}, {"types": ["film"]},
                                    {"releaseDate": "2026-02-30"}])
def test_pas_de_signal_pour_une_reco_qui_n_est_plus_relancable(champs):
    r = {**reco(releaseDate="2026-10-27"), **champs}
    etat = sp.noter_relance(sp.etat_vide(), [sp.cle_de(r)])
    assert sp.sabliers([r], AUJOURDHUI, etat) == []


# --- l'état : fonctions pures ----------------------------------------------------

def test_l_etat_vide_a_toutes_ses_cles_et_n_est_pas_partage():
    a, b = sp.etat_vide(), sp.etat_vide()
    a["relancees"].append("x")
    assert b["relancees"] == []
    assert set(a) == {"dernier_jour", "propositions", "relancees", "signaux", "erreurs",
                      "liens_au_depart"}


def test_les_fonctions_de_l_etat_ne_modifient_pas_leur_argument():
    etat = sp.etat_vide()
    avant = copy.deepcopy(etat)
    sp.noter_relance(etat, ["a"])
    sp.noter_proposition(etat, "a", "b", "s", ["u"])
    sp.noter_signal(etat, "sablier", "a")
    sp.noter_erreur(etat, "a", "panne")
    sp.noter_jour(etat, AUJOURDHUI)
    assert etat == avant


def test_noter_relance_sans_doublon_et_trie():
    etat = sp.noter_relance(sp.etat_vide(), ["b", "a"])
    etat = sp.noter_relance(etat, ["a", "c"])
    assert etat["relancees"] == ["a", "b", "c"]


def test_le_jour_traite_s_ecrit_et_se_relit():
    etat = sp.etat_vide()
    assert sp.jour_deja_traite(etat, AUJOURDHUI) is False
    etat = sp.noter_jour(etat, AUJOURDHUI)
    assert etat["dernier_jour"] == "2026-11-27"
    assert sp.jour_deja_traite(etat, AUJOURDHUI) is True
    assert sp.jour_deja_traite(etat, date(2026, 11, 28)) is False


def test_signal_deja_envoye():
    etat = sp.etat_vide()
    assert sp.deja_signale(etat, "sablier", "a") is False
    etat = sp.noter_signal(etat, "sablier", "a")
    assert sp.deja_signale(etat, "sablier", "a") is True
    assert sp.deja_signale(etat, "sautee", "a") is False
    assert sp.noter_signal(etat, "sablier", "a")["signaux"] == ["sablier:a"]


def test_une_panne_n_est_signalee_qu_une_fois_par_cle_jusqu_a_sa_reparation():
    etat, premiere = sp.noter_erreur(sp.etat_vide(), "a", "délai dépassé")
    assert premiere is True and etat["erreurs"] == {"a": "délai dépassé"}
    etat, premiere = sp.noter_erreur(etat, "a", "autre message")
    assert premiere is False and etat["erreurs"]["a"] == "autre message"
    etat, premiere = sp.noter_erreur(etat, "b", "panne")
    assert premiere is True
    etat = sp.effacer_erreur(etat, "a")
    assert "a" not in etat["erreurs"] and "b" in etat["erreurs"]
    _, premiere = sp.noter_erreur(etat, "a", "de nouveau")
    assert premiere is True


def test_effacer_une_erreur_absente_ne_change_rien():
    assert sp.effacer_erreur(sp.etat_vide(), "a") == sp.etat_vide()


# --- l'état : lecture et écriture --------------------------------------------------

def test_un_fichier_absent_donne_l_etat_vide(tmp_path):
    assert sp.lire_etat(tmp_path / "absent.json") == sp.etat_vide()


def test_l_etat_ecrit_se_relit_a_l_identique(tmp_path):
    chemin = tmp_path / "pipeline" / "sorties-annoncees.json"
    etat = sp.noter_proposition(sp.etat_vide(), "x/y", "contenu/sorties-2026-11-27", "abc", ["u"])
    etat = sp.noter_jour(sp.noter_signal(sp.noter_relance(etat, ["x/y"]), "sablier", "z/w"),
                         AUJOURDHUI)
    etat, _ = sp.noter_erreur(etat, "x/y", "délai dépassé : é")
    sp.ecrire_etat(chemin, etat)
    assert sp.lire_etat(chemin) == etat
    assert not chemin.with_suffix(".json.tmp").exists()
    assert "é" in chemin.read_text(encoding="utf-8")  # accents gardés, pas d'échappement


def test_une_ecriture_ratee_laisse_l_ancien_fichier(tmp_path, monkeypatch):
    chemin = tmp_path / "etat.json"
    sp.ecrire_etat(chemin, sp.noter_relance(sp.etat_vide(), ["a"]))
    avant = chemin.read_text(encoding="utf-8")

    def casse(*_a, **_k):
        raise OSError("disque plein")
    monkeypatch.setattr(os, "replace", casse)
    with pytest.raises(OSError):
        sp.ecrire_etat(chemin, sp.noter_relance(sp.etat_vide(), ["b"]))
    assert chemin.read_text(encoding="utf-8") == avant
    assert not chemin.with_suffix(".json.tmp").exists()


def test_un_etat_incomplet_est_complete_par_les_valeurs_vides(tmp_path):
    chemin = tmp_path / "etat.json"
    chemin.write_text(json.dumps({"relancees": ["a"]}), encoding="utf-8")
    etat = sp.lire_etat(chemin)
    assert etat["relancees"] == ["a"] and etat["propositions"] == {} and etat["dernier_jour"] is None


@pytest.mark.parametrize("contenu", [
    "", "{pas du json", "[]", '"texte"', "null",
    '{"relancees": "a"}', '{"propositions": []}', '{"signaux": {}}', '{"erreurs": []}',
    '{"dernier_jour": 20261127}', '{"propositions": {"a": "b"}}',
    '{"propositions": {"a": {"branche": "b", "sha": "s", "adresses": "u"}}}',
])
def test_un_etat_illisible_arrete_l_etape_sans_reecriture(tmp_path, contenu):
    chemin = tmp_path / "etat.json"
    chemin.write_text(contenu, encoding="utf-8")
    with pytest.raises(sp.EtatIllisible):
        sp.lire_etat(chemin)
    assert chemin.read_text(encoding="utf-8") == contenu


def test_un_fichier_non_utf8_est_illisible(tmp_path):
    chemin = tmp_path / "etat.json"
    chemin.write_bytes(b"\xff\xfe\x00")
    with pytest.raises(sp.EtatIllisible):
        sp.lire_etat(chemin)


# --- les messages -----------------------------------------------------------------

def test_le_message_de_trouvaille_donne_les_liens_la_pr_et_le_rappel_des_playlists():
    m = sp.message_trouvaille(reco(), ["Deezer", "Apple Music"], "https://github.com/x/y/pull/9")
    assert m.startswith("🗓️ « (Re)belle » : 2 liens trouvés après sa sortie du 20/11")
    assert "(Deezer, Apple Music)" in m and "https://github.com/x/y/pull/9" in m
    assert "playlists" in m and "œuvre" in m and "recos sœurs" in m


def test_le_message_de_trouvaille_dit_de_supprimer_la_branche_d_une_pr_refermee():
    # Sans jeton GitHub, la relance ne voit pas la fermeture : seule la branche supprimée la prévient.
    m = sp.message_trouvaille(reco(), ["Deezer"], "lien")
    assert "refermée sans fusion" in m and "supprimer sa branche" in m


def test_le_message_de_trouvaille_au_singulier():
    m = sp.message_trouvaille(reco(), ["Deezer"], "lien")
    assert "1 lien trouvé après" in m and "liens" not in m.split("playlists")[0]


def test_le_message_du_signal_dit_que_la_relance_s_arrete():
    m = sp.message_sablier(reco(releaseDate="2026-10-27"))
    assert m.startswith("⏳ « (Re)belle »") and "27/10" in m and "30 jours" in m


def test_le_message_de_reco_sautee_explique_comment_la_reprendre():
    m = sp.message_modifiee(reco())
    assert "« (Re)belle »" in m and "reco modifiée, sautée" in m


def test_le_message_de_panne_porte_la_cle_et_le_message():
    m = sp.message_panne("un-bon-moment/ubm-3348", "délai dépassé")
    assert m.startswith("⚠️") and "un-bon-moment/ubm-3348" in m and "délai dépassé" in m


# --- tour 1 de revue, PR #227 -------------------------------------------------------

def test_une_proposition_garde_les_adresses_de_sa_derniere_pr_et_cumule_les_identifiants():
    etat = sp.noter_proposition(sp.etat_vide(), "x/y", "b1", "s1", ["u1"], {"deezer": "1"})
    etat = sp.noter_proposition(etat, "x/y", "b2", "s2", ["u2"], {"itunes": "2"})
    p = etat["propositions"]["x/y"]
    assert p["derniere"] == ["u2"] and p["adresses"] == ["u1", "u2"]
    assert p["externalIds"] == {"deezer": "1", "itunes": "2"}


def test_les_identifiants_proposes_se_lisent_ensemble_avec_les_adresses():
    etat = sp.noter_proposition(sp.etat_vide(), "x/y", "b", "s", ["u"], {"deezer": "1"})
    assert sp.identifiants_deja_proposes(etat, "x/y") == {"deezer": "1"}
    assert sp.identifiants_deja_proposes(etat, "autre") == {}


def test_en_fenetre_dit_si_la_reco_est_relancable_aujourd_hui():
    assert sp.en_fenetre(reco(releaseDate="2026-11-20"), AUJOURDHUI)
    assert not sp.en_fenetre(reco(releaseDate="2026-10-27"), AUJOURDHUI)  # J+31
    assert not sp.en_fenetre(reco(releaseDate="2026-11-28"), AUJOURDHUI)  # demain
    assert not sp.en_fenetre(reco(status="draft"), AUJOURDHUI)


def test_la_premiere_relance_garde_les_liens_de_depart_et_la_suivante_ne_les_change_pas():
    etat = sp.noter_relance(sp.etat_vide(), ["x/y"], {"x/y": ["u2", "u1"]})
    assert etat["liens_au_depart"] == {"x/y": ["u1", "u2"]}
    etat = sp.noter_relance(etat, ["x/y"], {"x/y": ["u1", "u2", "u3"]})
    assert etat["liens_au_depart"] == {"x/y": ["u1", "u2"]}


def test_pas_de_sablier_si_l_editeur_a_pose_un_lien_depuis_la_premiere_relance():
    r = reco(releaseDate="2026-10-27", links=[{"url": "https://a/1"}])
    etat = sp.noter_relance(sp.etat_vide(), [sp.cle_de(r)], {sp.cle_de(r): ["https://a/1"]})
    assert sp.sabliers([r], AUJOURDHUI, etat) == [r]  # rien de nouveau : le signal part
    r_pose = reco(releaseDate="2026-10-27", links=[{"url": "https://a/1"}, {"url": "https://a/2"}])
    assert sp.sabliers([r_pose], AUJOURDHUI, etat) == []


def test_un_etat_ancien_sans_liens_de_depart_garde_l_ancien_comportement():
    r = reco(releaseDate="2026-10-27", links=[{"url": "https://a/1"}])
    etat = sp.noter_relance(sp.etat_vide(), [sp.cle_de(r)])  # aucun lien de départ noté
    assert sp.sabliers([r], AUJOURDHUI, etat) == [r]


def test_un_champ_de_proposition_de_forme_fausse_rend_l_etat_illisible(tmp_path):
    chemin = tmp_path / "etat.json"
    chemin.write_text(json.dumps({"propositions": {"x/y": {"branche": "b", "sha": "s", "adresses": [],
                                                           "externalIds": ["pas un objet"]}}}),
                      encoding="utf-8")
    with pytest.raises(sp.EtatIllisible):
        sp.lire_etat(chemin)
    chemin.write_text(json.dumps({"liens_au_depart": []}), encoding="utf-8")
    with pytest.raises(sp.EtatIllisible):
        sp.lire_etat(chemin)
