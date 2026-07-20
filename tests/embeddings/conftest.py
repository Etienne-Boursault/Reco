"""Fixtures partagées pour les tests d'embeddings.

Pas de ``__init__.py`` dans ce dossier : sinon le sous-package shadow
``tools/embeddings/`` dans sys.path (pyproject met `tests/` ET `tools/`
sur le pythonpath).
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from _embed_fakes import FakeEncoder  # noqa: F401 — réexport pour les tests
from embeddings.ports import Encoder
from embeddings.store import EmbeddingStore


@pytest.fixture
def fake_encoder() -> Encoder:
    return FakeEncoder()


@pytest.fixture
def tmp_store(tmp_path: Path):
    db = tmp_path / "emb.sqlite"
    store = EmbeddingStore(db)
    try:
        yield store
    finally:
        store.close()


@pytest.fixture
def items_root_factory(tmp_path: Path):
    def _make(source_id: str, items: list[dict]) -> Path:
        root = tmp_path / "content_items"
        src_dir = root / source_id
        src_dir.mkdir(parents=True, exist_ok=True)
        for it in items:
            (src_dir / f"{it['id']}.json").write_text(
                json.dumps(it, ensure_ascii=False), encoding="utf-8"
            )
        return root

    return _make
