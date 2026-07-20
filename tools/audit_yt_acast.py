"""audit_yt_acast.py — CLI : audit a posteriori des matchs YT ↔ Acast.

Détecte les épisodes pour lesquels le ``youtubeUrl`` semble pointer sur la
mauvaise vidéo (durée incohérente, intro divergente, …) et sépare
explicitement :

  --check (default)  : ne modifie rien (équivalent dry-run).
  --apply            : flag matchSuspect dans les épisodes + sidecar.
  --undo-last        : annule le dernier --apply (CR archi #6).
  --format json|markdown|human  : format de sortie (CR archi #25).
  --log-format json  : émet aussi des événements JSONL (CR senior H6).
  --fail-on-suspect  : exit code != 0 si des suspects (CR senior M5).
  --duration-tolerance / --intro-threshold / --title-threshold /
  --intro-chars      : seuils injectables (CR senior H1/M3, CR archi #5).

Cf. ADRs 0013 et 0015, mémoire ``reco-cleanup-collisions``.

Note packaging (CR archi #14) : ``pyproject.toml`` configure déjà
``pythonpath = ["tools"]``, donc PAS de hack ``sys.path`` ici. Un
``pyproject.toml`` avec entry-point ``audit-yt-acast`` est possible
mais reporté (non-bloquant — l'invocation ``python tools/...`` marche).
"""
from __future__ import annotations

import argparse
import os
import sys
from typing import Sequence

# Bootstrap minimal pour l'exécution standalone (`python tools/audit_yt_acast.py`).
# Pour pytest, `pyproject.toml` configure déjà `pythonpath = ["tools"]` ; le code
# ci-dessous est un no-op dans ce cas.
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:  # pragma: no cover — chemin script direct
    sys.path.insert(0, _PROJECT_ROOT)

import common  # type: ignore[attr-defined]  # noqa: E402
from review_lock import acquire_pipeline_lock  # type: ignore  # noqa: E402

from tools.match_audit.cli_runner import (  # noqa: E402
    LOG_FORMATS,
    OUTPUT_FORMATS,
    RunOptions,
    emit_jsonl_events,
    run_audit,
    undo_last_apply,
)
from tools.match_audit.settings import MatchAuditSettings  # noqa: E402


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Audit a posteriori des matchs YouTube ↔ Acast.",
    )
    p.add_argument("--source", required=True, help="ID de source (ex. un-bon-moment)")

    mode = p.add_mutually_exclusive_group()
    mode.add_argument(
        "--check", action="store_true", default=True,
        help="N'écrit rien — dry-run (par défaut)",
    )
    mode.add_argument(
        "--apply", action="store_true",
        help="Flag matchSuspect dans les épisodes + écrit sidecar",
    )
    mode.add_argument(
        "--undo-last", action="store_true",
        help="Annule le dernier --apply (CR archi #6)",
    )

    p.add_argument(
        "--format", choices=OUTPUT_FORMATS, default="human",
        help="Format de sortie (défaut: human)",
    )
    p.add_argument(
        "--log-format", choices=LOG_FORMATS, default="text",
        help="Format des événements émis sur stderr (text=log lisible, "
             "json=JSONL structuré — CR senior H6)",
    )
    p.add_argument(
        "--fail-on-suspect", action="store_true",
        help="Exit code 1 si au moins un suspect (CI/CD)",
    )

    p.add_argument(
        "--duration-tolerance", type=float, default=None,
        help="Tolérance relative pour le check durée (défaut: 0.05)",
    )
    p.add_argument(
        "--intro-threshold", type=float, default=None,
        help="Seuil similarité intro (défaut: 0.4)",
    )
    p.add_argument(
        "--intro-chars", type=int, default=None,
        help="Nombre de chars d'intro comparés (défaut: 500)",
    )
    p.add_argument(
        "--title-threshold", type=float, default=None,
        help="Seuil similarité titre (défaut: 0.3, warning)",
    )

    p.add_argument("--force", action="store_true", help="Forcer malgré le verrou pipeline")
    return p


def _settings_from_args(args: argparse.Namespace) -> MatchAuditSettings:
    overrides: dict = {}
    if args.duration_tolerance is not None:
        overrides["duration_tolerance"] = args.duration_tolerance
    if args.intro_threshold is not None:
        overrides["intro_threshold"] = args.intro_threshold
    if args.intro_chars is not None:
        overrides["intro_chars"] = args.intro_chars
    if args.title_threshold is not None:
        overrides["title_threshold"] = args.title_threshold
    # Best-effort : lit SourceConfig.extra["match_audit"] si dispo.
    extra: dict = {}
    try:
        from tools.config.registry import get_source  # noqa: PLC0415
        cfg = get_source(args.source)
        if cfg.extra:
            extra = dict(cfg.extra)
    except Exception:  # noqa: BLE001 — config absente : on prend défauts
        extra = {}
    return MatchAuditSettings.from_source_extra(extra, overrides=overrides)


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    with acquire_pipeline_lock(force=args.force):
        if args.undo_last:
            res = undo_last_apply(args.source)
            common.log.info(
                "[%s] undo-last : flags retirés=%d, sidecars supprimés=%d",
                args.source, res["flags_cleared"], res["sidecars_deleted"],
            )
            return 0

        mode = "apply" if args.apply else "check"
        settings = _settings_from_args(args)
        opts = RunOptions(
            source_id=args.source,
            mode=mode,
            output_format=args.format,
            log_format=args.log_format,
            settings=settings,
            fail_on_suspect=args.fail_on_suspect,
        )
        result = run_audit(opts)
        sys.stdout.write(result.output_text)
        if args.log_format == "json":
            emit_jsonl_events(result.report, sink=sys.stderr)
        if mode == "apply":
            common.log.info(
                "[%s] %d/%d suspects ; %d fichier(s) modifié(s) ; "
                "%d sidecar(s) écrit(s)",
                args.source,
                result.report.suspect_count,
                result.report.audited_count,
                result.files_changed,
                result.sidecars_written,
            )
        return result.exit_code


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
