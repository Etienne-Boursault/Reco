"""enrich_audit.cli_runner — orchestration métier extraite du CLI.

Le CLI ``tools/audit_tmdb.py`` n'est qu'une fine couche d'argparse autour
de ces fonctions. On peut donc tester la totalité du comportement sans
spawner un subprocess.

CR archi P2 #6 : module éclaté en :
  - :mod:`.cli_runner` (ici) : RunOptions + run_audit + default_service.
  - :mod:`.providers` : make_cache_provider.
  - :mod:`.reporters` : format_markdown / format_json / write_jsonl_log.

Réexports `make_cache_provider`, `format_markdown`, `format_json` pour
ne pas casser les imports historiques.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Sequence

from domain.item import Item

from .flag_writer import clear_source as clear_source_sidecars
from .flag_writer import write_sidecar
from .providers import make_cache_provider
from .reporters import format_json, format_markdown, write_jsonl_log
from .runtime_coherence_check import check_runtime_coherence
from .service import (
    AuditResult,
    Check,
    CheckFunction,
    EnrichAuditService,
    SourceAuditReport,
    TmdbDataProvider,
)
from .settings import EnrichAuditSettings
from .thresholds import (
    DEFAULT_FILM_MIN_RUNTIME,
    DEFAULT_TITLE_THRESHOLD,
    DEFAULT_YEAR_TOLERANCE,
)
from .title_similarity_check import check_title_similarity
from .tmdb_type_mismatch_check import check_tmdb_type_mismatch
from .year_mismatch_check import check_year_mismatch


# ---------------------------------------------------------------------------
# Default service factory — composition de tous les checks livrés.
# ---------------------------------------------------------------------------


def default_service(
    *,
    settings: EnrichAuditSettings | None = None,
    title_threshold: float | None = None,
    year_tolerance: int | None = None,
    film_min_runtime: int | None = None,
) -> EnrichAuditService:
    """Compose le service d'audit avec les 4 checks livrés.

    Seuils injectables (CR senior H4 + D-01 ADR 0019).

    Args:
        settings: ``EnrichAuditSettings`` consolidé (typiquement construit
            depuis ``SourceConfig.extra["enrich_audit"]`` via
            ``EnrichAuditSettings.from_source_extra``). ``None`` → défauts.
        title_threshold/year_tolerance/film_min_runtime: overrides
            historiques (call-site direct, ex. tests). ``None`` → valeur
            du ``settings`` ou défaut.
    """
    s = settings or EnrichAuditSettings()
    title_t = title_threshold if title_threshold is not None else s.title_threshold
    year_t = year_tolerance if year_tolerance is not None else s.year_tolerance
    film_min = (
        film_min_runtime if film_min_runtime is not None else s.film_min_runtime
    )

    # tmdb_type_mismatch first : c'est le check critique (CR senior C5).
    def _title(item: Item, tmdb_data: dict) -> object:
        return check_title_similarity(item, tmdb_data, threshold=title_t)

    def _year(item: Item, tmdb_data: dict) -> object:
        return check_year_mismatch(item, tmdb_data, tolerance=year_t)

    def _runtime(item: Item, tmdb_data: dict) -> object:
        return check_runtime_coherence(
            item, tmdb_data, film_min_runtime=film_min,
        )

    # Préserve `.name`/`.kind` pour le tracing.
    _title.name = check_title_similarity.name  # type: ignore[attr-defined]
    _title.kind = check_title_similarity.kind  # type: ignore[attr-defined]
    _year.name = check_year_mismatch.name  # type: ignore[attr-defined]
    _year.kind = check_year_mismatch.kind  # type: ignore[attr-defined]
    _runtime.name = check_runtime_coherence.name  # type: ignore[attr-defined]
    _runtime.kind = check_runtime_coherence.kind  # type: ignore[attr-defined]

    return EnrichAuditService(
        checks=[
            check_tmdb_type_mismatch,
            _title,  # type: ignore[list-item]
            _year,  # type: ignore[list-item]
            _runtime,  # type: ignore[list-item]
        ],
    )


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class RunOptions:
    """Options d'un run d'audit.

    Args:
        source_id: slug source à auditer.
        items: tuple immuable d'items (le caller a déjà décidé du repo).
        provider: callable tmdb_id → dict | None.
        apply: ``True`` = écrit les sidecars. Sinon dry-run.
        clear_before_apply: ``True`` = archive les sidecars existants
            avant write. ``False`` = write par-dessus (utile pour merges
            partiels).
        sidecar_base_dir: override du dossier sidecar (tests).
        service: service injecté (sinon `default_service()`).
        audited_at: ISO8601 UTC injecté pour idempotence des sidecars
            (cf. CR archi #14). ``None`` → now() au moment de l'écriture.
        jsonl_log_path: si fourni, append-log JSONL par item suspect.
    """

    source_id: str
    items: tuple[Item, ...]
    provider: TmdbDataProvider
    apply: bool
    clear_before_apply: bool = True
    sidecar_base_dir: Path | None = None
    service: EnrichAuditService | None = None
    audited_at: str | None = None
    jsonl_log_path: Path | None = None


def run_audit(opts: RunOptions) -> SourceAuditReport:
    """Boucle d'audit principale.

    - Toujours produit un `SourceAuditReport` (dry-run friendly).
    - Si `apply=True`, écrit un sidecar par item audité (clean ou suspect).
    - Si `clear_before_apply=True`, archive d'abord les sidecars existants.
    - Si `jsonl_log_path` est fourni, append une ligne par suspect.
    """
    svc = opts.service or default_service()
    report = svc.audit_items(opts.source_id, opts.items, opts.provider)

    # Mapping item_id → tmdb_id (pour debug sidecar — CR senior L8).
    tmdb_by_item: dict[str, int] = {
        it.id: it.external_ids.tmdb
        for it in opts.items
        if it.external_ids.tmdb is not None
    }

    if opts.apply:
        if opts.clear_before_apply:
            clear_source_sidecars(
                opts.source_id,
                base_dir=opts.sidecar_base_dir,
            )
        for r in report.results:
            write_sidecar(
                r,
                opts.source_id,
                base_dir=opts.sidecar_base_dir,
                audited_at=opts.audited_at,
                tmdb_id=tmdb_by_item.get(r.item_id),
            )

    if opts.jsonl_log_path is not None and report.suspect_count > 0:
        write_jsonl_log(
            report, log_path=opts.jsonl_log_path, timestamp=opts.audited_at,
        )

    return report


__all__ = [
    "RunOptions",
    "default_service",
    "format_json",
    "format_markdown",
    "make_cache_provider",
    "run_audit",
    "write_jsonl_log",
]
