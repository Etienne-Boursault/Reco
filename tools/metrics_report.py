"""
metrics_report.py — lire la télémétrie du pipeline, sans la mélanger.

    python metrics_report.py coverage --source un-bon-moment
    python metrics_report.py workflows --source un-bon-moment --format json|csv
    python metrics_report.py cohort --source un-bon-moment --season 6
    python metrics_report.py summary --source un-bon-moment --cohort qualified|all \\
        --format markdown|json
    python metrics_report.py export --source un-bon-moment --season 6 \\
        --output tools/output/telemetry/export.json
    python metrics_report.py recover --older-than-hours 24     # runs/tentatives interrompus
    python metrics_report.py purge --activity-days 395         # battements bruts anciens

Lecture seule, sauf `recover` et `purge`. Une base absente donne des rapports
vides (`null`), jamais des zéros. Contrat : docs/workflow-metrics.md.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from telemetry import cohorts, reports
from telemetry.donnees import Donnees, catalogue
from telemetry.recorder import default_db_path

#: Au-delà, une tentative encore `started` est tenue pour interrompue. Une
#: transcription `large-v3` sur le CPU de venus dure une heure : 24 h laissent
#: de la marge, sans retenir indéfiniment un arrêt brutal.
SEUIL_INTERRUPTION_H = 24
#: Battements bruts gardés 13 mois, comme les mesures d'audience du site.
RETENTION_ACTIVITE_J = 395


def _imprimer(objet: Any, sortie: Path | None = None) -> None:
    texte = objet if isinstance(objet, str) else json.dumps(objet, ensure_ascii=False, indent=2)
    if sortie is None:
        sys.stdout.write(texte if texte.endswith("\n") else texte + "\n")
        return
    from common import atomic_write_text
    sortie.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(sortie, texte if texte.endswith("\n") else texte + "\n")


def _cohorte(args: argparse.Namespace, donnees: Donnees) -> dict[str, Any]:
    return cohorts.selection(donnees, catalogue(args.source), season=args.season,
                             min_episodes=args.min_episodes)


def _finaliser_interrompus(base: Path, heures: float, maintenant: datetime) -> dict[str, int]:
    from telemetry.store import Store
    if not base.exists():
        return {"workflow_runs": 0, "stage_attempts": 0}
    limite = (maintenant - timedelta(hours=heures)).isoformat(timespec="milliseconds")
    store = Store(base)
    try:
        return {table: store.execute(
            f"UPDATE {table} SET status = 'interrupted', ended_at = ? "  # noqa: S608 — table fixe
            "WHERE status = 'started' AND ended_at IS NULL AND started_at < ?",
            [maintenant.isoformat(timespec="milliseconds"), limite])
            for table in ("workflow_runs", "stage_attempts")}
    finally:
        store.close()


def _purger(base: Path, jours: int, maintenant: datetime) -> int:
    from telemetry.store import Store
    if not base.exists():
        return 0
    store = Store(base)
    try:
        return store.execute("DELETE FROM review_activity WHERE received_at < ?",
                             [(maintenant - timedelta(days=jours)).isoformat()])
    finally:
        store.close()


def main(argv: list[str] | None = None, *, maintenant: datetime | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("commande", choices=["coverage", "workflows", "cohort", "summary",
                                             "export", "recover", "purge"])
    parser.add_argument("--source", default="un-bon-moment")
    parser.add_argument("--db", type=Path, default=None,
                        help="Base de télémétrie (défaut : RECO_METRICS_DB ou tools/output).")
    parser.add_argument("--season", type=int, default=6)
    parser.add_argument("--intent", default="standard_first_pass",
                        choices=["standard_first_pass"],
                        help="Seule la première passe nominale forme une cohorte.")
    parser.add_argument("--min-episodes", type=int, default=cohorts.MIN_EPISODES)
    parser.add_argument("--cohort", choices=["qualified", "all"], default="qualified")
    parser.add_argument("--format", choices=["json", "markdown", "csv"], default="json")
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--older-than-hours", type=float, default=SEUIL_INTERRUPTION_H)
    parser.add_argument("--activity-days", type=int, default=RETENTION_ACTIVITE_J)
    args = parser.parse_args(argv)
    maintenant = maintenant or datetime.now(UTC)
    base = args.db or default_db_path()

    if args.commande == "recover":
        _imprimer({"interrupted": _finaliser_interrompus(base, args.older_than_hours,
                                                         maintenant)})
        return 0
    if args.commande == "purge":
        _imprimer({"activityRowsDeleted": _purger(base, args.activity_days, maintenant)})
        return 0

    donnees = Donnees.charger(args.source, base)
    if args.commande == "coverage":
        _imprimer(reports.couverture(donnees), args.output)
    elif args.commande == "workflows":
        if args.format == "csv":
            _imprimer(reports.lignes_csv(donnees), args.output)
        else:
            _imprimer({"runs": donnees.runs, "batches": donnees.batches}, args.output)
    elif args.commande == "cohort":
        _imprimer(_cohorte(args, donnees), args.output)
    elif args.commande == "summary":
        cohorte = _cohorte(args, donnees)
        resume = reports.resume(donnees, cohorte if args.cohort == "qualified" else None)
        if args.format == "markdown":
            _imprimer(reports.markdown(reports.couverture(donnees), resume, cohorte), args.output)
        else:
            _imprimer(resume, args.output)
    else:
        sortie = reports.export(donnees, _cohorte(args, donnees), maintenant=maintenant)
        erreurs = reports.valider(sortie)
        if erreurs:
            sys.stderr.write("Export non conforme :\n" + "\n".join(erreurs) + "\n")
            return 1
        _imprimer(sortie, args.output)
    return 0


if __name__ == "__main__":
    sys.exit(main())
