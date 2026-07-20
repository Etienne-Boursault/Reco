"""backfill_extraction_history.py — Génère `extractionHistory` rétroactivement.

Pour chaque reco existante sans champ `extractionHistory`, on fabrique au moins
une entrée legacy à partir des informations disponibles :
  - `at`         : mtime du fichier
  - `transcriptModel` : "(assumed)"  (info perdue)
  - `transcriptSource`: existing.transcriptSource (sinon "acast")
  - `llmProvider`: extractors[0] (sinon "anthropic")
  - `llmModel`   : "(assumed)" — sauf heuristique ci-dessous
  - `worker`     : "(assumed)"
  - `timestamp_at_extraction` : existing.timestamp (sinon "00:00:00")

Heuristique d'amélioration :
  - Si `extractors == ["anthropic", "openai"]` ET `mtime >= 2026-06-04` →
    on génère 2 entrées (une par provider).
    - anthropic : "claude-haiku-4-5" si mtime >= 2026-06-04, sinon
      "claude-sonnet-4-6".
    - openai    : "gpt-4o-mini" par défaut.

Atomique : écriture via `tempfile + os.replace` pour ne jamais corrompre un
fichier en cas de coupure.

Usage :
    python tools/backfill_extraction_history.py
    python tools/backfill_extraction_history.py --source un-bon-moment --dry-run
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

_TOOLS = Path(__file__).resolve().parent
if str(_TOOLS) not in sys.path:
    sys.path.insert(0, str(_TOOLS))

from extraction_history import (  # noqa: E402
    ASSUMED,
    ExtractionEntry,
    derive_extractors,
    merge_history,
    pick_display_state,
    to_dict,
)

_HAIKU_CUTOVER = datetime(2026, 6, 4, tzinfo=timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.replace(microsecond=0).isoformat()


def _mtime_dt(path: Path) -> datetime:
    return datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)


def _anthropic_model_for(mtime: datetime) -> str:
    """Modèle Anthropic présumé selon la date d'extraction."""
    return "claude-haiku-4-5" if mtime >= _HAIKU_CUTOVER else "claude-sonnet-4-6"


def build_legacy_entries(reco: dict, mtime: datetime) -> list[ExtractionEntry]:
    """Construit la liste d'entrées legacy pour une reco sans historique.

    Heuristique : si extractors == ["anthropic", "openai"] ET mtime tardif,
    on génère 2 entrées avec modèles supposés. Sinon, 1 entrée unique.
    """
    extractors = reco.get("extractors") or []
    transcript_source = reco.get("transcriptSource") or "acast"
    if transcript_source not in ("acast", "youtube"):
        transcript_source = "acast"
    timestamp = reco.get("timestamp") or "00:00:00"
    at = _iso(mtime)

    providers_norm = sorted({p for p in extractors if p in ("anthropic", "openai")})
    if providers_norm == ["anthropic", "openai"] and mtime >= _HAIKU_CUTOVER:
        return [
            ExtractionEntry(
                at=at, transcriptModel=ASSUMED,
                transcriptSource=transcript_source,  # type: ignore[arg-type]
                llmProvider="anthropic",
                llmModel=_anthropic_model_for(mtime),
                worker=ASSUMED,
                timestamp_at_extraction=timestamp,
            ),
            ExtractionEntry(
                at=at, transcriptModel=ASSUMED,
                transcriptSource=transcript_source,  # type: ignore[arg-type]
                llmProvider="openai",
                llmModel="gpt-4o-mini",
                worker=ASSUMED,
                timestamp_at_extraction=timestamp,
            ),
        ]

    provider = extractors[0] if extractors else "anthropic"
    if provider not in ("anthropic", "openai"):
        provider = "anthropic"
    return [
        ExtractionEntry(
            at=at, transcriptModel=ASSUMED,
            transcriptSource=transcript_source,  # type: ignore[arg-type]
            llmProvider=provider,  # type: ignore[arg-type]
            llmModel=ASSUMED,
            worker=ASSUMED,
            timestamp_at_extraction=timestamp,
        )
    ]


def _atomic_write_json(path: Path, data: dict) -> None:
    """Écriture atomique (tempfile + os.replace)."""
    parent = path.parent
    parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=".tmp_", suffix=".json", dir=str(parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2, sort_keys=True)
            f.write("\n")
        os.replace(tmp_name, path)
    except Exception:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def backfill_file(path: Path, dry_run: bool = False) -> bool:
    """Backfille un fichier reco. Retourne True s'il a été modifié."""
    try:
        with path.open("r", encoding="utf-8") as f:
            reco = json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"  [SKIP] {path.name}: {exc}", file=sys.stderr)
        return False

    if reco.get("extractionHistory"):
        return False  # déjà migré

    mtime = _mtime_dt(path)
    entries = build_legacy_entries(reco, mtime)
    # On passe par merge_history pour bénéficier de la dédup + tri.
    history: list[ExtractionEntry] = []
    for e in entries:
        history = merge_history(history, e)

    reco["extractionHistory"] = [to_dict(e) for e in history]
    reco["extractors"] = derive_extractors(history)
    display = pick_display_state(history)
    reco["timestamp"] = display["timestamp"]
    reco["transcriptSource"] = display["transcriptSource"]

    if dry_run:
        return True
    _atomic_write_json(path, reco)
    return True


def backfill_dir(recos_dir: Path, dry_run: bool = False) -> tuple[int, int]:
    """Backfille tous les .json d'un répertoire. Retourne (touched, total)."""
    files = sorted(recos_dir.glob("*.json"))
    touched = 0
    for i, p in enumerate(files, 1):
        if backfill_file(p, dry_run=dry_run):
            touched += 1
        if i % 200 == 0:
            print(f"  … {i}/{len(files)} (touched={touched})")
    return touched, len(files)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", default="un-bon-moment",
                        help="Sous-répertoire de src/content/recos (défaut: %(default)s).")
    parser.add_argument("--dry-run", action="store_true",
                        help="N'écrit rien, n'affiche que le résultat prévu.")
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[1] / "src" / "content" / "recos" / args.source
    if not root.exists():
        print(f"Répertoire introuvable : {root}", file=sys.stderr)
        sys.exit(1)

    print(f"Backfill {root} (dry_run={args.dry_run})")
    touched, total = backfill_dir(root, dry_run=args.dry_run)
    print(f"Terminé : {touched}/{total} reco(s) modifiée(s).")


if __name__ == "__main__":
    main()
