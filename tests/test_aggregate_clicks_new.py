"""Tests Phase-4 fixer pour `tools/aggregate_clicks.py`.

Couvre :
- B-HIGH-2 — validation schéma event JSONL.
- B-HIGH-3 — validation `--source` slug.
- B-MED-2 — atomic write via `atomic_write_text`.
- B-MED-3 — lockfile.
- B-MED-4 — exit codes 0/1/2.
- B-MED-5 — from_date > to_date → exit 1.
- B-MED-17 — drop threshold.
- B-LOW-14 — bucket "" skipped pour --by source.
- B-NIT-8 — constante OTHER_CATEGORY.
"""
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
    from contextlib import nullcontext
    monkeypatch.setattr(
        aggregate_clicks, "acquire_pipeline_lock",
        lambda force=False: nullcontext(),
    )


def _ev(**over) -> dict:
    base = {
        "ts": "2026-06-12T10:00:00.000Z",
        "category": "tmdb",
        "sourceId": "src",
        "url": "https://x.example",
        "recoId": "r1",
        "ref": "/x",
    }
    base.update(over)
    return base


def _write_jsonl(path: Path, events: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for ev in events:
            fh.write(json.dumps(ev) + "\n")


# --- B-HIGH-2 — validation schéma -----------------------------------------


def test_validate_event_minimal_ok() -> None:
    out = aggregate_clicks._validate_event(_ev())
    assert out is not None and out.category == "tmdb"


def test_validate_event_missing_ts() -> None:
    bad = _ev()
    del bad["ts"]
    assert aggregate_clicks._validate_event(bad) is None


def test_validate_event_empty_category() -> None:
    bad = _ev(category="")
    assert aggregate_clicks._validate_event(bad) is None


def test_validate_event_wrong_type_url() -> None:
    bad = _ev(url=42)
    assert aggregate_clicks._validate_event(bad) is None


def test_validate_event_not_dict() -> None:
    assert aggregate_clicks._validate_event("nope") is None
    assert aggregate_clicks._validate_event(None) is None


def test_validate_event_none_optional_ok() -> None:
    """`url`/`recoId` à None est normalisé en chaîne vide."""
    ev = _ev()
    ev["url"] = None
    ev["recoId"] = None
    ev["ref"] = None
    out = aggregate_clicks._validate_event(ev)
    assert out is not None
    assert out.url == "" and out.recoId == "" and out.ref == ""


def test_iter_events_drops_invalid_schema(tmp_path: Path) -> None:
    root = tmp_path / "clicks"
    # 1 OK + 1 schéma invalide (sourceId absent) + 1 JSON invalide
    target = root / "src" / "2026-06-12.jsonl"
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8") as fh:
        fh.write(json.dumps(_ev(sourceId="src")) + "\n")
        fh.write(json.dumps({"ts": "x", "category": "y"}) + "\n")
        fh.write("not-json\n")
    from collections import Counter

    drops: Counter[str] = Counter()
    events = list(
        aggregate_clicks.iter_events(
            source="src", from_date=None, to_date=None,
            root=root, drop_counter=drops,
        ),
    )
    assert len(events) == 1
    assert drops["schema"] == 1
    assert drops["json"] == 1


# --- B-HIGH-3 — slug source ------------------------------------------------


def test_main_invalid_source_slug() -> None:
    rc = aggregate_clicks.main(["--source", "../etc/passwd"])
    assert rc == aggregate_clicks.EXIT_USAGE


def test_main_invalid_source_uppercase() -> None:
    rc = aggregate_clicks.main(["--source", "ABC"])
    assert rc == aggregate_clicks.EXIT_USAGE


def test_main_invalid_source_too_long() -> None:
    rc = aggregate_clicks.main(["--source", "a" * 129])
    assert rc == aggregate_clicks.EXIT_USAGE


def test_main_valid_source_slug(tmp_path: Path) -> None:
    rc = aggregate_clicks.main(
        ["--source", "un-bon-moment", "--root", str(tmp_path)],
    )
    assert rc == 0


def test_validate_source_arg_all() -> None:
    assert aggregate_clicks._validate_source_arg("all") is True


# --- B-MED-5 — plage de dates inversée -------------------------------------


def test_main_dates_inverted(tmp_path: Path) -> None:
    rc = aggregate_clicks.main(
        ["--from-date", "2026-06-15", "--to-date", "2026-06-10",
         "--root", str(tmp_path)],
    )
    assert rc == aggregate_clicks.EXIT_FUNCTIONAL


# --- B-MED-17 — drop threshold ---------------------------------------------


def test_main_drop_threshold_exit_1(tmp_path: Path) -> None:
    root = tmp_path / "clicks"
    target = root / "src" / "2026-06-12.jsonl"
    target.parent.mkdir(parents=True, exist_ok=True)
    # 5 events corrompus → seuil 2 dépassé
    with target.open("w", encoding="utf-8") as fh:
        for _ in range(5):
            fh.write("nope\n")
    rc = aggregate_clicks.main(
        ["--source", "src", "--root", str(root), "--drop-threshold", "2"],
    )
    assert rc == aggregate_clicks.EXIT_FUNCTIONAL


def test_main_drops_under_threshold_ok(tmp_path: Path) -> None:
    root = tmp_path / "clicks"
    target = root / "src" / "2026-06-12.jsonl"
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8") as fh:
        fh.write("nope\n")
        fh.write(json.dumps(_ev(sourceId="src")) + "\n")
    rc = aggregate_clicks.main(
        ["--source", "src", "--root", str(root), "--drop-threshold", "5"],
    )
    assert rc == 0


# --- B-LOW-14 — bucket "" pour --by source ---------------------------------


def test_aggregate_by_source_skips_empty_bucket() -> None:
    """B-LOW-14 — un event sans sourceId ne crée pas un bucket ''."""
    events = [_ev(), {"category": "x"}]  # 2e event invalide, mais aggregate()
    # ne valide pas — on simule un event sans sourceId.
    bad = {"ts": "x", "category": "x"}
    out = aggregate_clicks.aggregate(iter([_ev(), bad]), by="source")
    keys = [c["key"] for c in out["counts"]]
    assert "" not in keys


# --- B-MED-3 — lock conflict -----------------------------------------------


def test_main_server_lock_busy(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from review_lock import ServerLockBusy  # type: ignore

    def boom(force: bool = False):
        raise ServerLockBusy("server tourne")

    monkeypatch.setattr(aggregate_clicks, "acquire_pipeline_lock", boom)
    rc = aggregate_clicks.main(["--root", str(tmp_path)])
    assert rc == aggregate_clicks.EXIT_FUNCTIONAL


# --- B-NIT-8 — constante ---------------------------------------------------


def test_other_category_constant() -> None:
    assert aggregate_clicks.OTHER_CATEGORY == "other"


# --- atomic write ----------------------------------------------------------


def test_write_output_csv_atomic(tmp_path: Path) -> None:
    """B-MED-2 — le fichier final ne contient pas de `.tmp`."""
    data = {
        "by": "category", "total_clicks": 1,
        "counts": [{"key": "tmdb", "count": 1}],
        "by_category": {"tmdb": 1},
    }
    out = tmp_path / "x.csv"
    aggregate_clicks.write_output(data, out)
    assert out.exists()
    assert not (tmp_path / "x.csv.tmp").exists()
