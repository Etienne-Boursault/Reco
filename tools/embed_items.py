"""embed_items.py — CLI : encode les items en vecteurs sémantiques.

Roadmap item #15 / ADR 0033.

Usage typique :

.. code-block:: bash

    python tools/embed_items.py --source un-bon-moment --dry-run
    python tools/embed_items.py --source un-bon-moment
    python tools/embed_items.py --source all --batch-size 128
    python tools/embed_items.py --source un-bon-moment \\
        --export-dedup-json --dedup-threshold 0.85

Idempotence : un item dont ``source_hash`` est inchangé est skippé
(sauf ``--force``). Le ``source_hash`` est calculé sur le texte canonique
``build_input_text(...)`` — sensible aux changements de title/creator/types.

Le CLI tient le ``pipeline_lock`` (cf. ``review_lock``) pendant l'écriture
pour qu'aucun re-extract concurrent n'écrase un fichier item lu en cours
d'embedding.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterator, Sequence

import numpy as np

from common import CONTENT_DIR, OUTPUT_DIR, atomic_write_text, log
from embeddings.dedup import CrossEpisodeDedup
from embeddings.encoder import (
    DEFAULT_MODEL,
    EmbeddingInput,
    build_input_text,
    source_hash,
)
from embeddings.ports import Encoder, StoredEmbedding
from embeddings.settings import EmbeddingsSettings
from embeddings.store import EmbeddingStore

# Sortie par défaut — gitignored (sous OUTPUT_DIR).
DEFAULT_DB_PATH: Path = OUTPUT_DIR / "embeddings" / "embeddings.sqlite"
DEFAULT_DEDUP_DIR: Path = OUTPUT_DIR / "embeddings"

EXIT_OK = 0
EXIT_ERROR = 1


@dataclass(frozen=True, slots=True)
class _ItemPayload:
    """Item lu sur disque, prêt à être embeddé."""

    source_id: str
    id: str
    title: str
    text: str
    text_hash: str


def _iter_items_for_source(
    source_id: str, *, items_root: Path = CONTENT_DIR / "items"
) -> Iterator[_ItemPayload]:
    """Itère les items d'une source depuis ``src/content/items/<source>/``.

    Les fichiers commençant par ``__`` ou ``.`` sont ignorés (convention
    cache builder). On lit l'item *en lecture seule* — aucune écriture.
    """
    src_dir = items_root / source_id
    if not src_dir.exists():
        return
    for path in sorted(src_dir.iterdir()):
        if not path.is_file() or path.suffix != ".json":
            continue
        if path.name.startswith(("__", ".")):
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            log.warning("Item illisible %s: %s", path, exc)
            continue
        item_id = data.get("id")
        title = data.get("title")
        if not isinstance(item_id, str) or not isinstance(title, str):
            log.warning("Item invalide (id/title manquant): %s", path)
            continue
        creator = data.get("creator") if isinstance(data.get("creator"), str) else None
        raw_types = data.get("types")
        types: tuple[str, ...] = ()
        if isinstance(raw_types, list):
            types = tuple(t for t in raw_types if isinstance(t, str) and t)
        description = (
            data.get("description")
            if isinstance(data.get("description"), str)
            else None
        )
        try:
            text = build_input_text(
                EmbeddingInput(
                    title=title,
                    creator=creator,
                    types=types,
                    description=description,
                )
            )
        except ValueError:
            log.warning("Item sans titre exploitable: %s", path)
            continue
        yield _ItemPayload(
            source_id=source_id,
            id=item_id,
            title=title,
            text=text,
            text_hash=source_hash(text),
        )


def _discover_sources(items_root: Path) -> list[str]:
    """Liste les sources présentes sous ``src/content/items/``."""
    if not items_root.exists():
        return []
    return sorted(p.name for p in items_root.iterdir() if p.is_dir())


@dataclass(frozen=True, slots=True)
class EmbedRunOptions:
    """Options d'un run CLI ``embed_items``."""

    sources: tuple[str, ...]
    db_path: Path
    model_name: str
    batch_size: int
    force: bool
    dry_run: bool
    dedup_threshold: float
    export_dedup: bool
    dedup_dir: Path
    items_root: Path

    def __post_init__(self) -> None:
        if self.batch_size <= 0:
            raise ValueError(f"--batch-size doit être > 0 (reçu {self.batch_size})")
        if not (-1.0 <= self.dedup_threshold <= 1.0):
            raise ValueError(
                f"--dedup-threshold doit être dans [-1,1] (reçu {self.dedup_threshold})"
            )


@dataclass(slots=True)
class EmbedRunStats:
    """Statistiques d'un run."""

    n_seen: int = 0
    n_skipped: int = 0
    n_embedded: int = 0
    n_dedup_pairs: int = 0
    duration_s: float = 0.0


def _batched(seq: list[_ItemPayload], n: int) -> Iterator[list[_ItemPayload]]:
    for i in range(0, len(seq), n):
        yield seq[i : i + n]


def run_embed(
    opts: EmbedRunOptions,
    *,
    encoder_factory: Callable[[str], Encoder],
    store_factory: Callable[[Path], EmbeddingStore] | None = None,
    now_iso: Callable[[], str] | None = None,
    logger: logging.Logger | None = None,
) -> tuple[int, EmbedRunStats]:
    """Exécute un run. Tout injectable pour les tests.

    ``encoder_factory(model_name)`` est appelé UNE seule fois, et
    uniquement si on a quelque chose à encoder (en mode ``--dry-run`` ou
    si tout est déjà à jour, on ne charge même pas le modèle — économise
    le démarrage fastembed en CI).
    """
    out_log = logger or log
    stats = EmbedRunStats()
    t0 = time.perf_counter()
    store_open = store_factory or (lambda p: EmbeddingStore(p))
    now = now_iso or (lambda: datetime.now(timezone.utc).isoformat(timespec="seconds"))

    if opts.dry_run:
        for source_id in opts.sources:
            for item in _iter_items_for_source(source_id, items_root=opts.items_root):
                stats.n_seen += 1
        stats.duration_s = time.perf_counter() - t0
        out_log.info(
            "Dry-run : %d item(s) candidat(s) sur %d source(s).",
            stats.n_seen,
            len(opts.sources),
        )
        return EXIT_OK, stats

    store = store_open(opts.db_path)
    encoder: Encoder | None = None
    try:
        for source_id in opts.sources:
            items = list(_iter_items_for_source(source_id, items_root=opts.items_root))
            stats.n_seen += len(items)
            if not items:
                out_log.info("Source %s : 0 item.", source_id)
                continue

            # Filtre idempotent : skip si source_hash inchangé et même modèle.
            to_embed: list[_ItemPayload] = []
            if opts.force:
                to_embed = items
            else:
                for it in items:
                    existing = store.get(it.source_id, it.id)
                    if (
                        existing is not None
                        and existing.model == opts.model_name
                        and existing.source_hash == it.text_hash
                    ):
                        stats.n_skipped += 1
                        continue
                    to_embed.append(it)

            if not to_embed:
                out_log.info(
                    "Source %s : %d item(s) déjà à jour, rien à encoder.",
                    source_id,
                    len(items),
                )
                continue

            if encoder is None:
                out_log.info("Chargement modèle %s...", opts.model_name)
                encoder = encoder_factory(opts.model_name)

            out_log.info(
                "Source %s : encode %d item(s) (batch=%d).",
                source_id,
                len(to_embed),
                opts.batch_size,
            )

            for batch in _batched(to_embed, opts.batch_size):
                texts = [b.text for b in batch]
                vectors = encoder.encode(texts)
                if vectors.shape[0] != len(batch):
                    raise RuntimeError(
                        f"encoder a retourné {vectors.shape[0]} vecteurs "
                        f"pour {len(batch)} textes."
                    )
                ts = now()
                rows = [
                    StoredEmbedding(
                        source_id=b.source_id,
                        id=b.id,
                        model=encoder.model_name,
                        dim=int(vectors.shape[1]),
                        vector=vectors[i].astype(np.float32, copy=False),
                        source_hash=b.text_hash,
                        embedded_at=ts,
                    )
                    for i, b in enumerate(batch)
                ]
                store.upsert_batch(rows)
                stats.n_embedded += len(rows)

            if opts.export_dedup:
                pairs = CrossEpisodeDedup(store).suggest(
                    source_id,
                    threshold=opts.dedup_threshold,
                    model=opts.model_name,
                )
                stats.n_dedup_pairs += len(pairs)
                titles = {it.id: it.title for it in items}
                opts.dedup_dir.mkdir(parents=True, exist_ok=True)
                out_path = opts.dedup_dir / f"dedup_suggestions_{source_id}.json"
                payload = {
                    "source_id": source_id,
                    "model": opts.model_name,
                    "threshold": opts.dedup_threshold,
                    "generated_at": now(),
                    "pairs": [p.to_dict(titles=titles) for p in pairs],
                }
                atomic_write_text(
                    out_path,
                    json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                )
                out_log.info(
                    "Dedup %s : %d paire(s) ≥ %.2f → %s",
                    source_id,
                    len(pairs),
                    opts.dedup_threshold,
                    out_path,
                )
    finally:
        store.close()

    stats.duration_s = time.perf_counter() - t0
    out_log.info(
        "Terminé : seen=%d embedded=%d skipped=%d pairs=%d en %.2fs",
        stats.n_seen,
        stats.n_embedded,
        stats.n_skipped,
        stats.n_dedup_pairs,
        stats.duration_s,
    )
    return EXIT_OK, stats


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="embed_items",
        description="Encode les items d'une source en vecteurs sémantiques.",
    )
    p.add_argument(
        "--source",
        required=True,
        help="Slug de la source ou 'all' pour toutes les sources disponibles.",
    )
    p.add_argument(
        "--db",
        type=Path,
        default=DEFAULT_DB_PATH,
        help=f"Chemin de la base SQLite (défaut {DEFAULT_DB_PATH}).",
    )
    p.add_argument(
        "--model",
        default=DEFAULT_MODEL,
        help=f"Nom du modèle d'embeddings (défaut {DEFAULT_MODEL}).",
    )
    p.add_argument(
        "--batch-size",
        type=int,
        default=64,
        help="Taille des batches d'encodage (défaut 64).",
    )
    p.add_argument(
        "--force",
        action="store_true",
        help="Re-embedder même si le source_hash est inchangé.",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Ne charge pas le modèle ; compte les items à embedder.",
    )
    p.add_argument(
        "--dedup-threshold",
        type=float,
        default=0.85,
        help="Seuil de similarité pour la dédup cross-épisode (défaut 0.85).",
    )
    p.add_argument(
        "--export-dedup-json",
        action="store_true",
        help="Exporte les paires dédup ≥ seuil dans output/embeddings/.",
    )
    p.add_argument(
        "--items-root",
        type=Path,
        default=CONTENT_DIR / "items",
        help="Racine des items JSON (défaut src/content/items/).",
    )
    return p


def _resolve_sources(arg_source: str, items_root: Path) -> tuple[str, ...]:
    if arg_source == "all":
        sources = tuple(_discover_sources(items_root))
        if not sources:
            raise SystemExit(
                f"Aucune source trouvée sous {items_root}. Build content d'abord."
            )
        return sources
    return (arg_source,)


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    items_root = Path(args.items_root)
    sources = _resolve_sources(args.source, items_root)

    # P3.5-B : Settings centralisés. Les flags CLI restent overrides
    # (rétro-compat) ; ils gagnent sur les défauts du dataclass.
    # NOTE : on ne lit pas encore SourceConfig.extra ici (le CLI est
    # global multi-sources, pas par-source). Forward-compat — quand le
    # CLI sera scindé par source, ce read deviendra trivial via
    # ``EmbeddingsSettings.from_source_extra(src.extra, overrides=...)``.
    settings = EmbeddingsSettings.from_source_extra(
        None,
        overrides={
            "model_name": args.model,
            "batch_size": int(args.batch_size),
            "dedup_threshold": float(args.dedup_threshold),
            "db_path": Path(args.db),
        },
    )
    opts = EmbedRunOptions(
        sources=sources,
        db_path=settings.db_path,
        model_name=settings.model_name,
        batch_size=settings.batch_size,
        force=bool(args.force),
        dry_run=bool(args.dry_run),
        dedup_threshold=settings.dedup_threshold,
        export_dedup=bool(args.export_dedup_json),
        dedup_dir=DEFAULT_DEDUP_DIR,
        items_root=items_root,
    )

    # Import paresseux de fastembed via factory — JAMAIS en tests.
    def _default_encoder_factory(model_name: str) -> Encoder:
        from embeddings.encoder import FastEmbedEncoder  # noqa: PLC0415

        return FastEmbedEncoder(model_name=model_name)

    # Lock pipeline (refuse si review_server tourne).
    from review_lock import (  # noqa: PLC0415
        ServerLockBusy,
        acquire_pipeline_lock,
    )

    try:
        with acquire_pipeline_lock(force=args.force):
            exit_code, _stats = run_embed(
                opts, encoder_factory=_default_encoder_factory
            )
            return exit_code
    except ServerLockBusy as exc:
        log.error("%s", exc)
        return EXIT_ERROR


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
