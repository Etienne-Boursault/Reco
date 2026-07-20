"""Tests : tools.enrich_audit.cli_runner."""
from __future__ import annotations

import json
import os
from pathlib import Path

from domain.item import ExternalIds, Item, ItemType
from enrich_audit.cli_runner import (
    RunOptions,
    default_service,
    run_audit,
)
from enrich_audit.flag_writer import list_archives, list_sidecars, read_sidecar
from enrich_audit.service import AuditResult, EnrichAuditService
from enrich_audit.types import Severity, Suspicion


def _enriched_item(
    item_id: str, *,
    title: str,
    tmdb: int,
    year: int | None = None,
    types: tuple[ItemType, ...] = (ItemType.FILM,),
    tmdb_type: str = "movie",
) -> Item:
    return Item(
        id=item_id,
        types=types,
        title=title,
        year=year,
        external_ids=ExternalIds(tmdb=tmdb, tmdb_type=tmdb_type),
    )


# ===== default_service =====================================================


def test_default_service_runs_all_checks():
    svc = default_service()
    bad = _enriched_item("abc12345", title="Inception", tmdb=1, year=2010)
    result = svc.audit_item(
        bad,
        lambda _id: {
            "original_title": "The Godfather",
            "release_date": "1972-03-24",
            "runtime": 12,
        },
    )
    assert result is not None
    assert result.is_suspect is True
    kinds = {s.kind for s in result.suspicions}
    assert "title_mismatch" in kinds
    assert "year_mismatch" in kinds
    assert "runtime_short_film" in kinds


def test_default_service_detects_tmdb_type_mismatch():
    """CR senior C5 : le check critique est inclus."""
    svc = default_service()
    item = _enriched_item("abc12345", title="X", tmdb=1)
    result = svc.audit_item(
        item,
        lambda _id: {"name": "X", "first_air_date": "2010-01-01"},
    )
    assert result is not None
    kinds = {s.kind for s in result.suspicions}
    assert "tmdb_type_mismatch" in kinds


def test_default_service_thresholds_are_injectable():
    """CR senior H4 : seuils CLI propagés via default_service()."""
    svc = default_service(title_threshold=0.99)  # quasi-impossible
    item = _enriched_item("abc12345", title="Inception", tmdb=1)
    result = svc.audit_item(
        item,
        lambda _id: {"original_title": "Inceptin", "release_date": "2010-01-01"},
    )
    assert result is not None
    assert any(s.kind == "title_mismatch" for s in result.suspicions)


# ===== run_audit ===========================================================


_FIXED_TS = "2026-06-10T12:00:00Z"


def test_run_audit_dry_run_writes_nothing(tmp_path: Path):
    items = (_enriched_item("aaaaaaaa", title="Inception", tmdb=1, year=2010),)
    opts = RunOptions(
        source_id="src",
        items=items,
        provider=lambda _id: {"original_title": "Inception", "release_date": "2010-07-16"},
        apply=False,
        sidecar_base_dir=tmp_path,
        audited_at=_FIXED_TS,
    )
    report = run_audit(opts)
    assert report.audited_count == 1
    assert report.suspect_count == 0
    assert list_sidecars("src", base_dir=tmp_path) == []


def test_run_audit_apply_writes_sidecars(tmp_path: Path):
    items = (
        _enriched_item("aaaaaaaa", title="Inception", tmdb=1, year=2010),
        _enriched_item("bbbbbbbb", title="Inception", tmdb=2, year=2010),
    )

    def provider(tmdb_id: int) -> dict | None:
        return {
            1: {"original_title": "Inception", "release_date": "2010-07-16"},
            2: {"original_title": "The Godfather", "release_date": "1972-03-24"},
        }[tmdb_id]

    opts = RunOptions(
        source_id="src",
        items=items,
        provider=provider,
        apply=True,
        sidecar_base_dir=tmp_path,
        audited_at=_FIXED_TS,
    )
    report = run_audit(opts)
    assert report.audited_count == 2
    assert report.suspect_count == 1

    ok = read_sidecar("src", "aaaaaaaa", base_dir=tmp_path)
    bad = read_sidecar("src", "bbbbbbbb", base_dir=tmp_path)
    assert ok is not None and ok.is_suspect is False
    assert bad is not None and bad.is_suspect is True


def test_run_audit_apply_archives_stale_sidecars(tmp_path: Path):
    """CR archi P1 #16 : clear archive plutôt que delete."""
    from enrich_audit.flag_writer import write_sidecar
    stale = AuditResult(item_id="stalestl", is_suspect=False, suspicions=())
    write_sidecar(stale, "src", base_dir=tmp_path, audited_at=_FIXED_TS)
    assert read_sidecar("src", "stalestl", base_dir=tmp_path) is not None

    items = (_enriched_item("aaaaaaaa", title="Inception", tmdb=1, year=2010),)
    opts = RunOptions(
        source_id="src",
        items=items,
        provider=lambda _id: {"original_title": "Inception", "release_date": "2010-07-16"},
        apply=True,
        clear_before_apply=True,
        sidecar_base_dir=tmp_path,
        audited_at=_FIXED_TS,
    )
    run_audit(opts)
    assert read_sidecar("src", "stalestl", base_dir=tmp_path) is None
    assert read_sidecar("src", "aaaaaaaa", base_dir=tmp_path) is not None
    # Stale archivé, pas perdu.
    archives = list_archives("src", base_dir=tmp_path)
    assert len(archives) == 1
    assert (archives[0] / "stalestl.json").exists()


def test_run_audit_no_clear_keeps_existing_sidecars(tmp_path: Path):
    from enrich_audit.flag_writer import write_sidecar
    stale = AuditResult(item_id="stalestl", is_suspect=False, suspicions=())
    write_sidecar(stale, "src", base_dir=tmp_path, audited_at=_FIXED_TS)
    items = (_enriched_item("aaaaaaaa", title="Inception", tmdb=1, year=2010),)
    opts = RunOptions(
        source_id="src",
        items=items,
        provider=lambda _id: {"original_title": "Inception", "release_date": "2010-07-16"},
        apply=True,
        clear_before_apply=False,
        sidecar_base_dir=tmp_path,
        audited_at=_FIXED_TS,
    )
    run_audit(opts)
    assert read_sidecar("src", "stalestl", base_dir=tmp_path) is not None


def test_run_audit_uses_injected_service(tmp_path: Path):
    noop_svc = EnrichAuditService(checks=[lambda i, d: None])
    items = (_enriched_item("aaaaaaaa", title="Inception", tmdb=1, year=2010),)
    opts = RunOptions(
        source_id="src",
        items=items,
        provider=lambda _id: {"original_title": "Totally Different"},
        apply=False,
        service=noop_svc,
        sidecar_base_dir=tmp_path,
        audited_at=_FIXED_TS,
    )
    report = run_audit(opts)
    assert report.suspect_count == 0


def test_run_audit_writes_jsonl_log_when_suspects(tmp_path: Path):
    """CR senior H9 : log JSONL par item suspect."""
    items = (_enriched_item("aaaaaaaa", title="Inception", tmdb=1, year=2010),)
    log_path = tmp_path / "logs" / "audit.jsonl"
    opts = RunOptions(
        source_id="src",
        items=items,
        provider=lambda _id: {"original_title": "Totally Different",
                              "release_date": "1980-01-01"},
        apply=False,
        sidecar_base_dir=tmp_path,
        audited_at=_FIXED_TS,
        jsonl_log_path=log_path,
    )
    run_audit(opts)
    assert log_path.exists()
    lines = log_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    parsed = json.loads(lines[0])
    assert parsed["itemId"] == "aaaaaaaa"


def test_run_audit_no_jsonl_log_when_no_suspect(tmp_path: Path):
    items = (_enriched_item("aaaaaaaa", title="Inception", tmdb=1, year=2010),)
    log_path = tmp_path / "logs" / "audit.jsonl"
    opts = RunOptions(
        source_id="src",
        items=items,
        provider=lambda _id: {"original_title": "Inception", "release_date": "2010-07-16"},
        apply=False,
        sidecar_base_dir=tmp_path,
        audited_at=_FIXED_TS,
        jsonl_log_path=log_path,
    )
    run_audit(opts)
    assert not log_path.exists()


def test_run_audit_sidecar_includes_tmdb_id(tmp_path: Path):
    """CR senior L8 : sidecar contient tmdbId pour debug."""
    items = (_enriched_item("aaaaaaaa", title="Inception", tmdb=1577, year=2010),)
    opts = RunOptions(
        source_id="src",
        items=items,
        provider=lambda _id: {"original_title": "Inception", "release_date": "2010-07-16"},
        apply=True,
        sidecar_base_dir=tmp_path,
        audited_at=_FIXED_TS,
    )
    run_audit(opts)
    sidecar_file = tmp_path / "src" / "aaaaaaaa.json"
    raw = json.loads(sidecar_file.read_text(encoding="utf-8"))
    assert raw["tmdbId"] == 1577


# ===== Idempotence end-to-end (CR senior L10) ==============================


def test_run_audit_is_idempotent(tmp_path: Path):
    """Deux runs successifs avec mêmes inputs → contenu sidecars identique."""
    import hashlib

    items = (
        _enriched_item("aaaaaaaa", title="Inception", tmdb=1, year=2010),
        _enriched_item("bbbbbbbb", title="OtherTitle", tmdb=2, year=2010),
    )

    def provider(tmdb_id: int) -> dict | None:
        return {
            1: {"original_title": "Inception", "release_date": "2010-07-16"},
            2: {"original_title": "The Godfather", "release_date": "1972-03-24"},
        }[tmdb_id]

    def _run():
        opts = RunOptions(
            source_id="src",
            items=items,
            provider=provider,
            apply=True,
            sidecar_base_dir=tmp_path,
            audited_at=_FIXED_TS,  # injecté → idempotent
        )
        run_audit(opts)
        return {
            p.name: hashlib.sha256(p.read_bytes()).hexdigest()
            for p in list_sidecars("src", base_dir=tmp_path)
        }

    h1 = _run()
    h2 = _run()
    assert h1 == h2
    assert set(h1) == {"aaaaaaaa.json", "bbbbbbbb.json"}


# ===== Multi-source (CR archi P2 #17) ======================================


def test_run_audit_handles_arbitrary_source_id(tmp_path: Path):
    """Pas de hardcode `un-bon-moment` — n'importe quel slug fonctionne."""
    items = (_enriched_item("aaaaaaaa", title="X", tmdb=1),)
    for src_id in ("alpha", "beta-gamma", "x9"):
        opts = RunOptions(
            source_id=src_id,
            items=items,
            provider=lambda _id: {"original_title": "X", "release_date": "2010-01-01"},
            apply=True,
            sidecar_base_dir=tmp_path,
            audited_at=_FIXED_TS,
        )
        run_audit(opts)
        assert (tmp_path / src_id / "aaaaaaaa.json").exists()
