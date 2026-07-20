"""Tests CLI ``tools.export_similar_works`` — ADR 0044."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from embeddings.store import EmbeddingStore
from export_similar_works import (
    DEFAULT_K,
    SCHEMA_VERSION,
    ExportOptions,
    export_similar_works,
)


def _seed_store(store: EmbeddingStore, source: str = "s") -> None:
    """3 items : a ~ b proches, c orthogonal."""
    common = dict(model="m", dim=2, source_hash="h", embedded_at="t")
    store.upsert(
        source_id=source, id="a",
        vector=np.array([1.0, 0.0], dtype=np.float32), **common,
    )
    store.upsert(
        source_id=source, id="b",
        vector=np.array([0.99, 0.01], dtype=np.float32), **common,
    )
    store.upsert(
        source_id=source, id="c",
        vector=np.array([0.0, 1.0], dtype=np.float32), **common,
    )


@pytest.fixture
def seeded_db(tmp_path: Path) -> Path:
    db = tmp_path / "embeddings.sqlite"
    store = EmbeddingStore(db)
    try:
        _seed_store(store)
    finally:
        store.close()
    return db


class TestExportOptions:
    def test_validates_empty_source(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError):
            ExportOptions(
                source_id="", db_path=tmp_path / "x.sqlite",
                output_dir=tmp_path, k=5, dry_run=True,
            )

    def test_validates_k_lower_bound(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError):
            ExportOptions(
                source_id="s", db_path=tmp_path / "x.sqlite",
                output_dir=tmp_path, k=0, dry_run=True,
            )


class TestExportSimilarWorks:
    def test_writes_json_with_expected_schema(
        self, seeded_db: Path, tmp_path: Path
    ) -> None:
        out_dir = tmp_path / "out"
        opts = ExportOptions(
            source_id="s", db_path=seeded_db,
            output_dir=out_dir, k=2, dry_run=False,
        )
        n, mapping = export_similar_works(opts, now_iso=lambda: "2026-06-12T10:00:00Z")
        assert n == 3
        out_file = out_dir / "s.json"
        assert out_file.exists()
        payload = json.loads(out_file.read_text(encoding="utf-8"))
        assert payload["schemaVersion"] == SCHEMA_VERSION
        assert payload["source"] == "s"
        assert payload["k"] == 2
        assert payload["model"] == "m"
        assert payload["generated_at"] == "2026-06-12T10:00:00Z"
        assert "a" in payload["items"]
        # 'a' doit avoir 'b' en premier voisin (cosine).
        assert payload["items"]["a"][0]["id"] == "b"
        assert payload["items"]["a"][0]["score"] > 0.9

    def test_dry_run_does_not_write(
        self, seeded_db: Path, tmp_path: Path
    ) -> None:
        out_dir = tmp_path / "out"
        opts = ExportOptions(
            source_id="s", db_path=seeded_db,
            output_dir=out_dir, k=2, dry_run=True,
        )
        n, mapping = export_similar_works(opts)
        assert n == 3
        assert not out_dir.exists() or not (out_dir / "s.json").exists()
        # mapping retourné quand même
        assert "a" in mapping

    def test_missing_db_returns_zero(self, tmp_path: Path) -> None:
        opts = ExportOptions(
            source_id="s", db_path=tmp_path / "ghost.sqlite",
            output_dir=tmp_path / "out", k=2, dry_run=True,
        )
        n, mapping = export_similar_works(opts)
        assert n == 0
        assert mapping == {}

    def test_empty_source_yields_empty_mapping(self, tmp_path: Path) -> None:
        db = tmp_path / "empty.sqlite"
        EmbeddingStore(db).close()
        opts = ExportOptions(
            source_id="unknown", db_path=db,
            output_dir=tmp_path / "out", k=2, dry_run=True,
        )
        n, mapping = export_similar_works(opts)
        assert n == 0
        assert mapping == {}

    def test_default_k(self) -> None:
        assert DEFAULT_K >= 1
