"""Tests du fetcher de registries (Python)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from meta.fetcher import (
    DEFAULT_MAX_BYTES,
    RegistryFetcher,
    RegistryFetchError,
    RegistryHttpGet,
    load_registries_file,
)


VALID = {
    "schemaVersion": 1,
    "siteUrl": "https://x.example",
    "podcast": {"title": "X", "hosts": [], "language": "fr"},
    "stats": {
        "itemsCount": 1,
        "mentionsCount": 1,
        "episodesCount": 1,
        "guestsCount": 1,
        "lastUpdatedAt": "2026-06-12T00:00:00Z",
    },
    "meta": {"generator": "Reco/0.3.0", "generatedAt": "2026-06-12T00:00:00Z"},
    "endpoints": {},
}


def _fake_get(responses: dict[str, tuple[int, str]]):
    def get(url: str) -> tuple[int, str]:
        if url not in responses:
            raise ConnectionError(f"no fake for {url}")
        return responses[url]
    return get


def test_fetch_one_success() -> None:
    f = RegistryFetcher(allow_unsafe_urls=True, get=_fake_get({"https://x.example/.well-known/reco-registry.json": (200, json.dumps(VALID))}))
    r = f.fetch_one("https://x.example/.well-known/reco-registry.json")
    assert r.ok
    assert r.registry is not None
    assert r.registry["podcast"]["title"] == "X"


def test_fetch_one_http_error() -> None:
    f = RegistryFetcher(allow_unsafe_urls=True, get=_fake_get({"u": (404, "")}))
    r = f.fetch_one("u")
    assert not r.ok
    assert "404" in (r.error or "")


def test_fetch_one_json_error() -> None:
    f = RegistryFetcher(allow_unsafe_urls=True, get=_fake_get({"u": (200, "not-json")}))
    r = f.fetch_one("u")
    assert not r.ok
    assert "json" in (r.error or "")


def test_fetch_one_schema_error() -> None:
    bad = dict(VALID, siteUrl="http://x")
    f = RegistryFetcher(allow_unsafe_urls=True, get=_fake_get({"u": (200, json.dumps(bad))}))
    r = f.fetch_one("u")
    assert not r.ok
    assert "HTTPS" in (r.error or "")


def test_fetch_one_network_error() -> None:
    def boom(url: str):
        raise OSError("dns")
    f = RegistryFetcher(allow_unsafe_urls=True, get=boom)
    r = f.fetch_one("u")
    assert not r.ok
    # OSError fallback → "network:"
    assert "network" in (r.error or "")


def test_fetch_one_timeout_tagged() -> None:
    """M24-18 — TimeoutError → tag `timeout:`."""
    def boom(url: str):
        raise TimeoutError("read timed out")
    f = RegistryFetcher(allow_unsafe_urls=True, get=boom)
    r = f.fetch_one("u")
    assert not r.ok
    assert (r.error or "").startswith("timeout:")


def test_fetch_one_connection_tagged() -> None:
    """M24-18 — ConnectionError → tag `connection:`."""
    def boom(url: str):
        raise ConnectionError("refused")
    f = RegistryFetcher(allow_unsafe_urls=True, get=boom)
    r = f.fetch_one("u")
    assert not r.ok
    assert (r.error or "").startswith("connection:")


def test_fetch_one_rejects_oversize_payload() -> None:
    """H24-4 — payload > max_bytes → erreur sans parse."""
    huge = "x" * (DEFAULT_MAX_BYTES + 1)
    f = RegistryFetcher(allow_unsafe_urls=True, get=_fake_get({"u": (200, huge)}))
    r = f.fetch_one("u")
    assert not r.ok
    assert "payload too large" in (r.error or "")


def test_fetch_one_respects_custom_cap() -> None:
    f = RegistryFetcher(
        get=_fake_get({"u": (200, "y" * 1024)}),
        max_bytes=512,
        allow_unsafe_urls=True,
    )
    r = f.fetch_one("u")
    assert not r.ok
    assert "too large" in (r.error or "")


def test_fetch_one_network_error_by_name_timeout() -> None:
    """M24-18 — classification heuristique par nom (ex. requests.Timeout)."""
    class ReadTimeout(Exception):
        pass

    def boom(url: str):
        raise ReadTimeout("from custom client")

    f = RegistryFetcher(allow_unsafe_urls=True, get=boom)
    r = f.fetch_one("u")
    assert (r.error or "").startswith("timeout:")


def test_fetch_one_network_error_by_name_connection() -> None:
    class DnsError(Exception):
        pass

    def boom(url: str):
        raise DnsError("nxdomain")

    f = RegistryFetcher(allow_unsafe_urls=True, get=boom)
    r = f.fetch_one("u")
    assert (r.error or "").startswith("connection:")


def test_registry_http_get_is_a_protocol() -> None:
    """R-P1-02 — duck-typing : un callable simple satisfait le Protocol."""
    def get(url: str) -> tuple[int, str]:
        return (200, "{}")

    assert isinstance(get, RegistryHttpGet)


def test_fetch_many_accumulates() -> None:
    f = RegistryFetcher(
        get=_fake_get(
            {
                "a": (200, json.dumps(VALID)),
                "b": (500, ""),
            }
        ),
        allow_unsafe_urls=True,
    )
    out = f.fetch_many(["a", "b"])
    assert len(out) == 2
    assert out[0].ok and not out[1].ok


def test_load_registries_file_json_list(tmp_path: Path) -> None:
    p = tmp_path / "r.json"
    p.write_text(json.dumps(["https://a", "https://b"]), encoding="utf-8")
    assert load_registries_file(p) == ["https://a", "https://b"]


def test_load_registries_file_json_object(tmp_path: Path) -> None:
    p = tmp_path / "r.json"
    p.write_text(json.dumps({"registries": ["https://a"]}), encoding="utf-8")
    assert load_registries_file(p) == ["https://a"]


def test_load_registries_file_missing(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        load_registries_file(tmp_path / "absent.json")


def test_load_registries_file_bad_json(tmp_path: Path) -> None:
    p = tmp_path / "r.json"
    p.write_text("{not json", encoding="utf-8")
    with pytest.raises(RegistryFetchError):
        load_registries_file(p)


def test_load_registries_file_wrong_shape(tmp_path: Path) -> None:
    p = tmp_path / "r.json"
    p.write_text(json.dumps(42), encoding="utf-8")
    with pytest.raises(RegistryFetchError):
        load_registries_file(p)


def test_load_registries_file_non_string_item(tmp_path: Path) -> None:
    p = tmp_path / "r.json"
    p.write_text(json.dumps([1, 2]), encoding="utf-8")
    with pytest.raises(RegistryFetchError) as ei:
        load_registries_file(p)
    # B-LOW-6 — message distingue "non-string".
    assert "non-string" in str(ei.value) or "type" in str(ei.value)


def test_load_registries_file_blank_item(tmp_path: Path) -> None:
    """B-LOW-6 — entrée string vide → message dédié."""
    p = tmp_path / "r.json"
    p.write_text(json.dumps(["   "]), encoding="utf-8")
    with pytest.raises(RegistryFetchError) as ei:
        load_registries_file(p)
    assert "vide" in str(ei.value)


def test_load_registries_file_yaml(tmp_path: Path) -> None:
    yaml = pytest.importorskip("yaml")
    p = tmp_path / "r.yaml"
    p.write_text("- https://a\n- https://b\n", encoding="utf-8")
    assert load_registries_file(p) == ["https://a", "https://b"]
