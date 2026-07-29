"""cache.cli_runner — primitives partagées pour la CLI ``build_cache``.

Aligné sur le pattern ``audit_core.cli_runner`` (CR archi P2-5) : un
dataclass ``BuildCacheRunOptions`` immutable + ``run_build_cache(opts)``
qui orchestre, pendant que ``tools/build_cache.py`` se réduit à l'argparse.

Validation des chemins
----------------------
``--db`` est validé contre une whitelist par défaut (``OUTPUT_DIR``) afin
de bloquer un path-traversal (CR senior C4). Pour les usages dev hors
``OUTPUT_DIR``, passer ``allow_unsafe_db_path=True`` (option non exposée
par l'argparse).
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from cache.builder import BuildStats, CacheBuilder
from cache.schema import FTS5NotAvailableError

# Type alias pour le contexte ``acquire_pipeline_lock``.
LockCM = Callable[..., object]


@dataclass(frozen=True, slots=True)
class BuildCacheRunOptions:
    """Options d'un run CLI ``build_cache``.

    Attributs :
        source_id : ``None`` (toutes) ou slug.
        db_path   : chemin SQLite de sortie.
        items_dir / mentions_dir / episodes_dir : racines JSON.
        force     : ignorer le pipeline_lock si tenu par review_server.
        vacuum    : VACUUM post-build.
        optimize  : ``INSERT INTO items_fts(items_fts) VALUES('optimize')``.
        allowed_db_root : si fourni, ``db_path`` doit être sous cette racine
            (sinon ValueError). Mitigation path-traversal (CR senior C4).
    """

    source_id: str | None
    db_path: Path
    items_dir: Path
    mentions_dir: Path
    episodes_dir: Path
    force: bool = False
    vacuum: bool = False
    optimize: bool = False
    allowed_db_root: Path | None = None

    def __post_init__(self) -> None:
        if self.allowed_db_root is not None:
            self._validate_db_under(self.allowed_db_root, self.db_path)

    @staticmethod
    def _validate_db_under(root: Path, db: Path) -> None:
        try:
            db_abs = db.resolve()
            root_abs = root.resolve()
        except OSError as exc:  # pragma: no cover - defensive
            raise ValueError(f"db path inaccessible: {exc}") from exc
        try:
            db_abs.relative_to(root_abs)
        except ValueError as exc:
            raise ValueError(
                f"--db {db_abs} doit être sous {root_abs} (mitigation "
                f"path-traversal — cf. ADR 0020 § Sécurité)."
            ) from exc


# Exit codes (alignés avec audit_core).
EXIT_OK: Final[int] = 0
EXIT_ERROR: Final[int] = 1
EXIT_LOCK_BUSY: Final[int] = 1


def run_build_cache(
    opts: BuildCacheRunOptions,
    *,
    lock_factory: LockCM,
    log: Callable[..., None],
) -> tuple[int, BuildStats | None]:
    """Exécute un build. Retourne (exit_code, stats).

    ``lock_factory`` doit être un context manager compatible
    ``acquire_pipeline_lock(force=...)``. Injecté pour la testabilité.
    """
    builder = CacheBuilder(
        db_path=opts.db_path,
        items_dir=opts.items_dir,
        mentions_dir=opts.mentions_dir,
        episodes_dir=opts.episodes_dir,
    )

    stats: BuildStats | None = None
    try:
        with lock_factory(force=opts.force):
            log(
                "Build cache : source=%s db=%s",
                opts.source_id or "all",
                opts.db_path,
            )
            stats = builder.build(
                source_id=opts.source_id,
                optimize=opts.optimize,
            )
            log(
                "Cache OK : items=%d mentions=%d episodes=%d fts=%d en %.2fs",
                stats.n_items,
                stats.n_mentions,
                stats.n_episodes,
                stats.n_fts_rows,
                stats.duration_s,
            )
            if builder.last_errors:
                log(
                    "Build : %d fichier(s) JSON ignoré(s) (cf. logs)",
                    len(builder.last_errors),
                )
            if opts.vacuum:
                log("VACUUM...")
                builder.vacuum()
                log("VACUUM OK.")
    except FTS5NotAvailableError as exc:
        log("FTS5 indisponible : %s", exc)
        return EXIT_ERROR, None
    return EXIT_OK, stats


__all__ = [
    "EXIT_ERROR",
    "EXIT_LOCK_BUSY",
    "EXIT_OK",
    "BuildCacheRunOptions",
    "run_build_cache",
]
