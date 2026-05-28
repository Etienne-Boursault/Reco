"""Tests pour `tools/migrate_types.py` — migration `type` → `types`."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

import common
import migrate_types
from migrate_types import (
    main,
    migrate_all,
    migrate_file,
    migrate_reco,
    migrate_source,
)


# ===== Fixtures ============================================================
@pytest.fixture
def recos_root(tmp_path: Path, monkeypatch):
    """Redirige `common.RECOS_DIR` (et le miroir dans migrate_types) vers tmp."""
    root = tmp_path / "src" / "content" / "recos"
    root.mkdir(parents=True)
    monkeypatch.setattr(common, "RECOS_DIR", root)
    monkeypatch.setattr(migrate_types, "RECOS_DIR", root)
    return root


def _write(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


# ===== migrate_reco (pure) =================================================
def test_migrate_reco_replaces_type_with_types():
    out = migrate_reco({"id": "x", "type": "film", "title": "T"})
    assert out is not None
    assert out["types"] == ["film"]
    assert "type" not in out
    assert out["title"] == "T"
    assert out["id"] == "x"


def test_migrate_reco_idempotent_when_types_present():
    # Aucune migration nécessaire : renvoie None.
    assert migrate_reco({"id": "x", "types": ["film"], "title": "T"}) is None


def test_migrate_reco_no_type_no_types_returns_none():
    assert migrate_reco({"id": "x", "title": "T"}) is None


def test_migrate_reco_empty_string_type_returns_none():
    assert migrate_reco({"type": "", "title": "T"}) is None


def test_migrate_reco_non_string_type_returns_none():
    # Garde-fou : un `type` int/None est ignoré (pas migré).
    assert migrate_reco({"type": 42, "title": "T"}) is None
    assert migrate_reco({"type": None, "title": "T"}) is None


def test_migrate_reco_types_present_but_empty_falls_back_to_type():
    # types: [] est considéré comme non-migré ; si type présent on migre.
    out = migrate_reco({"type": "film", "types": [], "title": "T"})
    assert out is not None
    assert out["types"] == ["film"]


# ===== migrate_file =======================================================
def test_migrate_file_writes_when_migrating(recos_root):
    p = recos_root / "ubm" / "0001.json"
    _write(p, {"id": "ubm-0001", "type": "film", "title": "Mortel"})
    assert migrate_file(p) is True
    data = json.loads(p.read_text(encoding="utf-8"))
    assert data["types"] == ["film"]
    assert "type" not in data


def test_migrate_file_idempotent_no_write(recos_root):
    p = recos_root / "ubm" / "0001.json"
    _write(p, {"id": "x", "types": ["film"], "title": "T"})
    mtime_before = p.stat().st_mtime_ns
    assert migrate_file(p) is False
    # Aucune écriture : mtime inchangé.
    assert p.stat().st_mtime_ns == mtime_before


def test_migrate_file_no_type_field(recos_root):
    p = recos_root / "ubm" / "0001.json"
    _write(p, {"id": "x", "title": "T"})
    assert migrate_file(p) is False


def test_migrate_file_corrupted_returns_false(recos_root, caplog):
    p = recos_root / "ubm" / "0001.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("PAS DU JSON", encoding="utf-8")
    assert migrate_file(p) is False


# ===== migrate_source =====================================================
def test_migrate_source_counts_changes(recos_root):
    src = recos_root / "ubm"
    _write(src / "0001.json", {"type": "film", "title": "A"})
    _write(src / "0002.json", {"type": "serie", "title": "B"})
    _write(src / "0003.json", {"types": ["livre"], "title": "C"})  # déjà migrée
    n = migrate_source("ubm")
    assert n == 2
    # Recos migrées.
    assert json.loads((src / "0001.json").read_text("utf-8"))["types"] == ["film"]
    assert json.loads((src / "0002.json").read_text("utf-8"))["types"] == ["serie"]
    # Reco déjà OK : inchangée.
    assert json.loads((src / "0003.json").read_text("utf-8"))["types"] == ["livre"]


def test_migrate_source_missing_dir(recos_root, caplog):
    n = migrate_source("inexistante")
    assert n == 0


# ===== migrate_all ========================================================
def test_migrate_all_iterates_sources(recos_root):
    _write(recos_root / "ubm" / "0001.json", {"type": "film", "title": "A"})
    _write(recos_root / "autre" / "0001.json", {"type": "livre", "title": "B"})
    _write(recos_root / "autre" / "0002.json", {"types": ["bd"], "title": "C"})
    n = migrate_all()
    assert n == 2


def test_migrate_all_missing_root(tmp_path: Path, monkeypatch):
    missing = tmp_path / "ne-existe-pas"
    monkeypatch.setattr(migrate_types, "RECOS_DIR", missing)
    assert migrate_all() == 0


# ===== main / CLI =========================================================
def test_main_without_source_runs_migrate_all(recos_root, monkeypatch):
    _write(recos_root / "ubm" / "0001.json", {"type": "film", "title": "A"})
    monkeypatch.setattr(sys, "argv", ["migrate_types.py"])
    main()
    data = json.loads((recos_root / "ubm" / "0001.json").read_text("utf-8"))
    assert data["types"] == ["film"]


def test_main_with_source_argument(recos_root, monkeypatch):
    _write(recos_root / "ubm" / "0001.json", {"type": "film", "title": "A"})
    _write(recos_root / "autre" / "0001.json", {"type": "livre", "title": "B"})
    monkeypatch.setattr(sys, "argv", ["migrate_types.py", "--source", "ubm"])
    main()
    # ubm migré
    assert json.loads(
        (recos_root / "ubm" / "0001.json").read_text("utf-8")
    )["types"] == ["film"]
    # autre intouché
    assert "type" in json.loads(
        (recos_root / "autre" / "0001.json").read_text("utf-8")
    )
