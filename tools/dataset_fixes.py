"""
dataset_fixes.py — socle commun aux correctifs de données ponctuels.

Les trois correctifs (`fix_deezer_locale`, `fix_creator_aliases`,
`migrate_watch_page`) partagent exactement la même mécanique : parcourir
`src/content/recos/<source>/*.json`, appliquer une transformation pure,
n'écrire QUE si `--apply` est passé, et produire un rapport JSON.

Ce module centralise cette mécanique pour que chaque correctif se réduise à
sa règle métier. Le contrat est volontairement strict :

  - `--dry-run` est le DÉFAUT. Un correctif qui écrit sans qu'on le lui
    demande est un bug ; `--apply` est le seul opt-in.
  - la transformation reçoit une COPIE de la reco et renvoie la liste des
    changements qu'elle a opérés dessus. Aucune écriture n'a lieu dans la
    transformation elle-même.
  - l'écriture passe par `write_json_if_changed` (atomique, sérialisation
    canonique : indent=2, clés triées, UTF-8 non échappé, `\\n` final) —
    les 3008 fichiers du corpus sont déjà sous cette forme, donc le diff
    se limite aux lignes réellement touchées.
"""
from __future__ import annotations

import argparse
import json
from collections.abc import Callable, Iterator, Sequence
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from common import ITEMS_DIR, RECOS_DIR, log, read_json, write_json_if_changed

#: RÉEXPORTATIONS VOLONTAIRES. Les deux dossiers de contenu sont lus ici via
#: `dataset_fixes.<NOM>` — et non capturés à l'import par les correctifs — pour
#: que les tests puissent les rediriger vers un `tmp_path` en substituant CE
#: module. Sans cette indirection, une suite de tests écrit dans le vrai corpus
#: (arrivé le 2026-07-31 : 29 fichiers réécrits). `__all__` les déclare pour
#: que ruff ne les prenne pas pour des imports morts (F401).
__all__ = [
    "ITEMS_DIR", "RECOS_DIR",
    "Change", "add_common_args", "iter_reco_files", "run",
]


@dataclass(frozen=True)
class Change:
    """Une valeur réécrite, désignée par son chemin dans le document JSON."""

    field: str  # ex. « links[2].url », « creator », « externalIds.justwatch »
    before: Any
    after: Any


@dataclass
class FileResult:
    """Le bilan d'un fichier : ce qui changerait (ou a changé) et la version cible."""

    path: Path
    reco_id: str
    data: dict[str, Any]
    changes: list[Change] = field(default_factory=list)


#: Une transformation mute la reco reçue et renvoie les changements opérés.
Transform = Callable[[dict[str, Any]], list[Change]]


def parse_exclude_ids(raw: str | None) -> set[str]:
    """`--exclude-ids` : liste CSV, ou `@fichier` (un id par ligne, `#` = commentaire).

    Même convention que `enrich_creators.py`, pour que
    `--exclude-ids @tools/creators_exclusions.txt` marche à l'identique.
    """
    if not raw:
        return set()
    if raw.startswith("@"):
        lines = Path(raw[1:]).read_text(encoding="utf-8").splitlines()
        return {ln.strip() for ln in lines if ln.strip() and not ln.startswith("#")}
    return {part.strip() for part in raw.split(",") if part.strip()}


def iter_reco_files(
    source: str | None = None, roots: Sequence[Path] | None = None
) -> Iterator[Path]:
    """Tous les fichiers JSON de contenu, triés — d'une source donnée ou de toutes.

    `roots` par défaut = les recos seules. Le correctif `watchPage` passe
    `(RECOS_DIR, ITEMS_DIR)` : le champ vit dans les deux collections, et
    n'en migrer qu'une laisserait le corpus incohérent.

    Résolu à l'appel (et non au chargement du module) pour que les tests
    puissent réassigner `dataset_fixes.RECOS_DIR`.
    """
    for root in roots if roots is not None else (RECOS_DIR,):
        target = root / source if source else root
        if not target.is_dir():
            log.warning("Dossier de contenu absent : %s", target)
            continue
        yield from sorted(target.rglob("*.json"))


def collect(
    transform: Transform,
    *,
    source: str | None = None,
    exclude_ids: set[str] | None = None,
    roots: Sequence[Path] | None = None,
) -> list[FileResult]:
    """Applique `transform` à chaque reco et renvoie les fichiers qui changeraient.

    N'écrit rien. Les fichiers illisibles sont signalés puis ignorés : un
    JSON corrompu ne doit pas faire échouer un correctif portant sur 3000
    autres fichiers.
    """
    excluded = exclude_ids or set()
    results: list[FileResult] = []
    for path in iter_reco_files(source, roots):
        try:
            data = read_json(path)
        except (OSError, ValueError) as exc:
            log.warning("  Ignoré (lecture impossible) %s : %s", path.name, exc)
            continue
        reco_id = data.get("id") or path.stem
        if reco_id in excluded:
            log.debug("  Exclu par --exclude-ids : %s", reco_id)
            continue
        changes = transform(data)
        if changes:
            results.append(FileResult(path=path, reco_id=reco_id, data=data, changes=changes))
    return results


def apply_results(results: Sequence[FileResult]) -> int:
    """Écrit les fichiers modifiés. Renvoie le nombre d'écritures réelles."""
    written = 0
    for res in results:
        if write_json_if_changed(res.path, res.data):
            written += 1
    return written


def build_report(results: Sequence[FileResult], *, applied: bool, extra: dict | None = None) -> dict:
    """Rapport machine : compteurs + détail par reco."""
    report = {
        "applied": applied,
        "files": len(results),
        "changes": sum(len(r.changes) for r in results),
        "recos": [
            {
                "id": r.reco_id,
                "path": r.path.as_posix(),
                "changes": [asdict(c) for c in r.changes],
            }
            for r in results
        ],
    }
    if extra:
        report.update(extra)
    return report


def write_report(json_path: str | None, report: dict) -> None:
    """Écrit le rapport si `--json` a été fourni."""
    if not json_path:
        return
    path = Path(json_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    log.info("Rapport JSON écrit : %s", path)


def add_common_args(parser: argparse.ArgumentParser) -> argparse.ArgumentParser:
    """Les quatre options communes à tous les correctifs."""
    parser.add_argument("--source", default=None,
                        help="Limiter à une source (défaut : toutes).")
    parser.add_argument("--apply", action="store_true",
                        help="Écrire les corrections (DÉFAUT : dry-run, aucune écriture).")
    parser.add_argument("--dry-run", action="store_true",
                        help="Explicite le comportement par défaut (aucune écriture).")
    parser.add_argument("--exclude-ids", default=None,
                        help="Ids à ne PAS corriger : « a,b,c » ou « @fichier ».")
    parser.add_argument("--json", dest="json_path", default=None,
                        help="Écrit le rapport détaillé (JSON) à ce chemin.")
    return parser


def log_summary(results: Sequence[FileResult], *, applied: bool, sample: int = 5) -> None:
    """Résumé lisible : compteurs, échantillon avant/après, rappel du dry-run."""
    total = sum(len(r.changes) for r in results)
    log.info("%d fichier(s), %d valeur(s) concernée(s).", len(results), total)
    for res in results[:sample]:
        for chg in res.changes:
            log.info("  %s · %s", res.reco_id, chg.field)
            log.info("      avant : %s", chg.before)
            log.info("      après : %s", chg.after)
    if len(results) > sample:
        log.info("  … et %d fichier(s) de plus (voir --json).", len(results) - sample)
    if not applied:
        log.info("DRY-RUN — aucune écriture (ajoute --apply pour écrire).")


def run(
    transform: Transform,
    args: argparse.Namespace,
    *,
    roots: Sequence[Path] | None = None,
    extra_report: dict | Callable[[Sequence[FileResult]], dict] | None = None,
) -> list[FileResult]:
    """Enchaîne collecte → résumé → écriture conditionnelle → rapport.

    `extra_report` accepte un dict, ou un callable recevant les résultats —
    utile quand le supplément se DÉDUIT des changements (ex. le recensement
    des hôtes qui prouve que `justwatch` ne pointait pas sur JustWatch).

    Renvoie les résultats pour que l'appelant puisse en tirer son propre
    diagnostic (ex. la liste des groupes de créateurs à arbitrer).
    """
    results = collect(
        transform,
        source=args.source,
        exclude_ids=parse_exclude_ids(args.exclude_ids),
        roots=roots,
    )
    log_summary(results, applied=args.apply)
    if args.apply:
        written = apply_results(results)
        log.info("%d fichier(s) écrit(s).", written)
    extra = extra_report(results) if callable(extra_report) else extra_report
    write_report(args.json_path, build_report(results, applied=args.apply, extra=extra))
    return results
