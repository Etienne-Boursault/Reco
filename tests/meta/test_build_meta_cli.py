"""Tests CLI `tools/build_meta.py` — smoke + dry-run + écriture."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import build_meta
from build_meta import run


VALID = {
    "schemaVersion": 1,
    "siteUrl": "https://x.example",
    "podcast": {"title": "X", "hosts": [], "language": "fr"},
    "stats": {
        "itemsCount": 1,
        "mentionsCount": 5,
        "episodesCount": 1,
        "guestsCount": 1,
        "lastUpdatedAt": "2026-06-12T00:00:00Z",
    },
    "meta": {"generator": "Reco/0.3.0", "generatedAt": "2026-06-12T00:00:00Z"},
    "endpoints": {},
}


def _fake_get(payloads: dict[str, tuple[int, str]]):
    def _get(url: str) -> tuple[int, str]:
        if url not in payloads:
            return (404, "")
        return payloads[url]
    return _get


def test_run_writes_meta_index(tmp_path: Path) -> None:
    reg_file = tmp_path / "registries.json"
    reg_file.write_text(json.dumps(["https://x/.well-known/reco-registry.json"]), encoding="utf-8")
    out_dir = tmp_path / "out"
    get = _fake_get({"https://x/.well-known/reco-registry.json": (200, json.dumps(VALID))})
    index = run(
        registries_file=reg_file,
        output_dir=out_dir,
        get_callable=get,
        allow_unsafe_urls=True,
    )

    written = out_dir / "meta_index.json"
    assert written.exists()
    assert index["totals"]["podcasts"] == 1
    assert index["totals"]["mentions"] == 5


def test_run_collects_errors(tmp_path: Path) -> None:
    reg_file = tmp_path / "registries.json"
    reg_file.write_text(json.dumps(["https://x/", "https://broken/"]), encoding="utf-8")
    out_dir = tmp_path / "out"
    get = _fake_get(
        {
            "https://x/": (200, json.dumps(VALID)),
            "https://broken/": (200, "not-json"),
        }
    )
    index = run(
        registries_file=reg_file,
        output_dir=out_dir,
        get_callable=get,
        allow_unsafe_urls=True,
    )
    assert index["totals"]["podcasts"] == 1
    assert len(index["errors"]) == 1
    assert index["errors"][0]["sourceUrl"] == "https://broken/"


def test_run_dry_run_skips_write(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    reg_file = tmp_path / "registries.json"
    reg_file.write_text(json.dumps(["https://x/"]), encoding="utf-8")
    out_dir = tmp_path / "out"
    get = _fake_get({"https://x/": (200, json.dumps(VALID))})
    run(
        registries_file=reg_file,
        output_dir=out_dir,
        dry_run=True,
        get_callable=get,
        allow_unsafe_urls=True,
    )
    assert not (out_dir / "meta_index.json").exists()
    captured = capsys.readouterr()
    assert "podcasts" in captured.out  # JSON dumped to stdout


def _patch_lock(monkeypatch: pytest.MonkeyPatch) -> None:
    """Patch acquire_pipeline_lock pour ne pas dépendre du lockfile global."""
    from contextlib import nullcontext

    monkeypatch.setattr(
        build_meta, "acquire_pipeline_lock", lambda force=False: nullcontext()
    )
    # B-CRIT-2 — fixtures de tests utilisent des URLs non-résolvables.
    monkeypatch.setattr(build_meta, "ALLOW_UNSAFE_URLS_TEST_ONLY", True)


def test_main_smoke(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    reg_file = tmp_path / "registries.json"
    reg_file.write_text(json.dumps([]), encoding="utf-8")
    out_dir = tmp_path / "out"
    _patch_lock(monkeypatch)
    # Évite la dépendance requests_cache : on patche _default_get à un noop.
    monkeypatch.setattr(build_meta, "_default_get", lambda: (lambda url: (200, "{}")))
    rc = build_meta.main([
        "--registries-file", str(reg_file),
        "--output-dir", str(out_dir),
    ])
    assert rc == 0
    assert (out_dir / "meta_index.json").exists()


def test_main_exit_partial(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """M24-17 — au moins un OK + au moins une erreur → exit 1."""
    reg_file = tmp_path / "registries.json"
    reg_file.write_text(
        json.dumps(["https://x/", "https://broken/"]), encoding="utf-8"
    )
    out_dir = tmp_path / "out"
    _patch_lock(monkeypatch)
    monkeypatch.setattr(
        build_meta,
        "_default_get",
        lambda: _fake_get(
            {
                "https://x/": (200, json.dumps(VALID)),
                "https://broken/": (200, "not-json"),
            }
        ),
    )
    rc = build_meta.main([
        "--registries-file", str(reg_file),
        "--output-dir", str(out_dir),
    ])
    assert rc == 1


def test_main_exit_total_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """M24-17 — toutes les URLs en erreur → exit 2."""
    reg_file = tmp_path / "registries.json"
    reg_file.write_text(json.dumps(["https://broken/"]), encoding="utf-8")
    out_dir = tmp_path / "out"
    _patch_lock(monkeypatch)
    monkeypatch.setattr(
        build_meta,
        "_default_get",
        lambda: _fake_get({"https://broken/": (200, "not-json")}),
    )
    rc = build_meta.main([
        "--registries-file", str(reg_file),
        "--output-dir", str(out_dir),
    ])
    assert rc == 2


def test_main_server_lock_busy(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """R-P2-09 / M24-17 — lock occupé → exit total-failure."""
    from review_lock import ServerLockBusy  # type: ignore

    reg_file = tmp_path / "registries.json"
    reg_file.write_text(json.dumps([]), encoding="utf-8")

    def busy(force=False):
        raise ServerLockBusy("pipeline en cours")

    monkeypatch.setattr(build_meta, "acquire_pipeline_lock", busy)
    rc = build_meta.main([
        "--registries-file", str(reg_file),
        "--output-dir", str(tmp_path / "out"),
    ])
    assert rc == 2


def test_main_source_flag_removed(tmp_path: Path) -> None:
    """M24-16 — `--source` n'existe plus."""
    reg_file = tmp_path / "registries.json"
    reg_file.write_text(json.dumps([]), encoding="utf-8")
    with pytest.raises(SystemExit):
        build_meta.main([
            "--registries-file", str(reg_file),
            "--source", "all",
        ])
