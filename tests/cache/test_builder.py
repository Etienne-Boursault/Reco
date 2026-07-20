"""Tests cache.builder — build complet, par source, refresh, vacuum, stats."""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from cache.builder import (
    BuildStats,
    CacheBuilder,
    _FsJsonLoader,
    _parse_timestamp_to_seconds,
)


def _connect_ro(db_path: Path) -> sqlite3.Connection:
    uri = f"file:{db_path.as_posix()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    return conn


# ---------- _parse_timestamp_to_seconds (pure unit) ------------------------


class TestParseTimestamp:
    def test_none(self) -> None:
        assert _parse_timestamp_to_seconds(None) is None

    def test_hhmmss(self) -> None:
        assert _parse_timestamp_to_seconds("00:12:34") == 12 * 60 + 34
        assert _parse_timestamp_to_seconds("01:02:03") == 3723

    def test_mmss(self) -> None:
        assert _parse_timestamp_to_seconds("12:34") == 12 * 60 + 34

    def test_single_int_string(self) -> None:
        assert _parse_timestamp_to_seconds("42") == 42

    def test_int(self) -> None:
        assert _parse_timestamp_to_seconds(42) == 42

    def test_float(self) -> None:
        assert _parse_timestamp_to_seconds(42.7) == 42

    def test_invalid_string(self) -> None:
        assert _parse_timestamp_to_seconds("abc") is None

    def test_unsupported_type(self) -> None:
        assert _parse_timestamp_to_seconds([1, 2]) is None


# ---------- FsJsonLoader ---------------------------------------------------


class TestFsJsonLoader:
    def test_iter_files_filters_json_only(self, tmp_path: Path) -> None:
        (tmp_path / "a.json").write_text("{}", encoding="utf-8")
        (tmp_path / "b.txt").write_text("nope", encoding="utf-8")
        sub = tmp_path / "sub"
        sub.mkdir()
        loader = _FsJsonLoader()
        files = list(loader.iter_files(tmp_path))
        assert [f.name for f in files] == ["a.json"]

    def test_iter_files_missing_root_returns_empty(self, tmp_path: Path) -> None:
        loader = _FsJsonLoader()
        assert list(loader.iter_files(tmp_path / "nope")) == []

    def test_read_and_mtime(self, tmp_path: Path) -> None:
        p = tmp_path / "x.json"
        p.write_text('{"a": 1}', encoding="utf-8")
        loader = _FsJsonLoader()
        assert loader.read(p) == {"a": 1}
        assert isinstance(loader.mtime(p), float)


# ---------- CacheBuilder.build ---------------------------------------------


class TestBuildAll:
    def test_returns_stats_with_expected_counts(
        self, built_cache: tuple[Path, CacheBuilder]
    ) -> None:
        _, builder = built_cache
        # Rebuild explicite pour récupérer stats fraîches.
        stats = builder.build()
        assert isinstance(stats, BuildStats)
        assert stats.n_items == 3  # 2 (a) + 1 (b)
        assert stats.n_mentions == 3  # 2 (a) + 1 (b)
        assert stats.n_episodes == 2  # 1 (a) + 1 (b)
        # FTS = items + episodes
        assert stats.n_fts_rows == stats.n_items + stats.n_episodes
        assert stats.duration_s >= 0.0

    def test_stats_is_frozen(self, built_cache: tuple[Path, CacheBuilder]) -> None:
        _, builder = built_cache
        stats = builder.build()
        with pytest.raises((AttributeError, Exception)):
            stats.n_items = 999  # type: ignore[misc]

    def test_db_file_exists_after_build(
        self, built_cache: tuple[Path, CacheBuilder]
    ) -> None:
        db_path, _ = built_cache
        assert db_path.exists()
        assert db_path.stat().st_size > 0

    def test_tmp_file_cleaned_up(
        self, built_cache: tuple[Path, CacheBuilder]
    ) -> None:
        db_path, _ = built_cache
        tmp = db_path.with_suffix(db_path.suffix + ".tmp")
        assert not tmp.exists()

    def test_items_inserted_correctly(
        self, built_cache: tuple[Path, CacheBuilder]
    ) -> None:
        db_path, _ = built_cache
        conn = _connect_ro(db_path)
        try:
            row = conn.execute(
                "SELECT * FROM items WHERE source_id = ? AND id = ?",
                ("podcast-a", "item-001"),
            ).fetchone()
            assert row["title"] == "Parasite"
            assert row["schema_version"] == 1
            assert "film" in row["types"]
            assert row["external_ids"] is not None
            assert "tmdb" in row["external_ids"]
            assert row["enrichment_suspect"] == 0
            # canonical_key absent → NULL.
            assert row["canonical_key"] is None
        finally:
            conn.close()

    def test_enrichment_suspect_flag_propagates(
        self, built_cache: tuple[Path, CacheBuilder]
    ) -> None:
        db_path, _ = built_cache
        conn = _connect_ro(db_path)
        try:
            row = conn.execute(
                "SELECT enrichment_suspect, canonical_key FROM items WHERE id = 'item-002'"
            ).fetchone()
            assert row["enrichment_suspect"] == 1
            assert row["canonical_key"] == "kaamelott"
        finally:
            conn.close()

    def test_mention_timestamp_parsed_to_seconds(
        self, built_cache: tuple[Path, CacheBuilder]
    ) -> None:
        db_path, _ = built_cache
        conn = _connect_ro(db_path)
        try:
            row = conn.execute(
                "SELECT timestamp_seconds FROM mentions WHERE id = 'men-A1'"
            ).fetchone()
            assert row["timestamp_seconds"] == 12 * 60 + 34
            # int direct -> 42
            row2 = conn.execute(
                "SELECT timestamp_seconds FROM mentions WHERE id = 'men-B1'"
            ).fetchone()
            assert row2["timestamp_seconds"] == 42
        finally:
            conn.close()

    def test_episodes_guests_parsed_present(
        self, built_cache: tuple[Path, CacheBuilder]
    ) -> None:
        db_path, _ = built_cache
        conn = _connect_ro(db_path)
        try:
            row = conn.execute(
                "SELECT guests_parsed FROM episodes WHERE guid = 'ep-A1'"
            ).fetchone()
            assert "Bong Joon-ho" in row["guests_parsed"]
        finally:
            conn.close()

    def test_cache_meta_populated(
        self, built_cache: tuple[Path, CacheBuilder]
    ) -> None:
        db_path, _ = built_cache
        conn = _connect_ro(db_path)
        try:
            rows = {r[0]: r[1] for r in conn.execute("SELECT key, value FROM cache_meta")}
            assert rows["cache_schema_version"] == "2"
            assert rows["built_by"] == "cache.builder"
            assert "T" in rows["built_at"]  # ISO8601
        finally:
            conn.close()


class TestBuildBySource:
    def test_only_specified_source_loaded(
        self,
        tmp_path: Path,
        fake_content_dirs: tuple[Path, Path, Path],
    ) -> None:
        items_dir, mentions_dir, episodes_dir = fake_content_dirs
        db_path = tmp_path / "c.sqlite"
        builder = CacheBuilder(
            db_path=db_path,
            items_dir=items_dir,
            mentions_dir=mentions_dir,
            episodes_dir=episodes_dir,
        )
        stats = builder.build(source_id="podcast-a")
        assert stats.n_items == 2
        assert stats.n_episodes == 1
        assert stats.n_mentions == 2

    def test_unknown_source_yields_empty(
        self,
        tmp_path: Path,
        fake_content_dirs: tuple[Path, Path, Path],
    ) -> None:
        items_dir, mentions_dir, episodes_dir = fake_content_dirs
        db_path = tmp_path / "c.sqlite"
        builder = CacheBuilder(
            db_path=db_path,
            items_dir=items_dir,
            mentions_dir=mentions_dir,
            episodes_dir=episodes_dir,
        )
        stats = builder.build(source_id="nope")
        assert stats.n_items == 0
        assert stats.n_episodes == 0
        assert stats.n_mentions == 0


class TestBuildIdempotence:
    def test_rebuild_overwrites(
        self,
        tmp_path: Path,
        fake_content_dirs: tuple[Path, Path, Path],
    ) -> None:
        items_dir, mentions_dir, episodes_dir = fake_content_dirs
        db_path = tmp_path / "c.sqlite"
        builder = CacheBuilder(
            db_path=db_path,
            items_dir=items_dir,
            mentions_dir=mentions_dir,
            episodes_dir=episodes_dir,
        )
        s1 = builder.build()
        s2 = builder.build()
        # Mêmes counts entre deux rebuilds.
        assert (s1.n_items, s1.n_mentions, s1.n_episodes) == (
            s2.n_items,
            s2.n_mentions,
            s2.n_episodes,
        )

    def test_orphan_tmp_cleaned_before_build(
        self,
        tmp_path: Path,
        fake_content_dirs: tuple[Path, Path, Path],
    ) -> None:
        items_dir, mentions_dir, episodes_dir = fake_content_dirs
        db_path = tmp_path / "cache" / "c.sqlite"
        db_path.parent.mkdir(parents=True)
        tmp = db_path.with_suffix(db_path.suffix + ".tmp")
        tmp.write_bytes(b"garbage")
        builder = CacheBuilder(
            db_path=db_path,
            items_dir=items_dir,
            mentions_dir=mentions_dir,
            episodes_dir=episodes_dir,
        )
        builder.build()
        assert not tmp.exists()
        assert db_path.exists()


class TestIterSourceDirsEdgeCases:
    def test_missing_root_returns_no_iter(self, tmp_path: Path) -> None:
        builder = CacheBuilder(
            db_path=tmp_path / "c.sqlite",
            items_dir=tmp_path / "nope_items",
            mentions_dir=tmp_path / "nope_mentions",
            episodes_dir=tmp_path / "nope_episodes",
        )
        stats = builder.build()
        assert stats.n_items == 0
        assert stats.n_episodes == 0
        assert stats.n_mentions == 0

    def test_skips_files_at_source_root(
        self,
        tmp_path: Path,
        fake_content_dirs: tuple[Path, Path, Path],
    ) -> None:
        # Ajoute un fichier (non-dossier) au niveau racine `items/`.
        items_dir, mentions_dir, episodes_dir = fake_content_dirs
        (items_dir / "stray.txt").write_text("noise", encoding="utf-8")
        builder = CacheBuilder(
            db_path=tmp_path / "c.sqlite",
            items_dir=items_dir,
            mentions_dir=mentions_dir,
            episodes_dir=episodes_dir,
        )
        # Ne doit pas planter.
        stats = builder.build()
        assert stats.n_items == 3


class TestVacuum:
    def test_vacuum_runs(
        self, built_cache: tuple[Path, CacheBuilder]
    ) -> None:
        _, builder = built_cache
        # Ne doit pas lever.
        builder.vacuum()


class TestRefreshItemFile:
    def test_refresh_updates_item(
        self,
        tmp_path: Path,
        fake_content_dirs: tuple[Path, Path, Path],
    ) -> None:
        items_dir, mentions_dir, episodes_dir = fake_content_dirs
        db_path = tmp_path / "c.sqlite"
        builder = CacheBuilder(
            db_path=db_path,
            items_dir=items_dir,
            mentions_dir=mentions_dir,
            episodes_dir=episodes_dir,
        )
        builder.build()

        # Modifie le JSON sur disque.
        target = items_dir / "podcast-a" / "item-001.json"
        target.write_text(
            '{"id": "item-001", "schemaVersion": 1, "title": "Parasite (revu)", "types": ["film"]}',
            encoding="utf-8",
        )
        builder.refresh_item_file("podcast-a", "item-001", target)

        conn = _connect_ro(db_path)
        try:
            row = conn.execute(
                "SELECT title FROM items WHERE id = 'item-001'"
            ).fetchone()
            assert row["title"] == "Parasite (revu)"
            # FTS reflète aussi.
            fts_row = conn.execute(
                "SELECT title FROM items_fts WHERE id = 'item-001'"
            ).fetchone()
            assert fts_row["title"] == "Parasite (revu)"
        finally:
            conn.close()
