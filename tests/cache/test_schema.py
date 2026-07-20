"""Tests cache.schema — création / drop / version."""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from cache.schema import CACHE_SCHEMA_VERSION, create_schema, drop_schema


def _table_names(conn: sqlite3.Connection) -> set[str]:
    cur = conn.execute("SELECT name FROM sqlite_master WHERE type IN ('table')")
    return {r[0] for r in cur}


def _index_names(conn: sqlite3.Connection) -> set[str]:
    cur = conn.execute(
        "SELECT name FROM sqlite_master WHERE type = 'index' AND name NOT LIKE 'sqlite_%'"
    )
    return {r[0] for r in cur}


def test_schema_version_is_int_positive() -> None:
    assert isinstance(CACHE_SCHEMA_VERSION, int)
    assert CACHE_SCHEMA_VERSION >= 1


def test_create_schema_creates_all_tables(tmp_path: Path) -> None:
    conn = sqlite3.connect(str(tmp_path / "t.sqlite"))
    try:
        create_schema(conn)
        tables = _table_names(conn)
        # Tables physiques + FTS5 (incluant shadow tables _content/_data/etc).
        assert "items" in tables
        assert "mentions" in tables
        assert "episodes" in tables
        assert "cache_meta" in tables
        assert "items_fts" in tables
        assert "episodes_fts" in tables
    finally:
        conn.close()


def test_create_schema_creates_indexes(tmp_path: Path) -> None:
    conn = sqlite3.connect(str(tmp_path / "t.sqlite"))
    try:
        create_schema(conn)
        idx = _index_names(conn)
        assert "idx_mentions_item" in idx
        assert "idx_mentions_episode" in idx
        assert "idx_items_suspect" in idx
    finally:
        conn.close()


def test_create_schema_fails_if_already_exists(tmp_path: Path) -> None:
    """Le builder DOIT appeler `drop_schema` avant `create_schema`."""
    conn = sqlite3.connect(str(tmp_path / "t.sqlite"))
    try:
        create_schema(conn)
        with pytest.raises(sqlite3.OperationalError):
            create_schema(conn)
    finally:
        conn.close()


def test_drop_schema_is_idempotent(tmp_path: Path) -> None:
    conn = sqlite3.connect(str(tmp_path / "t.sqlite"))
    try:
        # Drop sur base vide ne lève rien.
        drop_schema(conn)
        drop_schema(conn)
        # Ni après création.
        create_schema(conn)
        drop_schema(conn)
        drop_schema(conn)
        assert _table_names(conn) == set()
    finally:
        conn.close()


def test_create_then_drop_then_create_works(tmp_path: Path) -> None:
    conn = sqlite3.connect(str(tmp_path / "t.sqlite"))
    try:
        create_schema(conn)
        drop_schema(conn)
        create_schema(conn)  # ne doit plus lever
        assert "items" in _table_names(conn)
    finally:
        conn.close()


def test_items_pk_enforced(tmp_path: Path) -> None:
    conn = sqlite3.connect(str(tmp_path / "t.sqlite"))
    try:
        create_schema(conn)
        conn.execute(
            "INSERT INTO items (source_id, id, schema_version, title, types, json_path, json_mtime) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("s", "i", 1, "T", "[]", "/p", 0.0),
        )
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO items (source_id, id, schema_version, title, types, json_path, json_mtime) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                ("s", "i", 1, "T", "[]", "/p", 0.0),
            )
    finally:
        conn.close()
