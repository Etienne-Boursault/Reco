"""Tests pour `tools/backfill_extraction_history.py`."""

from __future__ import annotations

import importlib
import importlib.util
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest

_TOOLS = Path(__file__).resolve().parents[1] / "tools"
if str(_TOOLS) not in sys.path:
    sys.path.insert(0, str(_TOOLS))

import backfill_extraction_history as bf


def _write_reco(tmp: Path, name: str, data: dict, mtime: datetime | None = None) -> Path:
    p = tmp / name
    p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    if mtime is not None:
        ts = mtime.timestamp()
        os.utime(p, (ts, ts))
    return p


def test_backfill_adds_entry_to_reco_without_history(tmp_path):
    p = _write_reco(tmp_path, "0001.json", {
        "id": "ubm-0001", "title": "Dune", "types": ["film"],
        "extractors": ["anthropic"], "timestamp": "00:12:34",
    }, mtime=datetime(2026, 5, 1, tzinfo=UTC))
    assert bf.backfill_file(p) is True
    data = json.loads(p.read_text(encoding="utf-8"))
    assert len(data["extractionHistory"]) == 1
    e = data["extractionHistory"][0]
    assert e["llmProvider"] == "anthropic"
    assert e["llmModel"] == bf.ASSUMED
    assert e["transcriptSource"] == "acast"
    assert e["timestamp_at_extraction"] == "00:12:34"
    assert data["extractors"] == ["anthropic"]
    assert data["transcriptSource"] == "acast"


def test_backfill_skips_reco_with_existing_history(tmp_path):
    p = _write_reco(tmp_path, "0001.json", {
        "id": "ubm-0001", "title": "Dune", "types": ["film"],
        "extractionHistory": [{"at": "2026-06-04T10:00:00",
                                "transcriptModel": "(assumed)",
                                "transcriptSource": "acast",
                                "llmProvider": "anthropic",
                                "llmModel": "(assumed)",
                                "worker": "(assumed)",
                                "timestamp_at_extraction": "00:00:00"}],
    })
    before = p.read_text(encoding="utf-8")
    assert bf.backfill_file(p) is False
    assert p.read_text(encoding="utf-8") == before


def test_backfill_dual_provider_late_mtime_generates_two_entries(tmp_path):
    """extractors=[anthropic,openai] et mtime tardif → 2 entries."""
    p = _write_reco(tmp_path, "0001.json", {
        "id": "ubm-0001", "title": "Dune", "types": ["film"],
        "extractors": ["anthropic", "openai"],
        "timestamp": "00:05:00", "transcriptSource": "youtube",
    }, mtime=datetime(2026, 6, 5, tzinfo=UTC))
    assert bf.backfill_file(p) is True
    data = json.loads(p.read_text(encoding="utf-8"))
    assert len(data["extractionHistory"]) == 2
    providers = sorted(e["llmProvider"] for e in data["extractionHistory"])
    assert providers == ["anthropic", "openai"]
    by_prov = {e["llmProvider"]: e for e in data["extractionHistory"]}
    assert by_prov["anthropic"]["llmModel"] == "claude-haiku-4-5"
    assert by_prov["openai"]["llmModel"] == "gpt-4o-mini"
    assert data["transcriptSource"] == "youtube"


def test_backfill_dual_provider_early_mtime_uses_sonnet(tmp_path):
    p = _write_reco(tmp_path, "0001.json", {
        "id": "ubm-0001", "title": "Dune", "types": ["film"],
        "extractors": ["anthropic", "openai"],
    }, mtime=datetime(2026, 5, 1, tzinfo=UTC))
    assert bf.backfill_file(p) is True
    data = json.loads(p.read_text(encoding="utf-8"))
    # mtime AVANT le cutover → on génère 1 seule entrée (heuristique exige date tardive).
    assert len(data["extractionHistory"]) == 1


def test_backfill_dir_counts(tmp_path):
    _write_reco(tmp_path, "0001.json",
                {"id": "ubm-0001", "title": "A", "types": ["film"],
                 "extractors": ["anthropic"]})
    _write_reco(tmp_path, "0002.json",
                {"id": "ubm-0002", "title": "B", "types": ["film"],
                 "extractionHistory": [{"at": "2026-01-01T00:00:00",
                                        "llmProvider": "anthropic",
                                        "transcriptSource": "acast",
                                        "transcriptModel": "(assumed)",
                                        "llmModel": "(assumed)",
                                        "worker": "(assumed)",
                                        "timestamp_at_extraction": "00:00:00"}]})
    touched, total = bf.backfill_dir(tmp_path)
    assert (touched, total) == (1, 2)


def test_backfill_atomic_via_tempfile(tmp_path, monkeypatch):
    """Si l'écriture échoue, le fichier original reste intact (atomicité)."""
    p = _write_reco(tmp_path, "0001.json", {
        "id": "ubm-0001", "title": "Dune", "types": ["film"],
        "extractors": ["anthropic"],
    })
    original = p.read_text(encoding="utf-8")
    real_replace = os.replace

    def boom(src, dst):
        # Simule un crash juste avant le swap atomique.
        raise OSError("disk full")

    monkeypatch.setattr(bf.os, "replace", boom)
    with pytest.raises(OSError):
        bf.backfill_file(p)
    # Le fichier d'origine n'a pas été modifié.
    assert p.read_text(encoding="utf-8") == original
    # Le tempfile a bien été nettoyé.
    leftovers = [x for x in tmp_path.iterdir() if x.name.startswith(".tmp_")]
    assert leftovers == []
    monkeypatch.setattr(bf.os, "replace", real_replace)


def test_backfill_skips_corrupted_file(tmp_path, capsys):
    p = tmp_path / "0099.json"
    p.write_text("PAS DU JSON", encoding="utf-8")
    assert bf.backfill_file(p) is False


def test_backfill_normalizes_unknown_provider(tmp_path):
    """Un provider inconnu retombe sur 'anthropic'."""
    p = _write_reco(tmp_path, "0001.json", {
        "id": "ubm-0001", "title": "Dune", "types": ["film"],
        "extractors": ["mystery-llm"],
    })
    assert bf.backfill_file(p) is True
    data = json.loads(p.read_text(encoding="utf-8"))
    assert data["extractionHistory"][0]["llmProvider"] == "anthropic"


def test_backfill_normalizes_unknown_transcript_source(tmp_path):
    p = _write_reco(tmp_path, "0001.json", {
        "id": "ubm-0001", "title": "Dune", "types": ["film"],
        "extractors": ["anthropic"], "transcriptSource": "spotify-xyz",
    })
    assert bf.backfill_file(p) is True
    data = json.loads(p.read_text(encoding="utf-8"))
    assert data["extractionHistory"][0]["transcriptSource"] == "acast"


# ===== dry-run =============================================================
def test_dry_run_reports_change_without_touching_the_file(tmp_path):
    """`--dry-run` doit annoncer la modification SANS écrire : c'est ce qui
    permet d'auditer le backfill avant de l'appliquer aux vraies recos."""
    p = _write_reco(tmp_path, "0001.json", {
        "id": "ubm-0001", "title": "Dune", "types": ["film"],
        "extractors": ["anthropic"],
    })
    original = p.read_text(encoding="utf-8")

    assert bf.backfill_file(p, dry_run=True) is True
    assert p.read_text(encoding="utf-8") == original
    assert "extractionHistory" not in json.loads(original)


def test_backfill_dir_dry_run_leaves_every_file_untouched(tmp_path):
    for i in range(3):
        _write_reco(tmp_path, f"000{i}.json", {
            "id": f"ubm-000{i}", "title": "A", "types": ["film"],
            "extractors": ["anthropic"],
        })
    before = {p.name: p.read_text(encoding="utf-8") for p in tmp_path.iterdir()}

    touched, total = bf.backfill_dir(tmp_path, dry_run=True)

    assert (touched, total) == (3, 3)
    assert {p.name: p.read_text(encoding="utf-8") for p in tmp_path.iterdir()} == before


def test_backfill_dir_prints_progress_every_200_files(tmp_path, capsys):
    """Le compteur de progression s'affiche tous les 200 fichiers (le vrai
    dossier en compte ~2000 : sans repère, le run paraît figé)."""
    for i in range(200):
        _write_reco(tmp_path, f"{i:04d}.json", {
            "id": f"ubm-{i:04d}", "title": "A", "types": ["film"],
            "extractors": ["anthropic"],
        })

    touched, total = bf.backfill_dir(tmp_path, dry_run=True)

    assert (touched, total) == (200, 200)
    assert "… 200/200 (touched=200)" in capsys.readouterr().out


# ===== atomicité : nettoyage du tempfile ===================================
def test_atomic_write_reraises_even_if_tempfile_cleanup_fails(
    tmp_path, monkeypatch,
):
    """Si le ménage du `.tmp_` échoue aussi, c'est bien l'erreur d'écriture
    d'origine qui remonte (pas celle du `unlink`)."""
    p = _write_reco(tmp_path, "0001.json", {
        "id": "ubm-0001", "title": "Dune", "types": ["film"],
        "extractors": ["anthropic"],
    })
    original = p.read_text(encoding="utf-8")

    def _no_replace(src, dst):
        raise OSError("disk full")

    def _no_unlink(target):
        raise OSError("fichier verrouillé")

    monkeypatch.setattr(bf.os, "replace", _no_replace)
    monkeypatch.setattr(bf.os, "unlink", _no_unlink)

    with pytest.raises(OSError, match="disk full"):
        bf.backfill_file(p)

    assert p.read_text(encoding="utf-8") == original


# ===== bootstrap sys.path ==================================================
def test_module_prepends_tools_dir_to_syspath_when_absent(monkeypatch):
    """Le script doit rester lançable directement (`python tools/backfill_…py`),
    c.-à-d. SANS `tools/` sur le PYTHONPATH : il l'ajoute lui-même pour trouver
    `extraction_history`. On rejoue donc son chargement depuis le fichier, avec
    un sys.path amputé — le `reload` classique ne conviendrait pas puisqu'il
    a justement besoin de ce chemin pour résoudre le module."""
    tools_dir = str(Path(bf.__file__).resolve().parent)
    monkeypatch.setattr(sys, "path", [p for p in sys.path if p != tools_dir])
    assert tools_dir not in sys.path

    spec = importlib.util.spec_from_file_location("_bf_direct_run", bf.__file__)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    assert sys.path[0] == tools_dir
    assert module.ASSUMED == bf.ASSUMED  # `extraction_history` bien importé


# ===== main ================================================================
def test_main_exits_when_source_dir_missing(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv",
                        ["backfill", "--source", "source-qui-nexiste-pas"])

    with pytest.raises(SystemExit) as err:
        bf.main()

    assert err.value.code == 1
    assert "Répertoire introuvable" in capsys.readouterr().err


def test_main_delegates_to_backfill_dir_with_dry_run(monkeypatch, capsys):
    """`main()` résout `src/content/recos/<source>` et propage `--dry-run`.
    `backfill_dir` est doublé : aucun fichier réel n'est lu ni écrit."""
    seen = {}

    def fake_dir(root, dry_run=False):
        seen["root"] = root
        seen["dry_run"] = dry_run
        return 7, 12

    monkeypatch.setattr(bf, "backfill_dir", fake_dir)
    monkeypatch.setattr(sys, "argv",
                        ["backfill", "--source", "un-bon-moment", "--dry-run"])

    bf.main()

    assert seen["dry_run"] is True
    assert seen["root"].parts[-3:] == ("content", "recos", "un-bon-moment")
    assert "Terminé : 7/12 reco(s) modifiée(s)." in capsys.readouterr().out
