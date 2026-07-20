"""CLI : compare un fichier de recos extraites à un golden set.

Usage principal::

    python tools/eval_extraction.py \\
        --golden-set tests/eval/golden_set \\
        --extracted path/to/extracted.json \\
        --format csv \\
        --output eval/runs/2026-06-10_haiku.csv

Comparaison de runs::

    python tools/eval_extraction.py compare \\
        --base tools/output/eval/runs/<run_id_base>.json \\
        --target tools/output/eval/runs/<run_id_target>.json

Le scope **exclut** tout appel LLM. L'extraction est faite ailleurs et
fournie en entrée via ``--extracted``.

Format du fichier ``--extracted`` ::

    {
      "<episode_guid>": [
        {"title": "...", "creator": "...", "timestamp": "00:34:12"},
        ...
      ],
      ...
    }

OU une simple liste si ``--episode-guid`` est précisé.

Codes de sortie :
    0 : succès.
    1 : erreur d'usage (arg invalide, fichier introuvable).
    2 : erreur d'exécution du harness (golden set cassé, schéma invalide).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Support exécution directe (`python tools/eval_extraction.py`).
if __package__ in (None, ""):  # pragma: no cover
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools.common import OUTPUT_DIR, atomic_write_text, log
from tools.eval.golden_set import (
    GoldenSet,
    GoldenSetError,
    golden_set_hash,
    load_golden_set,
)
from tools.eval.harness import EvalHarness
from tools.eval.reporters import REPORTERS
from tools.eval.reporters.csv_reporter import render_csv, write_csv
from tools.eval.reporters.markdown_reporter import render_markdown, write_markdown
from tools.eval.types import EvalConfig, ReportFormat, RunManifest


EXIT_OK = 0
EXIT_USAGE = 1
EXIT_HARNESS = 2


_RUNS_DIR = OUTPUT_DIR / "eval" / "runs"


# --- Parsing -----------------------------------------------------------------
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd")

    # Sous-commande implicite (compat legacy : tous les args au top-level).
    parser.add_argument(
        "--golden-set", required=False,
        help="Dossier (ou fichier) du golden set.",
    )
    parser.add_argument(
        "--extracted", required=False,
        help="Fichier JSON contenant les recos extraites.",
    )
    parser.add_argument(
        "--report", choices=tuple(ReportFormat), default=None,
        help="(deprecated) alias de --format.",
    )
    parser.add_argument(
        "--format", choices=tuple(ReportFormat), default=None,
        dest="fmt",
        help="Format du rapport (par défaut : csv).",
    )
    parser.add_argument(
        "--output", default=None,
        help="Chemin du rapport (par défaut : stdout).",
    )
    parser.add_argument(
        "--episode-guid", default=None,
        help="Évaluer un seul épisode.",
    )
    parser.add_argument(
        "--source", default=None, action="append",
        help="Filtre par source_id (répétable pour multi-source).",
    )
    parser.add_argument(
        "--fuzzy-threshold", type=float, default=0.85,
        help="Seuil de match fuzzy (défaut : 0.85).",
    )
    parser.add_argument(
        "--strict-guid", action="store_true",
        help="Échoue si un guid du golden set est absent du fichier --extracted.",
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true",
        help="Affiche les détails par épisode sur stdout.",
    )
    parser.add_argument(
        "--run-id", default=None,
        help="Identifiant du run (sinon dérivé du timestamp).",
    )
    parser.add_argument(
        "--timestamp", default=None,
        help="Timestamp ISO du run (injecté pour déterminisme ; "
             "défaut : now UTC).",
    )
    parser.add_argument(
        "--save-manifest", action="store_true",
        help=f"Persiste le manifest JSON sous {_RUNS_DIR}.",
    )

    # Sous-commande explicite : compare.
    cmp_parser = sub.add_parser("compare", help="Compare 2 run manifests.")
    cmp_parser.add_argument("--base", required=True,
                            help="Chemin (ou run_id) du manifest base.")
    cmp_parser.add_argument("--target", required=True,
                            help="Chemin (ou run_id) du manifest target.")
    return parser


# --- Helpers -----------------------------------------------------------------
def _load_extracted(path: Path, episode_guid: str | None) -> list[dict]:
    """Charge le fichier extracted. Gère le format flat (liste) ou par-épisode (dict)."""
    raw = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(raw, list):
        return raw
    if isinstance(raw, dict):
        if episode_guid is not None:
            return list(raw.get(episode_guid, []))
        merged: list[dict] = []
        for v in raw.values():
            if isinstance(v, list):
                merged.extend(v)
        return merged
    raise ValueError(f"Format `extracted` non reconnu : {type(raw).__name__}")


def _config_hash(config: EvalConfig) -> str:
    payload = json.dumps({
        "fuzzy_threshold": config.fuzzy_threshold,
        "timestamp_tolerance_sec": config.timestamp_tolerance_sec,
        "creator_boost_threshold": config.creator_boost_threshold,
        "creator_penalty_threshold": config.creator_penalty_threshold,
        "creator_boost": config.creator_boost,
        "creator_penalty": config.creator_penalty,
    }, sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def _git_sha() -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            check=True, capture_output=True, text=True,
        )
        return out.stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):  # pragma: no cover
        return ""


def _filter_sources(gs: GoldenSet, sources: list[str] | None) -> GoldenSet:
    if not sources:
        return gs
    keep = set(sources)
    return GoldenSet(episodes=tuple(
        e for e in gs.episodes if e.source_id in keep
    ))


def _check_strict_guid(gs: GoldenSet, raw_extracted: Any) -> list[str]:
    if not isinstance(raw_extracted, dict):
        return []
    missing: list[str] = []
    for ep in gs:
        if ep.episode_guid not in raw_extracted:
            missing.append(ep.episode_guid)
    return missing


def _save_manifest(
    manifest: RunManifest, runs_dir: Path | None = None,
) -> Path:
    target = runs_dir if runs_dir is not None else _RUNS_DIR
    target.mkdir(parents=True, exist_ok=True)
    p = target / f"{manifest.run_id}.json"
    atomic_write_text(p, manifest.to_json())
    return p


def _resolve_manifest_path(arg: str, runs_dir: Path | None = None) -> Path:
    p = Path(arg)
    if p.exists():
        return p
    target = runs_dir if runs_dir is not None else _RUNS_DIR
    candidate = target / f"{arg}.json"
    if candidate.exists():
        return candidate
    raise FileNotFoundError(f"Manifest introuvable : {arg}")


def _format_pct(x: float) -> str:
    return f"{100.0 * x:.2f}%"


def _compare_manifests(base_path: Path, target_path: Path) -> str:
    base = RunManifest.from_dict(json.loads(base_path.read_text("utf-8")))
    target = RunManifest.from_dict(json.loads(target_path.read_text("utf-8")))
    lines = [
        "# Comparaison de runs",
        "",
        f"- base   : {base.run_id} ({base.timestamp})",
        f"- target : {target.run_id} ({target.timestamp})",
        "",
        "| Métrique | base | target | delta |",
        "|---|---|---|---|",
    ]
    for k in ("precision", "recall", "f1"):
        b = float(base.scores.get(k, 0.0))
        t = float(target.scores.get(k, 0.0))
        lines.append(
            f"| {k} | {_format_pct(b)} | {_format_pct(t)} | "
            f"{(t - b) * 100:+.2f} pts |",
        )
    return "\n".join(lines) + "\n"


# --- Entrée principale -------------------------------------------------------
def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    # Sous-commande compare.
    if args.cmd == "compare":
        try:
            base_p = _resolve_manifest_path(args.base)
            target_p = _resolve_manifest_path(args.target)
        except FileNotFoundError as exc:
            sys.stderr.write(f"{exc}\n")
            return EXIT_USAGE
        sys.stdout.write(_compare_manifests(base_p, target_p))
        return EXIT_OK

    # Validation des args obligatoires hors compare.
    if not args.golden_set or not args.extracted:
        parser.print_usage(sys.stderr)
        sys.stderr.write(
            "Erreur : --golden-set et --extracted sont requis.\n",
        )
        return EXIT_USAGE

    fmt = args.fmt or args.report or ReportFormat.CSV.value

    try:
        golden = load_golden_set(args.golden_set)
    except GoldenSetError as exc:
        sys.stderr.write(f"Erreur golden set : {exc}\n")
        return EXIT_HARNESS

    if args.source:
        golden = _filter_sources(golden, args.source)
        if len(golden) == 0:
            sys.stderr.write(
                f"Aucun épisode pour les sources {args.source}.\n",
            )
            return EXIT_HARNESS

    extracted_path = Path(args.extracted)
    if not extracted_path.exists():
        sys.stderr.write(f"Fichier --extracted introuvable : {extracted_path}\n")
        return EXIT_USAGE

    raw_extracted = json.loads(extracted_path.read_text("utf-8"))

    # Strict guid check (cf. C3).
    if args.strict_guid:
        missing = _check_strict_guid(golden, raw_extracted)
        if missing:
            sys.stderr.write(
                "Guids absents du fichier --extracted (mode strict): "
                f"{', '.join(missing)}\n",
            )
            return EXIT_HARNESS

    extracted = _load_extracted(extracted_path, args.episode_guid)

    config = EvalConfig(fuzzy_threshold=args.fuzzy_threshold)
    harness = EvalHarness(golden, config=config)
    try:
        result = harness.evaluate(extracted, episode_guid=args.episode_guid)
    except KeyError as exc:
        sys.stderr.write(f"Erreur : {exc}\n")
        return EXIT_HARNESS

    if fmt == ReportFormat.CSV.value:
        if args.output:
            write_csv(result, args.output)
        else:
            sys.stdout.write(render_csv(result))
    elif fmt == ReportFormat.MARKDOWN.value:
        if args.output:
            write_markdown(result, args.output)
        else:
            sys.stdout.write(render_markdown(result))
    else:  # pragma: no cover
        reporter_cls = REPORTERS.get(fmt)
        if reporter_cls is None:
            sys.stderr.write(f"Format inconnu : {fmt}\n")
            return EXIT_USAGE
        reporter = reporter_cls()
        if args.output:
            reporter.write(result, args.output)
        else:
            sys.stdout.write(reporter.render(result))

    if args.verbose:
        sys.stdout.write("\n# Détails par verdict\n")
        for d in result.details:
            sys.stdout.write(json.dumps(d, ensure_ascii=False) + "\n")

    if args.save_manifest:
        timestamp = args.timestamp or datetime.now(timezone.utc).isoformat()
        run_id = args.run_id or timestamp.replace(":", "-")
        scores = {
            "precision": result.precision,
            "recall": result.recall,
            "f1": result.f1,
            "n_expected": result.n_expected,
            "n_extracted": result.n_extracted,
            "n_exact_match": result.n_exact_match,
            "n_fuzzy_match": result.n_fuzzy_match,
            "n_missed": result.n_missed,
            "n_spurious": result.n_spurious,
            "n_wrong_timestamp": result.n_wrong_timestamp,
        }
        manifest = RunManifest(
            run_id=run_id,
            timestamp=timestamp,
            git_sha=_git_sha(),
            config_hash=_config_hash(config),
            golden_set_hash=golden_set_hash(golden),
            scores=scores,
            sources=tuple(args.source or ()),
        )
        saved = _save_manifest(manifest)
        log.info("Manifest sauvegardé : %s", saved)

    return EXIT_OK


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
