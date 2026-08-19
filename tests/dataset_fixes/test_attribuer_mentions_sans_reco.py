"""Tests de `tools/attribuer_mentions_sans_reco.py`.

D'OU VIENNENT CES HUIT CAS
--------------------------
Huit mentions publiees n'ont pas de fiche de recommandation. Elles
s'affichaient dans la chronologie d'une oeuvre avec un nom approximatif —
« Nassim », « Kyan », « N/A » — et rien d'autre.

Le corpus n'est pas diarize : rien dans le transcript ne dit qui parle. Chaque
ligne de la table a donc ete tranchee A L'OREILLE par l'editeur, en ecoutant
l'episode au timecode de la mention (2026-08-19).

CE QUE CES TESTS PROTEGENT
--------------------------
Une table arbitree a la main ecrit sans condition ce qu'un humain y a mis. Les
gardes verifiees ici limitent sa portee : ne toucher que les mentions nommees,
ne jamais poser `guestWork: false` — ce qui dirait « verifie et non » quand
personne ne l'a verifie —, et signaler une mention introuvable plutot que de
l'ignorer, faute de quoi une decision editoriale se perdrait en silence.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import attribuer_mentions_sans_reco as ams
import common


@pytest.fixture
def corpus(tmp_path: Path, monkeypatch) -> Path:
    (tmp_path / "mentions").mkdir()
    monkeypatch.setattr(common, "MENTIONS_DIR", tmp_path / "mentions")
    return tmp_path


def poser(racine: Path, nom: str, doc: dict) -> Path:
    chemin = racine / "mentions" / f"{nom}.json"
    chemin.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
    return chemin


UNE = ams.Attribution("ubm-1", "Une œuvre", par="Kyan Khojandi",
                      pourquoi="test")


# ===== La table livree =====================================================
def test_chaque_attribution_fait_quelque_chose():
    for a in ams.ATTRIBUTIONS:
        assert a.par or a.kind or a.guest_work or a.ecarter, a.mention_id


def test_chaque_attribution_porte_sa_raison():
    for a in ams.ATTRIBUTIONS:
        assert len(a.pourquoi) > 8, a.mention_id


def test_aucune_mention_n_apparait_deux_fois():
    ids = [a.mention_id for a in ams.ATTRIBUTIONS]
    assert len(set(ids)) == len(ids)


def test_une_mention_ecartee_ne_recoit_rien_d_autre():
    """Poser un auteur sur une mention qu'on retire serait contradictoire."""
    for a in ams.ATTRIBUTIONS:
        if a.ecarter:
            assert not (a.par or a.kind or a.guest_work), a.mention_id


def test_les_kind_sont_ceux_du_schema():
    for a in ams.ATTRIBUTIONS:
        if a.kind is not None:
            assert a.kind in {"reco", "citation"}, a.mention_id


# ===== L'attribution =======================================================
def test_l_auteur_est_pose(corpus: Path):
    m = poser(corpus, "m1", {"id": "ubm-1", "recommendedBy": "N/A"})
    rapport = ams.executer([UNE], apply=True)
    assert json.loads(m.read_text(encoding="utf-8"))["recommendedBy"] == "Kyan Khojandi"
    assert rapport["mentions"] == 1


def test_un_auteur_deja_bon_ne_declenche_rien(corpus: Path):
    m = poser(corpus, "m1", {"id": "ubm-1", "recommendedBy": "Kyan Khojandi"})
    avant = m.read_text(encoding="utf-8")
    assert ams.executer([UNE], apply=True)["mentions"] == 0
    assert m.read_text(encoding="utf-8") == avant


def test_une_mention_de_passage_devient_une_CITATION(corpus: Path):
    """« Marvel » et « Visionnaire » sont citées, pas conseillées : le site
    les affiche alors « mentionné » et non « recommandé »."""
    a = ams.Attribution("ubm-1", "Marvel", par="Kyan Khojandi",
                        kind="citation", pourquoi="test")
    m = poser(corpus, "m1", {"id": "ubm-1", "kind": "reco"})
    ams.executer([a], apply=True)
    doc = json.loads(m.read_text(encoding="utf-8"))
    assert doc["kind"] == "citation"
    assert doc["recommendedBy"] == "Kyan Khojandi"


def test_l_etoile_leur_oeuvre_est_posee(corpus: Path):
    a = ams.Attribution("ubm-1", "Message Personnel", par="Kyan Khojandi",
                        guest_work=True, pourquoi="test")
    m = poser(corpus, "m1", {"id": "ubm-1"})
    ams.executer([a], apply=True)
    assert json.loads(m.read_text(encoding="utf-8"))["guestWork"] is True


def test_guestWork_n_est_JAMAIS_pose_a_false(corpus: Path):
    """Le schéma l'admet, mais une valeur explicite dirait « vérifié et non »,
    ce que personne n'a fait."""
    m = poser(corpus, "m1", {"id": "ubm-1"})
    ams.executer([UNE], apply=True)
    assert "guestWork" not in json.loads(m.read_text(encoding="utf-8"))


def test_le_reste_du_document_est_intact(corpus: Path):
    m = poser(corpus, "m1", {
        "id": "ubm-1", "itemId": "abc", "status": "validated",
        "quote": "gardée", "sourceRef": {"timestamp": "00:31:44"}})
    ams.executer([UNE], apply=True)
    doc = json.loads(m.read_text(encoding="utf-8"))
    assert doc["itemId"] == "abc"
    assert doc["quote"] == "gardée"
    assert doc["sourceRef"] == {"timestamp": "00:31:44"}
    assert doc["status"] == "validated"


# ===== Le doublon écarté ===================================================
def test_une_mention_en_DOUBLE_est_ecartee(corpus: Path):
    """`ubm-1559` pointait le même instant et la même phrase que `ubm-0525`."""
    a = ams.Attribution("ubm-1", "The Zone of Interest", ecarter=True,
                        pourquoi="test")
    m = poser(corpus, "m1", {"id": "ubm-1", "status": "validated"})
    rapport = ams.executer([a], apply=True)
    assert json.loads(m.read_text(encoding="utf-8"))["status"] == "discarded"
    assert (rapport["ecartees"], rapport["mentions"]) == (1, 0)


def test_une_mention_deja_ecartee_ne_declenche_rien(corpus: Path):
    a = ams.Attribution("ubm-1", "X", ecarter=True, pourquoi="test")
    m = poser(corpus, "m1", {"id": "ubm-1", "status": "discarded"})
    avant = m.read_text(encoding="utf-8")
    assert ams.executer([a], apply=True)["ecartees"] == 0
    assert m.read_text(encoding="utf-8") == avant


def test_ecarter_ne_touche_a_AUCUN_autre_champ(corpus: Path):
    a = ams.Attribution("ubm-1", "X", ecarter=True, pourquoi="test")
    m = poser(corpus, "m1", {
        "id": "ubm-1", "status": "validated", "recommendedBy": "Navo"})
    ams.executer([a], apply=True)
    assert json.loads(m.read_text(encoding="utf-8"))["recommendedBy"] == "Navo"


# ===== La portée ===========================================================
def test_une_mention_hors_table_n_est_pas_touchee(corpus: Path):
    autre = poser(corpus, "m9", {"id": "ubm-999", "recommendedBy": "N/A"})
    poser(corpus, "m1", {"id": "ubm-1"})
    avant = autre.read_text(encoding="utf-8")
    ams.executer([UNE], apply=True)
    assert autre.read_text(encoding="utf-8") == avant


def test_une_mention_INTROUVABLE_est_signalee(corpus: Path):
    """Sans ce signal, une decision editoriale se perdrait en silence."""
    rapport = ams.executer([UNE], apply=True)
    assert any("introuvable" in r for r in rapport["refus"])


def test_la_simulation_n_ecrit_rien(corpus: Path):
    m = poser(corpus, "m1", {"id": "ubm-1", "recommendedBy": "N/A"})
    avant = m.read_text(encoding="utf-8")
    assert ams.executer([UNE], apply=False)["mentions"] == 1
    assert m.read_text(encoding="utf-8") == avant


def test_la_passe_est_idempotente(corpus: Path):
    poser(corpus, "m1", {"id": "ubm-1", "recommendedBy": "N/A"})
    ams.executer([UNE], apply=True)
    assert ams.executer([UNE], apply=True)["mentions"] == 0


def test_un_json_illisible_est_ignore(corpus: Path):
    poser(corpus, "m1", {"id": "ubm-1", "recommendedBy": "N/A"})
    (corpus / "mentions" / "casse.json").write_text("{ nope", encoding="utf-8")
    assert ams.executer([UNE], apply=True)["mentions"] == 1


def test_un_document_sans_id_est_ignore(corpus: Path):
    poser(corpus, "m1", {"id": "ubm-1", "recommendedBy": "N/A"})
    poser(corpus, "m2", {"recommendedBy": "orphelin"})
    assert ams.executer([UNE], apply=True)["mentions"] == 1


# ===== CLI =================================================================
def test_main_applique(corpus: Path, monkeypatch):
    m = poser(corpus, "m1", {"id": "ubm-1", "recommendedBy": "N/A"})
    monkeypatch.setattr(ams, "ATTRIBUTIONS", (UNE,))
    assert ams.main(["--apply"]) == 0
    assert json.loads(m.read_text(encoding="utf-8"))["recommendedBy"] == "Kyan Khojandi"


def test_main_dry_run(corpus: Path, monkeypatch):
    m = poser(corpus, "m1", {"id": "ubm-1", "recommendedBy": "N/A"})
    monkeypatch.setattr(ams, "ATTRIBUTIONS", (UNE,))
    avant = m.read_text(encoding="utf-8")
    assert ams.main([]) == 0
    assert m.read_text(encoding="utf-8") == avant


def test_main_journalise_les_refus(corpus: Path, monkeypatch, caplog):
    monkeypatch.setattr(ams, "ATTRIBUTIONS", (UNE,))
    with caplog.at_level("WARNING"):
        assert ams.main(["--apply"]) == 0
    assert "REFUS" in caplog.text
