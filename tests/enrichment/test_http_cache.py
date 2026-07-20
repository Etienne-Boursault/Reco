"""Tests du wrapper `enrichment.http_cache`.

On utilise le backend `memory` pour ne pas écrire sur disque pendant les tests,
sauf le test de SQLite end-to-end (tmp_path).
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
import requests

from enrichment.http_cache import (
    DEFAULT_URL_TTL,
    CachedSession,
    CacheStats,
    build_cached_session,
)


class DummyResponse:
    def __init__(self, from_cache: bool):
        self.from_cache = from_cache
        self.status_code = 200


def test_stats_counts_hits_and_misses():
    stats = CacheStats()
    assert stats.hit_ratio() == 0.0
    stats.requests = 4
    stats.hits = 3
    stats.misses = 1
    assert stats.hit_ratio() == 0.75


def test_cachedsession_increments_on_get(monkeypatch):
    # Crée un faux session.get qui retourne séquentiellement miss puis hit.
    class FakeRcSession:
        def __init__(self):
            self.calls = 0

        def get(self, url, **kw):
            self.calls += 1
            return DummyResponse(from_cache=(self.calls > 1))

        def close(self):
            pass

    cs = CachedSession(session=FakeRcSession())
    cs.get("https://api.themoviedb.org/3/movie/1")
    cs.get("https://api.themoviedb.org/3/movie/1")
    assert cs.stats.requests == 2
    assert cs.stats.misses == 1
    assert cs.stats.hits == 1
    assert cs.stats.hit_ratio() == 0.5
    cs.close()


def test_response_without_from_cache_attribute_counts_as_miss():
    class R:
        status_code = 200

    class FakeRcSession:
        def get(self, url, **kw):
            return R()

        def close(self):
            pass

    cs = CachedSession(session=FakeRcSession())
    cs.get("https://example.com")
    assert cs.stats.misses == 1
    assert cs.stats.hits == 0


def test_build_cached_session_creates_parent_dir(tmp_path):
    cache_path = tmp_path / "subdir" / "http_cache.sqlite"
    cs = build_cached_session(cache_path)
    assert cache_path.parent.exists()
    assert isinstance(cs, CachedSession)
    cs.close()


def test_build_cached_session_memory_backend(tmp_path):
    # Backend memory : ne touche pas au disque.
    cs = build_cached_session(
        tmp_path / "ignored.sqlite", backend="memory",
    )
    assert cs.stats.requests == 0
    cs.close()


def test_default_url_ttl_contains_known_providers():
    patterns = [p for p, _ in DEFAULT_URL_TTL]
    assert any("themoviedb" in p for p in patterns)
    assert any("musicbrainz" in p for p in patterns)


def test_build_cached_session_accepts_custom_ttls(tmp_path):
    cs = build_cached_session(
        tmp_path / "c.sqlite",
        backend="memory",
        url_ttls=[(r"example\.com", 60)],
    )
    cs.close()
