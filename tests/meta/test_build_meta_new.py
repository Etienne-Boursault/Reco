"""Tests Phase-4 fixer pour `tools/build_meta.py`."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import build_meta
from build_meta import run


def _fake_get(payloads: dict[str, tuple[int, str]]):
    def _get(url: str) -> tuple[int, str]:
        if url not in payloads:
            return (404, "")
        return payloads[url]
    return _get


VALID = {
    "schemaVersion": 1,
    "siteUrl": "https://x.example",
    "podcast": {"title": "X", "hosts": [], "language": "fr"},
    "stats": {
        "itemsCount": 1, "mentionsCount": 1, "episodesCount": 1,
        "guestsCount": 1, "lastUpdatedAt": "2026-06-12T00:00:00Z",
    },
    "meta": {"generator": "Reco/0.3.0", "generatedAt": "2026-06-12T00:00:00Z"},
    "endpoints": {},
}


def test_run_requires_urls_or_file(tmp_path: Path) -> None:
    """B-HIGH-6 — au moins un input requis."""
    with pytest.raises(ValueError):
        run(output_dir=tmp_path)


def test_run_with_urls_arg_skips_file_read(tmp_path: Path) -> None:
    """B-HIGH-6 — passer `urls=` court-circuite `load_registries_file`."""
    out_dir = tmp_path / "out"
    get = _fake_get({"https://a/": (200, json.dumps(VALID))})
    idx = run(
        urls=["https://a/"], output_dir=out_dir,
        get_callable=get, allow_unsafe_urls=True,
    )
    assert idx["totals"]["podcasts"] == 1


def test_run_ssrf_blocks_private_ip(tmp_path: Path) -> None:
    """B-CRIT-2 — IP privée → erreur ssrf:, ne fetch jamais."""
    calls: list[str] = []

    def get(url: str):
        calls.append(url)
        return (200, json.dumps(VALID))

    idx = run(
        urls=["https://10.0.0.5/"], output_dir=tmp_path,
        get_callable=get, dry_run=True,
    )
    assert calls == []  # jamais appelé
    assert idx["errors"][0]["error"].startswith("ssrf:")


def test_run_ssrf_blocks_http(tmp_path: Path) -> None:
    """B-CRIT-2 — http:// rejeté avant fetch."""
    idx = run(
        urls=["http://example.com/"], output_dir=tmp_path,
        get_callable=lambda u: (200, "{}"), dry_run=True,
    )
    assert idx["errors"][0]["error"].startswith("ssrf:")


def test_run_ssrf_with_custom_resolver(tmp_path: Path) -> None:
    """B-CRIT-2 — resolver injecté permet de simuler IP publique."""
    out_dir = tmp_path / "out"
    idx = run(
        urls=["https://safe.example/"],
        output_dir=out_dir,
        get_callable=_fake_get({"https://safe.example/": (200, json.dumps(VALID))}),
        url_resolver=lambda h: ["93.184.216.34"],
    )
    assert idx["totals"]["podcasts"] == 1


def test_main_unexpected_exception_exit_2(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """B-MED-6 — exception inattendue → exit 2 (TOTAL_FAILURE)."""
    from contextlib import nullcontext

    reg = tmp_path / "r.json"
    reg.write_text("[]", encoding="utf-8")
    monkeypatch.setattr(
        build_meta, "acquire_pipeline_lock", lambda force=False: nullcontext(),
    )

    def boom(*a, **k):
        raise RuntimeError("kaboom")

    monkeypatch.setattr(build_meta, "load_registries_file", boom)
    rc = build_meta.main(
        ["--registries-file", str(reg), "--output-dir", str(tmp_path / "out")],
    )
    assert rc == 2


def test_exit_code_invariant_zero_urls_zero_errors() -> None:
    """B-LOW-7 — 0 URL déclarée → 0 erreur attendu, exit OK."""
    idx = {"totals": {"podcasts": 0}, "errors": []}
    assert build_meta._exit_code_for(idx, 0) == 0


def test_exit_code_all_ok_no_errors() -> None:
    """1 URL, 1 OK, 0 erreur → EXIT_OK (cover branch error_count == 0)."""
    idx = {"totals": {"podcasts": 1}, "errors": []}
    assert build_meta._exit_code_for(idx, 1) == 0


def test_exit_code_invariant_breaks_assert() -> None:
    """B-LOW-7 — invariant violé : assert lève."""
    idx = {"totals": {"podcasts": 0}, "errors": [{"sourceUrl": "x", "error": "?"}]}
    with pytest.raises(AssertionError):
        build_meta._exit_code_for(idx, 0)


def test_run_with_safe_url_resolver_blocks_private(tmp_path: Path) -> None:
    """resolver retourne private → bloqué via SSRF."""
    out_dir = tmp_path / "out"
    idx = run(
        urls=["https://attacker.example/"],
        output_dir=out_dir,
        get_callable=lambda u: (200, json.dumps(VALID)),
        url_resolver=lambda h: ["169.254.169.254"],
        dry_run=True,
    )
    assert idx["errors"][0]["error"].startswith("ssrf:")


def test_meta_index_documents_generated_at_and_errors(tmp_path: Path) -> None:
    """B-MED-7 — `generatedAt` et `errors` exposés, structure documentée."""
    idx = run(
        urls=["https://safe.example/"],
        output_dir=tmp_path / "out",
        get_callable=_fake_get({"https://safe.example/": (200, json.dumps(VALID))}),
        url_resolver=lambda h: ["93.184.216.34"],
        dry_run=True,
    )
    assert "generatedAt" in idx
    assert isinstance(idx["errors"], list)
    # Format documenté : `Z` final UTC.
    assert idx["generatedAt"].endswith("Z")
