"""Tests de `tools/fusionner_doublons_cures.py`.

POURQUOI CET OUTIL EXISTE
-------------------------
`fusion_items_doublons.py` groupe par identifiant TMDB, ou par titre ET
createur identiques. Il laisse donc passer deux fiches du meme titre dont
l'une est NUE — sans createur ni identifiant. Il ne peut pas savoir s'il
s'agit de la meme oeuvre ; un humain, si.

Releve a la relecture du 2026-08-19 : Balade Mentale portait trois fiches,
Orelsan deux, LOL trois.

CE QUE CES TESTS PROTEGENT
--------------------------
Une fusion est DESTRUCTIVE : elle supprime des fichiers. Les tests portent
donc surtout sur ce qui ne doit jamais arriver — perdre une mention en la
laissant pointer une oeuvre supprimee, ecraser un champ du survivant, ou
fusionner deux oeuvres que la table croyait identiques alors que le corpus
dit le contraire.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import common
import fusionner_doublons_cures as fdc


@pytest.fixture
def corpus(tmp_path: Path, monkeypatch) -> Path:
    for nom in ("items", "mentions"):
        (tmp_path / nom).mkdir()
    monkeypatch.setattr(common, "ITEMS_DIR", tmp_path / "items")
    monkeypatch.setattr(common, "MENTIONS_DIR", tmp_path / "mentions")
    return tmp_path


def poser(racine: Path, dossier: str, nom: str, doc: dict) -> Path:
    chemin = racine / dossier / f"{nom}.json"
    chemin.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
    return chemin


GROUPE = fdc.Groupe(survivant="aaa", perdants=("bbb",), titre="Balade Mentale",
                    raison="test", types=("chaine",))


def monter(racine: Path, *, survivant=None, perdant=None) -> tuple[Path, Path]:
    a = poser(racine, "items", "aaa", survivant or {
        "id": "aaa", "title": "Balade Mentale", "types": ["chaine"],
        "creator": "Christophe Pauly"})
    b = poser(racine, "items", "bbb", perdant or {
        "id": "bbb", "title": "Balade Mentale", "types": ["video", "podcast"]})
    return a, b


# ===== La fusion ===========================================================
def test_le_perdant_est_supprime(corpus: Path):
    a, b = monter(corpus)
    rapport = fdc.executer([GROUPE], apply=True)
    assert a.exists() and not b.exists()
    assert (rapport["fusions"], rapport["supprimes"]) == (1, 1)


def test_les_mentions_du_perdant_SUIVENT(corpus: Path):
    """Sans ce report, la suppression laisserait des mentions orphelines
    pointant une oeuvre qui n'existe plus — et le build Astro echouerait."""
    monter(corpus)
    m = poser(corpus, "mentions", "m1", {
        "id": "ubm-1", "itemId": "bbb", "status": "validated"})
    rapport = fdc.executer([GROUPE], apply=True)
    assert json.loads(m.read_text(encoding="utf-8"))["itemId"] == "aaa"
    assert rapport["mentions_reportees"] == 1


def test_les_mentions_du_SURVIVANT_ne_bougent_pas(corpus: Path):
    monter(corpus)
    m = poser(corpus, "mentions", "m1", {
        "id": "ubm-1", "itemId": "aaa", "status": "validated"})
    avant = m.read_text(encoding="utf-8")
    fdc.executer([GROUPE], apply=True)
    assert m.read_text(encoding="utf-8") == avant


def test_une_mention_ECARTEE_suit_aussi(corpus: Path):
    """Elle ne s'affiche pas, mais elle reference l'item : la laisser
    pointer un fichier supprime casserait le schema."""
    monter(corpus)
    m = poser(corpus, "mentions", "m1", {
        "id": "ubm-1", "itemId": "bbb", "status": "discarded"})
    fdc.executer([GROUPE], apply=True)
    assert json.loads(m.read_text(encoding="utf-8"))["itemId"] == "aaa"


def test_les_types_de_la_table_priment(corpus: Path):
    """Les fiches divergeaient — c'est souvent pour cela qu'on les fusionne.
    La table tranche."""
    a, _ = monter(corpus)
    fdc.executer([GROUPE], apply=True)
    assert json.loads(a.read_text(encoding="utf-8"))["types"] == ["chaine"]


def test_le_survivant_recupere_ce_que_le_perdant_avait_en_PLUS(corpus: Path):
    a, _ = monter(corpus, perdant={
        "id": "bbb", "title": "Balade Mentale", "types": ["video"],
        "year": 2015})
    fdc.executer([GROUPE], apply=True)
    assert json.loads(a.read_text(encoding="utf-8"))["year"] == 2015


def test_le_createur_du_survivant_n_est_pas_ECRASE(corpus: Path):
    """« Yacine Belhousse » (verifie chez TMDB) ne doit pas ceder devant
    « Yacine Bellous » — c'est le cas qui a fait inverser un survivant."""
    a, _ = monter(corpus, perdant={
        "id": "bbb", "title": "Balade Mentale", "types": ["video"],
        "creator": "Quelqu'un d'autre"})
    fdc.executer([GROUPE], apply=True)
    assert json.loads(a.read_text(encoding="utf-8"))["creator"] == "Christophe Pauly"


def test_la_simulation_ne_supprime_RIEN(corpus: Path):
    a, b = monter(corpus)
    m = poser(corpus, "mentions", "m1", {"id": "ubm-1", "itemId": "bbb"})
    avant = (a.read_text(encoding="utf-8"), m.read_text(encoding="utf-8"))
    rapport = fdc.executer([GROUPE], apply=False)
    assert b.exists()
    assert (a.read_text(encoding="utf-8"), m.read_text(encoding="utf-8")) == avant
    assert rapport["fusions"] == 1   # le rapport annonce quand meme


def test_la_passe_est_idempotente(corpus: Path):
    monter(corpus)
    fdc.executer([GROUPE], apply=True)
    assert fdc.executer([GROUPE], apply=True)["fusions"] == 0


def test_plusieurs_perdants_sont_fusionnes_ensemble(corpus: Path):
    """Balade Mentale en avait trois."""
    monter(corpus)
    c = poser(corpus, "items", "ccc", {
        "id": "ccc", "title": "Balade Mentale", "types": ["chaine"]})
    groupe = fdc.Groupe(survivant="aaa", perdants=("bbb", "ccc"),
                        titre="Balade Mentale", raison="test")
    rapport = fdc.executer([groupe], apply=True)
    assert not c.exists()
    assert rapport["supprimes"] == 2


# ===== Les refus ===========================================================
def test_des_TITRES_DIVERGENTS_bloquent_la_fusion(corpus: Path):
    """La table decrit un corpus a un instant donne. Si un titre a change,
    elle ne le decrit plus, et fusionner deux oeuvres serait irreversible."""
    a, b = monter(corpus, perdant={
        "id": "bbb", "title": "Tout autre chose", "types": ["video"]})
    rapport = fdc.executer([GROUPE], apply=True)
    assert b.exists()
    assert rapport["fusions"] == 0
    assert any("titres divergents" in r for r in rapport["refus"])


def test_un_survivant_introuvable_est_refuse(corpus: Path):
    poser(corpus, "items", "bbb", {"id": "bbb", "title": "Balade Mentale"})
    rapport = fdc.executer([GROUPE], apply=True)
    assert any("introuvable" in r for r in rapport["refus"])


def test_un_perdant_deja_disparu_ne_fait_rien(corpus: Path):
    poser(corpus, "items", "aaa", {"id": "aaa", "title": "Balade Mentale"})
    assert fdc.executer([GROUPE], apply=True)["fusions"] == 0


def test_le_titre_est_compare_sans_la_casse(corpus: Path):
    _, b = monter(corpus, perdant={
        "id": "bbb", "title": "BALADE MENTALE", "types": ["video"]})
    assert fdc.executer([GROUPE], apply=True)["fusions"] == 1
    assert not b.exists()


def test_un_json_illisible_est_ignore(corpus: Path):
    monter(corpus)
    (corpus / "items" / "casse.json").write_text("{ pas du json", encoding="utf-8")
    (corpus / "mentions" / "casse.json").write_text("{{{", encoding="utf-8")
    assert fdc.executer([GROUPE], apply=True)["fusions"] == 1


def test_un_document_sans_id_est_ignore(corpus: Path):
    monter(corpus)
    poser(corpus, "items", "orphelin", {"title": "Sans id"})
    assert fdc.executer([GROUPE], apply=True)["fusions"] == 1


# ===== La table livree =====================================================
def test_aucun_item_n_est_a_la_fois_survivant_et_perdant():
    """Il disparaitrait apres avoir absorbe d'autres fiches."""
    survivants = {g.survivant for g in fdc.GROUPES}
    perdants = {p for g in fdc.GROUPES for p in g.perdants}
    assert not (survivants & perdants)


def test_aucun_perdant_n_apparait_dans_deux_groupes():
    perdants = [p for g in fdc.GROUPES for p in g.perdants]
    assert len(set(perdants)) == len(perdants)


def test_chaque_groupe_porte_une_raison():
    for g in fdc.GROUPES:
        assert len(g.raison) > 10, g.titre
        assert g.perdants, g.titre


def test_les_types_de_la_table_sont_dans_l_enum():
    admis = {"film", "serie", "livre", "bd", "musique", "album", "artiste",
             "podcast", "video", "chaine", "jeu", "spectacle", "lieu",
             "application", "autre"}
    for g in fdc.GROUPES:
        for t in g.types:
            assert t in admis, (g.titre, t)


# ===== CLI =================================================================
def test_main_applique(corpus: Path):
    monkey = fdc.GROUPES
    _, b = monter(corpus)
    fdc.GROUPES = (GROUPE,)
    try:
        assert fdc.main(["--apply"]) == 0
        assert not b.exists()
    finally:
        fdc.GROUPES = monkey


def test_main_dry_run(corpus: Path):
    monkey = fdc.GROUPES
    _, b = monter(corpus)
    fdc.GROUPES = (GROUPE,)
    try:
        assert fdc.main([]) == 0
        assert b.exists()
    finally:
        fdc.GROUPES = monkey


def test_main_journalise_les_refus(corpus: Path, caplog):
    monkey = fdc.GROUPES
    poser(corpus, "items", "bbb", {"id": "bbb", "title": "Balade Mentale"})
    fdc.GROUPES = (GROUPE,)
    try:
        with caplog.at_level("WARNING"):
            assert fdc.main(["--apply"]) == 0
        assert "REFUS" in caplog.text
    finally:
        fdc.GROUPES = monkey
