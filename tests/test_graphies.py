"""Registre des graphies corrigées (`tools/graphies.py`, décision R6 A du 2026-11-27).

Cas réels qui l'ont motivé : sur S6-E10, « Hilleret » pour Hillairet, et sur
S5-E37 « Gat Buzzy » pour Get Busy, corrigés à la main en relecture puis perdus
pour les épisodes suivants.
"""
from __future__ import annotations

import json

import pytest

import common
import graphies

SOURCE = "demo"
# Pris avant que `conftest` ne le détourne vers un dossier temporaire.
_DOSSIER_REEL = graphies._dossier
GUID = "yt-abc"


@pytest.fixture
def sortie(tmp_path, monkeypatch):
    """Dossier de sortie temporaire : jamais le vrai registre de venus."""
    monkeypatch.setattr(common, "OUTPUT_DIR", tmp_path)
    return tmp_path / "graphies"


def _reco(**champs):
    base = {"id": "ubm-0001", "episodeGuid": GUID, "status": "validated",
            "title": "Le Titre", "types": ["film"]}
    base.update(champs)
    return base


# ----- corrections : ce que la relecture a changé --------------------------

def test_un_nom_propre_corrige_est_retenu():
    avant = _reco(creator="Pierre Hilleret")
    apres = _reco(creator="Pierre Hillairet")
    assert graphies.corrections(avant, apres) == [
        {"fausse": "Hilleret", "juste": "Hillairet", "champ": "creator"}]


def test_plusieurs_mots_remplaces_ensemble():
    avant = _reco(title="Gat Buzzy")
    apres = _reco(title="Get Busy")
    assert graphies.corrections(avant, apres) == [
        {"fausse": "Gat Buzzy", "juste": "Get Busy", "champ": "title"}]


def test_une_reformulation_n_est_pas_une_graphie():
    avant = _reco(quote="C'est un super film.")
    apres = _reco(quote="C'est un très bon film.")
    assert graphies.corrections(avant, apres) == []


def test_une_autre_oeuvre_n_est_pas_une_graphie():
    avant = _reco(title="Dark Matter")
    apres = _reco(title="Interstellar")
    assert graphies.corrections(avant, apres) == []


def test_une_citation_raccourcie_ne_donne_rien():
    avant = _reco(quote="Alors franchement, Waly Dia, c'est génial, allez-y.")
    apres = _reco(quote="Waly Dia, c'est génial.")
    assert graphies.corrections(avant, apres) == []


def test_dans_une_citation_seuls_les_noms_propres_comptent():
    avant = _reco(quote="J'adore Wally Dia, il est drole.")
    apres = _reco(quote="J'adore Waly Dia, il est drôle.")
    assert graphies.corrections(avant, apres) == [
        {"fausse": "Wally", "juste": "Waly", "champ": "quote"}]


def test_une_simple_casse_n_est_pas_retenue():
    assert graphies.corrections(_reco(creator="orelsan"), _reco(creator="Orelsan")) == []


# ----- brouillon gardé à l'extraction --------------------------------------

def test_le_brouillon_d_origine_n_est_jamais_ecrase(sortie):
    graphies.garder_brouillon(SOURCE, _reco(creator="Pierre Hilleret"))
    graphies.garder_brouillon(SOURCE, _reco(creator="Pierre Hillairet"))
    garde = json.loads((sortie / "brouillons" / SOURCE / "ubm-0001.json")
                       .read_text(encoding="utf-8"))
    assert garde["creator"] == "Pierre Hilleret"
    assert "links" not in garde


# ----- enregistrer : à la finalisation --------------------------------------

def test_la_finalisation_remplit_le_registre(sortie):
    graphies.garder_brouillon(SOURCE, _reco(creator="Pierre Hilleret"))
    n = graphies.enregistrer(SOURCE, GUID, [_reco(creator="Pierre Hillairet")])
    assert n == 1
    assert graphies.charger() == [{
        "fausse": "Hilleret", "juste": "Hillairet", "champs": ["creator"],
        "episodes": [GUID], "vu": 1}]


def test_une_meme_correction_vue_deux_fois_se_cumule(sortie):
    graphies.garder_brouillon(SOURCE, _reco(creator="Pierre Hilleret"))
    graphies.enregistrer(SOURCE, GUID, [_reco(creator="Pierre Hillairet")])
    graphies.garder_brouillon(SOURCE, _reco(id="ubm-0002", episodeGuid="yt-def",
                                            quote="Hilleret est génial."))
    graphies.enregistrer(SOURCE, "yt-def", [_reco(id="ubm-0002", episodeGuid="yt-def",
                                                  quote="Hillairet est génial.")])
    [entree] = graphies.charger()
    assert entree["vu"] == 2
    assert entree["episodes"] == [GUID, "yt-def"]
    assert entree["champs"] == ["creator", "quote"]


def test_un_episode_finalise_deux_fois_ne_compte_qu_une_fois(sortie):
    graphies.garder_brouillon(SOURCE, _reco(creator="Pierre Hilleret"))
    graphies.enregistrer(SOURCE, GUID, [_reco(creator="Pierre Hillairet")])
    assert graphies.enregistrer(SOURCE, GUID, [_reco(creator="Pierre Hillairet")]) == 0
    assert graphies.charger()[0]["vu"] == 1


def test_une_reco_ecartee_ou_sans_brouillon_est_ignoree(sortie):
    graphies.garder_brouillon(SOURCE, _reco(creator="Pierre Hilleret"))
    ecartee = _reco(creator="Pierre Hillairet", status="discarded")
    sans_brouillon = _reco(id="ubm-0009", creator="Jean Valjean")
    assert graphies.enregistrer(SOURCE, GUID, [ecartee, sans_brouillon]) == 0
    assert graphies.charger() == []


def test_registre_absent_ou_illisible_vaut_vide(sortie):
    assert graphies.charger() == []
    sortie.mkdir(parents=True)
    (sortie / "registre.json").write_text("{pas du json", encoding="utf-8")
    assert graphies.charger() == []


# ----- propositions : à la relecture des épisodes suivants ------------------

REGISTRE = [{"fausse": "Hilleret", "juste": "Hillairet", "champs": ["creator"],
             "episodes": [GUID], "vu": 2}]


def test_une_graphie_deja_corrigee_est_proposee():
    reco = _reco(status="draft", quote="Le film de Hilleret, allez le voir.")
    assert graphies.propositions(reco, REGISTRE) == [("Hilleret", "Hillairet", 2)]


def test_pas_de_proposition_au_milieu_d_un_mot():
    reco = _reco(status="draft", quote="Les Hillerets sont là.")
    assert graphies.propositions(reco, REGISTRE) == []


def test_pas_de_proposition_quand_la_bonne_graphie_est_la():
    reco = _reco(status="draft", creator="Hillairet", quote="Hillairet, pas Hilleret.")
    assert graphies.propositions(reco, REGISTRE) == []


def test_la_casse_n_empeche_pas_la_proposition():
    reco = _reco(status="draft", title="hilleret")
    assert graphies.propositions(reco, REGISTRE) == [("Hilleret", "Hillairet", 2)]


# ----- erreurs : le registre ne bloque jamais la chaîne ----------------------

def test_un_brouillon_impossible_a_ecrire_ne_bloque_pas(sortie, monkeypatch, caplog):
    def refuse(*_a, **_k):
        raise OSError("disque plein")
    monkeypatch.setattr(graphies, "write_json_if_changed", refuse)
    graphies.garder_brouillon(SOURCE, _reco())
    assert "ubm-0001" in caplog.text


def test_une_reco_sans_identifiant_n_a_pas_de_brouillon(sortie):
    graphies.garder_brouillon(SOURCE, {"title": "Sans id"})
    assert not (sortie / "brouillons").exists()


def test_noter_un_episode_journalise_une_panne_sans_la_remonter(monkeypatch, caplog):
    def panne(*_a, **_k):
        raise ValueError("registre cassé")
    monkeypatch.setattr(graphies, "enregistrer", panne)
    assert graphies.noter_episode(SOURCE, GUID, []) == 0
    assert GUID in caplog.text


def test_noter_un_episode_rend_les_nouveautes(sortie):
    graphies.garder_brouillon(SOURCE, _reco(creator="Pierre Hilleret"))
    assert graphies.noter_episode(SOURCE, GUID, [_reco(creator="Pierre Hillairet")]) == 1


def test_une_entree_incomplete_du_registre_est_ignoree():
    assert graphies.propositions(_reco(title="Hilleret"), [{"fausse": "Hilleret"}]) == []


# ----- branchements ------------------------------------------------------------

def test_l_extraction_garde_le_brouillon_d_une_reco_neuve(tmp_path, monkeypatch):
    import extract_recos
    recos = tmp_path / "recos"
    (recos / "un-bon-moment").mkdir(parents=True)
    monkeypatch.setattr(common, "RECOS_DIR", recos)
    extract_recos._persist_recos("un-bon-moment", "EP001",
                                 [{"title": "Get Buzzy", "type": "album", "creator": "Hilleret"}])
    [garde] = (tmp_path / "graphies" / "brouillons" / "un-bon-moment").glob("*.json")
    assert json.loads(garde.read_text(encoding="utf-8"))["creator"] == "Hilleret"


def test_la_publication_d_un_episode_remplit_le_registre(tmp_path, monkeypatch):
    import publier_episode
    content = tmp_path / "content"
    monkeypatch.setattr(common, "CONTENT_DIR", content)
    monkeypatch.setattr(common, "RECOS_DIR", content / "recos")
    for sub in ("recos", "items", "mentions"):
        (content / sub / SOURCE).mkdir(parents=True)
    reco = _reco(sourceId=SOURCE, creator="Pierre Hillairet")
    (content / "recos" / SOURCE / "0001.json").write_text(json.dumps(reco), encoding="utf-8")
    graphies.garder_brouillon(SOURCE, _reco(creator="Pierre Hilleret"))
    plan = publier_episode.preparer(SOURCE, GUID, apply=True)
    assert not plan.errors
    assert graphies.charger()[0]["juste"] == "Hillairet"


def test_la_simulation_de_publication_n_ecrit_pas_le_registre(tmp_path, monkeypatch):
    import publier_episode
    content = tmp_path / "content"
    monkeypatch.setattr(common, "CONTENT_DIR", content)
    monkeypatch.setattr(common, "RECOS_DIR", content / "recos")
    for sub in ("recos", "items", "mentions"):
        (content / sub / SOURCE).mkdir(parents=True)
    reco = _reco(sourceId=SOURCE, creator="Pierre Hillairet")
    (content / "recos" / SOURCE / "0001.json").write_text(json.dumps(reco), encoding="utf-8")
    graphies.garder_brouillon(SOURCE, _reco(creator="Pierre Hilleret"))
    publier_episode.preparer(SOURCE, GUID, apply=False)
    assert graphies.charger() == []


def test_la_relecture_affiche_la_graphie_deja_corrigee():
    import review_signals
    reco = _reco(status="draft", creator="Hilleret")
    signaux = review_signals.reco_signals(reco, {"title": "Épisode"}, [], [], registre=REGISTRE)
    [graphie] = [s for s in signaux if s.kind == "graphie"]
    assert graphie.message == "Graphie déjà corrigée : « Hilleret » → « Hillairet » (vue 2 fois)."
    assert review_signals.reco_signals(reco, {"title": "Épisode"}, [], []) == [
        s for s in signaux if s.kind != "graphie"]


def test_le_vrai_registre_vit_hors_de_git_dans_tools_output():
    assert _DOSSIER_REEL() == common.OUTPUT_DIR / "graphies"


def test_noter_un_episode_sans_correction_ne_dit_rien(sortie):
    assert graphies.noter_episode(SOURCE, GUID, [_reco()]) == 0
    assert graphies.charger() == []
