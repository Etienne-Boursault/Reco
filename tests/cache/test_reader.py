"""Tests cache.reader — CacheReader read-only, projections immutables."""
from __future__ import annotations

import sqlite3
from pathlib import Path
from types import MappingProxyType

import pytest

from cache.builder import CacheBuilder
from cache.reader import CacheReader, EpisodeRow, ItemRow, MentionRow


class _BrokenConn:
    """Fake connection qui lève ProgrammingError au close (couvre la branche)."""

    def close(self) -> None:
        raise sqlite3.ProgrammingError("already closed")


class TestReaderLifecycle:
    def test_missing_db_raises(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            CacheReader(tmp_path / "absent.sqlite")

    def test_context_manager_closes(
        self, built_cache: tuple[Path, CacheBuilder]
    ) -> None:
        db_path, _ = built_cache
        with CacheReader(db_path) as r:
            assert r.get_item("podcast-a", "item-001") is not None
        # Idempotent : double close ne lève rien.
        r.close()

    def test_double_close_idempotent(
        self, built_cache: tuple[Path, CacheBuilder]
    ) -> None:
        db_path, _ = built_cache
        r = CacheReader(db_path)
        r.close()
        # Re-fermeture après cleanup : sqlite peut lever ProgrammingError,
        # qu'on swallow.
        r._conn = _BrokenConn()  # type: ignore[assignment]
        r.close()

    def test_read_only_mode_rejects_writes(
        self, built_cache: tuple[Path, CacheBuilder]
    ) -> None:
        db_path, _ = built_cache
        r = CacheReader(db_path)
        try:
            with pytest.raises(sqlite3.OperationalError):
                r._conn.execute("DELETE FROM items")
        finally:
            r.close()


class TestGetItem:
    def test_returns_itemrow(self, built_cache: tuple[Path, CacheBuilder]) -> None:
        db_path, _ = built_cache
        with CacheReader(db_path) as r:
            item = r.get_item("podcast-a", "item-001")
            assert isinstance(item, ItemRow)
            assert item.title == "Parasite"
            assert item.types == ("film",)
            assert item.external_ids is not None
            assert isinstance(item.external_ids, MappingProxyType)
            assert item.external_ids["tmdb"] == 496243
            assert item.enrichment_suspect is False

    def test_returns_none_for_unknown(
        self, built_cache: tuple[Path, CacheBuilder]
    ) -> None:
        db_path, _ = built_cache
        with CacheReader(db_path) as r:
            assert r.get_item("podcast-a", "ghost") is None

    def test_itemrow_is_frozen(
        self, built_cache: tuple[Path, CacheBuilder]
    ) -> None:
        db_path, _ = built_cache
        with CacheReader(db_path) as r:
            item = r.get_item("podcast-a", "item-001")
            assert item is not None
            with pytest.raises((AttributeError, Exception)):
                item.title = "x"  # type: ignore[misc]


class TestIterItems:
    def test_all(self, built_cache: tuple[Path, CacheBuilder]) -> None:
        db_path, _ = built_cache
        with CacheReader(db_path) as r:
            ids = [it.id for it in r.iter_items("podcast-a")]
            assert ids == ["item-001", "item-002"]

    def test_only_suspect(self, built_cache: tuple[Path, CacheBuilder]) -> None:
        db_path, _ = built_cache
        with CacheReader(db_path) as r:
            ids = [it.id for it in r.iter_items("podcast-a", only_suspect=True)]
            assert ids == ["item-002"]


class TestMentions:
    def test_for_item(self, built_cache: tuple[Path, CacheBuilder]) -> None:
        db_path, _ = built_cache
        with CacheReader(db_path) as r:
            mentions = r.get_mentions_for_item("podcast-a", "item-001")
            assert len(mentions) == 1
            m = mentions[0]
            assert isinstance(m, MentionRow)
            assert m.recommended_by == "Bong Joon-ho"
            assert m.episode_guid == "ep-A1"
            assert m.timestamp_seconds == 12 * 60 + 34

    def test_for_episode(self, built_cache: tuple[Path, CacheBuilder]) -> None:
        db_path, _ = built_cache
        with CacheReader(db_path) as r:
            mentions = r.get_mentions_for_episode("podcast-a", "ep-A1")
            assert {m.id for m in mentions} == {"men-A1", "men-A2"}


class TestEpisode:
    def test_get(self, built_cache: tuple[Path, CacheBuilder]) -> None:
        db_path, _ = built_cache
        with CacheReader(db_path) as r:
            ep = r.get_episode("podcast-a", "ep-A1")
            assert isinstance(ep, EpisodeRow)
            assert ep.title == "Avec Bong Joon-ho"
            assert ep.hosts == ("Kyan Khojandi", "Navo")
            assert ep.guests_parsed == ("Bong Joon-ho",)
            assert ep.match_suspect is False

    def test_unknown(self, built_cache: tuple[Path, CacheBuilder]) -> None:
        db_path, _ = built_cache
        with CacheReader(db_path) as r:
            assert r.get_episode("podcast-a", "ghost") is None


class TestMeta:
    def test_get_meta(self, built_cache: tuple[Path, CacheBuilder]) -> None:
        db_path, _ = built_cache
        with CacheReader(db_path) as r:
            assert r.get_meta("cache_schema_version") == "2"
            assert r.get_meta("inexistant") is None
