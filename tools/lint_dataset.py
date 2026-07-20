"""
lint_dataset.py — CLI d'audit du dataset (P1.5).

Charge le dataset d'une source (recos legacy + items + mentions +
episodes + source config), exécute toutes les règles enregistrées, écrit
un rapport (Markdown ou JSON). Exit code = 0 / 1 (errors) / 2 (warnings only).

Usage :
    python tools/lint_dataset.py --source un-bon-moment
    python tools/lint_dataset.py --source un-bon-moment --output audit/x.md
    python tools/lint_dataset.py --source un-bon-moment --severity error
    python tools/lint_dataset.py --source un-bon-moment --rule required_fields
    python tools/lint_dataset.py --source un-bon-moment --format json
    python tools/lint_dataset.py --source all --format json

Convention de nommage (P0 #3) :
    audit/<YYYY-MM-DD>__lint__<source>.md
"""
from __future__ import annotations

import argparse
import sys
from datetime import date as _date_module_alias
from pathlib import Path

# Permettre l'exécution directe `python tools/lint_dataset.py`.
sys.path.insert(0, str(Path(__file__).resolve().parent))

import review_lock  # noqa: E402
from lint import LintReport, Severity  # noqa: E402
from lint.cli_runner import LintRunOptions, run_lint  # noqa: E402
from lint.loaders import JsonDatasetLoader, _load_jsons_with_errors  # noqa: E402
from lint.reporters import REPORTERS, get_reporter  # noqa: E402
from lint.rules.base import LintContext  # noqa: E402
from lint.settings import LintSettings  # noqa: E402
from repository._base import _SOURCE_ID_PATTERN as _RE_SOURCE_ID  # noqa: E402
from repository.item_repo import ItemRepoJson  # noqa: E402
from repository.mention_repo import MentionRepoJson  # noqa: E402
from tools.config.registry import get_source as _get_source  # noqa: E402
from tools.config.registry import list_sources as _list_sources  # noqa: E402

# Alias `date` pour permettre aux tests de monkeypatcher
# `lint_dataset.date` (M9).
date = _date_module_alias

# Chemins par défaut — overridable côté tests via monkeypatch / arg.
RECOS_BASE_DIR = Path("src/content/recos")
EPISODES_BASE_DIR = Path("src/content/episodes")
ITEMS_BASE_DIR = Path("src/content/items")
MENTIONS_BASE_DIR = Path("src/content/mentions")
DEFAULT_OUTPUT_DIR = Path("audit")
DEFAULT_OUTPUT_LINT_JSON_DIR = Path("tools/output/lint")
DEFAULT_SCOPE = "lint"


# ---------------------------------------------------------------------------
# Loader backward-compat (utilisé par les tests existants)
# ---------------------------------------------------------------------------


def _load_jsons(directory: Path) -> tuple[dict, ...]:
    """Backward-compat helper (H7 wrapper).

    Renvoie uniquement les payloads valides — les erreurs IO sont loggées
    sur stderr par ``_load_jsons_with_errors`` mais perdues ici (les
    tests historiques attendent ce contrat). Préférer le loader pour
    une intégration propre au rapport.
    """
    payloads, _ = _load_jsons_with_errors(directory, source_id="")
    return tuple(payloads)


def build_context(
    source_id: str,
    *,
    recos_base: Path | None = None,
    episodes_base: Path | None = None,
    items_base: Path | None = None,
    mentions_base: Path | None = None,
) -> LintContext:
    """Compose un `LintContext` depuis le disque (backward-compat).

    Implémenté en termes du loader DI (CR archi #4). Les tests historiques
    qui appelaient ``build_context()`` directement continuent à fonctionner.
    """
    loader = JsonDatasetLoader(
        recos_base=recos_base if recos_base is not None else RECOS_BASE_DIR,
        episodes_base=episodes_base if episodes_base is not None else EPISODES_BASE_DIR,
        items_base=items_base if items_base is not None else ITEMS_BASE_DIR,
        mentions_base=mentions_base if mentions_base is not None else MENTIONS_BASE_DIR,
        source_registry_get=_get_source,
        item_repo_factory=ItemRepoJson,
        mention_repo_factory=MentionRepoJson,
    )
    ctx, _io_issues = loader.load(source_id)
    return ctx


# ---------------------------------------------------------------------------
# Path resolution
# ---------------------------------------------------------------------------


def _resolve_output_path(
    arg: Path | None,
    *,
    source_id: str,
    fmt: str = "markdown",
    scope: str = DEFAULT_SCOPE,
) -> Path:
    """Convention P0 #3 : ``audit/<date>__<scope>__<source>.<ext>``."""
    if arg is not None:
        return arg
    suffix = ".json" if fmt == "json" else ".md"
    base = DEFAULT_OUTPUT_DIR if fmt == "markdown" else DEFAULT_OUTPUT_LINT_JSON_DIR / source_id
    return base / f"{date.today().isoformat()}__{scope}__{source_id}{suffix}"


def _validate_output_safe(out_path: Path) -> bool:
    """M2 : refuse les paths sortant du CWD (path traversal)."""
    try:
        out_path.resolve().relative_to(Path.cwd().resolve())
    except ValueError:
        return False
    return True


def _avoid_overwrite(path: Path) -> Path:
    """L7 : si `path` existe, renvoie un nom horodaté seconde."""
    if not path.exists():
        return path
    import datetime
    stamp = datetime.datetime.now().strftime("%H%M%S")
    return path.with_name(f"{path.stem}__{stamp}{path.suffix}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description=(
            "Audit le dataset d'une source et émet un rapport (Markdown/JSON)."
        )
    )
    p.add_argument(
        "--source", required=True,
        help="Slug de la source ('all' pour itérer sur toutes — P2 #15).",
    )
    p.add_argument(
        "--output", type=Path, default=None,
        help=(
            "Fichier de sortie. Défaut : "
            "audit/<YYYY-MM-DD>__lint__<source>.md "
            "ou tools/output/lint/<source>/<YYYY-MM-DD>__lint__<source>.json."
        ),
    )
    p.add_argument(
        "--severity",
        choices=[s.value for s in Severity], default=None,
        help="Filtre les issues par sévérité (cosmétique — n'affecte pas l'exit code).",
    )
    p.add_argument(
        "--rule", default=None,
        help="Filtre les issues par nom de règle (cosmétique).",
    )
    p.add_argument(
        "--format", default="markdown",
        choices=sorted(REPORTERS.keys()),
        help="Format du rapport (markdown / json).",
    )
    p.add_argument(
        "--no-overwrite", action="store_true",
        help="Si la sortie existe, ajouter un suffixe horodaté plutôt qu'écraser (L7).",
    )
    p.add_argument(
        "--ignore-server-lock", action="store_true",
        help="Force l'exécution même si review_server tourne.",
    )
    return p


def _compute_exit_code(report: LintReport) -> int:
    """Exit code basé sur les compteurs *_unfiltered (H9).

    Pour un rapport qui n'est jamais passé par `.filter()` les compteurs
    unfiltered == compteurs normaux.
    """
    if (report.n_errors_unfiltered or report.n_errors) > 0:
        return 1
    if (report.n_warnings_unfiltered or report.n_warnings) > 0:
        return 2
    return 0


def _make_loader() -> JsonDatasetLoader:
    return JsonDatasetLoader(
        recos_base=RECOS_BASE_DIR,
        episodes_base=EPISODES_BASE_DIR,
        items_base=ITEMS_BASE_DIR,
        mentions_base=MENTIONS_BASE_DIR,
        source_registry_get=_get_source,
        item_repo_factory=ItemRepoJson,
        mention_repo_factory=MentionRepoJson,
    )


def _settings_for_source(source_id: str) -> LintSettings:
    """Charge `SourceConfig.extra["lint"]` si disponible."""
    try:
        cfg = _get_source(source_id)
    except Exception:
        return LintSettings()
    return LintSettings.from_source_extra(cfg.extra)


def _iter_target_sources(source_arg: str) -> tuple[str, ...]:
    """`--source all` itère sur toutes les sources actives (P2 #15)."""
    if source_arg != "all":
        return (source_arg,)
    return tuple(s.id for s in _list_sources())


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    sources = _iter_target_sources(args.source)
    if args.source != "all":
        if not _RE_SOURCE_ID.match(args.source):
            sys.stderr.write(
                f"source invalide: {args.source!r}. "
                f"Attendu: slug ^[a-z0-9]+(-[a-z0-9]+)*$.\n"
            )
            return 2

    exit_codes: list[int] = []
    try:
        with review_lock.acquire_pipeline_lock(force=args.ignore_server_lock):
            for source_id in sources:
                code = _run_one(source_id, args)
                exit_codes.append(code)
    except (review_lock.PipelineLockBusy, review_lock.ServerLockBusy) as exc:
        sys.stderr.write(f"{exc}\n")
        return 4

    if not exit_codes:
        return 0
    # Si plusieurs sources : code max (= la plus grave).
    return max(exit_codes)


def _run_one(source_id: str, args: argparse.Namespace) -> int:
    out_path = _resolve_output_path(
        args.output, source_id=source_id, fmt=args.format,
    )
    if not _validate_output_safe(out_path):
        sys.stderr.write(
            f"refus path traversal : {out_path} hors du CWD\n"
        )
        return 2
    if args.no_overwrite:
        out_path = _avoid_overwrite(out_path)
    severity = Severity(args.severity) if args.severity else None

    settings = _settings_for_source(source_id)
    opts = LintRunOptions(
        source_id=source_id,
        output=out_path,
        severity_filter=severity,
        rule_filter=args.rule,
        reporter=get_reporter(args.format),
        loader=_make_loader(),
        settings=settings,
    )
    result = run_lint(opts)
    sys.stdout.write(
        f"Lint report écrit dans {result.output_path} "
        f"(total={result.report.n_total}, "
        f"errors={result.report.n_errors_unfiltered or result.report.n_errors}, "
        f"warnings={result.report.n_warnings_unfiltered or result.report.n_warnings}, "
        f"duration={result.duration_s:.2f}s)\n"
    )
    return result.exit_code


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
