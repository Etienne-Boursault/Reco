"""Tests pour `tools/backfill_extraction_history.py`."""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

_TOOLS = Path(__file__).resolve().parents[1] / "tools"
if str(_TOOLS) not in sys.path:
    sys.path.insert(0, str(_TOOLS))

import backfill_extraction_history as bf  # noqa: E402


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
    }, mtime=datetime(2026, 5, 1, tzinfo=timezone.utc))
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
    }, mtime=datetime(2026, 6, 5, tzinfo=timezone.utc))
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
    }, mtime=datetime(2026, 5, 1, tzinfo=timezone.utc))
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
