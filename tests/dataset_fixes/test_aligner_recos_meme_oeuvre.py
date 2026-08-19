"""Tests de `tools/aligner_recos_meme_oeuvre.py`.

CE QUE LA RELECTURE A VU
------------------------
Sur la fiche d'une oeuvre, ses recommandations s'affichent cote a cote. Elles
devraient se ressembler ; elles ne se ressemblaient pas. « Balade Mentale » :
trois cartes, l'une avec un createur, deux sans, et des jeux de liens de un a
trois. « Fouloscopie » : un, trois et trois liens. Releve le 2026-08-19 —
« certaines avec des liens incomplets ».

CE QUE CES TESTS PROTEGENT
--------------------------
Deux proprietes qui s'opposent, et dont l'equilibre fait tout l'interet de
l'outil.

D'un cote, il doit COMPLETER : une recommandation pauvre recupere les liens
de ses voisines. De l'autre, il ne doit RIEN INVENTER : deux createurs qui ne
s'emboitent pas restent un desaccord qu'un script n'a pas a trancher, et
propager un nom faux a toutes les cartes serait pire que de le laisser sur
une seule.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import aligner_recos_meme_oeuvre as arm
import common


@pytest.fixture
def corpus(tmp_path: Path, monkeypatch) -> Path:
    for nom in ("mentions", "recos"):
        (tmp_path / nom).mkdir()
    monkeypatch.setattr(common, "MENTIONS_DIR", tmp_path / "mentions")
    monkeypatch.setattr(common, "RECOS_DIR", tmp_path / "recos")
    return tmp_path


def poser(racine: Path, dossier: str, nom: str, doc: dict) -> Path:
    chemin = racine / dossier / f"{nom}.json"
    chemin.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
    return chemin


def lien(url: str, label: str = "L") -> dict:
    return {"kind": "info", "ethics": "neutral", "label": label, "url": url}


def oeuvre(racine: Path, recos: list[dict], *, item="abc",
           statut="validated") -> list[Path]:
    """Pose N recommandations rattachees a la meme oeuvre."""
    chemins = []
    for n, doc in enumerate(recos, start=1):
        poser(racine, "mentions", f"m{n}", {
            "id": f"ubm-{n}", "itemId": item, "status": statut})
        chemins.append(poser(racine, "recos", f"r{n}", {
            "id": f"ubm-{n}", "title": "Balade Mentale", **doc}))
    return chemins


# ===== Le createur le plus complet =========================================
@pytest.mark.parametrize("valeurs, attendu", [
    (["Vince Gilligan", "Vince Gilligan, Peter Gould"],
     "Vince Gilligan, Peter Gould"),          # liste tronquee, pas desaccord
    ([None, "Alexandre Astier"], "Alexandre Astier"),
    (["", "Adam McKay", None], "Adam McKay"),
    (["Greg Daniels", "Greg Daniels, Ricky Gervais", ""],
     "Greg Daniels, Ricky Gervais"),
    (["Jamel Debbouze", "Claire Dabrowski, Jamel Debbouze"],
     "Claire Dabrowski, Jamel Debbouze"),
])
def test_la_liste_la_plus_complete_gagne(valeurs, attendu):
    assert arm.createur_le_plus_complet(valeurs) == attendu


@pytest.mark.parametrize("valeurs", [
    ["Théo Drieu", "Christophe Pauly"],       # deux personnes differentes
    ["Kyan Khojandi", "Navo"],
    ["A, B", "C, D"],
])
def test_deux_noms_qui_ne_s_emboitent_pas_restent_un_DESACCORD(valeurs):
    """Un script n'a pas a trancher entre deux personnes."""
    assert arm.createur_le_plus_complet(valeurs) is None


@pytest.mark.parametrize("valeur, attendu", [
    ("Vince Gilligan", {"vince gilligan"}),
    ("A, B", {"a", "b"}),
    (" Kyan Khojandi , Navo ", {"kyan khojandi", "navo"}),
    ("A,,B", {"a", "b"}),          # separateur vide ignore
    (None, set()),
    ("", set()),
])
def test_noms_decoupe_et_normalise(valeur, attendu):
    assert arm.noms(valeur) == attendu


def test_aucun_createur_renseigne_ne_donne_rien_a_propager():
    assert arm.createur_le_plus_complet([None, "", "  "]) is None


def test_la_comparaison_ignore_la_casse_et_les_espaces():
    assert arm.createur_le_plus_complet(
        ["vince gilligan", "Vince Gilligan ,  Peter Gould"]
    ) == "Vince Gilligan ,  Peter Gould"


# ===== L'union des liens ===================================================
def test_l_union_garde_l_ORDRE_de_premiere_apparition():
    """Cet ordre a ete pose a la main : le premier lien est le plus utile."""
    resultat = arm.union_des_liens([
        [lien("https://a"), lien("https://b")],
        [lien("https://c"), lien("https://a")],
    ])
    assert [l["url"] for l in resultat] == ["https://a", "https://b", "https://c"]


def test_l_union_ne_repete_jamais_une_URL():
    resultat = arm.union_des_liens([[lien("https://a")], [lien("https://a")]])
    assert len(resultat) == 1


def test_un_lien_sans_url_est_ignore():
    resultat = arm.union_des_liens([[{"label": "cassé"}, lien("https://a")]])
    assert [l["url"] for l in resultat] == ["https://a"]


def test_l_union_copie_les_liens(corpus: Path):
    """Sans copie, deux recommandations partageraient le meme objet et une
    modification ulterieure les toucherait toutes les deux."""
    source = lien("https://a")
    resultat = arm.union_des_liens([[source]])
    resultat[0]["label"] = "modifié"
    assert source["label"] == "L"


# ===== La passe ============================================================
def test_une_reco_pauvre_recupere_les_liens_de_ses_voisines(corpus: Path):
    a, b = oeuvre(corpus, [
        {"links": [lien("https://un"), lien("https://deux")]},
        {"links": [lien("https://un")]},
    ])
    rapport = arm.executer(apply=True)
    assert [l["url"] for l in json.loads(b.read_text(encoding="utf-8"))["links"]] == [
        "https://un", "https://deux"]
    assert rapport["recos_liens"] == 1        # seule la pauvre a bouge


def test_aucun_lien_n_est_RETIRE(corpus: Path):
    """L'union n'enleve rien : chaque recommandation garde les siens."""
    a, b = oeuvre(corpus, [
        {"links": [lien("https://un")]},
        {"links": [lien("https://deux")]},
    ])
    arm.executer(apply=True)
    for chemin in (a, b):
        urls = [l["url"] for l in json.loads(chemin.read_text(encoding="utf-8"))["links"]]
        assert set(urls) == {"https://un", "https://deux"}


def test_le_createur_manquant_est_propage(corpus: Path):
    a, b = oeuvre(corpus, [
        {"creator": "Théo Drieu, Kévin Fauvre"}, {},
    ])
    rapport = arm.executer(apply=True)
    assert json.loads(b.read_text(encoding="utf-8"))["creator"] == "Théo Drieu, Kévin Fauvre"
    assert rapport["recos_createur"] == 1


def test_un_DESACCORD_de_createur_ne_touche_a_rien(corpus: Path):
    a, b = oeuvre(corpus, [
        {"creator": "Théo Drieu"}, {"creator": "Christophe Pauly"},
    ])
    rapport = arm.executer(apply=True)
    assert json.loads(a.read_text(encoding="utf-8"))["creator"] == "Théo Drieu"
    assert json.loads(b.read_text(encoding="utf-8"))["creator"] == "Christophe Pauly"
    assert rapport["recos_createur"] == 0
    assert len(rapport["desaccords"]) == 1


def test_un_desaccord_n_empeche_PAS_l_alignement_des_liens(corpus: Path):
    """Les deux sujets sont independants : bloquer l'un sur l'autre laisserait
    des cartes incompletes sans raison."""
    a, b = oeuvre(corpus, [
        {"creator": "A", "links": [lien("https://un")]},
        {"creator": "B", "links": []},
    ])
    arm.executer(apply=True)
    assert json.loads(b.read_text(encoding="utf-8"))["links"][0]["url"] == "https://un"


def test_une_oeuvre_a_UNE_SEULE_reco_n_est_pas_touchee(corpus: Path):
    (a,) = oeuvre(corpus, [{"links": [lien("https://un")]}])
    avant = a.read_text(encoding="utf-8")
    assert arm.executer(apply=True)["oeuvres"] == 0
    assert a.read_text(encoding="utf-8") == avant


def test_les_recos_ECARTEES_sont_hors_jeu(corpus: Path):
    a, b = oeuvre(corpus, [
        {"links": [lien("https://un"), lien("https://deux")]},
        {"links": [lien("https://un")]},
    ], statut="discarded")
    avant = b.read_text(encoding="utf-8")
    assert arm.executer(apply=True)["oeuvres"] == 0
    assert b.read_text(encoding="utf-8") == avant


def test_deux_oeuvres_distinctes_ne_se_melangent_pas(corpus: Path):
    oeuvre(corpus, [{"links": [lien("https://un")]}], item="abc")
    poser(corpus, "mentions", "m9", {
        "id": "ubm-9", "itemId": "xyz", "status": "validated"})
    autre = poser(corpus, "recos", "r9", {
        "id": "ubm-9", "title": "Rien a voir", "links": []})
    arm.executer(apply=True)
    assert json.loads(autre.read_text(encoding="utf-8"))["links"] == []


def test_la_simulation_n_ecrit_rien(corpus: Path):
    a, b = oeuvre(corpus, [
        {"links": [lien("https://un"), lien("https://deux")]},
        {"links": [lien("https://un")]},
    ])
    avant = b.read_text(encoding="utf-8")
    rapport = arm.executer(apply=False)
    assert rapport["oeuvres"] == 1               # le rapport annonce
    assert b.read_text(encoding="utf-8") == avant  # rien n'est ecrit


def test_la_passe_est_idempotente(corpus: Path):
    oeuvre(corpus, [
        {"creator": "A, B", "links": [lien("https://un")]},
        {"links": [lien("https://deux")]},
    ])
    arm.executer(apply=True)
    assert arm.executer(apply=True)["oeuvres"] == 0


def test_le_reste_du_document_est_intact(corpus: Path):
    a, b = oeuvre(corpus, [
        {"links": [lien("https://un")], "note": "gardee", "status": "validated"},
        {"links": []},
    ])
    arm.executer(apply=True)
    doc = json.loads(a.read_text(encoding="utf-8"))
    assert doc["note"] == "gardee"
    assert doc["status"] == "validated"


def test_un_json_illisible_est_ignore(corpus: Path):
    oeuvre(corpus, [{"links": [lien("https://un")]}, {"links": []}])
    (corpus / "recos" / "casse.json").write_text("{ pas du json", encoding="utf-8")
    (corpus / "mentions" / "casse.json").write_text("{{{", encoding="utf-8")
    assert arm.executer(apply=True)["oeuvres"] == 1


def test_un_document_sans_id_est_ignore(corpus: Path):
    oeuvre(corpus, [{"links": [lien("https://un")]}, {"links": []}])
    poser(corpus, "recos", "orphelin", {"title": "Sans id", "links": []})
    assert arm.executer(apply=True)["oeuvres"] == 1


def test_une_mention_SANS_reco_ne_fait_pas_echouer(corpus: Path):
    oeuvre(corpus, [{"links": [lien("https://un")]}, {"links": []}])
    poser(corpus, "mentions", "m7", {
        "id": "ubm-77", "itemId": "abc", "status": "validated"})  # aucune reco
    assert arm.executer(apply=True)["oeuvres"] == 1


# ===== CLI =================================================================
def test_main_applique(corpus: Path):
    a, b = oeuvre(corpus, [{"links": [lien("https://un")]}, {"links": []}])
    assert arm.main(["--apply"]) == 0
    assert json.loads(b.read_text(encoding="utf-8"))["links"][0]["url"] == "https://un"


def test_main_dry_run(corpus: Path):
    a, b = oeuvre(corpus, [{"links": [lien("https://un")]}, {"links": []}])
    avant = b.read_text(encoding="utf-8")
    assert arm.main([]) == 0
    assert b.read_text(encoding="utf-8") == avant


def test_main_journalise_les_desaccords(corpus: Path, caplog):
    oeuvre(corpus, [{"creator": "A"}, {"creator": "B"}])
    with caplog.at_level("WARNING"):
        assert arm.main(["--apply"]) == 0
    assert "DESACCORD" in caplog.text
