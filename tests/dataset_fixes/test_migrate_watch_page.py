"""Tests de `tools/migrate_watch_page.py` — `justwatch` → `watchPage`.

Invariant : ce correctif répare un NOM. Aucune valeur n'est réécrite — si
une URL est mauvaise, elle le reste, et c'est délibéré : mélanger les deux
rendrait le diff illisible et la décision non révisable.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import common
import dataset_fixes as df
import migrate_watch_page as mwp


@pytest.fixture
def content_roots(tmp_path: Path, monkeypatch) -> tuple[Path, Path]:
    """Redirige les DEUX collections (recos + items) vers tmp."""
    recos = tmp_path / "src" / "content" / "recos"
    items = tmp_path / "src" / "content" / "items"
    recos.mkdir(parents=True)
    items.mkdir(parents=True)
    monkeypatch.setattr(common, "RECOS_DIR", recos)
    monkeypatch.setattr(df, "RECOS_DIR", recos)
    monkeypatch.setattr(mwp, "MIGRATION_ROOTS", (recos, items))
    return recos, items


def _write(path: Path, data: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                    encoding="utf-8")
    return path


# ===== _rename_key =========================================================
def test_rename_key_moves_value_untouched():
    container = {"justwatch": "https://x"}
    changes = mwp._rename_key(container, "justwatch", "watchPage", "externalIds", "a")
    assert container == {"watchPage": "https://x"}
    assert changes[0].before == changes[0].after == "https://x"
    assert changes[0].field == "externalIds.justwatch → externalIds.watchPage"


def test_rename_key_noop_when_old_absent():
    container = {"tmdb": "1"}
    assert mwp._rename_key(container, "justwatch", "watchPage", "externalIds", "a") == []
    assert container == {"tmdb": "1"}


def test_rename_key_refuses_to_overwrite_existing_target(caplog):
    container = {"justwatch": "ancien", "watchPage": "déjà là"}
    with caplog.at_level("WARNING"):
        assert mwp._rename_key(container, "justwatch", "watchPage", "externalIds", "ubm-1") == []
    assert container == {"justwatch": "ancien", "watchPage": "déjà là"}
    assert "laissée intacte" in caplog.text


# ===== transform ===========================================================
def test_transform_renames_external_id():
    doc = {"id": "a", "externalIds": {"tmdb": "1", "justwatch": "https://tmdb/x"}}
    changes = mwp.transform(doc)
    assert doc["externalIds"] == {"tmdb": "1", "watchPage": "https://tmdb/x"}
    assert len(changes) == 1


def test_transform_renames_link_override_label():
    """Sans ça, l'override deviendrait orphelin quand le libellé change."""
    doc = {"id": "a", "linkOverrides": {"JustWatch": "https://jw/x", "YouTube": "https://y"}}
    changes = mwp.transform(doc)
    assert doc["linkOverrides"] == {"YouTube": "https://y", "Où regarder": "https://jw/x"}
    assert changes[0].field == "linkOverrides.JustWatch → linkOverrides.Où regarder"


def test_transform_handles_both_at_once():
    doc = {"id": "a", "externalIds": {"justwatch": "u"}, "linkOverrides": {"JustWatch": "v"}}
    assert len(mwp.transform(doc)) == 2


def test_transform_noop_on_clean_document():
    doc = {"id": "a", "externalIds": {"tmdb": "1"}, "linkOverrides": {"YouTube": "y"}}
    assert mwp.transform(doc) == []


def test_transform_tolerates_missing_or_non_dict_containers():
    for doc in ({"id": "a"}, {"id": "b", "externalIds": None},
                {"id": "c", "externalIds": "x", "linkOverrides": 7}):
        assert mwp.transform(doc) == []


def test_transform_preserves_a_non_url_value():
    """La fixture cross-stack porte la valeur littérale « jw »."""
    doc = {"id": "fixture0", "externalIds": {"justwatch": "jw"}}
    mwp.transform(doc)
    assert doc["externalIds"]["watchPage"] == "jw"


# ===== host_census =========================================================
def test_host_census_counts_hosts_and_non_urls():
    fake = [
        df.FileResult(path=Path("a"), reco_id="a", data={}, changes=[
            df.Change(field="f", before="https://www.themoviedb.org/movie/1/watch",
                      after="https://www.themoviedb.org/movie/1/watch"),
            df.Change(field="f", before="jw", after="jw"),
        ]),
        df.FileResult(path=Path("b"), reco_id="b", data={}, changes=[
            df.Change(field="f", before=None, after=None),
        ]),
    ]
    census = mwp.host_census(fake)["hotes_des_valeurs"]
    assert census["www.themoviedb.org"] == 1
    assert census["(valeur non-URL)"] == 2


def test_host_census_on_empty_results():
    assert mwp.host_census([]) == {"hotes_des_valeurs": {}}


# ===== CLI =================================================================
def test_main_migrates_both_collections(content_roots: tuple[Path, Path], tmp_path: Path):
    recos, items = content_roots
    reco = _write(recos / "s" / "a.json", {"id": "a", "externalIds": {"justwatch": "https://t/x"}})
    item = _write(items / "s" / "b.json", {"id": "b", "externalIds": {"justwatch": "https://t/y"}})
    report = tmp_path / "r.json"
    assert mwp.main(["--apply", "--json", str(report)]) == 0
    assert json.loads(reco.read_text("utf-8"))["externalIds"] == {"watchPage": "https://t/x"}
    assert json.loads(item.read_text("utf-8"))["externalIds"] == {"watchPage": "https://t/y"}
    data = json.loads(report.read_text(encoding="utf-8"))
    assert data["files"] == 2
    assert data["hotes_des_valeurs"] == {"t": 2}


def test_main_dry_run_leaves_files_untouched(content_roots: tuple[Path, Path]):
    recos, _ = content_roots
    path = _write(recos / "s" / "a.json", {"id": "a", "externalIds": {"justwatch": "u"}})
    before = path.read_text(encoding="utf-8")
    assert mwp.main([]) == 0
    assert path.read_text(encoding="utf-8") == before


def test_main_apply_only_renames_the_key(content_roots: tuple[Path, Path]):
    """Le diff se réduit à la clé : la valeur et les autres champs bougent pas."""
    recos, _ = content_roots
    path = _write(recos / "s" / "a.json", {
        "id": "a", "title": "Mortel",
        "externalIds": {"justwatch": "https://www.themoviedb.org/tv/94801/watch", "tmdb": "94801"},
    })
    before = json.loads(path.read_text(encoding="utf-8"))
    assert mwp.main(["--apply"]) == 0
    after = json.loads(path.read_text(encoding="utf-8"))
    assert after["externalIds"].pop("watchPage") == before["externalIds"].pop("justwatch")
    assert after == before


def test_build_parser_defaults_to_dry_run():
    assert mwp.build_parser().parse_args([]).apply is False
