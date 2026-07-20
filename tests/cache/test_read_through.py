"""Tests cache.reader.get_item_or_rebuild — read-through avec mtime."""
from __future__ import annotations

import os
import time
from pathlib import Path

from cache.builder import CacheBuilder
from cache.reader import CacheReader


def _touch_future(path: Path, *, delta_s: float = 10.0) -> None:
    """Force le mtime à `now + delta` pour simuler une édition."""
    now = time.time() + delta_s
    os.utime(path, (now, now))


class TestReadThrough:
    def test_returns_cached_when_mtime_fresh(
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
        with CacheReader(db_path) as r:
            row = r.get_item_or_rebuild("podcast-a", "item-001", builder=builder)
            assert row is not None
            assert row.title == "Parasite"

    def test_returns_none_for_unknown(
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
        with CacheReader(db_path) as r:
            assert r.get_item_or_rebuild("podcast-a", "ghost", builder=builder) is None

    def test_rebuilds_on_stale_mtime(
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

        # Modifie le JSON et avance le mtime → cache stale.
        target = items_dir / "podcast-a" / "item-001.json"
        target.write_text(
            '{"id": "item-001", "schemaVersion": 1, "title": "Parasite (édité)", "types": ["film"]}',
            encoding="utf-8",
        )
        _touch_future(target)

        with CacheReader(db_path) as r:
            row = r.get_item_or_rebuild("podcast-a", "item-001", builder=builder)
            assert row is not None
            assert row.title == "Parasite (édité)"

    def test_returns_row_when_json_file_missing(
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

        target = items_dir / "podcast-a" / "item-001.json"
        target.unlink()  # JSON supprimé entre temps.

        with CacheReader(db_path) as r:
            row = r.get_item_or_rebuild("podcast-a", "item-001", builder=builder)
            # Pas de fichier → on retourne ce qu'on a en cache (stale OK).
            assert row is not None
            assert row.title == "Parasite"
