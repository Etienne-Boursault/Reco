"""Tests CLI ``tools.export_similar_works`` — ADR 0044."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from embeddings.store import EmbeddingStore
from export_similar_works import (
    DEFAULT_DB_PATH,
    DEFAULT_K,
    DEFAULT_OUTPUT_DIR,
    EXIT_ERROR,
    EXIT_OK,
    SCHEMA_VERSION,
    ExportOptions,
    _parse_args,
    export_similar_works,
    main,
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

    def test_item_without_neighbours_is_skipped(self, tmp_path: Path) -> None:
        """Un item seul dans sa source n'a aucun voisin : il est absent du
        mapping (plutôt que présent avec une liste vide, qui alourdirait le
        JSON consommé au build Astro)."""
        import numpy as np

        db = tmp_path / "lonely.sqlite"
        store = EmbeddingStore(db)
        try:
            store.upsert(
                source_id="s", id="seul",
                vector=np.array([1.0, 0.0], dtype=np.float32),
                model="m", dim=2, source_hash="h", embedded_at="t",
            )
        finally:
            store.close()
        opts = ExportOptions(
            source_id="s", db_path=db, output_dir=tmp_path / "out",
            k=3, dry_run=False,
        )

        n, mapping = export_similar_works(opts, now_iso=lambda: "2026-06-12T10:00:00Z")

        assert (n, mapping) == (0, {})
        payload = json.loads((tmp_path / "out" / "s.json").read_text(encoding="utf-8"))
        assert payload["items"] == {}
        assert payload["model"] == "m"  # le modèle reste renseigné


class TestParseArgs:
    def test_defaults(self) -> None:
        opts = _parse_args(["--source", "un-bon-moment"])
        assert opts.source_id == "un-bon-moment"
        assert opts.k == DEFAULT_K
        assert opts.dry_run is False
        assert opts.db_path == DEFAULT_DB_PATH
        assert opts.output_dir == DEFAULT_OUTPUT_DIR

    def test_all_flags(self, tmp_path: Path) -> None:
        opts = _parse_args([
            "--source", "s", "--db", str(tmp_path / "e.sqlite"),
            "--output-dir", str(tmp_path / "out"), "--k", "8", "--dry-run",
        ])
        assert opts.db_path == tmp_path / "e.sqlite"
        assert opts.output_dir == tmp_path / "out"
        assert (opts.k, opts.dry_run) == (8, True)

    def test_source_is_required(self) -> None:
        with pytest.raises(SystemExit):
            _parse_args([])

    def test_invalid_k_raises_value_error(self) -> None:
        with pytest.raises(ValueError, match="--k doit être >= 1"):
            _parse_args(["--source", "s", "--k", "0"])


class TestMain:
    def test_returns_ok_and_holds_the_pipeline_lock(
        self, monkeypatch, seeded_db: Path, tmp_path: Path
    ) -> None:
        """L'export tourne SOUS le verrou pipeline (un `embed_items` concurrent
        réécrirait la base sous nos pieds)."""
        import contextlib

        import export_similar_works as esw

        events: list[str] = []

        @contextlib.contextmanager
        def _lock():
            events.append("lock")
            yield
            events.append("unlock")

        monkeypatch.setattr(esw, "acquire_pipeline_lock", _lock)
        real_export = esw.export_similar_works
        monkeypatch.setattr(
            esw, "export_similar_works",
            lambda opts: events.append("export") or real_export(opts),
        )

        code = main(["--source", "s", "--db", str(seeded_db),
                     "--output-dir", str(tmp_path / "out")])

        assert code == EXIT_OK
        assert events == ["lock", "export", "unlock"]
        assert (tmp_path / "out" / "s.json").exists()

    def test_returns_error_on_invalid_option(self) -> None:
        assert main(["--source", "s", "--k", "-1"]) == EXIT_ERROR

    def test_propagates_argparse_exit(self) -> None:
        """`--help` / argument manquant : on laisse argparse sortir avec son
        propre code plutôt que de le convertir en EXIT_ERROR silencieux."""
        with pytest.raises(SystemExit):
            main([])

    def test_returns_error_when_export_raises(self, monkeypatch, seeded_db: Path,
                                              tmp_path: Path) -> None:
        import contextlib

        import export_similar_works as esw

        monkeypatch.setattr(esw, "acquire_pipeline_lock", contextlib.nullcontext)

        def _boom(opts):
            raise RuntimeError("base corrompue")

        monkeypatch.setattr(esw, "export_similar_works", _boom)

        assert main(["--source", "s", "--db", str(seeded_db)]) == EXIT_ERROR

    def test_returns_error_when_lock_is_busy(self, monkeypatch,
                                             seeded_db: Path) -> None:
        import export_similar_works as esw
        from review_lock import ServerLockBusy

        def _busy():
            raise ServerLockBusy("le review_server tourne")

        monkeypatch.setattr(esw, "acquire_pipeline_lock", _busy)

        assert main(["--source", "s", "--db", str(seeded_db)]) == EXIT_ERROR
