"""tests pour le CLI tools/embed_items.py.

Tous les tests mockent l'Encoder (jamais de download fastembed en CI).
On utilise un items_root tmp pour ne pas dépendre de src/content/.
"""
from __future__ import annotations

import contextlib
import json
import sys
from pathlib import Path

import numpy as np
import pytest

import embed_items
from embed_items import (
    EmbedRunOptions,
    _build_parser,
    _discover_sources,
    _iter_items_for_source,
    _resolve_sources,
    main,
    run_embed,
)
from _embed_fakes import FakeEncoder
from embeddings.store import EmbeddingStore


# ---------- helpers ----------------------------------------------------------


def _make_items_root(tmp_path: Path, source_id: str, items: list[dict]) -> Path:
    root = tmp_path / "items_root"
    sub = root / source_id
    sub.mkdir(parents=True, exist_ok=True)
    for it in items:
        (sub / f"{it['id']}.json").write_text(
            json.dumps(it, ensure_ascii=False), encoding="utf-8"
        )
    return root


def _opts(
    *,
    sources: tuple[str, ...] = ("s1",),
    db_path: Path,
    items_root: Path,
    dry_run: bool = False,
    force: bool = False,
    export_dedup: bool = False,
    threshold: float = 0.85,
    batch: int = 64,
) -> EmbedRunOptions:
    return EmbedRunOptions(
        sources=sources,
        db_path=db_path,
        model_name="fake-test",
        batch_size=batch,
        force=force,
        dry_run=dry_run,
        dedup_threshold=threshold,
        export_dedup=export_dedup,
        dedup_dir=db_path.parent,
        items_root=items_root,
    )


def _encoder_factory(_name: str) -> FakeEncoder:
    return FakeEncoder()


# ---------- iter_items_for_source -------------------------------------------


def test_iter_items_skips_missing_dir(tmp_path: Path) -> None:
    assert list(_iter_items_for_source("nope", items_root=tmp_path)) == []


def test_iter_items_skips_dunder_and_dot_files(tmp_path: Path) -> None:
    root = _make_items_root(tmp_path, "s", [{"id": "a", "title": "X"}])
    (root / "s" / "__schema.json").write_text("{}", encoding="utf-8")
    (root / "s" / ".hidden.json").write_text("{}", encoding="utf-8")
    (root / "s" / "notes.txt").write_text("noise", encoding="utf-8")
    payloads = list(_iter_items_for_source("s", items_root=root))
    assert [p.id for p in payloads] == ["a"]


def test_iter_items_skips_invalid_json(tmp_path: Path) -> None:
    root = _make_items_root(tmp_path, "s", [{"id": "a", "title": "X"}])
    (root / "s" / "bad.json").write_text("{not-json", encoding="utf-8")
    payloads = list(_iter_items_for_source("s", items_root=root))
    assert [p.id for p in payloads] == ["a"]


def test_iter_items_skips_missing_id_or_title(tmp_path: Path) -> None:
    root = _make_items_root(
        tmp_path,
        "s",
        [
            {"id": "a", "title": "Ok"},
            {"id": "no-title"},  # missing title
        ],
    )
    # Ajoute manuellement un fichier où le champ "id" du JSON est absent
    # (l'écriture _make_items_root indexait par 'id', donc on contourne).
    (root / "s" / "no_id.json").write_text(
        json.dumps({"title": "no-id"}), encoding="utf-8"
    )
    payloads = list(_iter_items_for_source("s", items_root=root))
    assert [p.id for p in payloads] == ["a"]


def test_iter_items_skips_blank_title(tmp_path: Path) -> None:
    root = _make_items_root(
        tmp_path, "s", [{"id": "a", "title": "  "}, {"id": "b", "title": "Ok"}]
    )
    payloads = list(_iter_items_for_source("s", items_root=root))
    assert [p.id for p in payloads] == ["b"]


def test_iter_items_uses_creator_types_description(tmp_path: Path) -> None:
    root = _make_items_root(
        tmp_path,
        "s",
        [
            {
                "id": "a",
                "title": "Mortel",
                "creator": "FG",
                "types": ["serie", "drama", 0, ""],
                "description": "Une série",
            }
        ],
    )
    payloads = list(_iter_items_for_source("s", items_root=root))
    assert "Mortel | FG | serie, drama | Une série" == payloads[0].text


# ---------- discover_sources & resolve_sources ------------------------------


def test_discover_sources(tmp_path: Path) -> None:
    root = tmp_path / "items"
    (root / "src-a").mkdir(parents=True)
    (root / "src-b").mkdir(parents=True)
    (root / "loose.txt").write_text("", encoding="utf-8")
    assert _discover_sources(root) == ["src-a", "src-b"]


def test_discover_sources_missing(tmp_path: Path) -> None:
    assert _discover_sources(tmp_path / "absent") == []


def test_resolve_sources_named(tmp_path: Path) -> None:
    assert _resolve_sources("mySource", tmp_path) == ("mySource",)


def test_resolve_sources_all(tmp_path: Path) -> None:
    (tmp_path / "x").mkdir()
    (tmp_path / "y").mkdir()
    assert _resolve_sources("all", tmp_path) == ("x", "y")


def test_resolve_sources_all_empty_raises(tmp_path: Path) -> None:
    with pytest.raises(SystemExit):
        _resolve_sources("all", tmp_path)


# ---------- run_embed --------------------------------------------------------


def test_run_embed_dry_run(tmp_path: Path) -> None:
    root = _make_items_root(
        tmp_path, "s1", [{"id": "a", "title": "X"}, {"id": "b", "title": "Y"}]
    )
    db = tmp_path / "emb.sqlite"
    code, stats = run_embed(
        _opts(db_path=db, items_root=root, dry_run=True),
        encoder_factory=_encoder_factory,
    )
    assert code == 0
    assert stats.n_seen == 2
    assert stats.n_embedded == 0
    assert not db.exists()  # dry-run n'ouvre PAS le store


def test_run_embed_encodes_and_persists(tmp_path: Path) -> None:
    root = _make_items_root(
        tmp_path, "s1", [{"id": "a", "title": "X"}, {"id": "b", "title": "Y"}]
    )
    db = tmp_path / "emb.sqlite"
    code, stats = run_embed(
        _opts(db_path=db, items_root=root), encoder_factory=_encoder_factory
    )
    assert code == 0
    assert stats.n_embedded == 2
    store = EmbeddingStore(db)
    try:
        assert store.count("s1") == 2
    finally:
        store.close()


def test_run_embed_is_idempotent(tmp_path: Path) -> None:
    root = _make_items_root(tmp_path, "s1", [{"id": "a", "title": "X"}])
    db = tmp_path / "emb.sqlite"
    run_embed(_opts(db_path=db, items_root=root), encoder_factory=_encoder_factory)
    # 2e run : tout doit être skippé.
    _, stats = run_embed(
        _opts(db_path=db, items_root=root), encoder_factory=_encoder_factory
    )
    assert stats.n_skipped == 1
    assert stats.n_embedded == 0


def test_run_embed_force_reembeds(tmp_path: Path) -> None:
    root = _make_items_root(tmp_path, "s1", [{"id": "a", "title": "X"}])
    db = tmp_path / "emb.sqlite"
    run_embed(_opts(db_path=db, items_root=root), encoder_factory=_encoder_factory)
    _, stats = run_embed(
        _opts(db_path=db, items_root=root, force=True),
        encoder_factory=_encoder_factory,
    )
    assert stats.n_embedded == 1
    assert stats.n_skipped == 0


def test_run_embed_skips_when_title_changes_then_reembeds(tmp_path: Path) -> None:
    root = _make_items_root(tmp_path, "s1", [{"id": "a", "title": "X"}])
    db = tmp_path / "emb.sqlite"
    run_embed(_opts(db_path=db, items_root=root), encoder_factory=_encoder_factory)
    # Modifie le titre → source_hash change → re-embed.
    (root / "s1" / "a.json").write_text(
        json.dumps({"id": "a", "title": "Y"}), encoding="utf-8"
    )
    _, stats = run_embed(
        _opts(db_path=db, items_root=root), encoder_factory=_encoder_factory
    )
    assert stats.n_embedded == 1


def test_run_embed_empty_source(tmp_path: Path) -> None:
    db = tmp_path / "emb.sqlite"
    code, stats = run_embed(
        _opts(db_path=db, items_root=tmp_path / "nothing"),
        encoder_factory=_encoder_factory,
    )
    assert code == 0
    assert stats.n_embedded == 0 and stats.n_seen == 0


def test_run_embed_export_dedup(tmp_path: Path) -> None:
    """2 items à texte identique → vecteurs identiques → paire détectée."""
    root = _make_items_root(
        tmp_path,
        "s1",
        [
            {"id": "tombeau", "title": "Tombeau des lucioles"},
            # Texte différent mais on s'assure que SimplyAndsimilar pour test
            # le FakeEncoder utilise un hash : on met DEUX items avec EXACT
            # même titre pour garantir cosine=1.
            {"id": "grave", "title": "Tombeau des lucioles"},
        ],
    )
    db = tmp_path / "emb.sqlite"
    code, stats = run_embed(
        _opts(db_path=db, items_root=root, export_dedup=True, threshold=0.99),
        encoder_factory=_encoder_factory,
    )
    assert code == 0
    out_file = db.parent / "dedup_suggestions_s1.json"
    assert out_file.exists()
    payload = json.loads(out_file.read_text(encoding="utf-8"))
    assert payload["source_id"] == "s1"
    assert payload["threshold"] == 0.99
    assert len(payload["pairs"]) == 1
    pair = payload["pairs"][0]
    assert set([pair["a"], pair["b"]]) == {"tombeau", "grave"}
    assert pair["titles"] == ["Tombeau des lucioles", "Tombeau des lucioles"]
    assert stats.n_dedup_pairs == 1


def test_run_embed_encoder_size_mismatch_raises(tmp_path: Path) -> None:
    root = _make_items_root(tmp_path, "s1", [{"id": "a", "title": "X"}])
    db = tmp_path / "emb.sqlite"

    class BrokenEncoder(FakeEncoder):
        def encode(self, texts):  # type: ignore[override]
            return np.zeros((0, self.dim), dtype=np.float32)

    with pytest.raises(RuntimeError, match="vecteurs"):
        run_embed(
            _opts(db_path=db, items_root=root),
            encoder_factory=lambda _: BrokenEncoder(),
        )


def test_run_embed_batches(tmp_path: Path) -> None:
    items = [{"id": f"i{i:03d}", "title": f"T{i}"} for i in range(10)]
    root = _make_items_root(tmp_path, "s1", items)
    db = tmp_path / "emb.sqlite"
    _, stats = run_embed(
        _opts(db_path=db, items_root=root, batch=3),
        encoder_factory=_encoder_factory,
    )
    assert stats.n_embedded == 10


# ---------- options validation ----------------------------------------------


def test_options_invalid_batch_size(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        EmbedRunOptions(
            sources=("s",), db_path=tmp_path / "x", model_name="m",
            batch_size=0, force=False, dry_run=False,
            dedup_threshold=0.5, export_dedup=False,
            dedup_dir=tmp_path, items_root=tmp_path,
        )


def test_options_invalid_threshold(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        EmbedRunOptions(
            sources=("s",), db_path=tmp_path / "x", model_name="m",
            batch_size=1, force=False, dry_run=False,
            dedup_threshold=2.0, export_dedup=False,
            dedup_dir=tmp_path, items_root=tmp_path,
        )


# ---------- parser ----------------------------------------------------------


def test_parser_defaults() -> None:
    ns = _build_parser().parse_args(["--source", "s"])
    assert ns.source == "s"
    assert ns.batch_size == 64
    assert ns.dedup_threshold == 0.85
    assert ns.dry_run is False


# ---------- main() ----------------------------------------------------------


@contextlib.contextmanager
def _noop_lock(force: bool = False):  # noqa: ARG001
    yield


def test_main_dry_run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = _make_items_root(tmp_path, "s1", [{"id": "a", "title": "X"}])
    db = tmp_path / "emb.sqlite"
    # Patch lock + encoder.
    import review_lock

    monkeypatch.setattr(review_lock, "acquire_pipeline_lock", _noop_lock)
    monkeypatch.setattr(
        embed_items,
        "_resolve_sources",
        lambda src, root: ("s1",),
    )
    rc = main(
        [
            "--source",
            "s1",
            "--db",
            str(db),
            "--items-root",
            str(root),
            "--dry-run",
            "--model",
            "fake-test",
        ]
    )
    assert rc == 0
    assert not db.exists()


def test_main_real_run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = _make_items_root(tmp_path, "s1", [{"id": "a", "title": "X"}])
    db = tmp_path / "emb.sqlite"
    import review_lock

    monkeypatch.setattr(review_lock, "acquire_pipeline_lock", _noop_lock)
    # Remplace FastEmbedEncoder par notre Fake.
    from embeddings import encoder as encoder_mod

    monkeypatch.setattr(encoder_mod, "FastEmbedEncoder", FakeEncoder)
    rc = main(
        [
            "--source",
            "s1",
            "--db",
            str(db),
            "--items-root",
            str(root),
            "--model",
            "fake-test",
        ]
    )
    assert rc == 0
    assert db.exists()


def test_main_server_lock_busy(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = _make_items_root(tmp_path, "s1", [{"id": "a", "title": "X"}])
    db = tmp_path / "emb.sqlite"
    import review_lock

    @contextlib.contextmanager
    def _busy(force: bool = False):  # noqa: ARG001
        raise review_lock.ServerLockBusy("server tourne")
        yield  # pragma: no cover

    monkeypatch.setattr(review_lock, "acquire_pipeline_lock", _busy)
    rc = main(
        [
            "--source",
            "s1",
            "--db",
            str(db),
            "--items-root",
            str(root),
            "--dry-run",
        ]
    )
    assert rc == 1
