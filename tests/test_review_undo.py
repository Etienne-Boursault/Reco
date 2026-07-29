"""Tests de `tools/review_undo.py` — pile d'annulation des décisions de relecture.

La pile vit sur disque sous ``tools/output/review-undo/<source>/`` : tous les
tests redirigent `_UNDO_ROOT` vers un `tmp_path` dédié. Les chemins d'échec
(disque plein, entrée corrompue, restauration impossible) sont vérifiés
explicitement car l'undo est un filet de sécurité *best-effort* : il ne doit
JAMAIS casser le flux de relecture.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import review_undo


@pytest.fixture(autouse=True)
def _undo_root(tmp_path: Path, monkeypatch):
    """Isole la pile d'undo sur un dossier temporaire par test."""
    root = tmp_path / "review-undo"
    monkeypatch.setattr(review_undo, "_UNDO_ROOT", root)
    return root


def _snapshot(guid: str = "g1", status: str = "pending") -> dict:
    return {"id": "ubm-001", "episodeGuid": guid, "status": status}


# ===== _entries / _next_index ==============================================
def test_entries_empty_when_dir_absent():
    """Aucun dossier pour la source → liste vide (pas d'exception)."""
    assert review_undo._entries("jamais-vue") == []
    assert review_undo.has_undo("jamais-vue") is False


def test_next_index_starts_at_zero_then_increments(tmp_path: Path):
    review_undo.push_snapshot("s", "ubm-001", str(tmp_path / "a.json"), _snapshot())
    review_undo.push_snapshot("s", "ubm-002", str(tmp_path / "b.json"), _snapshot())
    names = sorted(p.name for p in review_undo._entries("s"))
    assert names == ["000000__ubm-001.json", "000001__ubm-002.json"]


def test_next_index_falls_back_to_count_when_name_not_numbered(_undo_root: Path):
    """Un fichier étranger non numéroté ne doit pas faire planter l'empilement :
    on retombe sur `len(existing)` comme index."""
    d = _undo_root / "s"
    d.mkdir(parents=True)
    (d / "zzz-pas-un-index.json").write_text("{}", encoding="utf-8")

    assert review_undo._next_index(review_undo._entries("s")) == 1


# ===== push_snapshot =======================================================
def test_push_snapshot_writes_full_payload(tmp_path: Path, _undo_root: Path):
    reco_path = tmp_path / "recos" / "ubm" / "001.json"
    review_undo.push_snapshot(
        "ubm", "ubm-001", str(reco_path), _snapshot(), label="Valider",
    )

    entries = review_undo._entries("ubm")
    assert len(entries) == 1
    payload = json.loads(entries[0].read_text(encoding="utf-8"))
    assert payload == {
        "reco_id": "ubm-001",
        "path": str(reco_path),
        "label": "Valider",
        "snapshot": _snapshot(),
    }
    assert review_undo.has_undo("ubm") is True


def test_push_snapshot_purges_beyond_max_depth(monkeypatch, tmp_path: Path):
    """Au-delà de `_MAX_DEPTH`, les instantanés les plus ANCIENS sont oubliés."""
    monkeypatch.setattr(review_undo, "_MAX_DEPTH", 2)
    for i in range(4):
        review_undo.push_snapshot(
            "ubm", f"ubm-{i:03d}", str(tmp_path / f"{i}.json"), _snapshot(),
        )

    names = [p.name for p in review_undo._entries("ubm")]
    assert names == ["000002__ubm-002.json", "000003__ubm-003.json"]


def test_push_snapshot_survives_unlink_failure_during_purge(
    monkeypatch, tmp_path: Path,
):
    """Si la purge ne peut pas supprimer un vieux fichier, l'empilement du
    nouvel instantané reste valide."""
    monkeypatch.setattr(review_undo, "_MAX_DEPTH", 1)
    review_undo.push_snapshot("ubm", "ubm-000", str(tmp_path / "0.json"), _snapshot())

    def _boom(self):
        raise OSError("verrouillé par un autre process")

    monkeypatch.setattr(Path, "unlink", _boom)
    review_undo.push_snapshot("ubm", "ubm-001", str(tmp_path / "1.json"), _snapshot())

    # La purge a échoué → les deux entrées subsistent, mais aucune exception.
    assert len(review_undo._entries("ubm")) == 2


def test_push_snapshot_never_raises_when_disk_unavailable(
    tmp_path: Path, _undo_root: Path, caplog,
):
    """Un `_dir()` occupé par un FICHIER rend `mkdir` impossible : la décision
    de relecture doit quand même s'appliquer (aucune exception remontée)."""
    _undo_root.mkdir(parents=True)
    (_undo_root / "ubm").write_text("je suis un fichier, pas un dossier",
                                    encoding="utf-8")

    review_undo.push_snapshot("ubm", "ubm-001", str(tmp_path / "1.json"), _snapshot())

    assert review_undo.has_undo("ubm") is False


# ===== pop_and_restore =====================================================
def test_pop_on_empty_stack_reports_not_restored():
    assert review_undo.pop_and_restore("vide") == {
        "restored": False, "reco_id": "", "guid": "",
    }


def test_pop_restores_exact_pre_decision_state(tmp_path: Path):
    """Le fichier reco revient EXACTEMENT à son état d'avant la décision."""
    reco_path = tmp_path / "001.json"
    before = _snapshot(status="pending")
    reco_path.write_text(json.dumps(before), encoding="utf-8")

    review_undo.push_snapshot("ubm", "ubm-001", str(reco_path), before)
    # Décision humaine : la reco est validée sur disque.
    reco_path.write_text(json.dumps(_snapshot(status="validated")),
                         encoding="utf-8")

    out = review_undo.pop_and_restore("ubm")

    assert out == {"restored": True, "reco_id": "ubm-001", "guid": "g1"}
    assert json.loads(reco_path.read_text(encoding="utf-8")) == before
    # LIFO : la pile est vidée de son sommet.
    assert review_undo.has_undo("ubm") is False


def test_pop_is_lifo_across_several_decisions(tmp_path: Path):
    p1, p2 = tmp_path / "1.json", tmp_path / "2.json"
    review_undo.push_snapshot("ubm", "ubm-001", str(p1), _snapshot("gA"))
    review_undo.push_snapshot("ubm", "ubm-002", str(p2), _snapshot("gB"))

    assert review_undo.pop_and_restore("ubm")["reco_id"] == "ubm-002"
    assert review_undo.pop_and_restore("ubm")["reco_id"] == "ubm-001"
    assert review_undo.pop_and_restore("ubm")["restored"] is False


def test_pop_discards_unreadable_entry(_undo_root: Path):
    """Une entrée corrompue (JSON invalide) est jetée, pas rejouée."""
    d = _undo_root / "ubm"
    d.mkdir(parents=True)
    corrupted = d / "000000__ubm-001.json"
    corrupted.write_text("{ ceci n'est pas du JSON", encoding="utf-8")

    out = review_undo.pop_and_restore("ubm")

    assert out == {"restored": False, "reco_id": "", "guid": ""}
    assert not corrupted.exists()


def test_pop_keeps_corrupted_entry_when_unlink_fails(monkeypatch, _undo_root: Path):
    """Entrée corrompue + suppression impossible : on renvoie `restored: False`
    sans lever."""
    d = _undo_root / "ubm"
    d.mkdir(parents=True)
    (d / "000000__ubm-001.json").write_text("pas du JSON", encoding="utf-8")

    def _boom(self):
        raise OSError("fichier verrouillé")

    monkeypatch.setattr(Path, "unlink", _boom)
    assert review_undo.pop_and_restore("ubm")["restored"] is False
    assert len(review_undo._entries("ubm")) == 1


def test_pop_without_snapshot_still_pops_entry(tmp_path: Path, _undo_root: Path):
    """Payload sans `snapshot` : rien à réécrire, mais l'entrée est dépilée et
    le résultat annoncé comme restauré (l'état disque était déjà le bon)."""
    d = _undo_root / "ubm"
    d.mkdir(parents=True)
    (d / "000000__ubm-001.json").write_text(
        json.dumps({"reco_id": "ubm-001", "path": str(tmp_path / "x.json")}),
        encoding="utf-8",
    )

    out = review_undo.pop_and_restore("ubm")

    assert out == {"restored": True, "reco_id": "ubm-001", "guid": ""}
    assert review_undo._entries("ubm") == []


def test_pop_reports_failure_when_write_raises(monkeypatch, tmp_path: Path):
    """Restauration disque impossible → `restored: False`, et l'entrée est
    CONSERVÉE pour pouvoir réessayer."""
    reco_path = tmp_path / "001.json"
    review_undo.push_snapshot("ubm", "ubm-001", str(reco_path), _snapshot())

    def _boom(path, data):
        raise OSError("disque plein")

    monkeypatch.setattr(review_undo, "write_json_if_changed", _boom)
    out = review_undo.pop_and_restore("ubm")

    assert out == {"restored": False, "reco_id": "ubm-001", "guid": "g1"}
    assert len(review_undo._entries("ubm")) == 1


def test_pop_succeeds_even_if_entry_unlink_fails(monkeypatch, tmp_path: Path):
    """La reco est restaurée : l'échec de suppression de l'instantané ne doit
    pas transformer un succès en échec."""
    reco_path = tmp_path / "001.json"
    review_undo.push_snapshot("ubm", "ubm-001", str(reco_path), _snapshot())

    def _boom(self):
        raise OSError("fichier verrouillé")

    monkeypatch.setattr(Path, "unlink", _boom)
    out = review_undo.pop_and_restore("ubm")

    assert out["restored"] is True
    assert json.loads(reco_path.read_text(encoding="utf-8")) == _snapshot()
