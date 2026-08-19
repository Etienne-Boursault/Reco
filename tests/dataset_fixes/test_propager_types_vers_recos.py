"""Tests de `tools/propager_types_vers_recos.py`.

LE DEFAUT
---------
Yseult figurait dans `/musique` et dans `/artistes`, mais sa carte sur
`/recos` ne portait que la puce « artiste » : qui filtrait `/recos` sur
« musique » ne la trouvait pas. Soixante-dix oeuvres etaient dans ce cas,
dont cinquante et une venues de `marquer_artistes_musicaux`, qui n'ecrit que
sur les fiches.

Arbitre le 2026-08-19 : « j'ai une preference pour la propagation ».

CE QUE CES TESTS PROTEGENT
--------------------------
Le SENS unique de la passe. Elle ajoute aux recos ce que la fiche porte en
plus, et rien d'autre : jamais elle ne retire un type a une reco, jamais elle
ne touche une oeuvre dont la fiche en porte MOINS — ce cas-la releve d'un
arbitrage, pas d'une propagation.

Et la consigne qui l'accompagne : « n'oublie pas d'aligner les liens ». Une
reco qui gagne le type `musique` sans gagner le lien d'ecoute qui l'a
justifie serait un progres a moitie.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import common
import propager_types_vers_recos as ptr


@pytest.fixture
def corpus(tmp_path: Path, monkeypatch) -> Path:
    for nom in ("items", "mentions", "recos"):
        (tmp_path / nom).mkdir()
    monkeypatch.setattr(common, "ITEMS_DIR", tmp_path / "items")
    monkeypatch.setattr(common, "MENTIONS_DIR", tmp_path / "mentions")
    monkeypatch.setattr(common, "RECOS_DIR", tmp_path / "recos")
    return tmp_path


def poser(racine: Path, dossier: str, nom: str, doc: dict) -> Path:
    chemin = racine / dossier / f"{nom}.json"
    chemin.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
    return chemin


def lien(url: str) -> dict:
    return {"kind": "streaming", "ethics": "neutral", "label": "L", "url": url}


def monter(racine: Path, *, types_item, recos, item_id="abc",
           statut="validated") -> tuple[Path, list[Path]]:
    item = poser(racine, "items", "i", {
        "id": item_id, "title": "Yseult", "types": list(types_item)})
    chemins = []
    for n, doc in enumerate(recos, start=1):
        poser(racine, "mentions", f"m{n}", {
            "id": f"ubm-{n}", "itemId": item_id, "status": statut})
        chemins.append(poser(racine, "recos", f"r{n}", {
            "id": f"ubm-{n}", "title": "Yseult", **doc}))
    return item, chemins


# ===== La propagation ======================================================
def test_la_reco_gagne_le_type_qui_lui_manquait(corpus: Path):
    """Le cas d'Yseult : la fiche dit « artiste, musique », la carte disait
    seulement « artiste »."""
    _, (reco,) = monter(corpus, types_item=["artiste", "musique"],
                        recos=[{"types": ["artiste"]}])
    rapport = ptr.executer(apply=True)
    assert json.loads(reco.read_text(encoding="utf-8"))["types"] == [
        "artiste", "musique"]
    assert (rapport["oeuvres"], rapport["recos_types"]) == (1, 1)


def test_toutes_les_recos_de_l_oeuvre_suivent(corpus: Path):
    _, chemins = monter(corpus, types_item=["artiste", "musique"],
                        recos=[{"types": ["artiste"]}] * 3)
    assert ptr.executer(apply=True)["recos_types"] == 3


def test_les_liens_sont_alignes_AVEC_les_types(corpus: Path):
    """« N'oublie pas d'aligner les liens » : le lien d'écoute qui a justifié
    le type `musique` doit suivre le type."""
    _, (a, b) = monter(corpus, types_item=["artiste", "musique"], recos=[
        {"types": ["artiste"], "links": [lien("https://deezer.com/artist/1")]},
        {"types": ["artiste"], "links": []},
    ])
    rapport = ptr.executer(apply=True)
    assert [x["url"] for x in json.loads(b.read_text(encoding="utf-8"))["links"]] == [
        "https://deezer.com/artist/1"]
    assert rapport["recos_liens"] == 1


def test_l_ordre_des_liens_est_celui_de_premiere_apparition(corpus: Path):
    _, (a, b) = monter(corpus, types_item=["artiste", "musique"], recos=[
        {"types": ["artiste"], "links": [lien("https://un"), lien("https://deux")]},
        {"types": ["artiste"], "links": [lien("https://trois")]},
    ])
    ptr.executer(apply=True)
    assert [x["url"] for x in json.loads(a.read_text(encoding="utf-8"))["links"]] == [
        "https://un", "https://deux", "https://trois"]


def test_le_reste_du_document_est_intact(corpus: Path):
    _, (reco,) = monter(corpus, types_item=["artiste", "musique"], recos=[
        {"types": ["artiste"], "creator": "Yseult", "status": "validated",
         "quote": "gardée"},
    ])
    ptr.executer(apply=True)
    doc = json.loads(reco.read_text(encoding="utf-8"))
    assert doc["creator"] == "Yseult"
    assert doc["quote"] == "gardée"


# ===== Ce qui n'est PAS propagé ===========================================
def test_une_fiche_MOINS_riche_que_ses_recos_n_est_pas_touchee(corpus: Path):
    """Ce cas relève d'un arbitrage — retirer un type à une reco n'est pas
    une propagation."""
    _, (reco,) = monter(corpus, types_item=["artiste"],
                        recos=[{"types": ["artiste", "chaine"]}])
    rapport = ptr.executer(apply=True)
    assert json.loads(reco.read_text(encoding="utf-8"))["types"] == [
        "artiste", "chaine"]
    assert rapport["oeuvres"] == 0


def test_des_types_qui_se_CROISENT_ne_sont_pas_touches(corpus: Path):
    """`{film}` d'un côté, `{video}` de l'autre : ni l'un ne contient
    l'autre, c'est un désaccord."""
    _, (reco,) = monter(corpus, types_item=["film"], recos=[{"types": ["video"]}])
    assert ptr.executer(apply=True)["oeuvres"] == 0
    assert json.loads(reco.read_text(encoding="utf-8"))["types"] == ["video"]


def test_des_types_DEJA_identiques_ne_declenchent_rien(corpus: Path):
    _, (reco,) = monter(corpus, types_item=["artiste"], recos=[{"types": ["artiste"]}])
    avant = reco.read_text(encoding="utf-8")
    assert ptr.executer(apply=True)["oeuvres"] == 0
    assert reco.read_text(encoding="utf-8") == avant


def test_une_fiche_SANS_type_ne_propage_rien(corpus: Path):
    _, (reco,) = monter(corpus, types_item=[], recos=[{"types": ["artiste"]}])
    assert ptr.executer(apply=True)["oeuvres"] == 0


def test_des_recos_SANS_type_ne_sont_pas_touchees(corpus: Path):
    """Une reco sans type n'a pas ete curee : lui en poser ne corrige rien
    et masquerait le manque."""
    _, (reco,) = monter(corpus, types_item=["artiste", "musique"], recos=[{}])
    assert ptr.executer(apply=True)["oeuvres"] == 0


def test_les_mentions_ECARTEES_sont_hors_jeu(corpus: Path):
    _, (reco,) = monter(corpus, types_item=["artiste", "musique"],
                        recos=[{"types": ["artiste"]}], statut="discarded")
    assert ptr.executer(apply=True)["oeuvres"] == 0
    assert json.loads(reco.read_text(encoding="utf-8"))["types"] == ["artiste"]


def test_une_oeuvre_hors_corpus_ne_fait_pas_echouer(corpus: Path):
    monter(corpus, types_item=["artiste", "musique"], recos=[{"types": ["artiste"]}])
    poser(corpus, "mentions", "m9", {
        "id": "ubm-9", "itemId": "inconnu", "status": "validated"})
    assert ptr.executer(apply=True)["oeuvres"] == 1


def test_une_mention_sans_reco_ne_fait_pas_echouer(corpus: Path):
    monter(corpus, types_item=["artiste", "musique"], recos=[{"types": ["artiste"]}])
    poser(corpus, "mentions", "m9", {
        "id": "ubm-99", "itemId": "abc", "status": "validated"})
    assert ptr.executer(apply=True)["oeuvres"] == 1


def test_une_reco_deja_a_jour_parmi_d_autres_n_est_pas_reecrite(corpus: Path):
    """Deux recos, l'une deja alignee : seule l'autre bouge, et la passe
    poursuit au lieu de s'arreter la."""
    _, (a, b) = monter(corpus, types_item=["artiste", "musique"], recos=[
        {"types": ["artiste", "musique"]},
        {"types": ["artiste"]},
    ])
    avant = a.read_text(encoding="utf-8")
    rapport = ptr.executer(apply=True)
    assert a.read_text(encoding="utf-8") == avant
    assert json.loads(b.read_text(encoding="utf-8"))["types"] == ["artiste", "musique"]
    assert rapport["recos_types"] == 1


def test_deux_oeuvres_sont_traitees_l_une_apres_l_autre(corpus: Path):
    """Une oeuvre ecartee ne doit pas interrompre le parcours des suivantes."""
    monter(corpus, types_item=["artiste", "musique"], recos=[{"types": ["artiste"]}])
    poser(corpus, "items", "j", {
        "id": "xyz", "title": "Autre", "types": ["serie", "video"]})
    poser(corpus, "mentions", "m9", {
        "id": "ubm-9", "itemId": "xyz", "status": "validated"})
    autre = poser(corpus, "recos", "r9", {
        "id": "ubm-9", "title": "Autre", "types": ["serie"]})
    rapport = ptr.executer(apply=True)
    assert json.loads(autre.read_text(encoding="utf-8"))["types"] == ["serie", "video"]
    assert rapport["oeuvres"] == 2


def test_une_oeuvre_ecartee_n_INTERROMPT_pas_les_suivantes(corpus: Path):
    """La premiere oeuvre du parcours n'a rien a gagner ; la seconde, si."""
    poser(corpus, "items", "i0", {
        "id": "aaa", "title": "Deja bonne", "types": ["serie"]})
    poser(corpus, "mentions", "m0", {
        "id": "ubm-0", "itemId": "aaa", "status": "validated"})
    poser(corpus, "recos", "r0", {
        "id": "ubm-0", "title": "Deja bonne", "types": ["serie"]})
    _, (reco,) = monter(corpus, types_item=["artiste", "musique"],
                        recos=[{"types": ["artiste"]}], item_id="zzz")
    rapport = ptr.executer(apply=True)
    assert json.loads(reco.read_text(encoding="utf-8"))["types"] == [
        "artiste", "musique"]
    assert rapport["oeuvres"] == 1


# ===== La passe ============================================================
def test_la_simulation_n_ecrit_rien(corpus: Path):
    _, (reco,) = monter(corpus, types_item=["artiste", "musique"],
                        recos=[{"types": ["artiste"]}])
    avant = reco.read_text(encoding="utf-8")
    assert ptr.executer(apply=False)["oeuvres"] == 1     # annonce
    assert reco.read_text(encoding="utf-8") == avant     # n'ecrit pas


def test_la_passe_est_idempotente(corpus: Path):
    monter(corpus, types_item=["artiste", "musique"], recos=[{"types": ["artiste"]}])
    ptr.executer(apply=True)
    assert ptr.executer(apply=True)["oeuvres"] == 0


def test_un_json_illisible_est_ignore(corpus: Path):
    monter(corpus, types_item=["artiste", "musique"], recos=[{"types": ["artiste"]}])
    for dossier in ("items", "mentions", "recos"):
        (corpus / dossier / "casse.json").write_text("{ nope", encoding="utf-8")
    assert ptr.executer(apply=True)["oeuvres"] == 1


def test_un_document_sans_id_est_ignore(corpus: Path):
    monter(corpus, types_item=["artiste", "musique"], recos=[{"types": ["artiste"]}])
    poser(corpus, "items", "orphelin", {"title": "Sans id", "types": ["autre"]})
    assert ptr.executer(apply=True)["oeuvres"] == 1


# ===== CLI =================================================================
def test_main_applique(corpus: Path):
    _, (reco,) = monter(corpus, types_item=["artiste", "musique"],
                        recos=[{"types": ["artiste"]}])
    assert ptr.main(["--apply"]) == 0
    assert json.loads(reco.read_text(encoding="utf-8"))["types"] == [
        "artiste", "musique"]


def test_main_dry_run(corpus: Path):
    _, (reco,) = monter(corpus, types_item=["artiste", "musique"],
                        recos=[{"types": ["artiste"]}])
    avant = reco.read_text(encoding="utf-8")
    assert ptr.main([]) == 0
    assert reco.read_text(encoding="utf-8") == avant
