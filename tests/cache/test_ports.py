"""Tests cache.ports — runtime_checkable Protocols."""
from __future__ import annotations

from pathlib import Path
from typing import Iterable

from cache.builder import CacheBuilder, _FsJsonLoader
from cache.ports import CacheBackend, JsonLoader


class TestJsonLoaderProtocol:
    def test_fs_loader_satisfies(self) -> None:
        loader = _FsJsonLoader()
        assert isinstance(loader, JsonLoader)

    def test_custom_loader_satisfies(self) -> None:
        class _Mem:
            def iter_files(self, root: Path) -> Iterable[Path]:
                return ()

            def read(self, path: Path) -> dict:
                return {}

            def mtime(self, path: Path) -> float:
                return 0.0

        assert isinstance(_Mem(), JsonLoader)

    def test_partial_impl_not_loader(self) -> None:
        class _Bad:
            def iter_files(self, root: Path) -> Iterable[Path]:
                return ()

        assert not isinstance(_Bad(), JsonLoader)


class TestCacheBackendProtocol:
    def test_builder_satisfies(self, tmp_path: Path) -> None:
        builder = CacheBuilder(
            db_path=tmp_path / "x.sqlite",
            items_dir=tmp_path / "items",
            mentions_dir=tmp_path / "mentions",
            episodes_dir=tmp_path / "episodes",
        )
        assert isinstance(builder, CacheBackend)
