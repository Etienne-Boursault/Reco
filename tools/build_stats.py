"""build_stats.py — CLI : agrège items + mentions + episodes → ``stats.json``.

Usage :
    python tools/build_stats.py --source un-bon-moment
    python tools/build_stats.py --source all --format json
    python tools/build_stats.py --source all --format csv --output-dir custom/

Cf. ADR 0047. La logique métier vit dans ``tools.stats.aggregator`` ; ce
module se limite à l'argparse + lecture/écriture des collections JSON +
câblage du lock pipeline.

Exit codes (alignés `audit_core`, M26-22) :
    0 — OK
    1 — erreur fonctionnelle (source inconnue, lock pris)
    2 — erreur d'exécution non rattrapée (exception inattendue)
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import sys
from pathlib import Path
from typing import Any, Final, Sequence

from common import CONTENT_DIR, OUTPUT_DIR, atomic_write_text, log
from review_lock import ServerLockBusy, acquire_pipeline_lock
from stats import build_snapshot

_DEFAULT_OUTPUT: Final[Path] = OUTPUT_DIR / "stats"
_SOURCES_DIR: Final[Path] = CONTENT_DIR / "sources"
_EPISODES_DIR: Final[Path] = CONTENT_DIR / "episodes"
_MENTIONS_DIR: Final[Path] = CONTENT_DIR / "mentions"
_ITEMS_DIR: Final[Path] = CONTENT_DIR / "items"

#: B-MED-15 — garde-fou : au-delà, on warn (un dataset prod n'atteint
#: pas ce volume — le dépasser pointe une fuite de fixtures).
_DEFAULT_MAX_ITEMS: Final[int] = 200_000
#: B-MED-17 — au-delà de N fichiers skip on bascule en exit 1.
_DEFAULT_SKIPPED_THRESHOLD: Final[int] = 10


# --- I/O --------------------------------------------------------------------


def _read_json_dir(
    base: Path,
    *,
    skipped: list[Path] | None = None,
) -> list[dict[str, Any]]:
    """Lit récursivement tous les `*.json` sous `base`.

    B-MED-17 — alimente `skipped` avec les fichiers ignorés (OS error
    ou JSON corrompu) pour exposer un compteur au caller.
    """
    out: list[dict[str, Any]] = []
    if not base.exists():
        return out
    # M26-24 : exclure les fixtures dédiées et les dossiers legacy/archivés.
    _excluded_parts = {"__cross_stack_fixture__", "_legacy", ".archived"}
    for path in sorted(base.rglob("*.json")):
        if _excluded_parts.intersection(path.parts):
            continue
        try:
            out.append(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError) as exc:
            log.warning("Skipping %s : %s", path, exc)
            if skipped is not None:
                skipped.append(path)
    return out


def _coerce_sources(raw: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{"id": s["id"], "hosts": s.get("hosts", [])} for s in raw]


def _coerce_episodes(raw: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for e in raw:
        sid = e.get("sourceId")
        # `sourceId` peut être un objet `{ id, collection }` (style Astro
        # reference) ou un simple string selon le pipeline. On normalise.
        if isinstance(sid, dict):
            sid = sid.get("id")
        out.append({"sourceId": sid, "date": e.get("date")})
    return out


def _coerce_mentions(raw: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for m in raw:
        out.append(
            {
                "itemId": m.get("itemId"),
                "recommendedBy": m.get("recommendedBy"),
                "status": m.get("status", "draft"),
                "sourceRef": {
                    "sourceId": (m.get("sourceRef") or {}).get("sourceId"),
                },
            }
        )
    return out


def _coerce_items(raw: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {"id": i["id"], "title": i.get("title", ""), "types": i.get("types", [])}
        for i in raw
    ]


# --- Format writers ---------------------------------------------------------


def _write_json(payload: dict[str, Any], dest: Path) -> None:
    # B-LOW-11 — `sort_keys=True` est un choix volontaire : il garantit
    # un diff stable entre deux runs (idempotence) et fournit une parité
    # forte avec la sérialisation TS (`JSON.stringify` + tri côté Astro).
    text = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    atomic_write_text(dest, text)


def _write_csv(payload: dict[str, Any], dest: Path) -> None:
    """Sérialise les compteurs principaux en CSV (1 ligne par bucket)."""
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(["section", "key", "value"])
    writer.writerow(["meta", "schemaVersion", payload["schemaVersion"]])
    writer.writerow(["meta", "generatedAt", payload["generatedAt"]])
    for k, v in payload["global"].items():
        writer.writerow(["global", k, v])
    for sid, counts in payload["perSource"].items():
        for k, v in counts.items():
            writer.writerow([f"perSource:{sid}", k, v])
    for g in payload["topGuests"]:
        writer.writerow(["topGuests", g["name"], g["count"]])
    for w in payload["topWorks"]:
        writer.writerow(["topWorks", w["title"], w["mentionsCount"]])
    for k, v in payload["typeDistribution"].items():
        writer.writerow(["typeDistribution", k, v])
    for b in payload["monthlyEpisodes"]:
        writer.writerow(["monthlyEpisodes", b["month"], b["count"]])
    atomic_write_text(dest, buf.getvalue())


# --- Run --------------------------------------------------------------------


def _is_safe_path_segment(segment: str) -> bool:
    """B-LOW-12 — factorisation du check anti-traversal.

    Vrai si `segment` peut être utilisé comme nom de dossier sûr :
      - pas de séparateur (`/` ni `\\`) ;
      - pas ``""`` / ``"."`` / ``".."`` ;
      - pas de prefix `.` (caché / dotfile).
    """
    if not isinstance(segment, str):
        return False
    if segment in ("", ".", ".."):
        return False
    if "/" in segment or "\\" in segment:
        return False
    if segment.startswith("."):
        return False
    return True


def run(
    *,
    source: str,
    output_dir: Path,
    fmt: str,
    generated_at: str | None = None,
    max_items: int = _DEFAULT_MAX_ITEMS,
    skipped_threshold: int = _DEFAULT_SKIPPED_THRESHOLD,
) -> int:
    """Cœur exécutable, sans gestion de lock (testable directement).

    B-MED-16 — la validation du nom de source (anti path-traversal)
    s'effectue AVANT toute lecture / écriture, pour court-circuiter
    rapidement et ne jamais laisser un input non-sain atteindre l'I/O.
    """
    # M26-23 / B-MED-16 — anti path-traversal AVANT _read_json_dir.
    sub_check = source if source != "all" else "_global"
    if not _is_safe_path_segment(sub_check):
        log.error("Source invalide pour le chemin de sortie : %r", source)
        return 1

    skipped: list[Path] = []
    sources = _coerce_sources(_read_json_dir(_SOURCES_DIR, skipped=skipped))
    episodes = _coerce_episodes(_read_json_dir(_EPISODES_DIR, skipped=skipped))
    mentions = _coerce_mentions(_read_json_dir(_MENTIONS_DIR, skipped=skipped))
    items = _coerce_items(_read_json_dir(_ITEMS_DIR, skipped=skipped))

    # B-MED-15 — garde-fou volume : on warn (sans fail) si on dépasse.
    total_items = (
        len(sources) + len(episodes) + len(mentions) + len(items)
    )
    if total_items > max_items:
        log.warning(
            "Volume agrégé inhabituel : %d items > --max-items %d "
            "(continue, mais vérifie les fixtures).",
            total_items, max_items,
        )

    if source != "all":
        known = {s["id"] for s in sources}
        if source not in known:
            log.error("Source inconnue : %s (connues : %s)", source, sorted(known))
            return 1
        source_id: str | None = source
    else:
        source_id = None

    snapshot = build_snapshot(
        sources=sources,
        episodes=episodes,
        mentions=mentions,
        items=items,
        source_id=source_id,
        generated_at=generated_at,
    )
    payload = snapshot.to_dict()

    dest_dir = output_dir / sub_check
    dest_dir.mkdir(parents=True, exist_ok=True)
    if fmt == "json":
        _write_json(payload, dest_dir / "stats.json")
    elif fmt == "csv":
        _write_csv(payload, dest_dir / "stats.csv")
    else:  # pragma: no cover — argparse l'interdit déjà
        log.error("Format inconnu : %s", fmt)
        return 1

    log.info(
        "Stats écrites : %s recos · %s œuvres · %s invités → %s",
        payload["global"]["recommendationsCount"],
        payload["global"]["uniqueWorksCount"],
        payload["global"]["uniqueGuestsCount"],
        dest_dir,
    )
    # B-MED-17 — exit 1 si trop de fichiers ont été skip (corruption).
    if len(skipped) > skipped_threshold:
        log.error(
            "Trop de fichiers JSON ignorés (%d > %d) — corruption probable.",
            len(skipped), skipped_threshold,
        )
        return 1
    if skipped:
        log.warning("Fichiers JSON ignorés : %d", len(skipped))
    return 0


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="build_stats",
        description="Agrège items + mentions + episodes → stats.json (cf. ADR 0047).",
    )
    p.add_argument(
        "--source",
        default="all",
        help='ID de source (ex. "un-bon-moment") ou "all" (défaut).',
    )
    p.add_argument(
        "--output-dir",
        type=Path,
        default=_DEFAULT_OUTPUT,
        help=f"Dossier de sortie (défaut : {_DEFAULT_OUTPUT}).",
    )
    p.add_argument(
        "--format",
        choices=("json", "csv"),
        default="json",
        help="Format de sortie (défaut : json).",
    )
    p.add_argument(
        "--force",
        action="store_true",
        help="Ignorer le verrou serveur (review_server) si tenu.",
    )
    p.add_argument(
        "--generated-at",
        default=None,
        help="(tests) Force la valeur ISO de generatedAt pour la reproductibilité.",
    )
    p.add_argument(
        "--max-items",
        type=int,
        default=_DEFAULT_MAX_ITEMS,
        help=(
            f"Volume d'items total maximal (warn si dépassé, "
            f"défaut : {_DEFAULT_MAX_ITEMS})."
        ),
    )
    p.add_argument(
        "--skipped-threshold",
        type=int,
        default=_DEFAULT_SKIPPED_THRESHOLD,
        help=(
            f"Seuil de fichiers JSON ignorés au-delà duquel on exit 1 "
            f"(défaut : {_DEFAULT_SKIPPED_THRESHOLD})."
        ),
    )
    return p.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        with acquire_pipeline_lock(force=args.force):
            return run(
                source=args.source,
                output_dir=args.output_dir,
                fmt=args.format,
                generated_at=args.generated_at,
                max_items=args.max_items,
                skipped_threshold=args.skipped_threshold,
            )
    except ServerLockBusy as exc:
        log.error("review_server tient le verrou : %s", exc)
        return 1
    except Exception as exc:  # pragma: no cover (catch-all CLI)
        # M26-22 : exit 2 pour exception non rattrapée (vs 1 = fonctionnel).
        log.exception("build_stats a échoué : %s", exc)
        return 2


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
