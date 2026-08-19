"""Tests de `tools/appliquer_types_items.py`.

CE QUE LA RELECTURE A VU
------------------------
La galerie `/un-bon-moment/autres` affichait 67 oeuvres, dont beaucoup
n'avaient rien de mysterieux. Demande du 2026-08-19 : « il y en a beaucoup qui
ont l'air d'etre un autre type, je te laisse corriger et remettre les
categories dans leurs bonnes categories (certaines de ces recos doivent rester
"Autres") ».

CE QUE CES TESTS PROTEGENT
--------------------------
Le script applique des verdicts rendus par des agents. Il n'a donc AUCUNE
raison de leur faire confiance : chaque garde-fou ci-dessous correspond a une
facon dont un verdict peut etre faux ou perime.

Le cas le plus subtil est celui de la reco deja typee. Items et recos ont
diverge — 43 des 67 items « autre » avaient deja une reco correcte. Aligner
aveuglement ecraserait ce travail : on ne touche une reco que si elle est
elle-meme restee au fourre-tout.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import appliquer_types_items as ati
import common


@pytest.fixture
def corpus(tmp_path: Path, monkeypatch) -> Path:
    """Un corpus minuscule : un item, sa mention, sa reco."""
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


def corpus_type(racine: Path, *, types_item=("autre",), types_reco=("autre",),
                statut_mention="validated") -> tuple[Path, Path]:
    item = poser(racine, "items", "abc", {
        "id": "abc", "title": "Pluribus", "types": list(types_item)})
    poser(racine, "mentions", "ubm-1", {
        "id": "ubm-1", "itemId": "abc", "status": statut_mention})
    reco = poser(racine, "recos", "1", {
        "id": "ubm-1", "title": "Pluribus", "types": list(types_reco)})
    return item, reco


VERDICT = {"itemId": "abc", "titre": "Pluribus", "typesProposes": ["serie"],
           "confiance": "certain", "pourquoi": "Serie de Vince Gilligan.",
           "preuve": "https://www.themoviedb.org/tv/1"}


# ===== Le cas nominal ======================================================
def test_l_item_ET_sa_reco_sont_retypes(corpus: Path):
    item, reco = corpus_type(corpus)
    rapport = ati.executer([VERDICT], apply=True)
    assert json.loads(item.read_text(encoding="utf-8"))["types"] == ["serie"]
    assert json.loads(reco.read_text(encoding="utf-8"))["types"] == ["serie"]
    assert rapport["items_modifies"] == 1
    assert rapport["recos_modifiees"] == 1


def test_la_simulation_n_ecrit_rien(corpus: Path):
    item, reco = corpus_type(corpus)
    avant = (item.read_text(encoding="utf-8"), reco.read_text(encoding="utf-8"))
    rapport = ati.executer([VERDICT], apply=False)
    assert rapport["items_modifies"] == 1          # le rapport annonce
    assert (item.read_text(encoding="utf-8"),
            reco.read_text(encoding="utf-8")) == avant   # rien n'est ecrit


def test_plusieurs_types_sont_admis(corpus: Path):
    item, _ = corpus_type(corpus)
    ati.executer([{**VERDICT, "typesProposes": ["artiste", "musique"]}],
                 apply=True)
    assert json.loads(item.read_text(encoding="utf-8"))["types"] == [
        "artiste", "musique"]


def test_le_reste_du_document_est_intact(corpus: Path):
    item = poser(corpus, "items", "abc", {
        "id": "abc", "title": "Pluribus", "types": ["autre"],
        "creator": "Vince Gilligan", "externalIds": {"tmdb": 1}})
    ati.executer([VERDICT], apply=True)
    doc = json.loads(item.read_text(encoding="utf-8"))
    assert doc["creator"] == "Vince Gilligan"
    assert doc["externalIds"] == {"tmdb": 1}


# ===== Ce qui est laisse tranquille ========================================
def test_une_reco_DEJA_typee_n_est_pas_reecrite(corpus: Path):
    """43 des 67 items « autre » avaient deja une reco correcte : c'est du
    travail cure, pas une valeur par defaut."""
    item, reco = corpus_type(corpus, types_reco=("serie", "video"))
    rapport = ati.executer([VERDICT], apply=True)
    assert json.loads(reco.read_text(encoding="utf-8"))["types"] == [
        "serie", "video"]
    assert rapport["recos_modifiees"] == 0
    assert json.loads(item.read_text(encoding="utf-8"))["types"] == ["serie"]


def test_un_verdict_qui_MAINTIENT_autre_ne_touche_rien(corpus: Path):
    """« certaines de ces recos doivent rester Autres »."""
    item, reco = corpus_type(corpus)
    avant = item.read_text(encoding="utf-8")
    rapport = ati.executer([{**VERDICT, "typesProposes": ["autre"]}], apply=True)
    assert item.read_text(encoding="utf-8") == avant
    assert rapport["maintenus_autre"] == 1
    assert rapport["items_modifies"] == 0


def test_une_reco_d_un_AUTRE_item_n_est_pas_touchee(corpus: Path):
    _, reco = corpus_type(corpus)
    poser(corpus, "mentions", "ubm-9", {
        "id": "ubm-9", "itemId": "xyz", "status": "validated"})
    autre_reco = poser(corpus, "recos", "9", {
        "id": "ubm-9", "title": "Rien a voir", "types": ["autre"]})
    ati.executer([VERDICT], apply=True)
    assert json.loads(autre_reco.read_text(encoding="utf-8"))["types"] == ["autre"]


def test_une_mention_ECARTEE_ne_propage_pas(corpus: Path):
    """Elle ne s'affiche nulle part ; sa reco n'a pas a suivre."""
    _, reco = corpus_type(corpus, statut_mention="discarded")
    rapport = ati.executer([VERDICT], apply=True)
    assert json.loads(reco.read_text(encoding="utf-8"))["types"] == ["autre"]
    assert rapport["recos_modifiees"] == 0


# ===== Les refus ===========================================================
def test_un_item_qui_n_est_PLUS_en_autre_est_refuse(corpus: Path):
    """Le corpus a bouge depuis l'analyse : appliquer un verdict perime
    ecraserait un travail plus recent."""
    item, _ = corpus_type(corpus, types_item=("film",))
    rapport = ati.executer([VERDICT], apply=True)
    assert json.loads(item.read_text(encoding="utf-8"))["types"] == ["film"]
    assert rapport["items_modifies"] == 0
    assert any("n'est plus en" in r for r in rapport["refus"])


def test_un_item_introuvable_est_refuse(corpus: Path):
    rapport = ati.executer([{**VERDICT, "itemId": "zzz"}], apply=True)
    assert any("introuvable" in r for r in rapport["refus"])


@pytest.mark.parametrize("types, motif", [
    ([], "vide"),
    (["serie", "serie"], "repete"),
    (["saga"], "hors enum"),
    (["serie", "SERIE"], "hors enum"),
    (None, "vide"),
])
def test_les_types_invalides_sont_refuses(corpus: Path, types, motif):
    corpus_type(corpus)
    rapport = ati.executer([{**VERDICT, "typesProposes": types}], apply=True)
    assert rapport["items_modifies"] == 0
    assert any(motif in r for r in rapport["refus"]), rapport["refus"]


def test_un_verdict_sans_itemId_est_refuse(corpus: Path):
    rapport = ati.executer([{"typesProposes": ["serie"]}], apply=True)
    assert any("sans itemId" in r for r in rapport["refus"])


# ===== Le chargement =======================================================
def test_charger_concatene_plusieurs_lots(tmp_path: Path):
    a = tmp_path / "a.json"; a.write_text(json.dumps([VERDICT]), encoding="utf-8")
    b = tmp_path / "b.json"
    b.write_text(json.dumps([{**VERDICT, "itemId": "def"}]), encoding="utf-8")
    assert len(ati.charger([a, b])) == 2


def test_charger_REFUSE_un_item_present_dans_deux_lots(tmp_path: Path):
    """Deux agents qui se contredisent sur la meme oeuvre : mieux vaut
    s'arreter que d'appliquer celui qui passe en dernier."""
    a = tmp_path / "a.json"; a.write_text(json.dumps([VERDICT]), encoding="utf-8")
    b = tmp_path / "b.json"
    b.write_text(json.dumps([{**VERDICT, "typesProposes": ["film"]}]),
                 encoding="utf-8")
    with pytest.raises(ati.VerdictInvalide, match="double"):
        ati.charger([a, b])


def test_un_document_sans_id_est_ignore(corpus: Path):
    """Le corpus porte quelques fichiers techniques sans `id` : les indexer
    sous la cle vide ferait collisionner tout ce qui n'en a pas."""
    corpus_type(corpus)
    poser(corpus, "items", "sans_id", {"title": "Orphelin", "types": ["autre"]})
    assert ati.executer([VERDICT], apply=True)["items_modifies"] == 1


def test_une_mention_SANS_reco_ne_fait_pas_echouer(corpus: Path):
    """Une mention peut survivre a la suppression de sa reco."""
    item, _ = corpus_type(corpus)
    poser(corpus, "mentions", "ubm-7", {
        "id": "ubm-7", "itemId": "abc", "status": "validated"})  # aucune reco
    rapport = ati.executer([VERDICT], apply=True)
    assert rapport["items_modifies"] == 1
    assert json.loads(item.read_text(encoding="utf-8"))["types"] == ["serie"]


def test_un_fichier_json_illisible_est_ignore(corpus: Path):
    """Un `.json` corrompu dans le corpus ne doit pas interrompre la passe."""
    corpus_type(corpus)
    (corpus / "items" / "casse.json").write_text("{ pas du json", encoding="utf-8")
    (corpus / "mentions" / "casse.json").write_text("{{{", encoding="utf-8")
    rapport = ati.executer([VERDICT], apply=True)
    assert rapport["items_modifies"] == 1


# ===== CLI =================================================================
def test_main_applique(corpus: Path, tmp_path: Path):
    item, _ = corpus_type(corpus)
    f = tmp_path / "v.json"; f.write_text(json.dumps([VERDICT]), encoding="utf-8")
    assert ati.main([str(f), "--apply"]) == 0
    assert json.loads(item.read_text(encoding="utf-8"))["types"] == ["serie"]


def test_main_dry_run(corpus: Path, tmp_path: Path):
    item, _ = corpus_type(corpus)
    f = tmp_path / "v.json"; f.write_text(json.dumps([VERDICT]), encoding="utf-8")
    avant = item.read_text(encoding="utf-8")
    assert ati.main([str(f)]) == 0
    assert item.read_text(encoding="utf-8") == avant


def test_main_sort_en_erreur_sur_un_doublon(corpus: Path, tmp_path: Path):
    corpus_type(corpus)
    f = tmp_path / "v.json"
    f.write_text(json.dumps([VERDICT, VERDICT]), encoding="utf-8")
    assert ati.main([str(f), "--apply"]) == 1


def test_main_journalise_les_refus(corpus: Path, tmp_path: Path, caplog):
    corpus_type(corpus, types_item=("film",))
    f = tmp_path / "v.json"; f.write_text(json.dumps([VERDICT]), encoding="utf-8")
    with caplog.at_level("WARNING"):
        assert ati.main([str(f), "--apply"]) == 0
    assert "REFUS" in caplog.text
