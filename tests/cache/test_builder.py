"""Tests cache.builder — build complet, par source, refresh, vacuum, stats."""
from __future__ import annotations

import sqlite3
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from cache.builder import (
    BuildStats,
    CacheBuilder,
    _FsJsonLoader,
    _normalize_recommended_by,
    _parse_timestamp_to_seconds,
    _safe_str_list,
    _try_git_sha,
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


# ---------- helpers purs : cas limites -------------------------------------


class TestParseTimestampEdgeCases:
    def test_bool_is_not_a_timestamp(self) -> None:
        """`True` est un `int` en Python : sans garde explicite, il vaudrait
        1 seconde. On le rejette."""
        assert _parse_timestamp_to_seconds(True) is None
        assert _parse_timestamp_to_seconds(False) is None

    def test_too_many_parts_is_rejected(self) -> None:
        assert _parse_timestamp_to_seconds("1:2:3:4") is None

    def test_empty_string_is_rejected(self) -> None:
        assert _parse_timestamp_to_seconds("") is None

    def test_unsupported_type_is_rejected(self) -> None:
        assert _parse_timestamp_to_seconds({"h": 1}) is None
        assert _parse_timestamp_to_seconds(["00:01:00"]) is None


class TestNormalizeRecommendedBy:
    def test_collapses_whitespace_and_lowercases(self) -> None:
        assert _normalize_recommended_by("  Bong   Joon-ho \n") == "bong joon-ho"

    def test_none_and_blank_become_none(self) -> None:
        assert _normalize_recommended_by(None) is None
        assert _normalize_recommended_by("   ") is None

    def test_non_string_becomes_none(self) -> None:
        """Le champ vient de JSON libre : un nombre ou une liste ne doit pas
        faire planter la dédup."""
        assert _normalize_recommended_by(42) is None
        assert _normalize_recommended_by(["Bong"]) is None


class TestSafeStrList:
    def test_non_list_becomes_empty(self) -> None:
        assert _safe_str_list("Kyan") == []
        assert _safe_str_list(None) == []

    def test_strips_and_drops_empty_entries(self) -> None:
        assert _safe_str_list([" Kyan ", "", None, "  ", "Navo"]) == [
            "Kyan", "Navo",
        ]

    def test_coerces_non_string_entries(self) -> None:
        assert _safe_str_list([1, 2.5]) == ["1", "2.5"]


class TestTryGitSha:
    def test_returns_none_when_git_is_absent(self, monkeypatch) -> None:
        def _no_git(*a, **k):
            raise FileNotFoundError("git introuvable")

        monkeypatch.setattr(subprocess, "run", _no_git)
        assert _try_git_sha() is None

    def test_returns_none_on_non_zero_exit(self, monkeypatch) -> None:
        """Hors dépôt Git (ex. tarball de release) : `rev-parse` sort en 128."""
        monkeypatch.setattr(
            subprocess, "run",
            lambda *a, **k: SimpleNamespace(returncode=128, stdout=""),
        )
        assert _try_git_sha() is None

    def test_returns_none_on_empty_output(self, monkeypatch) -> None:
        monkeypatch.setattr(
            subprocess, "run",
            lambda *a, **k: SimpleNamespace(returncode=0, stdout="  \n"),
        )
        assert _try_git_sha() is None

    def test_returns_the_sha(self, monkeypatch) -> None:
        monkeypatch.setattr(
            subprocess, "run",
            lambda *a, **k: SimpleNamespace(returncode=0, stdout="abc123\n"),
        )
        assert _try_git_sha() == "abc123"


# ---------- _warn : logger injecté vs repli stderr --------------------------


class TestWarn:
    def _builder(self, tmp_path: Path, logger=None) -> CacheBuilder:
        return CacheBuilder(
            db_path=tmp_path / "c.sqlite",
            items_dir=tmp_path / "items",
            mentions_dir=tmp_path / "mentions",
            episodes_dir=tmp_path / "episodes",
            logger=logger,
        )

    def test_uses_the_injected_logger(self, tmp_path: Path) -> None:
        seen = []
        b = self._builder(tmp_path, logger=lambda msg, *a: seen.append((msg, a)))
        b._warn("Skip %s: %s", "x.json", "boom")

        assert seen == [("Skip %s: %s", ("x.json", "boom"))]

    def test_falls_back_to_stdout_without_logger(
        self, tmp_path: Path, capsys
    ) -> None:
        b = self._builder(tmp_path)
        b._warn("Skip %s: %s", "x.json", "boom")

        assert "Skip x.json: boom" in capsys.readouterr().out

    def test_falls_back_when_the_logger_raises(
        self, tmp_path: Path, capsys
    ) -> None:
        """Un logger défaillant ne doit pas faire échouer un build."""
        def _boom(msg, *a):
            raise RuntimeError("handler cassé")

        b = self._builder(tmp_path, logger=_boom)
        b._warn("Skip %s", "x.json")

        assert "Skip x.json" in capsys.readouterr().out


# ---------- JSON invalide : le build continue et rapporte -------------------


class TestInvalidJsonIsSkipped:
    def _dirs(self, tmp_path: Path) -> tuple[Path, Path, Path]:
        items = tmp_path / "items" / "src-a"
        mentions = tmp_path / "mentions" / "src-a"
        episodes = tmp_path / "episodes" / "src-a"
        for d in (items, mentions, episodes):
            d.mkdir(parents=True)
        return items, mentions, episodes

    def _build(self, tmp_path: Path) -> tuple[BuildStats, CacheBuilder]:
        builder = CacheBuilder(
            db_path=tmp_path / "c.sqlite",
            items_dir=tmp_path / "items",
            mentions_dir=tmp_path / "mentions",
            episodes_dir=tmp_path / "episodes",
            logger=lambda *a: None,
        )
        return builder.build(), builder

    def test_broken_item_is_skipped_and_reported(self, tmp_path: Path) -> None:
        items, _, _ = self._dirs(tmp_path)
        (items / "ok.json").write_text(
            '{"id": "i1", "schemaVersion": 1, "title": "OK", "types": ["film"]}',
            encoding="utf-8",
        )
        (items / "casse.json").write_text("{ pas du JSON", encoding="utf-8")

        stats, builder = self._build(tmp_path)

        assert stats.items == 1  # le fichier sain est bien indexé
        assert any("casse.json" in e for e in builder._errors)

    def test_broken_episode_is_skipped_and_reported(self, tmp_path: Path) -> None:
        _, _, episodes = self._dirs(tmp_path)
        (episodes / "ok.json").write_text(
            '{"guid": "e1", "schemaVersion": 1, "title": "OK"}',
            encoding="utf-8",
        )
        (episodes / "casse.json").write_text("[", encoding="utf-8")

        stats, builder = self._build(tmp_path)

        assert stats.episodes == 1
        assert any("episodes:" in e and "casse.json" in e for e in builder._errors)

    def test_broken_mention_is_skipped_and_reported(self, tmp_path: Path) -> None:
        items, mentions, episodes = self._dirs(tmp_path)
        (items / "i1.json").write_text(
            '{"id": "i1", "schemaVersion": 1, "title": "OK", "types": ["film"]}',
            encoding="utf-8",
        )
        (episodes / "e1.json").write_text(
            '{"guid": "e1", "schemaVersion": 1, "title": "OK"}',
            encoding="utf-8",
        )
        (mentions / "ok.json").write_text(
            '{"id": "m1", "schemaVersion": 1, "itemId": "i1", "kind": "reco",'
            ' "sourceRef": {"episodeGuid": "e1", "sourceId": "src-a"}}',
            encoding="utf-8",
        )
        (mentions / "casse.json").write_text("{{{", encoding="utf-8")

        stats, builder = self._build(tmp_path)

        assert stats.mentions == 1
        assert any("mentions:" in e and "casse.json" in e for e in builder._errors)
