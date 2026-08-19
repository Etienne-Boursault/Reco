"""Tests de `tools/aligner_titres_item_reco.py`.

CE QUE LA RELECTURE A VU
------------------------
« Du meme createur » proposait « Agendas », un titre introuvable ailleurs :
« quand je filtre dans les recos, je ne la trouve pas et je trouve bien
Haagen-Dazs » (2026-08-19). Le morceau avait ete mal entendu par la
transcription, puis corrige — sur la RECO seulement, pas sur la fiche.

CE QUE CES TESTS PROTEGENT
--------------------------
Le SENS de la propagation. Par defaut la reco a raison : elle a ete relue une
par une, la fiche non. Mais pas toujours — « La Zone d'interet » porte le
titre francais sur sa fiche et le titre anglais sur sa reco, et c'est la fiche
qui a raison. Une table d'exceptions inverse le sens, et ces tests verifient
qu'elle inverse bien tout, y compris le decompte.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import aligner_titres_item_reco as ati
import common


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


def monter(racine: Path, *, titre_item: str, titres_recos: list[str | None],
           item_id="abc", statut="validated") -> tuple[Path, list[Path]]:
    item = poser(racine, "items", "i", {"id": item_id, "title": titre_item})
    recos = []
    for n, titre in enumerate(titres_recos, start=1):
        poser(racine, "mentions", f"m{n}", {
            "id": f"ubm-{n}", "itemId": item_id, "status": statut})
        doc: dict = {"id": f"ubm-{n}"}
        if titre is not None:
            doc["title"] = titre
        recos.append(poser(racine, "recos", f"r{n}", doc))
    return item, recos


# ===== Le cas nominal ======================================================
def test_l_oeuvre_reprend_le_titre_corrige(corpus: Path):
    """« Agendas » sur la fiche, « Haagen-Dazs » sur la reco."""
    item, _ = monter(corpus, titre_item="Agendas", titres_recos=["Haagen-Dazs"])
    rapport = ati.executer(apply=True)
    assert json.loads(item.read_text(encoding="utf-8"))["title"] == "Haagen-Dazs"
    assert rapport["items"] == 1


def test_plusieurs_recos_du_MEME_titre_suffisent(corpus: Path):
    item, _ = monter(corpus, titre_item="Diams",
                     titres_recos=["Diam's", "Diam's", "Diam's"])
    ati.executer(apply=True)
    assert json.loads(item.read_text(encoding="utf-8"))["title"] == "Diam's"


def test_un_titre_deja_aligne_ne_bouge_pas(corpus: Path):
    item, _ = monter(corpus, titre_item="Kaamelott", titres_recos=["Kaamelott"])
    avant = item.read_text(encoding="utf-8")
    assert ati.executer(apply=True)["items"] == 0
    assert item.read_text(encoding="utf-8") == avant


def test_la_comparaison_ignore_la_casse(corpus: Path):
    """« KAAMELOTT » et « Kaamelott » ne sont pas une divergence de fond."""
    item, _ = monter(corpus, titre_item="Kaamelott", titres_recos=["KAAMELOTT"])
    assert ati.executer(apply=True)["items"] == 0


def test_le_reste_du_document_est_intact(corpus: Path):
    item = poser(corpus, "items", "i", {
        "id": "abc", "title": "Agendas", "types": ["musique"],
        "creator": "Kyan Khojandi"})
    poser(corpus, "mentions", "m1", {"id": "ubm-1", "itemId": "abc",
                                     "status": "validated"})
    poser(corpus, "recos", "r1", {"id": "ubm-1", "title": "Haagen-Dazs"})
    ati.executer(apply=True)
    doc = json.loads(item.read_text(encoding="utf-8"))
    assert doc["types"] == ["musique"]
    assert doc["creator"] == "Kyan Khojandi"


# ===== Le sens inverse =====================================================
def test_l_exception_INVERSE_le_sens(corpus: Path):
    """« La Zone d'intérêt » : la fiche porte le titre français, celui
    d'AlloCiné et de SOONER — les deux liens de la reco elle-même."""
    exception = next(iter(ati.L_OEUVRE_A_RAISON))
    item, (reco,) = monter(corpus, titre_item="La Zone d'intérêt",
                           titres_recos=["Zone of Interest"], item_id=exception)
    rapport = ati.executer(apply=True)
    assert json.loads(item.read_text(encoding="utf-8"))["title"] == "La Zone d'intérêt"
    assert json.loads(reco.read_text(encoding="utf-8"))["title"] == "La Zone d'intérêt"
    assert (rapport["items"], rapport["recos"]) == (0, 1)


def test_l_exception_ne_touche_que_les_recos_DIVERGENTES(corpus: Path):
    """Deux recos, l'une deja au bon titre : seule l'autre bouge, et la passe
    poursuit au lieu de s'arreter a la premiere."""
    exception = next(iter(ati.L_OEUVRE_A_RAISON))
    item, (a, b) = monter(corpus, titre_item="La Zone d'intérêt",
                          titres_recos=["La Zone d'intérêt", "Zone of Interest"],
                          item_id=exception)
    avant = a.read_text(encoding="utf-8")
    rapport = ati.executer(apply=True)
    assert a.read_text(encoding="utf-8") == avant          # deja bonne
    assert json.loads(b.read_text(encoding="utf-8"))["title"] == "La Zone d'intérêt"
    assert rapport["recos"] == 1


def test_l_exception_en_simulation_n_ecrit_rien(corpus: Path):
    exception = next(iter(ati.L_OEUVRE_A_RAISON))
    _, (reco,) = monter(corpus, titre_item="La Zone d'intérêt",
                        titres_recos=["Zone of Interest"], item_id=exception)
    avant = reco.read_text(encoding="utf-8")
    assert ati.executer(apply=False)["recos"] == 1
    assert reco.read_text(encoding="utf-8") == avant


def test_chaque_exception_porte_sa_source():
    """Inverser le sens par defaut demande une raison verifiable."""
    for item_id, preuve in ati.L_OEUVRE_A_RAISON.items():
        assert preuve.startswith("https://"), item_id


# ===== Les désaccords ======================================================
def test_des_recos_qui_se_CONTREDISENT_ne_decident_pas(corpus: Path):
    item, _ = monter(corpus, titre_item="Quelque chose",
                     titres_recos=["Un titre", "Un autre titre"])
    rapport = ati.executer(apply=True)
    assert json.loads(item.read_text(encoding="utf-8"))["title"] == "Quelque chose"
    assert rapport["items"] == 0
    assert len(rapport["desaccords"]) == 1


# ===== La portée ===========================================================
def test_une_reco_SANS_titre_est_ignoree(corpus: Path):
    item, _ = monter(corpus, titre_item="Agendas",
                     titres_recos=[None, "Haagen-Dazs"])
    ati.executer(apply=True)
    assert json.loads(item.read_text(encoding="utf-8"))["title"] == "Haagen-Dazs"


def test_aucune_reco_titree_ne_change_rien(corpus: Path):
    item, _ = monter(corpus, titre_item="Agendas", titres_recos=[None, None])
    assert ati.executer(apply=True)["items"] == 0


def test_les_mentions_ECARTEES_sont_hors_jeu(corpus: Path):
    item, _ = monter(corpus, titre_item="Agendas",
                     titres_recos=["Haagen-Dazs"], statut="discarded")
    assert ati.executer(apply=True)["items"] == 0
    assert json.loads(item.read_text(encoding="utf-8"))["title"] == "Agendas"


def test_une_mention_sans_oeuvre_ne_fait_pas_echouer(corpus: Path):
    monter(corpus, titre_item="Agendas", titres_recos=["Haagen-Dazs"])
    poser(corpus, "mentions", "m9", {
        "id": "ubm-9", "itemId": "inconnu", "status": "validated"})
    assert ati.executer(apply=True)["items"] == 1


def test_une_mention_sans_reco_ne_fait_pas_echouer(corpus: Path):
    monter(corpus, titre_item="Agendas", titres_recos=["Haagen-Dazs"])
    poser(corpus, "mentions", "m9", {
        "id": "ubm-99", "itemId": "abc", "status": "validated"})
    assert ati.executer(apply=True)["items"] == 1


def test_la_simulation_n_ecrit_rien(corpus: Path):
    item, _ = monter(corpus, titre_item="Agendas", titres_recos=["Haagen-Dazs"])
    avant = item.read_text(encoding="utf-8")
    assert ati.executer(apply=False)["items"] == 1     # annonce
    assert item.read_text(encoding="utf-8") == avant   # n'ecrit pas


def test_la_passe_est_idempotente(corpus: Path):
    monter(corpus, titre_item="Agendas", titres_recos=["Haagen-Dazs"])
    ati.executer(apply=True)
    assert ati.executer(apply=True)["items"] == 0


def test_un_json_illisible_est_ignore(corpus: Path):
    monter(corpus, titre_item="Agendas", titres_recos=["Haagen-Dazs"])
    for dossier in ("items", "mentions", "recos"):
        (corpus / dossier / "casse.json").write_text("{ nope", encoding="utf-8")
    assert ati.executer(apply=True)["items"] == 1


def test_un_document_sans_id_est_ignore(corpus: Path):
    monter(corpus, titre_item="Agendas", titres_recos=["Haagen-Dazs"])
    poser(corpus, "items", "orphelin", {"title": "Sans id"})
    assert ati.executer(apply=True)["items"] == 1


# ===== CLI =================================================================
def test_main_applique(corpus: Path):
    item, _ = monter(corpus, titre_item="Agendas", titres_recos=["Haagen-Dazs"])
    assert ati.main(["--apply"]) == 0
    assert json.loads(item.read_text(encoding="utf-8"))["title"] == "Haagen-Dazs"


def test_main_dry_run(corpus: Path):
    item, _ = monter(corpus, titre_item="Agendas", titres_recos=["Haagen-Dazs"])
    avant = item.read_text(encoding="utf-8")
    assert ati.main([]) == 0
    assert item.read_text(encoding="utf-8") == avant


def test_main_journalise_les_desaccords(corpus: Path, caplog):
    monter(corpus, titre_item="X", titres_recos=["A", "B"])
    with caplog.at_level("WARNING"):
        assert ati.main(["--apply"]) == 0
    assert "DESACCORD" in caplog.text
