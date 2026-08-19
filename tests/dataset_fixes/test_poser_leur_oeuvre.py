"""Tests de `tools/poser_leur_oeuvre.py`.

LE CHAMP VIT A DEUX ENDROITS
----------------------------
`guestWork` existe sur la MENTION et sur la RECO. La carte de `/recos` lit
celui de la reco, la chronologie d'une fiche d'oeuvre lit celui de la mention.
Une passe qui n'ecrit que d'un cote produit une etoile sur une page et pas sur
l'autre.

CE QUE LA RELECTURE A VU (2026-08-19)
-------------------------------------
« Pulsions » portait l'etoile sur cinq cartes sur neuf, alors que Kyan
Khojandi anime le podcast — le spectacle est le sien quel que soit l'episode.
« Valide » la portait a tort : celui qui recommande est Hakim Jemili, simple
invite, et la serie est de Franck Gastambide.

CE QUE CES TESTS PROTEGENT
--------------------------
Que les deux collections bougent ENSEMBLE, et que retirer l'etoile supprime la
cle au lieu d'ecrire `False` — une valeur explicite dirait « verifie et non »,
alors que la quasi-totalite du corpus n'a jamais ete examinee sous cet angle.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import common
import poser_leur_oeuvre as plo


@pytest.fixture
def corpus(tmp_path: Path, monkeypatch) -> Path:
    for nom in ("mentions", "recos"):
        (tmp_path / nom).mkdir()
    monkeypatch.setattr(common, "MENTIONS_DIR", tmp_path / "mentions")
    monkeypatch.setattr(common, "RECOS_DIR", tmp_path / "recos")
    return tmp_path


def poser_fichier(racine: Path, dossier: str, nom: str, doc: dict) -> Path:
    chemin = racine / dossier / f"{nom}.json"
    chemin.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
    return chemin


def monter(racine: Path, mentions: list[dict], *, item="abc") -> list[tuple[Path, Path]]:
    """Pose N mentions et leurs recos, appariees par identifiant."""
    couples = []
    for n, extra in enumerate(mentions, start=1):
        m = poser_fichier(racine, "mentions", f"m{n}", {
            "id": f"ubm-{n}", "itemId": item, "status": "validated", **extra})
        r = poser_fichier(racine, "recos", f"r{n}", {
            "id": f"ubm-{n}", "title": "Pulsions", **extra})
        couples.append((m, r))
    return couples


POSE = plo.Decision(item_id="abc", titre="Pulsions", etoile=True,
                    pourquoi="test")
RETIRE = plo.Decision(item_id="abc", titre="Validé", etoile=False,
                      pourquoi="test")


# ===== La table livree =====================================================
def test_chaque_decision_porte_sa_raison():
    for d in plo.DECISIONS:
        assert len(d.pourquoi) > 20, d.item_id


def test_deux_decisions_sur_une_oeuvre_visent_des_recos_disjointes():
    """« Valide » pose l'etoile sur la carte du co-createur et la retire de
    celle de l'invite : deux decisions, la meme oeuvre, jamais la meme reco."""
    par_oeuvre = {}
    for d in plo.DECISIONS:
        par_oeuvre.setdefault(d.item_id, []).append(d)
    for item_id, liste in par_oeuvre.items():
        if len(liste) == 1:
            continue
        vues = set()
        for d in liste:
            assert d.seulement, item_id     # sinon elle prendrait toute l'oeuvre
            assert not (vues & set(d.seulement)), item_id
            vues |= set(d.seulement)


def test_deux_decisions_opposees_cohabitent(corpus: Path):
    couples = monter(corpus, [{"guestWork": True}, {}])
    decisions = [
        plo.Decision(item_id="abc", titre="X", etoile=False,
                     seulement=("ubm-1",), pourquoi="test"),
        plo.Decision(item_id="abc", titre="X", etoile=True,
                     seulement=("ubm-2",), pourquoi="test"),
    ]
    plo.executer(decisions, apply=True)
    assert "guestWork" not in json.loads(couples[0][0].read_text(encoding="utf-8"))
    assert json.loads(couples[1][0].read_text(encoding="utf-8"))["guestWork"] is True


def test_un_retrait_cible_toujours_des_recos_precises():
    """Retirer l'etoile de TOUTES les cartes d'une oeuvre serait presque
    toujours faux : c'est le cas par carte qui compte."""
    for d in plo.DECISIONS:
        if not d.etoile:
            assert d.seulement, d.item_id


# ===== Les deux collections bougent ensemble ==============================
def test_l_etoile_est_posee_des_DEUX_cotes(corpus: Path):
    (m, r), = monter(corpus, [{}])
    rapport = plo.executer([POSE], apply=True)
    assert json.loads(m.read_text(encoding="utf-8"))["guestWork"] is True
    assert json.loads(r.read_text(encoding="utf-8"))["guestWork"] is True
    assert (rapport["mentions"], rapport["recos"]) == (1, 1)


def test_toutes_les_cartes_d_une_oeuvre_suivent(corpus: Path):
    """« Pulsions » portait l'étoile sur cinq cartes sur neuf."""
    couples = monter(corpus, [{"guestWork": True}, {}, {}, {"guestWork": True}])
    rapport = plo.executer([POSE], apply=True)
    for m, r in couples:
        assert json.loads(m.read_text(encoding="utf-8"))["guestWork"] is True
        assert json.loads(r.read_text(encoding="utf-8"))["guestWork"] is True
    assert rapport["mentions"] == 2      # seules les deux qui manquaient


def test_l_etoile_est_RETIREE_des_deux_cotes(corpus: Path):
    (m, r), = monter(corpus, [{"guestWork": True}])
    decision = plo.Decision(item_id="abc", titre="Validé", etoile=False,
                            seulement=("ubm-1",), pourquoi="test")
    plo.executer([decision], apply=True)
    assert "guestWork" not in json.loads(m.read_text(encoding="utf-8"))
    assert "guestWork" not in json.loads(r.read_text(encoding="utf-8"))


def test_retirer_SUPPRIME_la_cle_au_lieu_d_ecrire_false(corpus: Path):
    """Le schéma admet `false`, mais l'écrire dirait « vérifié et non »,
    alors que la quasi-totalité du corpus n'a jamais été examinée."""
    (m, _), = monter(corpus, [{"guestWork": True}])
    decision = plo.Decision(item_id="abc", titre="X", etoile=False,
                            seulement=("ubm-1",), pourquoi="test")
    plo.executer([decision], apply=True)
    doc = json.loads(m.read_text(encoding="utf-8"))
    assert "guestWork" not in doc
    assert doc.get("guestWork") is not False


def test_retirer_une_etoile_ABSENTE_ne_change_rien(corpus: Path):
    """La quasi-totalite du corpus n'a pas de `guestWork` : un retrait ne doit
    pas reecrire des milliers de fichiers pour rien."""
    (m, r), = monter(corpus, [{}])
    avant = (m.read_text(encoding="utf-8"), r.read_text(encoding="utf-8"))
    decision = plo.Decision(item_id="abc", titre="X", etoile=False,
                            seulement=("ubm-1",), pourquoi="test")
    rapport = plo.executer([decision], apply=True)
    assert (rapport["mentions"], rapport["recos"]) == (0, 0)
    assert (m.read_text(encoding="utf-8"), r.read_text(encoding="utf-8")) == avant


def test_un_retrait_CIBLE_ne_touche_pas_les_autres_cartes(corpus: Path):
    """« Validé » : la carte de Hakim Jemili perd l'étoile, celle de Xavier
    Lacaille la garde — il est co-créateur."""
    couples = monter(corpus, [{"guestWork": True}, {"guestWork": True}])
    decision = plo.Decision(item_id="abc", titre="Validé", etoile=False,
                            seulement=("ubm-1",), pourquoi="test")
    plo.executer([decision], apply=True)
    assert "guestWork" not in json.loads(couples[0][0].read_text(encoding="utf-8"))
    assert json.loads(couples[1][0].read_text(encoding="utf-8"))["guestWork"] is True


# ===== La portée ===========================================================
def test_une_oeuvre_hors_table_n_est_pas_touchee(corpus: Path):
    monter(corpus, [{}])
    autre_m = poser_fichier(corpus, "mentions", "m9", {
        "id": "ubm-9", "itemId": "xyz", "status": "validated"})
    avant = autre_m.read_text(encoding="utf-8")
    plo.executer([POSE], apply=True)
    assert autre_m.read_text(encoding="utf-8") == avant


def test_une_mention_ECARTEE_ne_recoit_rien(corpus: Path):
    m = poser_fichier(corpus, "mentions", "m1", {
        "id": "ubm-1", "itemId": "abc", "status": "discarded"})
    r = poser_fichier(corpus, "recos", "r1", {"id": "ubm-1"})
    plo.executer([POSE], apply=True)
    assert "guestWork" not in json.loads(m.read_text(encoding="utf-8"))
    assert "guestWork" not in json.loads(r.read_text(encoding="utf-8"))


def test_une_oeuvre_SANS_mention_publiee_est_signalee(corpus: Path):
    """Sans ce signal, un arbitrage editorial se perdrait en silence."""
    rapport = plo.executer([POSE], apply=True)
    assert any("aucune mention" in r for r in rapport["refus"])


def test_la_simulation_n_ecrit_rien(corpus: Path):
    (m, r), = monter(corpus, [{}])
    avant = (m.read_text(encoding="utf-8"), r.read_text(encoding="utf-8"))
    rapport = plo.executer([POSE], apply=False)
    assert (rapport["mentions"], rapport["recos"]) == (1, 1)
    assert (m.read_text(encoding="utf-8"), r.read_text(encoding="utf-8")) == avant


def test_la_passe_est_idempotente(corpus: Path):
    monter(corpus, [{}])
    plo.executer([POSE], apply=True)
    rapport = plo.executer([POSE], apply=True)
    assert (rapport["mentions"], rapport["recos"]) == (0, 0)


def test_une_mention_sans_reco_ne_fait_pas_echouer(corpus: Path):
    poser_fichier(corpus, "mentions", "m1", {
        "id": "ubm-1", "itemId": "abc", "status": "validated"})
    assert plo.executer([POSE], apply=True)["mentions"] == 1


def test_un_json_illisible_est_ignore(corpus: Path):
    monter(corpus, [{}])
    for dossier in ("mentions", "recos"):
        (corpus / dossier / "casse.json").write_text("{ nope", encoding="utf-8")
    assert plo.executer([POSE], apply=True)["mentions"] == 1


def test_le_reste_du_document_est_intact(corpus: Path):
    m = poser_fichier(corpus, "mentions", "m1", {
        "id": "ubm-1", "itemId": "abc", "status": "validated",
        "recommendedBy": "Kyan Khojandi", "quote": "gardée"})
    poser_fichier(corpus, "recos", "r1", {"id": "ubm-1"})
    plo.executer([POSE], apply=True)
    doc = json.loads(m.read_text(encoding="utf-8"))
    assert doc["recommendedBy"] == "Kyan Khojandi"
    assert doc["quote"] == "gardée"


# ===== CLI =================================================================
def test_main_applique(corpus: Path, monkeypatch):
    (m, _), = monter(corpus, [{}])
    monkeypatch.setattr(plo, "DECISIONS", (POSE,))
    assert plo.main(["--apply"]) == 0
    assert json.loads(m.read_text(encoding="utf-8"))["guestWork"] is True


def test_main_dry_run(corpus: Path, monkeypatch):
    (m, _), = monter(corpus, [{}])
    monkeypatch.setattr(plo, "DECISIONS", (POSE,))
    avant = m.read_text(encoding="utf-8")
    assert plo.main([]) == 0
    assert m.read_text(encoding="utf-8") == avant


def test_main_journalise_les_refus(corpus: Path, monkeypatch, caplog):
    monkeypatch.setattr(plo, "DECISIONS", (POSE,))
    with caplog.at_level("WARNING"):
        assert plo.main(["--apply"]) == 0
    assert "REFUS" in caplog.text
