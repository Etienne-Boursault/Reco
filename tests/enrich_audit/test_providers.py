"""Tests : tools.enrich_audit.providers — cache TMDB versionné + LRU."""
from __future__ import annotations

import json
from pathlib import Path

from enrich_audit.providers import _coerce_cache_payload, make_cache_provider
from enrich_audit.types import TMDB_CACHE_VERSION


# ===== _coerce_cache_payload ===============================================


def test_coerce_legacy_payload_passthrough():
    raw = {"original_title": "X", "release_date": "2010-01-01"}
    assert _coerce_cache_payload(raw) == raw


def test_coerce_v1_payload_unwraps():
    """CR senior C4 : format versionné v1 unwrap correct."""
    raw = {
        "_cacheVersion": TMDB_CACHE_VERSION,
        "kind": "movie",
        "fetchedAt": "2026-06-10T00:00:00Z",
        "payload": {"original_title": "X"},
    }
    assert _coerce_cache_payload(raw) == {"original_title": "X"}


def test_coerce_v1_wrong_version_returns_none():
    raw = {"_cacheVersion": 999, "payload": {"title": "X"}}
    assert _coerce_cache_payload(raw) is None


def test_coerce_v1_non_int_version_returns_none():
    raw = {"_cacheVersion": "1", "payload": {"title": "X"}}
    assert _coerce_cache_payload(raw) is None


def test_coerce_v1_missing_payload_returns_none():
    raw = {"_cacheVersion": TMDB_CACHE_VERSION}
    assert _coerce_cache_payload(raw) is None


def test_coerce_v1_non_dict_payload_returns_none():
    raw = {"_cacheVersion": TMDB_CACHE_VERSION, "payload": []}
    assert _coerce_cache_payload(raw) is None


def test_coerce_non_dict_root_returns_none():
    assert _coerce_cache_payload([1, 2]) is None
    assert _coerce_cache_payload("hello") is None
    assert _coerce_cache_payload(None) is None


# ===== make_cache_provider =================================================


def test_provider_reads_existing_file(tmp_path: Path):
    (tmp_path / "777.json").write_text(json.dumps({"k": 1}), encoding="utf-8")
    provider = make_cache_provider(tmp_path)
    assert provider(777) == {"k": 1}


def test_provider_returns_none_when_missing(tmp_path: Path):
    provider = make_cache_provider(tmp_path)
    assert provider(404) is None


def test_provider_returns_none_on_invalid_json(tmp_path: Path):
    (tmp_path / "1.json").write_text("{not json", encoding="utf-8")
    assert make_cache_provider(tmp_path)(1) is None


def test_provider_returns_none_on_non_dict_root(tmp_path: Path):
    (tmp_path / "1.json").write_text("[1,2]", encoding="utf-8")
    assert make_cache_provider(tmp_path)(1) is None


def test_provider_reads_v1_versioned_cache(tmp_path: Path):
    payload = {"original_title": "X"}
    versioned = {
        "_cacheVersion": TMDB_CACHE_VERSION,
        "kind": "movie",
        "fetchedAt": "2026-06-10T00:00:00Z",
        "payload": payload,
    }
    (tmp_path / "1.json").write_text(json.dumps(versioned), encoding="utf-8")
    assert make_cache_provider(tmp_path)(1) == payload


def test_provider_skips_mismatched_version(tmp_path: Path):
    versioned = {"_cacheVersion": 999, "payload": {"x": 1}}
    (tmp_path / "1.json").write_text(json.dumps(versioned), encoding="utf-8")
    assert make_cache_provider(tmp_path)(1) is None


def test_provider_lru_cache_avoids_redundant_reads(tmp_path: Path):
    """CR senior H10 : LRU évite la relecture sur dataset large."""
    p = tmp_path / "1.json"
    p.write_text(json.dumps({"x": 1}), encoding="utf-8")
    provider = make_cache_provider(tmp_path, use_lru=True)
    assert provider(1) == {"x": 1}
    # Modifier le fichier : la deuxième lecture renvoie quand même la
    # valeur cached (preuve que le LRU a marché).
    p.write_text(json.dumps({"x": 999}), encoding="utf-8")
    assert provider(1) == {"x": 1}
    # Purge → relit.
    provider.cache_clear()
    assert provider(1) == {"x": 999}


def test_provider_no_lru_reads_each_time(tmp_path: Path):
    p = tmp_path / "1.json"
    p.write_text(json.dumps({"x": 1}), encoding="utf-8")
    provider = make_cache_provider(tmp_path, use_lru=False)
    assert provider(1) == {"x": 1}
    p.write_text(json.dumps({"x": 999}), encoding="utf-8")
    assert provider(1) == {"x": 999}
