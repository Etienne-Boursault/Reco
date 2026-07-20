"""Tests CLI tools/build_cache.py."""
from __future__ import annotations

import contextlib
from pathlib import Path

import pytest

import build_cache
from cache.reader import CacheReader


@pytest.fixture
def cli_env(
    tmp_path: Path,
    fake_content_dirs: tuple[Path, Path, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> Path:
    """Patche les chemins module-level pour pointer le mini-dataset.

    Renvoie le chemin du fichier DB attendu (sous tmp_path).
    """
    items_dir, mentions_dir, episodes_dir = fake_content_dirs
    db_path = tmp_path / "cache" / "reco.sqlite"
    monkeypatch.setattr(build_cache, "_ITEMS_DIR", items_dir)
    monkeypatch.setattr(build_cache, "_MENTIONS_DIR", mentions_dir)
    monkeypatch.setattr(build_cache, "_EPISODES_DIR", episodes_dir)
    monkeypatch.setattr(build_cache, "_DEFAULT_DB_PATH", db_path)

    # Lock no-op (évite collision avec un éventuel review_server).
    @contextlib.contextmanager
    def _fake_lock(force: bool = False):
        yield

    monkeypatch.setattr(build_cache, "acquire_pipeline_lock", _fake_lock)
    return db_path


def _common_args(db: Path) -> list[str]:
    return ["--db", str(db), "--allow-unsafe-db-path"]


class TestCli:
    def test_run_all_sources(self, cli_env: Path) -> None:
        rc = build_cache.main(["--source", "all", *_common_args(cli_env)])
        assert rc == 0
        assert cli_env.exists()
        with CacheReader(cli_env) as r:
            # 2 sources fixtures.
            assert r.get_item("podcast-a", "item-001") is not None
            assert r.get_item("podcast-b", "item-B1") is not None

    def test_run_single_source(self, cli_env: Path) -> None:
        rc = build_cache.main(
            ["--source", "podcast-a", *_common_args(cli_env)]
        )
        assert rc == 0
        with CacheReader(cli_env) as r:
            assert r.get_item("podcast-a", "item-001") is not None
            assert r.get_item("podcast-b", "item-B1") is None

    def test_vacuum_flag(self, cli_env: Path) -> None:
        rc = build_cache.main(
            ["--source", "all", *_common_args(cli_env), "--vacuum"]
        )
        assert rc == 0
        assert cli_env.exists()

    def test_optimize_flag(self, cli_env: Path) -> None:
        rc = build_cache.main(
            ["--source", "all", *_common_args(cli_env), "--optimize"]
        )
        assert rc == 0
        assert cli_env.exists()

    def test_force_flag(self, cli_env: Path) -> None:
        rc = build_cache.main(
            ["--source", "all", *_common_args(cli_env), "--force"]
        )
        assert rc == 0

    def test_server_lock_busy_returns_1(
        self,
        cli_env: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from review_lock import ServerLockBusy

        @contextlib.contextmanager
        def _busy_lock(force: bool = False):
            raise ServerLockBusy("server tient le verrou")
            yield  # pragma: no cover

        monkeypatch.setattr(build_cache, "acquire_pipeline_lock", _busy_lock)
        rc = build_cache.main(["--source", "all", *_common_args(cli_env)])
        assert rc == 1
        assert not cli_env.exists()

    def test_default_db_path_used_when_omitted(
        self, cli_env: Path
    ) -> None:
        # `cli_env` a patché `_DEFAULT_DB_PATH` → on n'envoie pas `--db`.
        # Avec `--allow-unsafe-db-path` on contourne la whitelist OUTPUT_DIR
        # car le défaut patché est sous tmp_path.
        rc = build_cache.main(["--source", "all", "--allow-unsafe-db-path"])
        assert rc == 0
        assert cli_env.exists()

    def test_db_outside_output_dir_rejected(self, cli_env: Path) -> None:
        # Sans --allow-unsafe-db-path, un chemin hors OUTPUT_DIR est refusé
        # (mitigation path-traversal — CR senior C4).
        rc = build_cache.main(["--source", "all", "--db", str(cli_env)])
        assert rc == 1
        assert not cli_env.exists()
