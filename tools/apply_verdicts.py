"""
apply_verdicts.py — applique au corpus les verdicts d'une relecture par agents.

Un agent relit les recos `draft` d'un épisode et rend un fichier JSON :

    {
      "ubm-3021": {"verdict": "validate", "recommendedBy": "Navo",
                   "confidence": 0.9, "reason": "Recommandation explicite.",
                   "flags": ["title_suspect"], "note": "Titre à vérifier."}
    }

Verdicts : validate · citation · guest-work · discard · unsure.
`unsure` laisse la reco en `draft` : un humain tranchera dans le review_server.
`recommendedBy` est obligatoire ; une chaîne vide dit « attribution douteuse ».

Garde-fous — un fichier fautif est refusé EN ENTIER, avant toute écriture :
  - identifiant inconnu, ou reco qui n'est pas un `draft` de cet épisode ;
  - verdict inconnu, confiance hors [0, 1], raison vide, champ manquant ;
  - reco `draft` de l'épisode restée sans verdict (sauf --allow-partial).

Ne supprime jamais rien. Relit le disque à la fin pour contrôler que chaque
statut correspond à son verdict. La mutation elle-même est celle du
review_server (`review_actions.apply_review_action`), sans le marqueur
`reviewedByHuman`.

Usage :
    cd tools
    python apply_verdicts.py --source un-bon-moment --guid <GUID> \\
        --verdicts verdicts.json --model claude-opus-5 [--dry-run] [--allow-partial]

Codes de sortie : 0 appliqué · 1 contrôle d'intégrité en échec · 2 refusé.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from common import log, read_json, recos_dir_for, write_json_if_changed
from review_actions import SAVE_ACTIONS, apply_review_action

VERDICTS: frozenset[str] = SAVE_ACTIONS | {"unsure"}

# Clés du bloc `agentReview` posées par un humain dans le review_server : une
# relecture d'agent relancée ne doit pas les effacer.
_HUMAN_KEYS = ("reviewedByHuman", "flagsResolved")

_EXPECTED_STATUS = {
    "validate": "validated",
    "citation": "validated",
    "guest-work": "validated",
    "discard": "discarded",
    "unsure": "draft",
}


@dataclass
class Draft:
    path: Path
    reco: dict[str, Any]


def load_episode_recos(source_id: str, guid: str) -> dict[str, Draft]:
    """Toutes les recos de l'épisode, indexées par id (tous statuts)."""
    out: dict[str, Draft] = {}
    recos_dir = recos_dir_for(source_id)
    if not recos_dir.is_dir():
        return out
    for path in sorted(recos_dir.glob("*.json")):
        reco = read_json(path)
        if reco.get("episodeGuid") == guid and reco.get("id"):
            out[reco["id"]] = Draft(path, reco)
    return out


def validate_verdicts(raw: Any, recos: dict[str, Draft], *,
                      allow_partial: bool) -> list[str]:
    """Liste des erreurs qui interdisent d'appliquer le fichier (vide = OK)."""
    if not isinstance(raw, dict) or not raw:
        return ["le fichier doit être un objet JSON non vide {id: verdict}"]
    errors: list[str] = []
    for reco_id, entry in raw.items():
        where = f"{reco_id} :"
        found = recos.get(reco_id)
        if found is None:
            errors.append(f"{where} aucune reco de cet épisode ne porte cet id")
            continue
        if found.reco.get("status") != "draft":
            errors.append(f"{where} statut « {found.reco.get('status')} », "
                          "seules les recos draft se relisent ici")
        if not isinstance(entry, dict):
            errors.append(f"{where} le verdict doit être un objet")
            continue
        if entry.get("verdict") not in VERDICTS:
            errors.append(f"{where} verdict « {entry.get('verdict')} » inconnu "
                          f"(attendu : {', '.join(sorted(VERDICTS))})")
        confidence = entry.get("confidence")
        if (not isinstance(confidence, (int, float)) or isinstance(confidence, bool)
                or not 0 <= confidence <= 1):
            errors.append(f"{where} confidence doit être un nombre entre 0 et 1")
        if not isinstance(entry.get("reason"), str) or not entry["reason"].strip():
            errors.append(f"{where} reason vide")
        if not isinstance(entry.get("recommendedBy"), str):
            errors.append(f"{where} recommendedBy manquant (chaîne vide si douteux)")
        flags = entry.get("flags", [])
        if not isinstance(flags, list) or not all(isinstance(f, str) for f in flags):
            errors.append(f"{where} flags doit être une liste de chaînes")
        if not isinstance(entry.get("note", ""), str):
            errors.append(f"{where} note doit être une chaîne")
    if not allow_partial:
        missing = sorted(rid for rid, d in recos.items()
                         if d.reco.get("status") == "draft" and rid not in raw)
        if missing:
            errors.append(f"{len(missing)} reco(s) draft sans verdict : "
                          f"{', '.join(missing)} (--allow-partial pour passer outre)")
    return errors


def _agent_review(previous: Any, entry: dict[str, Any], *, model: str,
                  today: str) -> dict[str, Any]:
    review = {k: previous[k] for k in _HUMAN_KEYS
              if isinstance(previous, dict) and k in previous}
    review.update({
        "verdict": entry["verdict"],
        "confidence": entry["confidence"],
        "reason": entry["reason"].strip(),
        "model": model,
        "date": today,
        "applied": entry["verdict"] != "unsure",
    })
    if entry.get("flags"):
        review["flags"] = list(entry["flags"])
    if entry.get("note", "").strip():
        review["note"] = entry["note"].strip()
    return review


def apply_verdicts(raw: dict[str, Any], recos: dict[str, Draft], *, model: str,
                   today: str, dry_run: bool = False) -> int:
    """Applique des verdicts DÉJÀ validés. Renvoie le nombre de fichiers écrits."""
    written = 0
    for reco_id, entry in raw.items():
        draft = recos[reco_id]
        reco = dict(draft.reco)
        if entry["verdict"] != "unsure":
            apply_review_action(reco, entry["verdict"], entry["recommendedBy"].strip(),
                                reco_id)
        reco["agentReview"] = _agent_review(draft.reco.get("agentReview"), entry,
                                            model=model, today=today)
        if not dry_run and write_json_if_changed(draft.path, reco):
            written += 1
    return written


def check_integrity(source_id: str, guid: str, raw: dict[str, Any]) -> list[str]:
    """Relit le disque : chaque statut et chaque verdict sont-ils bien posés ?"""
    on_disk = load_episode_recos(source_id, guid)
    problems = []
    for reco_id, entry in raw.items():
        found = on_disk.get(reco_id)
        if found is None:
            problems.append(f"{reco_id} : fichier introuvable après écriture")
            continue
        reco = found.reco
        expected = _EXPECTED_STATUS[entry["verdict"]]
        if reco.get("status") != expected:
            problems.append(f"{reco_id} : statut « {reco.get('status')} », "
                            f"attendu « {expected} »")
        if (reco.get("agentReview") or {}).get("verdict") != entry["verdict"]:
            problems.append(f"{reco_id} : agentReview.verdict absent ou différent")
    return problems


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Applique les verdicts d'une relecture par agents.")
    parser.add_argument("--source", required=True, help="Identifiant de la source.")
    parser.add_argument("--guid", required=True, help="Guid de l'épisode relu.")
    parser.add_argument("--verdicts", required=True, type=Path,
                        help="Fichier JSON {id: verdict}.")
    parser.add_argument("--model", required=True,
                        help="Modèle qui a produit les verdicts (tracé dans agentReview).")
    parser.add_argument("--dry-run", action="store_true",
                        help="Valide et résume sans rien écrire.")
    parser.add_argument("--allow-partial", action="store_true",
                        help="Accepte que des recos draft restent sans verdict.")
    parser.add_argument("--force", action="store_true",
                        help="Ignore le verrou du review_server (écritures concurrentes).")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None, *, today: str | None = None,
         use_lock: bool = True) -> int:
    args = _parse_args(argv)
    try:
        raw = json.loads(args.verdicts.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        log.error("Fichier de verdicts illisible : %s", exc)
        return 2

    recos = load_episode_recos(args.source, args.guid)
    if not recos:
        log.error("Aucune reco pour l'épisode %s dans la source %s.", args.guid, args.source)
        return 2
    errors = validate_verdicts(raw, recos, allow_partial=args.allow_partial)
    if errors:
        log.error("Fichier refusé, rien n'a été écrit :")
        for err in errors:
            log.error("  - %s", err)
        return 2

    counts = Counter(entry["verdict"] for entry in raw.values())
    today = today or dt.date.today().isoformat()
    if args.dry_run:
        apply_verdicts(raw, recos, model=args.model, today=today, dry_run=True)
        log.info("Simulation — %d verdict(s) valides : %s", len(raw), dict(counts))
        return 0

    if use_lock:
        from review_lock import LockBusy, acquire_pipeline_lock
        try:
            with acquire_pipeline_lock(force=args.force):
                written = apply_verdicts(raw, recos, model=args.model, today=today)
        except LockBusy as exc:
            log.error("%s", exc)
            return 2
    else:
        written = apply_verdicts(raw, recos, model=args.model, today=today)

    problems = check_integrity(args.source, args.guid, raw)
    remaining = sum(1 for d in load_episode_recos(args.source, args.guid).values()
                    if d.reco.get("status") == "draft")
    log.info("%d fichier(s) écrit(s) · verdicts %s · %d draft restant(s)",
             written, dict(counts), remaining)
    if problems:
        log.error("Contrôle d'intégrité en échec :")
        for problem in problems:
            log.error("  - %s", problem)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
