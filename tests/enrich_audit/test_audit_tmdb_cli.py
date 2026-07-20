"""Tests : tools/audit_tmdb.py (CLI)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import audit_tmdb
from domain.item import ExternalIds, Item, ItemType
from enrich_audit.flag_writer import write_sidecar
from enrich_audit.service import AuditResult
from repository.item_repo import ItemRepoJson


def _write_items(items_dir: Path, source: str, items: list[Item]) -> None:
    repo = ItemRepoJson(items_dir, source)
    for it in items:
        repo.upsert(it)


def _write_tmdb_cache(cache_dir: Path, payloads: dict[int, dict]) -> None:
    cache_dir.mkdir(parents=True, exist_ok=True)
    for tmdb_id, payload in payloads.items():
        (cache_dir / f"{tmdb_id}.json").write_text(
            json.dumps(payload, ensure_ascii=False), encoding="utf-8"
        )


@pytest.fixture
def isolated_dirs(tmp_path: Path):
    items = tmp_path / "items"
    cache = tmp_path / "cache"
    sidecar = tmp_path / "sidecar"
    return items, cache, sidecar


def _parse(*argv: str):
    return audit_tmdb.build_parser().parse_args(list(argv))


# ===== parser ==============================================================


def test_cli_parser_requires_source():
    parser = audit_tmdb.build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args([])


def test_cli_parser_apply_flag():
    args = _parse("--source", "ubm", "--apply")
    assert args.apply is True


def test_cli_parser_default_is_dry_run():
    """CR senior C1 : sans `--apply`, dry-run par défaut (calculé)."""
    args = _parse("--source", "ubm")
    assert args.apply is False


def test_cli_parser_thresholds_flags():
    """CR senior H4 : seuils injectables."""
    args = _parse(
        "--source", "ubm",
        "--title-threshold", "0.85",
        "--year-tolerance", "3",
        "--film-min-runtime", "30",
    )
    assert args.title_threshold == 0.85
    assert args.year_tolerance == 3
    assert args.film_min_runtime == 30


def test_cli_parser_fail_on_suspect_flag():
    args = _parse("--source", "ubm", "--fail-on-suspect")
    assert args.fail_on_suspect is True


def test_cli_parser_undo_last_flag():
    args = _parse("--source", "ubm", "--undo-last")
    assert args.undo_last is True


# ===== run() ===============================================================


def test_cli_dry_run_does_not_write_sidecars(isolated_dirs, capsys):
    items_dir, cache_dir, sidecar_dir = isolated_dirs
    _write_items(items_dir, "src", [
        Item(id="aaaaaaaa", types=(ItemType.FILM,), title="Inception",
             external_ids=ExternalIds(tmdb=1, tmdb_type="movie")),
    ])
    _write_tmdb_cache(cache_dir, {1: {"original_title": "Inception"}})
    args = _parse(
        "--source", "src",
        "--items-dir", str(items_dir),
        "--tmdb-cache-dir", str(cache_dir),
        "--sidecar-dir", str(sidecar_dir),
        "--report", "none",
        "--no-jsonl-log",
    )
    rc = audit_tmdb.run(args)
    assert rc == 0
    assert not sidecar_dir.exists() or not list((sidecar_dir / "src").glob("*.json"))


def test_cli_apply_writes_sidecars(isolated_dirs, capsys):
    items_dir, cache_dir, sidecar_dir = isolated_dirs
    _write_items(items_dir, "src", [
        Item(id="bbbbbbbb", types=(ItemType.FILM,), title="Inception", year=2010,
             external_ids=ExternalIds(tmdb=2, tmdb_type="movie")),
    ])
    _write_tmdb_cache(cache_dir, {
        2: {"original_title": "The Godfather", "release_date": "1972-03-24"},
    })
    args = _parse(
        "--source", "src",
        "--apply",
        "--items-dir", str(items_dir),
        "--tmdb-cache-dir", str(cache_dir),
        "--sidecar-dir", str(sidecar_dir),
        "--report", "none",
        "--no-jsonl-log",
    )
    rc = audit_tmdb.run(args)
    assert rc == 0
    sidecar = sidecar_dir / "src" / "bbbbbbbb.json"
    assert sidecar.exists()
    raw = json.loads(sidecar.read_text(encoding="utf-8"))
    assert raw["enrichmentSuspect"] is True


def test_cli_markdown_report_to_stdout(isolated_dirs, capsys):
    items_dir, cache_dir, sidecar_dir = isolated_dirs
    _write_items(items_dir, "src", [
        Item(id="cccccccc", types=(ItemType.FILM,), title="Inception",
             external_ids=ExternalIds(tmdb=3, tmdb_type="movie")),
    ])
    _write_tmdb_cache(cache_dir, {3: {"original_title": "Inception"}})
    args = _parse(
        "--source", "src",
        "--items-dir", str(items_dir),
        "--tmdb-cache-dir", str(cache_dir),
        "--sidecar-dir", str(sidecar_dir),
        "--report", "markdown",
        "--no-jsonl-log",
    )
    audit_tmdb.run(args)
    out = capsys.readouterr().out
    assert "Audit TMDB" in out
    assert "Aucun item suspect" in out


def test_cli_json_report_to_stdout(isolated_dirs, capsys):
    items_dir, cache_dir, sidecar_dir = isolated_dirs
    _write_items(items_dir, "src", [
        Item(id="dddddddd", types=(ItemType.FILM,), title="Inception",
             external_ids=ExternalIds(tmdb=4, tmdb_type="movie")),
    ])
    _write_tmdb_cache(cache_dir, {4: {"original_title": "Inception"}})
    args = _parse(
        "--source", "src",
        "--items-dir", str(items_dir),
        "--tmdb-cache-dir", str(cache_dir),
        "--sidecar-dir", str(sidecar_dir),
        "--report", "json",
        "--no-jsonl-log",
    )
    audit_tmdb.run(args)
    out = capsys.readouterr().out
    parsed = json.loads(out)
    assert parsed["sourceId"] == "src"
    assert parsed["audited"] == 1


def test_cli_empty_source_warns_but_succeeds(isolated_dirs):
    items_dir, cache_dir, sidecar_dir = isolated_dirs
    args = _parse(
        "--source", "ghost",
        "--items-dir", str(items_dir),
        "--tmdb-cache-dir", str(cache_dir),
        "--sidecar-dir", str(sidecar_dir),
        "--report", "none",
        "--no-jsonl-log",
    )
    rc = audit_tmdb.run(args)
    assert rc == 0


def test_cli_skips_items_without_tmdb_cache(isolated_dirs, capsys):
    items_dir, cache_dir, sidecar_dir = isolated_dirs
    _write_items(items_dir, "src", [
        Item(id="eeeeeeee", types=(ItemType.FILM,), title="Inception",
             external_ids=ExternalIds(tmdb=999, tmdb_type="movie")),
    ])
    args = _parse(
        "--source", "src",
        "--items-dir", str(items_dir),
        "--tmdb-cache-dir", str(cache_dir),
        "--sidecar-dir", str(sidecar_dir),
        "--report", "json",
        "--no-jsonl-log",
    )
    audit_tmdb.run(args)
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["skippedNoCache"] == 1
    assert parsed["audited"] == 0


def test_cli_fail_on_suspect_returns_code_2(isolated_dirs):
    """CR senior M9 : exit 2 si --fail-on-suspect et suspect détecté."""
    items_dir, cache_dir, sidecar_dir = isolated_dirs
    _write_items(items_dir, "src", [
        Item(id="bbbbbbbb", types=(ItemType.FILM,), title="Inception", year=2010,
             external_ids=ExternalIds(tmdb=2, tmdb_type="movie")),
    ])
    _write_tmdb_cache(cache_dir, {
        2: {"original_title": "The Godfather", "release_date": "1972-03-24"},
    })
    args = _parse(
        "--source", "src",
        "--items-dir", str(items_dir),
        "--tmdb-cache-dir", str(cache_dir),
        "--sidecar-dir", str(sidecar_dir),
        "--report", "none",
        "--fail-on-suspect",
        "--no-jsonl-log",
    )
    rc = audit_tmdb.run(args)
    assert rc == 2


def test_cli_undo_last_restores_archive(isolated_dirs):
    items_dir, cache_dir, sidecar_dir = isolated_dirs
    sidecar_dir.mkdir(parents=True, exist_ok=True)
    # Setup: un sidecar archivé.
    r = AuditResult(item_id="aaaaaaaa", is_suspect=False, suspicions=())
    write_sidecar(r, "src", base_dir=sidecar_dir, audited_at="2026-06-10T12:00:00Z")
    from enrich_audit.flag_writer import clear_source
    clear_source("src", base_dir=sidecar_dir,
                archive_timestamp="20260610T120000Z")

    args = _parse(
        "--source", "src",
        "--items-dir", str(items_dir),
        "--tmdb-cache-dir", str(cache_dir),
        "--sidecar-dir", str(sidecar_dir),
        "--undo-last",
    )
    rc = audit_tmdb.run(args)
    assert rc == 0
    assert (sidecar_dir / "src" / "aaaaaaaa.json").exists()


def test_cli_undo_last_returns_error_if_no_archive(isolated_dirs):
    items_dir, cache_dir, sidecar_dir = isolated_dirs
    args = _parse(
        "--source", "ghost",
        "--items-dir", str(items_dir),
        "--tmdb-cache-dir", str(cache_dir),
        "--sidecar-dir", str(sidecar_dir),
        "--undo-last",
    )
    rc = audit_tmdb.run(args)
    assert rc == 1


def test_cli_main_lock_failure_returns_1(monkeypatch, isolated_dirs):
    items_dir, cache_dir, sidecar_dir = isolated_dirs
    from review_lock import ServerLockBusy

    class _BoomCtx:
        def __enter__(self):
            raise ServerLockBusy("review_server tient le verrou")

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(audit_tmdb, "acquire_pipeline_lock",
                        lambda force=False: _BoomCtx())
    rc = audit_tmdb.main([
        "--source", "src",
        "--items-dir", str(items_dir),
        "--tmdb-cache-dir", str(cache_dir),
        "--sidecar-dir", str(sidecar_dir),
        "--report", "none",
        "--no-jsonl-log",
    ])
    assert rc == 1


def test_cli_main_lock_ok_runs(monkeypatch, isolated_dirs):
    items_dir, cache_dir, sidecar_dir = isolated_dirs

    import contextlib

    @contextlib.contextmanager
    def fake_lock(force=False):
        yield

    monkeypatch.setattr(audit_tmdb, "acquire_pipeline_lock", fake_lock)
    rc = audit_tmdb.main([
        "--source", "src",
        "--items-dir", str(items_dir),
        "--tmdb-cache-dir", str(cache_dir),
        "--sidecar-dir", str(sidecar_dir),
        "--report", "none",
        "--no-jsonl-log",
    ])
    assert rc == 0


def test_cli_writes_jsonl_log_when_enabled(isolated_dirs, tmp_path):
    """JSONL log enabled (default) → écrit une ligne par suspect."""
    items_dir, cache_dir, sidecar_dir = isolated_dirs
    log_path = tmp_path / "logs" / "audit_tmdb.jsonl"
    _write_items(items_dir, "src", [
        Item(id="bbbbbbbb", types=(ItemType.FILM,), title="Inception", year=2010,
             external_ids=ExternalIds(tmdb=2, tmdb_type="movie")),
    ])
    _write_tmdb_cache(cache_dir, {
        2: {"original_title": "The Godfather", "release_date": "1972-03-24"},
    })
    args = _parse(
        "--source", "src",
        "--items-dir", str(items_dir),
        "--tmdb-cache-dir", str(cache_dir),
        "--sidecar-dir", str(sidecar_dir),
        "--jsonl-log", str(log_path),
        "--report", "none",
    )
    audit_tmdb.run(args)
    assert log_path.exists()


def test_cli_main_parses_argv_only_once(monkeypatch, isolated_dirs):
    """CR senior H5 : argv parsé une fois (delegate à run(args))."""
    items_dir, cache_dir, sidecar_dir = isolated_dirs

    import contextlib

    @contextlib.contextmanager
    def fake_lock(force=False):
        yield

    monkeypatch.setattr(audit_tmdb, "acquire_pipeline_lock", fake_lock)

    parse_count = {"n": 0}
    original_parse = audit_tmdb.build_parser

    def wrapped_parser():
        parse_count["n"] += 1
        return original_parse()

    monkeypatch.setattr(audit_tmdb, "build_parser", wrapped_parser)

    audit_tmdb.main([
        "--source", "src",
        "--items-dir", str(items_dir),
        "--tmdb-cache-dir", str(cache_dir),
        "--sidecar-dir", str(sidecar_dir),
        "--report", "none",
        "--no-jsonl-log",
    ])
    assert parse_count["n"] == 1
