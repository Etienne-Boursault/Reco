"""tools/manage_reports.py — CLI admin des signalements visiteurs.

Gère les reports JSON produits par l'endpoint `/api/report` :
  - `--list` : liste les reports d'une source (filtrable par status).
  - `--show ID` : affiche un report complet.
  - `--resolve ID [--note "..."]` : marque résolu.
  - `--dismiss ID [--note "..."]` : marque écarté.
  - `--export FILE` : exporte tous les reports d'une source en JSON.

Stockage : `tools/output/reports/<source>/<reportId>.json`, format
identique au handler TS (cf. `src/lib/reports/types.ts`).

Coordination : prend le verrou `pipeline` (`review_lock`) pour les
opérations mutatives — évite les races si le review_server tourne.
Lecture seule (--list, --show, --export) ne prend pas le verrou.

Cf. ADR 0034 (Signalements visiteurs).
"""
from __future__ import annotations

import argparse
import getpass
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

# Le script vit dans tools/ ; les imports `common` / `review_lock` reposent
# sur le sys.path tools/ (cf. autres scripts du dossier).
sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import OUTPUT_DIR, atomic_write_text, log  # noqa: E402
from review_lock import acquire_pipeline_lock  # noqa: E402

REPORTS_DIR: Path = OUTPUT_DIR / "reports"

_VALID_STATUSES = {"pending", "resolved", "dismissed"}


# --- I/O --------------------------------------------------------------------
def _source_dir(source_id: str) -> Path:
    return REPORTS_DIR / source_id


def _list_source_ids() -> list[str]:
    """Énumère les sources qui ont au moins un sous-dossier de reports."""
    if not REPORTS_DIR.exists():
        return []
    return sorted(p.name for p in REPORTS_DIR.iterdir() if p.is_dir())


def _iter_report_paths(source_id: str | None) -> Iterable[Path]:
    sources = [source_id] if source_id else _list_source_ids()
    for sid in sources:
        d = _source_dir(sid)
        if not d.exists():
            continue
        for p in sorted(d.glob("*.json")):
            # Ignore les .json.tmp d'écritures atomiques en cours.
            if p.name.endswith(".tmp"):
                continue
            yield p


def _read_report(path: Path) -> dict[str, Any] | None:
    try:
        with path.open("r", encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, json.JSONDecodeError) as exc:
        log.warning("Report illisible %s : %s", path, exc)
        return None


def _find_report(report_id: str, source_id: str | None) -> tuple[Path, dict[str, Any]] | None:
    """Retrouve un report par id (cherche dans `source_id` si fourni, sinon partout)."""
    for path in _iter_report_paths(source_id):
        report = _read_report(path)
        if report and report.get("id") == report_id:
            return path, report
    return None


def _write_report(path: Path, report: dict[str, Any]) -> None:
    text = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    atomic_write_text(path, text)


# --- Affichage --------------------------------------------------------------
def _short(s: str, n: int = 60) -> str:
    s = (s or "").replace("\n", " ").strip()
    return s if len(s) <= n else s[: n - 1] + "…"


def _print_list(reports: list[tuple[Path, dict[str, Any]]]) -> None:
    if not reports:
        print("Aucun report.")
        return
    # En-tête tabulaire compact.
    print(f"{'ID':<42}  {'SOURCE':<22}  {'STATUS':<10}  {'CAT':<14}  DETAILS")
    print("-" * 120)
    for _, r in reports:
        print(
            f"{r.get('id', '?'):<42}  "
            f"{r.get('sourceId', '?'):<22}  "
            f"{r.get('status', '?'):<10}  "
            f"{r.get('category', '?'):<14}  "
            f"{_short(r.get('details', ''))}"
        )


def _print_show(report: dict[str, Any]) -> None:
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))


# --- Commandes mutatives ----------------------------------------------------
def _mutate(
    report_id: str,
    source_id: str | None,
    *,
    new_status: str,
    note: str | None,
) -> int:
    found = _find_report(report_id, source_id)
    if not found:
        log.error("Report introuvable : %s", report_id)
        return 1
    path, report = found
    if report.get("status") == new_status and not note:
        log.info("Report %s déjà %s, rien à faire.", report_id, new_status)
        return 0
    report["status"] = new_status
    report["resolvedAt"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    try:
        report["resolvedBy"] = getpass.getuser()
    except OSError:  # pragma: no cover — Windows edge case rare
        report["resolvedBy"] = "unknown"
    if note is not None:
        report["notes"] = note
    _write_report(path, report)
    log.info("Report %s → %s (par %s).", report_id, new_status, report["resolvedBy"])
    return 0


# --- Export -----------------------------------------------------------------
def _export(source_id: str | None, output: Path) -> int:
    reports = [r for _, r in (
        (p, _read_report(p)) for p in _iter_report_paths(source_id)
    ) if r]
    payload = {
        "exportedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "sourceFilter": source_id or "all",
        "count": len(reports),
        "reports": reports,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(
        output,
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
    )
    log.info("Exporté %d reports vers %s", len(reports), output)
    return 0


# --- CLI --------------------------------------------------------------------
def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="manage_reports.py",
        description="CLI admin des signalements visiteurs (cf. ADR 0034).",
    )
    p.add_argument(
        "--source",
        default="all",
        help="ID de source (ex. 'un-bon-moment') ou 'all'.",
    )

    # Actions mutuellement exclusives.
    actions = p.add_mutually_exclusive_group(required=True)
    actions.add_argument("--list", action="store_true", help="Liste les reports.")
    actions.add_argument("--show", metavar="ID", help="Affiche un report complet.")
    actions.add_argument("--resolve", metavar="ID", help="Marque résolu.")
    actions.add_argument("--dismiss", metavar="ID", help="Marque écarté.")
    actions.add_argument("--export", metavar="FILE", help="Exporte en JSON.")

    p.add_argument(
        "--status",
        choices=sorted(_VALID_STATUSES),
        help="Filtre par status (pour --list).",
    )
    p.add_argument(
        "--note",
        help="Note libre attachée à la résolution.",
    )
    p.add_argument(
        "--force",
        action="store_true",
        help="Force l'acquisition du verrou pipeline (cf. review_lock).",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    source = None if args.source == "all" else args.source

    # --- Lecture seule (pas de verrou nécessaire) -----------------------------
    if args.list:
        reports: list[tuple[Path, dict[str, Any]]] = []
        for p in _iter_report_paths(source):
            r = _read_report(p)
            if not r:
                continue
            if args.status and r.get("status") != args.status:
                continue
            reports.append((p, r))
        _print_list(reports)
        return 0

    if args.show:
        found = _find_report(args.show, source)
        if not found:
            log.error("Report introuvable : %s", args.show)
            return 1
        _print_show(found[1])
        return 0

    if args.export:
        return _export(source, Path(args.export))

    # --- Mutations (sous verrou pipeline) -------------------------------------
    with acquire_pipeline_lock(force=args.force):
        if args.resolve:
            return _mutate(args.resolve, source, new_status="resolved", note=args.note)
        if args.dismiss:
            return _mutate(args.dismiss, source, new_status="dismissed", note=args.note)

    return 1  # unreachable — argparse garantit qu'une action est choisie.


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
