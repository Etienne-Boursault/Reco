"""tests/test_aggregate_clicks.py — Smoke + agrégation CLI clics (ADR 0046)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

TOOLS = Path(__file__).resolve().parents[1] / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import aggregate_clicks  # noqa: E402


@pytest.fixture(autouse=True)
def _patch_lock(monkeypatch: pytest.MonkeyPatch) -> None:
    """B-MED-3 — neutralise `acquire_pipeline_lock` pour les tests."""
    from contextlib import nullcontext

    monkeypatch.setattr(
        aggregate_clicks,
        "acquire_pipeline_lock",
        lambda force=False: nullcontext(),
    )


def _write_jsonl(path: Path, events: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for ev in events:
            fh.write(json.dumps(ev, ensure_ascii=False) + "\n")


def _ev(**over) -> dict:
    base = {
        "ts": "2026-06-12T10:00:00.000Z",
        "url": "https://themoviedb.org/movie/42",
        "category": "tmdb",
        "sourceId": "un-bon-moment",
        "recoId": "ubm-0001",
        "ref": "/un-bon-moment/episode/abc",
    }
    base.update(over)
    return base


def test_iter_events_filtre_par_source(tmp_path: Path) -> None:
    root = tmp_path / "clicks"
    _write_jsonl(root / "un-bon-moment" / "2026-06-12.jsonl", [_ev()])
    _write_jsonl(root / "autre" / "2026-06-12.jsonl", [_ev(sourceId="autre")])
    events = list(
        aggregate_clicks.iter_events(
            source="un-bon-moment", from_date=None, to_date=None, root=root,
        ),
    )
    assert len(events) == 1
    assert events[0]["sourceId"] == "un-bon-moment"


def test_iter_events_source_all(tmp_path: Path) -> None:
    root = tmp_path / "clicks"
    _write_jsonl(root / "un-bon-moment" / "2026-06-12.jsonl", [_ev()])
    _write_jsonl(root / "autre" / "2026-06-12.jsonl", [_ev(sourceId="autre")])
    events = list(
        aggregate_clicks.iter_events(
            source=None, from_date=None, to_date=None, root=root,
        ),
    )
    assert len(events) == 2


def test_iter_events_filtre_dates(tmp_path: Path) -> None:
    from datetime import date

    root = tmp_path / "clicks"
    _write_jsonl(root / "src" / "2026-06-10.jsonl", [_ev(sourceId="src")])
    _write_jsonl(root / "src" / "2026-06-12.jsonl", [_ev(sourceId="src")])
    _write_jsonl(root / "src" / "2026-06-15.jsonl", [_ev(sourceId="src")])
    events = list(
        aggregate_clicks.iter_events(
            source="src",
            from_date=date(2026, 6, 11),
            to_date=date(2026, 6, 13),
            root=root,
        ),
    )
    assert len(events) == 1


def test_iter_events_skip_lignes_corrompues(tmp_path: Path) -> None:
    root = tmp_path / "clicks"
    target = root / "src" / "2026-06-12.jsonl"
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8") as fh:
        fh.write(json.dumps(_ev(sourceId="src")) + "\n")
        fh.write("not-json\n")
        fh.write(json.dumps(_ev(sourceId="src", recoId="other")) + "\n")
    events = list(
        aggregate_clicks.iter_events(
            source="src", from_date=None, to_date=None, root=root,
        ),
    )
    assert len(events) == 2


def test_aggregate_by_category(tmp_path: Path) -> None:
    events = [
        _ev(category="tmdb"),
        _ev(category="tmdb"),
        _ev(category="spotify"),
    ]
    out = aggregate_clicks.aggregate(iter(events), by="category")
    assert out["total_clicks"] == 3
    assert out["counts"][0] == {"key": "tmdb", "count": 2}
    assert out["counts"][1] == {"key": "spotify", "count": 1}
    assert out["by_category"] == {"tmdb": 2, "spotify": 1}


def test_aggregate_by_reco(tmp_path: Path) -> None:
    events = [
        _ev(recoId="a"),
        _ev(recoId="a"),
        _ev(recoId="b"),
        _ev(recoId=None),
    ]
    out = aggregate_clicks.aggregate(iter(events), by="reco")
    # recoId=None est skip pour l'axe reco
    assert out["counts"] == [{"key": "a", "count": 2}, {"key": "b", "count": 1}]


def test_aggregate_by_url(tmp_path: Path) -> None:
    events = [
        _ev(url="https://a.example"),
        _ev(url="https://b.example"),
        _ev(url="https://a.example"),
    ]
    out = aggregate_clicks.aggregate(iter(events), by="url")
    assert out["counts"][0]["key"] == "https://a.example"
    assert out["counts"][0]["count"] == 2


def test_aggregate_by_source(tmp_path: Path) -> None:
    events = [_ev(sourceId="x"), _ev(sourceId="y"), _ev(sourceId="x")]
    out = aggregate_clicks.aggregate(iter(events), by="source")
    assert out["counts"][0] == {"key": "x", "count": 2}


def test_aggregate_invalid_axis_raises() -> None:
    with pytest.raises(ValueError):
        aggregate_clicks.aggregate(iter([]), by="nope")


def test_write_output_json(tmp_path: Path) -> None:
    data = {"by": "category", "total_clicks": 1, "counts": [{"key": "tmdb", "count": 1}], "by_category": {"tmdb": 1}}
    out = tmp_path / "stats.json"
    aggregate_clicks.write_output(data, out)
    loaded = json.loads(out.read_text(encoding="utf-8"))
    assert loaded == data


def test_write_output_csv(tmp_path: Path) -> None:
    data = {"by": "category", "total_clicks": 2, "counts": [{"key": "tmdb", "count": 2}], "by_category": {"tmdb": 2}}
    out = tmp_path / "stats.csv"
    aggregate_clicks.write_output(data, out)
    text = out.read_text(encoding="utf-8")
    assert "key,count" in text
    assert "tmdb,2" in text


def test_main_smoke_stdout(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = tmp_path / "clicks"
    _write_jsonl(root / "src" / "2026-06-12.jsonl", [_ev(sourceId="src"), _ev(sourceId="src", category="spotify")])
    rc = aggregate_clicks.main(
        ["--source", "src", "--by", "category", "--root", str(root)],
    )
    assert rc == 0
    out = capsys.readouterr().out
    payload = json.loads(out)
    assert payload["total_clicks"] == 2


def test_main_smoke_output_file(tmp_path: Path) -> None:
    root = tmp_path / "clicks"
    out = tmp_path / "out.json"
    _write_jsonl(root / "src" / "2026-06-12.jsonl", [_ev(sourceId="src")])
    rc = aggregate_clicks.main(
        [
            "--source", "src",
            "--by", "reco",
            "--root", str(root),
            "--output", str(out),
        ],
    )
    assert rc == 0
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["total_clicks"] == 1


def test_main_invalid_date(tmp_path: Path) -> None:
    rc = aggregate_clicks.main(["--from-date", "not-a-date", "--root", str(tmp_path)])
    assert rc == 2


def test_aggregate_by_url_skip_url_absente(tmp_path: Path) -> None:
    """M25-25 — un event sans `url` est skip silencieusement (axe url)."""
    events = [
        _ev(url="https://a.example"),
        {"ts": "2026-06-12T10:00:00.000Z", "category": "tmdb", "sourceId": "src"},
        _ev(url=""),
    ]
    out = aggregate_clicks.aggregate(iter(events), by="url")
    # 3 events comptés total, mais axe url : seul `a.example` est compté.
    assert out["total_clicks"] == 3
    assert out["counts"] == [{"key": "https://a.example", "count": 1}]


def test_write_output_csv_include_dimension(tmp_path: Path) -> None:
    """M25-24 — colonne `by` dans le CSV."""
    data = {
        "by": "category",
        "total_clicks": 2,
        "counts": [{"key": "tmdb", "count": 2}],
        "by_category": {"tmdb": 2},
    }
    out = tmp_path / "stats.csv"
    aggregate_clicks.write_output(data, out, csv_include_dimension=True)
    text = out.read_text(encoding="utf-8")
    assert text.startswith("by,key,count")
    assert "category,tmdb,2" in text


def test_main_csv_include_dimension_flag(tmp_path: Path) -> None:
    root = tmp_path / "clicks"
    out = tmp_path / "out.csv"
    _write_jsonl(root / "src" / "2026-06-12.jsonl", [_ev(sourceId="src")])
    rc = aggregate_clicks.main(
        [
            "--source", "src",
            "--by", "category",
            "--root", str(root),
            "--output", str(out),
            "--csv-include-dimension",
        ],
    )
    assert rc == 0
    assert out.read_text(encoding="utf-8").startswith("by,key,count")


def test_iter_events_source_dir_absent(tmp_path: Path) -> None:
    """Source explicite mais dossier inexistant → silencieux."""
    root = tmp_path / "clicks"
    root.mkdir()
    events = list(
        aggregate_clicks.iter_events(
            source="ghost", from_date=None, to_date=None, root=root,
        ),
    )
    assert events == []


def test_date_from_filename_edge_cases() -> None:
    """Couvre les chemins skip de `_date_from_filename`."""
    assert aggregate_clicks._date_from_filename("foo.txt") is None
    assert aggregate_clicks._date_from_filename("nope.jsonl") is None


def test_iter_events_skip_non_dir_and_blank_lines(tmp_path: Path) -> None:
    """Couvre `continue` sur non-dir et lignes vides."""
    root = tmp_path / "clicks"
    root.mkdir()
    # Fichier (non-dir) dans root → skip
    (root / "not-a-dir.txt").write_text("noise", encoding="utf-8")
    # Source légitime + ligne vide + filename non-date
    src = root / "src"
    src.mkdir()
    (src / "weird-name.jsonl").write_text("", encoding="utf-8")
    target = src / "2026-06-12.jsonl"
    target.write_text("\n" + json.dumps(_ev(sourceId="src")) + "\n", encoding="utf-8")
    events = list(
        aggregate_clicks.iter_events(
            source=None, from_date=None, to_date=None, root=root,
        ),
    )
    assert len(events) == 1


def test_iter_events_empty_root(tmp_path: Path) -> None:
    events = list(
        aggregate_clicks.iter_events(
            source=None, from_date=None, to_date=None, root=tmp_path / "absent",
        ),
    )
    assert events == []
