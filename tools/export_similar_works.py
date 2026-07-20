"""export_similar_works.py — CLI : exporte les top-K voisins par item en JSON.

Cf. ADR 0044. Lit ``tools/output/embeddings/embeddings.sqlite`` (produit
par :mod:`embed_items`) et écrit ``tools/output/similar_works/<source>.json``
consommable au build Astro.

Usage typique :

.. code-block:: bash

    python tools/export_similar_works.py --source un-bon-moment
    python tools/export_similar_works.py --source un-bon-moment --k 8
    python tools/export_similar_works.py --source un-bon-moment --dry-run

Le JSON exporté suit le schéma défini dans ADR 0044 § "Build-time export
Python". Écriture atomique via :func:`common.atomic_write_text` ; le
lockfile pipeline (`review_lock`) protège contre un ``embed_items``
concurrent.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from common import OUTPUT_DIR, atomic_write_text, log
from embeddings.recommend import SimilarityRecommender
from embeddings.store import EmbeddingStore
from review_lock import acquire_pipeline_lock

DEFAULT_DB_PATH: Path = OUTPUT_DIR / "embeddings" / "embeddings.sqlite"
DEFAULT_OUTPUT_DIR: Path = OUTPUT_DIR / "similar_works"
DEFAULT_K: int = 6
SCHEMA_VERSION: int = 1

EXIT_OK = 0
EXIT_ERROR = 1


@dataclass(frozen=True, slots=True)
class ExportOptions:
    """Options d'un export — validées au constructeur."""

    source_id: str
    db_path: Path
    output_dir: Path
    k: int
    dry_run: bool

    def __post_init__(self) -> None:
        if not self.source_id:
            raise ValueError("--source ne peut pas être vide")
        if self.k < 1:
            raise ValueError(f"--k doit être >= 1 (reçu {self.k})")


def export_similar_works(
    opts: ExportOptions,
    *,
    store_factory: Callable[[Path], EmbeddingStore] | None = None,
    now_iso: Callable[[], str] | None = None,
    logger: logging.Logger | None = None,
) -> tuple[int, dict[str, list[dict[str, float | str]]]]:
    """Exécute l'export. Tout injectable pour les tests.

    Returns ``(n_items, mapping)`` où ``mapping[item_id] = [{id, score}, ...]``.
    En ``dry_run`` : pas d'écriture sur disque.
    """
    lg = logger or log
    factory = store_factory or (lambda p: EmbeddingStore(p))
    iso = now_iso or (lambda: datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))

    if not opts.db_path.exists():
        lg.error("DB embeddings absente: %s", opts.db_path)
        return 0, {}

    store = factory(opts.db_path)
    try:
        recommender = SimilarityRecommender(store)
        mapping: dict[str, list[dict[str, float | str]]] = {}
        # Modèle "principal" — on prend le premier rencontré (cas typique :
        # une seule famille d'embeddings active par source ; cf. ADR 0033).
        model_seen: str | None = None
        n = 0
        for emb in store.iter_source(opts.source_id):
            if model_seen is None:
                model_seen = emb.model
            recos = recommender.top_k(
                opts.source_id, emb.id, k=opts.k, model=model_seen
            )
            if not recos:
                continue
            mapping[emb.id] = [
                {"id": r.item_id, "score": float(r.score)} for r in recos
            ]
            n += 1
    finally:
        store.close()

    payload = {
        "schemaVersion": SCHEMA_VERSION,
        "source": opts.source_id,
        "model": model_seen or "",
        "k": opts.k,
        "generated_at": iso(),
        "items": mapping,
    }

    if opts.dry_run:
        lg.info("[dry-run] %d items, model=%s", n, model_seen)
        return n, mapping

    out_path = opts.output_dir / f"{opts.source_id}.json"
    payload_text = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    atomic_write_text(out_path, payload_text)
    lg.info("Écrit %d items → %s", n, out_path)
    return n, mapping


def _parse_args(argv: list[str]) -> ExportOptions:
    p = argparse.ArgumentParser(
        description="Exporte les top-K voisins sémantiques en JSON (cf. ADR 0044)."
    )
    p.add_argument("--source", required=True, help="Identifiant de source (ex: un-bon-moment)")
    p.add_argument("--db", type=Path, default=DEFAULT_DB_PATH, help="Chemin embeddings.sqlite")
    p.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    p.add_argument("--k", type=int, default=DEFAULT_K)
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args(argv)
    return ExportOptions(
        source_id=args.source,
        db_path=args.db,
        output_dir=args.output_dir,
        k=args.k,
        dry_run=args.dry_run,
    )


def main(argv: list[str] | None = None) -> int:
    try:
        opts = _parse_args(argv if argv is not None else sys.argv[1:])
    except (ValueError, SystemExit) as exc:
        if isinstance(exc, SystemExit):
            raise
        log.error("%s", exc)
        return EXIT_ERROR

    try:
        with acquire_pipeline_lock():
            export_similar_works(opts)
    except Exception as exc:  # noqa: BLE001 — top-level CLI guard
        log.error("Export échoué: %s", exc)
        return EXIT_ERROR
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
