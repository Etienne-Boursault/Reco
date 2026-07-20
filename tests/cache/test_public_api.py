"""Couvre cache/__init__.py — réexports publics."""
from __future__ import annotations

import cache


def test_public_exports() -> None:
    for name in (
        "BuildStats",
        "CacheBackend",
        "CacheBuilder",
        "CacheReader",
        "EpisodeRow",
        "ItemRow",
        "JsonLoader",
        "MentionRow",
        "SearchHit",
        "create_schema",
        "fts_query",
        "CACHE_SCHEMA_VERSION",
    ):
        assert hasattr(cache, name), f"cache.{name} manquant"
    assert cache.CACHE_SCHEMA_VERSION >= 1
