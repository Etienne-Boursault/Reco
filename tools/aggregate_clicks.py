"""tools/aggregate_clicks.py — Agrégation des clics sortants (ADR 0046).

Lit les fichiers JSONL produits par `/api/click` :
  tools/output/clicks/<sourceId>/<YYYY-MM-DD>.jsonl

et agrège selon plusieurs axes (`--by category|url|reco|source`).

Sortie : JSON par défaut, CSV via `--output file.csv`.

Exit codes (B-MED-4 — alignés `audit_core`) :
    0 — OK
    1 — erreur fonctionnelle (plage de dates inversée, lock pris, …)
    2 — erreur d'usage (CLI invalide : ``--source`` mal formé, date
        ISO invalide, axe d'agrégation inconnu).

Privacy : aucun stockage d'IP (cf. ADR 0046), l'agrégation ne fait que
compter ; aucune dimension réversible vers un visiteur.
"""
from __future__ import annotations

import argparse
import csv
import json
import logging
import re
import sys
from collections import Counter
from dataclasses import dataclass
from datetime import date as date_cls, datetime
from pathlib import Path
from typing import Any, Iterable

sys.path.insert(0, str(Path(__file__).resolve().parent))

from audit_core.cli_runner import utcnow_iso  # noqa: E402,F401 — utilisé pour cohérence ; importé via audit_core
from common import OUTPUT_DIR, atomic_write_text  # noqa: E402
from review_lock import ServerLockBusy, acquire_pipeline_lock  # type: ignore  # noqa: E402

CLICKS_DIR: Path = OUTPUT_DIR / "clicks"

_VALID_BY = {"category", "url", "reco", "source"}

#: B-NIT-8 — constante partagée pour le bucket par défaut (events sans
#: catégorie). Évite la chaîne libre "other" dispersée.
OTHER_CATEGORY: str = "other"

#: B-HIGH-3 — validation slug source : ASCII restreint, longueur bornée.
_SLUG_RE = re.compile(r"^[a-z0-9_-]{1,128}$")

#: B-MED-17 — seuil par défaut au-delà duquel on bascule en exit 1.
_DEFAULT_DROP_THRESHOLD: int = 50

#: B-MED-4 — exit codes alignés audit_core.
EXIT_OK: int = 0
EXIT_FUNCTIONAL: int = 1
EXIT_USAGE: int = 2

log = logging.getLogger("aggregate_clicks")
if not log.handlers:
    _h = logging.StreamHandler(sys.stderr)
    _h.setFormatter(logging.Formatter("%(levelname)s %(name)s: %(message)s"))
    log.addHandler(_h)
    log.setLevel(logging.INFO)


# --- Schéma event ----------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ClickEvent:
    """B-HIGH-2 — schéma strict d'un event JSONL.

    Champs requis :
      - ``ts`` : ISO-8601 (string)
      - ``category`` : string non vide
      - ``sourceId`` : slug source (string)

    Champs optionnels :
      - ``url`` : string (peut être vide → l'axe ``url`` skip)
      - ``recoId`` : string (peut être vide → l'axe ``reco`` skip)
      - ``ref`` : string libre (origine de la navigation)
    """

    ts: str
    category: str
    sourceId: str
    url: str = ""
    recoId: str = ""
    ref: str = ""


def _validate_event(raw: Any) -> ClickEvent | None:
    """B-HIGH-2 — valide un event brut ; renvoie ``None`` si invalide.

    Règles : `dict`, champs requis présents et strings non-vides pour
    `ts`/`category`/`sourceId`. Les champs optionnels doivent être des
    strings (ou absents).
    """
    if not isinstance(raw, dict):
        return None
    required: tuple[str, ...] = ("ts", "category", "sourceId")
    for k in required:
        v = raw.get(k)
        if not isinstance(v, str) or not v:
            return None
    optional: tuple[str, ...] = ("url", "recoId", "ref")
    for k in optional:
        v = raw.get(k)
        if v is not None and not isinstance(v, str):
            return None
    return ClickEvent(
        ts=raw["ts"],
        category=raw["category"],
        sourceId=raw["sourceId"],
        url=raw.get("url") or "",
        recoId=raw.get("recoId") or "",
        ref=raw.get("ref") or "",
    )


# --- IO --------------------------------------------------------------------


def _parse_iso_date(s: str) -> date_cls:
    return datetime.strptime(s, "%Y-%m-%d").date()


def _date_from_filename(name: str) -> date_cls | None:
    """Extrait `YYYY-MM-DD` du nom de fichier JSONL."""
    if not name.endswith(".jsonl"):
        return None
    try:
        return _parse_iso_date(name[:-6])
    except ValueError:
        return None


def iter_events(
    *,
    source: str | None,
    from_date: date_cls | None,
    to_date: date_cls | None,
    root: Path = CLICKS_DIR,
    drop_counter: Counter[str] | None = None,
) -> Iterable[dict[str, Any]]:
    """Stream les events JSONL filtrés par source + plage de dates.

    B-HIGH-2 — chaque ligne est validée via ``_validate_event``.
    Les invalides (JSON parse error OU schéma cassé) sont droppées
    silencieusement avec un log.warning ; le compteur ``drop_counter``
    est incrémenté pour permettre une exit code remontée par le caller.
    """
    if not root.exists():
        return
    sources = [source] if source and source != "all" else [
        p.name for p in sorted(root.iterdir()) if p.is_dir()
    ]
    for src in sources:
        sdir = root / src
        if not sdir.is_dir():
            continue
        for fpath in sorted(sdir.glob("*.jsonl")):
            d = _date_from_filename(fpath.name)
            if d is None:
                continue
            if from_date and d < from_date:
                continue
            if to_date and d > to_date:
                continue
            with fpath.open("r", encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        raw = json.loads(line)
                    except json.JSONDecodeError:
                        if drop_counter is not None:
                            drop_counter["json"] += 1
                        log.warning("event JSON invalide ignoré (%s)", fpath.name)
                        continue
                    ev = _validate_event(raw)
                    if ev is None:
                        if drop_counter is not None:
                            drop_counter["schema"] += 1
                        log.warning(
                            "event schéma invalide ignoré (%s) : %r",
                            fpath.name,
                            raw if isinstance(raw, dict) else type(raw).__name__,
                        )
                        continue
                    # On rétro-projette en dict pour rester compatible avec
                    # le contrat existant (consommé par `aggregate`).
                    yield {
                        "ts": ev.ts,
                        "category": ev.category,
                        "sourceId": ev.sourceId,
                        "url": ev.url,
                        "recoId": ev.recoId,
                        "ref": ev.ref,
                    }


# --- Agrégation ------------------------------------------------------------


def aggregate(events: Iterable[dict[str, Any]], by: str) -> dict[str, Any]:
    """Agrège un flux d'events selon l'axe `by`.

    Renvoie toujours la même forme :
      {
        "by": <axe>,
        "total_clicks": N,
        "counts": [{"key": str, "count": int}, ...],   # trié desc
        "by_category": {cat: count, ...},              # toujours présent
      }
    """
    if by not in _VALID_BY:
        raise ValueError(f"--by invalide : {by!r} (attendu: {_VALID_BY})")

    counter: Counter[str] = Counter()
    cat_counter: Counter[str] = Counter()
    total = 0
    for ev in events:
        total += 1
        cat = ev.get("category", OTHER_CATEGORY)
        cat_counter[cat] += 1
        if by == "category":
            counter[cat] += 1
        elif by == "url":
            # M25-25 : skip silencieusement les events sans `url` — un bucket
            # `""` vide trompeur (mélange « URL absente » et « URL vide »).
            u = ev.get("url")
            if u:
                counter[u] += 1
        elif by == "reco":
            rid = ev.get("recoId")
            if rid:
                counter[rid] += 1
        elif by == "source":
            # B-LOW-14 — cohérent avec l'axe `url` : on ne crée pas de
            # bucket "" pour les events sans `sourceId` (l'invariant
            # schéma le rend pratiquement impossible, mais on reste
            # défensif).
            sid = ev.get("sourceId")
            if sid:
                counter[sid] += 1

    return {
        "by": by,
        "total_clicks": total,
        "counts": [
            {"key": k, "count": v}
            for k, v in counter.most_common()
        ],
        "by_category": dict(cat_counter.most_common()),
    }


# --- Output ----------------------------------------------------------------


def write_output(
    data: dict[str, Any],
    path: Path,
    *,
    csv_include_dimension: bool = False,
) -> None:
    """Écrit `data` en JSON ou CSV selon l'extension du path.

    B-MED-2 — l'écriture passe par ``atomic_write_text`` pour qu'un
    lecteur concurrent ne tombe jamais sur un fichier tronqué.

    M25-24 : `csv_include_dimension=True` ajoute une colonne `by` qui
    indique l'axe (`category`, `url`, `reco`, `source`) — utile pour
    concaténer plusieurs CSV sans perdre la dimension.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.suffix.lower() == ".csv":
        import io

        buf = io.StringIO()
        w = csv.writer(buf, lineterminator="\n")
        if csv_include_dimension:
            w.writerow(["by", "key", "count"])
            by = data.get("by", "")
            for row in data["counts"]:
                w.writerow([by, row["key"], row["count"]])
        else:
            w.writerow(["key", "count"])
            for row in data["counts"]:
                w.writerow([row["key"], row["count"]])
        atomic_write_text(path, buf.getvalue())
    else:
        atomic_write_text(
            path,
            json.dumps(data, indent=2, ensure_ascii=False) + "\n",
        )


# --- CLI -------------------------------------------------------------------


def _validate_source_arg(source: str) -> bool:
    """B-HIGH-3 — `--source` doit matcher `_SLUG_RE` (ou être "all")."""
    if source == "all":
        return True
    return bool(_SLUG_RE.match(source))


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Agrège les clics sortants (ADR 0046).")
    p.add_argument("--source", default="all", help="sourceId ou 'all' (défaut)")
    p.add_argument("--from-date", dest="from_date", help="YYYY-MM-DD (incl.)")
    p.add_argument("--to-date", dest="to_date", help="YYYY-MM-DD (incl.)")
    p.add_argument(
        "--by",
        choices=sorted(_VALID_BY),
        default="category",
        help="axe d'agrégation (défaut: category)",
    )
    p.add_argument("--output", help="chemin de sortie (.json ou .csv)")
    p.add_argument(
        "--csv-include-dimension",
        action="store_true",
        help="CSV : ajoute une colonne `by` (axe d'agrégation) — M25-24",
    )
    p.add_argument("--root", help="override CLICKS_DIR (tests)")
    p.add_argument(
        "--drop-threshold",
        type=int,
        default=_DEFAULT_DROP_THRESHOLD,
        help=(
            "Seuil au-delà duquel les events invalides droppés déclenchent "
            f"un exit 1 (défaut : {_DEFAULT_DROP_THRESHOLD})."
        ),
    )
    p.add_argument(
        "--force",
        action="store_true",
        help="Force l'acquisition du pipeline lock (debug).",
    )
    args = p.parse_args(argv)

    # B-HIGH-3 — validation `--source` (avant tout I/O).
    if not _validate_source_arg(args.source):
        print(
            f"--source invalide : {args.source!r} (attendu slug "
            f"[a-z0-9_-]{{1,128}} ou 'all')",
            file=sys.stderr,
        )
        return EXIT_USAGE

    try:
        from_d = _parse_iso_date(args.from_date) if args.from_date else None
        to_d = _parse_iso_date(args.to_date) if args.to_date else None
    except ValueError as e:
        print(f"date invalide : {e}", file=sys.stderr)
        return EXIT_USAGE

    # B-MED-5 — `from_date` doit être ≤ `to_date`.
    if from_d and to_d and from_d > to_d:
        print(
            f"plage de dates inversée : --from-date {from_d.isoformat()} > "
            f"--to-date {to_d.isoformat()}",
            file=sys.stderr,
        )
        return EXIT_FUNCTIONAL

    # B-MED-3 — lockfile pipeline.
    try:
        with acquire_pipeline_lock(force=args.force):
            return _run(args, from_d, to_d)
    except ServerLockBusy as exc:
        log.error("%s", exc)
        return EXIT_FUNCTIONAL


def _run(
    args: argparse.Namespace,
    from_d: date_cls | None,
    to_d: date_cls | None,
) -> int:
    root = Path(args.root) if args.root else CLICKS_DIR
    drops: Counter[str] = Counter()
    events = iter_events(
        source=args.source if args.source != "all" else None,
        from_date=from_d,
        to_date=to_d,
        root=root,
        drop_counter=drops,
    )
    data = aggregate(events, by=args.by)

    if args.output:
        write_output(
            data,
            Path(args.output),
            csv_include_dimension=args.csv_include_dimension,
        )
        print(
            f"écrit {data['total_clicks']} clics agrégés par {args.by} → {args.output}",
        )
    else:
        json.dump(data, sys.stdout, indent=2, ensure_ascii=False)
        sys.stdout.write("\n")

    # B-MED-17 — exit 1 si trop d'events droppés (WARNING audit_core).
    total_dropped = sum(drops.values())
    if total_dropped > 0:
        log.warning(
            "events droppés : %d (json=%d schéma=%d)",
            total_dropped, drops.get("json", 0), drops.get("schema", 0),
        )
    if total_dropped > args.drop_threshold:
        log.error(
            "seuil de drop dépassé (%d > %d) — exit %d",
            total_dropped, args.drop_threshold, EXIT_FUNCTIONAL,
        )
        return EXIT_FUNCTIONAL
    return EXIT_OK


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
