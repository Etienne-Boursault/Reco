"""Tests CLI `tools/build_stats.py` (smoke + edge cases)."""
from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

import build_stats


@pytest.fixture
def fake_content(tmp_path, monkeypatch):
    """Construit un faux dossier `src/content/` minimal et patche les chemins."""
    sources_dir = tmp_path / "sources"
    episodes_dir = tmp_path / "episodes" / "ubm"
    mentions_dir = tmp_path / "mentions" / "ubm"
    items_dir = tmp_path / "items" / "ubm"
    for d in (sources_dir, episodes_dir, mentions_dir, items_dir):
        d.mkdir(parents=True)

    (sources_dir / "ubm.json").write_text(
        json.dumps({"id": "ubm", "title": "UBM", "hosts": ["Kyan"]}),
        encoding="utf-8",
    )
    (episodes_dir / "ep1.json").write_text(
        json.dumps({"sourceId": "ubm", "guid": "g1", "title": "T1",
                    "date": "2026-01-15T00:00:00Z"}),
        encoding="utf-8",
    )
    (mentions_dir / "m1.json").write_text(
        json.dumps({"id": "m1", "itemId": "parasite", "recommendedBy": "Alice",
                    "status": "validated",
                    "sourceRef": {"sourceId": "ubm"}}),
        encoding="utf-8",
    )
    (items_dir / "parasite.json").write_text(
        json.dumps({"id": "parasite", "title": "Parasite",
                    "types": ["film"]}),
        encoding="utf-8",
    )

    monkeypatch.setattr(build_stats, "_SOURCES_DIR", sources_dir)
    monkeypatch.setattr(build_stats, "_EPISODES_DIR", tmp_path / "episodes")
    monkeypatch.setattr(build_stats, "_MENTIONS_DIR", tmp_path / "mentions")
    monkeypatch.setattr(build_stats, "_ITEMS_DIR", tmp_path / "items")
    return tmp_path


def test_run_smoke_json(fake_content, tmp_path):
    out = tmp_path / "out"
    rc = build_stats.run(
        source="all",
        output_dir=out,
        fmt="json",
        generated_at="2026-06-12T00:00:00Z",
    )
    assert rc == 0
    payload = json.loads((out / "_global" / "stats.json").read_text(encoding="utf-8"))
    assert payload["schemaVersion"] == 1
    assert payload["global"]["podcastsCount"] == 1
    assert payload["global"]["recommendationsCount"] == 1
    assert payload["global"]["uniqueWorksCount"] == 1
    assert payload["topGuests"][0]["name"] == "Alice"
    assert payload["typeDistribution"] == {"film": 1}


def test_run_single_source_filtered(fake_content, tmp_path):
    out = tmp_path / "out"
    rc = build_stats.run(
        source="ubm",
        output_dir=out,
        fmt="json",
        generated_at="2026-06-12T00:00:00Z",
    )
    assert rc == 0
    payload = json.loads((out / "ubm" / "stats.json").read_text(encoding="utf-8"))
    assert payload["global"]["podcastsCount"] == 1
    assert list(payload["perSource"].keys()) == ["ubm"]


def test_run_unknown_source_returns_1(fake_content, tmp_path):
    rc = build_stats.run(
        source="inexistante",
        output_dir=tmp_path / "out",
        fmt="json",
        generated_at="x",
    )
    assert rc == 1


def test_run_csv_format(fake_content, tmp_path):
    out = tmp_path / "out"
    rc = build_stats.run(
        source="all",
        output_dir=out,
        fmt="csv",
        generated_at="2026-06-12T00:00:00Z",
    )
    assert rc == 0
    rows = list(csv.reader((out / "_global" / "stats.csv").open(encoding="utf-8")))
    header = rows[0]
    assert header == ["section", "key", "value"]
    # Au moins une ligne 'global'
    assert any(r[0] == "global" for r in rows[1:])


def test_run_handles_empty_collections(tmp_path, monkeypatch):
    empty = tmp_path / "empty"
    empty.mkdir()
    monkeypatch.setattr(build_stats, "_SOURCES_DIR", empty)
    monkeypatch.setattr(build_stats, "_EPISODES_DIR", empty)
    monkeypatch.setattr(build_stats, "_MENTIONS_DIR", empty)
    monkeypatch.setattr(build_stats, "_ITEMS_DIR", empty)
    out = tmp_path / "out"
    rc = build_stats.run(source="all", output_dir=out, fmt="json", generated_at="x")
    assert rc == 0
    payload = json.loads((out / "_global" / "stats.json").read_text(encoding="utf-8"))
    assert payload["global"]["podcastsCount"] == 0


def test_main_cli_parses_args(fake_content, tmp_path, monkeypatch):
    """Smoke complet de `main()` avec lock pipeline réel (non concurrent)."""
    out = tmp_path / "out"
    rc = build_stats.main([
        "--source", "all",
        "--output-dir", str(out),
        "--format", "json",
        "--generated-at", "2026-06-12T00:00:00Z",
    ])
    assert rc == 0
    assert (out / "_global" / "stats.json").exists()


def test_main_propagates_server_lock_busy(fake_content, tmp_path, monkeypatch):
    """Si le verrou pipeline est déjà tenu, `main()` retourne 1 proprement."""
    from contextlib import contextmanager
    from review_lock import ServerLockBusy

    @contextmanager
    def _busy(*, force=False):  # noqa: ARG001
        raise ServerLockBusy("Verrou déjà tenu")
        yield  # pragma: no cover

    monkeypatch.setattr(build_stats, "acquire_pipeline_lock", _busy)
    rc = build_stats.main([
        "--source", "all",
        "--output-dir", str(tmp_path / "out"),
    ])
    assert rc == 1


def test_read_json_dir_skips_invalid_files(tmp_path):
    d = tmp_path / "x"
    d.mkdir()
    (d / "ok.json").write_text(json.dumps({"id": "ok"}), encoding="utf-8")
    (d / "broken.json").write_text("{ not json", encoding="utf-8")
    out = build_stats._read_json_dir(d)
    assert [r["id"] for r in out] == ["ok"]


def test_coerce_episodes_accepts_object_sourceid():
    raw = [{"sourceId": {"id": "ubm", "collection": "sources"}, "date": "x"}]
    coerced = build_stats._coerce_episodes(raw)
    assert coerced[0]["sourceId"] == "ubm"


def test_read_json_dir_skips_legacy_and_archived(tmp_path):
    """M26-24 : `_legacy/` et `.archived/` sont exclus comme la fixture."""
    d = tmp_path / "x"
    (d / "kept").mkdir(parents=True)
    (d / "_legacy").mkdir()
    (d / ".archived").mkdir()
    (d / "kept" / "ok.json").write_text(json.dumps({"id": "ok"}), encoding="utf-8")
    (d / "_legacy" / "old.json").write_text(json.dumps({"id": "old"}), encoding="utf-8")
    (d / ".archived" / "v0.json").write_text(json.dumps({"id": "v0"}), encoding="utf-8")
    out = build_stats._read_json_dir(d)
    ids = sorted(r["id"] for r in out)
    assert ids == ["ok"]


def test_run_rejects_path_traversal_source(fake_content, tmp_path):
    """M26-23 : un `source` avec un séparateur de chemin ne doit pas créer un
    dossier hors `output_dir`."""
    out = tmp_path / "out"
    rc = build_stats.run(
        source="../evil",
        output_dir=out,
        fmt="json",
        generated_at="x",
    )
    assert rc == 1


def test_read_json_dir_returns_empty_when_missing(tmp_path):
    """Couvre `if not base.exists(): return out`."""
    out = build_stats._read_json_dir(tmp_path / "ghost")
    assert out == []


def test_run_rejects_source_with_dot(fake_content, tmp_path):
    """`source` ne doit pas commencer par `.` (dossier caché)."""
    out = tmp_path / "out"
    rc = build_stats.run(
        source=".hidden",
        output_dir=out,
        fmt="json",
        generated_at="x",
    )
    assert rc == 1


def test_main_returns_2_on_unexpected_exception(fake_content, tmp_path, monkeypatch):
    """M26-22 : exception non rattrapée → exit code 2 (vs 1 = fonctionnel)."""
    def _boom(**_kwargs):
        raise RuntimeError("boom inattendu")

    monkeypatch.setattr(build_stats, "run", _boom)
    rc = build_stats.main([
        "--source", "all",
        "--output-dir", str(tmp_path / "out"),
        "--generated-at", "x",
    ])
    assert rc == 2
