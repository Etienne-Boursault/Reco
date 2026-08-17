"""Tests du socle commun aux correctifs de données (`tools/dataset_fixes.py`).

Le point le plus important couvert ici : `--dry-run` est le défaut. Un
correctif qui écrit sans `--apply` serait un bug, pas une commodité.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pytest

import common
import dataset_fixes as df


# ===== Fixtures ============================================================
@pytest.fixture
def recos_root(tmp_path: Path, monkeypatch) -> Path:
    """Redirige `RECOS_DIR` (module + common) vers un dossier temporaire."""
    root = tmp_path / "src" / "content" / "recos"
    root.mkdir(parents=True)
    monkeypatch.setattr(common, "RECOS_DIR", root)
    monkeypatch.setattr(df, "RECOS_DIR", root)
    return root


def _write(path: Path, data: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                    encoding="utf-8")
    return path


def _args(**kw) -> argparse.Namespace:
    base = {"source": None, "apply": False, "dry_run": False,
            "exclude_ids": None, "json_path": None}
    base.update(kw)
    return argparse.Namespace(**base)


def _upper_title(reco: dict) -> list[df.Change]:
    """Transformation d'essai : met le titre en capitales."""
    title = reco.get("title")
    if not isinstance(title, str) or title.isupper():
        return []
    reco["title"] = title.upper()
    return [df.Change(field="title", before=title, after=title.upper())]


# ===== parse_exclude_ids ===================================================
def test_parse_exclude_ids_none_and_empty():
    assert df.parse_exclude_ids(None) == set()
    assert df.parse_exclude_ids("") == set()


def test_parse_exclude_ids_csv_trims_and_drops_blanks():
    assert df.parse_exclude_ids(" a , b ,, c ") == {"a", "b", "c"}


def test_parse_exclude_ids_from_file_ignores_comments(tmp_path: Path):
    f = tmp_path / "excl.txt"
    f.write_text("# entête\nubm-1\n\n  ubm-2  \n# fin\n", encoding="utf-8")
    assert df.parse_exclude_ids(f"@{f}") == {"ubm-1", "ubm-2"}


# ===== iter_reco_files =====================================================
def test_iter_reco_files_sorted_and_recursive(recos_root: Path):
    _write(recos_root / "s" / "b.json", {"id": "b"})
    _write(recos_root / "s" / "a.json", {"id": "a"})
    assert [p.name for p in df.iter_reco_files()] == ["a.json", "b.json"]


def test_iter_reco_files_scoped_to_one_source(recos_root: Path):
    _write(recos_root / "s1" / "a.json", {"id": "a"})
    _write(recos_root / "s2" / "b.json", {"id": "b"})
    assert [p.name for p in df.iter_reco_files("s1")] == ["a.json"]


def test_iter_reco_files_warns_on_missing_dir(recos_root: Path, caplog):
    with caplog.at_level("WARNING"):
        assert list(df.iter_reco_files("absente")) == []
    assert "Dossier de contenu absent" in caplog.text


def test_iter_reco_files_walks_several_roots(tmp_path: Path):
    """Le correctif `watchPage` passe deux racines : recos ET items."""
    r1, r2 = tmp_path / "recos", tmp_path / "items"
    _write(r1 / "a.json", {"id": "a"})
    _write(r2 / "b.json", {"id": "b"})
    assert [p.name for p in df.iter_reco_files(roots=(r1, r2))] == ["a.json", "b.json"]


# ===== collect =============================================================
def test_collect_returns_only_changed_files(recos_root: Path):
    _write(recos_root / "s" / "a.json", {"id": "a", "title": "bas"})
    _write(recos_root / "s" / "b.json", {"id": "b", "title": "HAUT"})
    results = df.collect(_upper_title)
    assert [r.reco_id for r in results] == ["a"]
    assert results[0].data["title"] == "BAS"
    assert results[0].changes == [df.Change(field="title", before="bas", after="BAS")]


def test_collect_skips_excluded_ids(recos_root: Path):
    _write(recos_root / "s" / "a.json", {"id": "a", "title": "x"})
    assert df.collect(_upper_title, exclude_ids={"a"}) == []


def test_collect_skips_unreadable_file(recos_root: Path, caplog):
    (recos_root / "s").mkdir(parents=True)
    (recos_root / "s" / "cassé.json").write_text("{pas du json", encoding="utf-8")
    with caplog.at_level("WARNING"):
        assert df.collect(_upper_title) == []
    assert "lecture impossible" in caplog.text


def test_collect_falls_back_to_filename_when_id_missing(recos_root: Path):
    _write(recos_root / "s" / "sans-id.json", {"title": "x"})
    assert df.collect(_upper_title)[0].reco_id == "sans-id"


# ===== apply_results / rapport ============================================
def test_apply_results_writes_and_counts(recos_root: Path):
    path = _write(recos_root / "s" / "a.json", {"id": "a", "title": "bas"})
    results = df.collect(_upper_title)
    assert df.apply_results(results) == 1
    assert json.loads(path.read_text(encoding="utf-8"))["title"] == "BAS"


def test_apply_results_returns_zero_when_content_identical(recos_root: Path):
    """`write_json_if_changed` est idempotent : rien à réécrire, 0 écriture."""
    path = _write(recos_root / "s" / "a.json", {"id": "a", "title": "bas"})
    results = df.collect(_upper_title)
    df.apply_results(results)
    stale = [df.FileResult(path=path, reco_id="a",
                           data=json.loads(path.read_text(encoding="utf-8")))]
    assert df.apply_results(stale) == 0


def test_build_report_counts_and_merges_extra(recos_root: Path):
    _write(recos_root / "s" / "a.json", {"id": "a", "title": "bas"})
    report = df.build_report(df.collect(_upper_title), applied=True, extra={"k": "v"})
    assert report["applied"] is True
    assert report["files"] == 1 and report["changes"] == 1
    assert report["recos"][0]["changes"][0]["after"] == "BAS"
    assert report["k"] == "v"


def test_build_report_without_extra(recos_root: Path):
    assert "k" not in df.build_report([], applied=False)


def test_write_report_noop_without_path(tmp_path: Path):
    df.write_report(None, {"a": 1})
    assert list(tmp_path.iterdir()) == []


def test_write_report_creates_parent_dirs(tmp_path: Path):
    target = tmp_path / "sous" / "dossier" / "r.json"
    df.write_report(str(target), {"a": 1})
    assert json.loads(target.read_text(encoding="utf-8")) == {"a": 1}


# ===== add_common_args =====================================================
def test_add_common_args_defaults_to_dry_run():
    args = df.add_common_args(argparse.ArgumentParser()).parse_args([])
    assert args.apply is False
    assert args.source is None and args.exclude_ids is None and args.json_path is None


def test_add_common_args_accepts_apply_and_dry_run():
    parser = df.add_common_args(argparse.ArgumentParser())
    assert parser.parse_args(["--apply"]).apply is True
    assert parser.parse_args(["--dry-run"]).dry_run is True


# ===== log_summary =========================================================
def test_log_summary_truncates_and_mentions_dry_run(recos_root: Path, caplog):
    for i in range(7):
        _write(recos_root / "s" / f"{i}.json", {"id": str(i), "title": "bas"})
    with caplog.at_level("INFO"):
        df.log_summary(df.collect(_upper_title), applied=False, sample=2)
    assert "et 5 fichier(s) de plus" in caplog.text
    assert "DRY-RUN" in caplog.text


def test_log_summary_silent_about_dry_run_when_applied(caplog):
    with caplog.at_level("INFO"):
        df.log_summary([], applied=True)
    assert "DRY-RUN" not in caplog.text


# ===== run =================================================================
def test_run_dry_run_does_not_write(recos_root: Path):
    path = _write(recos_root / "s" / "a.json", {"id": "a", "title": "bas"})
    before = path.read_text(encoding="utf-8")
    results = df.run(_upper_title, _args())
    assert len(results) == 1
    assert path.read_text(encoding="utf-8") == before


def test_run_apply_writes(recos_root: Path):
    path = _write(recos_root / "s" / "a.json", {"id": "a", "title": "bas"})
    df.run(_upper_title, _args(apply=True))
    assert json.loads(path.read_text(encoding="utf-8"))["title"] == "BAS"


def test_run_honours_exclude_ids_and_source(recos_root: Path):
    _write(recos_root / "s1" / "a.json", {"id": "a", "title": "bas"})
    _write(recos_root / "s1" / "b.json", {"id": "b", "title": "bas"})
    _write(recos_root / "s2" / "c.json", {"id": "c", "title": "bas"})
    results = df.run(_upper_title, _args(source="s1", exclude_ids="a"))
    assert [r.reco_id for r in results] == ["b"]


def test_run_writes_report_with_callable_extra(recos_root: Path, tmp_path: Path):
    _write(recos_root / "s" / "a.json", {"id": "a", "title": "bas"})
    target = tmp_path / "r.json"
    df.run(_upper_title, _args(json_path=str(target)),
           extra_report=lambda results: {"n": len(results)})
    assert json.loads(target.read_text(encoding="utf-8"))["n"] == 1


def test_run_writes_report_with_dict_extra(recos_root: Path, tmp_path: Path):
    _write(recos_root / "s" / "a.json", {"id": "a", "title": "bas"})
    target = tmp_path / "r.json"
    df.run(_upper_title, _args(json_path=str(target)), extra_report={"k": "v"})
    assert json.loads(target.read_text(encoding="utf-8"))["k"] == "v"


def test_run_accepts_explicit_roots(tmp_path: Path):
    root = tmp_path / "items"
    path = _write(root / "a.json", {"id": "a", "title": "bas"})
    df.run(_upper_title, _args(apply=True), roots=(root,))
    assert json.loads(path.read_text(encoding="utf-8"))["title"] == "BAS"
