"""review_undo.py — Pile d'annulation des décisions de relecture.

Avant chaque décision humaine sur une reco depuis /doutes (Valider, Citation,
Leur œuvre, Pas une reco, ou une correction via « Corriger »), on empile un
INSTANTANÉ de l'état disque de la reco. « ↩ Annuler » (POST /undo-save) dépile
le dernier instantané et le réécrit tel quel : la reco revient EXACTEMENT à son
état d'avant la décision et réapparaît donc dans la file des doutes.

Contexte mono-utilisateur / mono-thread : la pile vit sur disque en fichiers
numérotés sous ``tools/output/review-undo/<source>/`` — hors du contenu
versionné (``src/content``) — et survit au rechargement comme au redémarrage du
serveur. LIFO : chaque annulation défait la décision la plus récente ; annuler
plusieurs fois remonte l'historique décision par décision.

Retour utilisateur 2026-07-24 : « un bouton retour pour annuler une validation
faite par erreur ».
"""
from __future__ import annotations

import json
from pathlib import Path

from common import TOOLS_DIR, log, write_json_if_changed

_UNDO_ROOT: Path = TOOLS_DIR / "output" / "review-undo"
# Borne la profondeur : au-delà, on oublie les décisions les plus anciennes
# (on ne remonte jamais un historique infini — inutile et coûteux en fichiers).
_MAX_DEPTH = 100


def _dir(source_id: str) -> Path:
    return _UNDO_ROOT / source_id


def _entries(source_id: str) -> list[Path]:
    """Instantanés de la source, du plus ANCIEN au plus RÉCENT (tri lexical sur
    l'index numéroté zero-paddé)."""
    d = _dir(source_id)
    if not d.exists():
        return []
    return sorted(d.glob("*.json"))


def _next_index(existing: list[Path]) -> int:
    if not existing:
        return 0
    try:
        return int(existing[-1].name.split("__", 1)[0]) + 1
    except ValueError:
        return len(existing)


def push_snapshot(source_id: str, reco_id: str, path: str,
                  snapshot: dict, label: str = "") -> None:
    """Empile l'état actuel (`snapshot`) d'une reco AVANT de la muter.

    `path` : chemin disque exact de la reco (restauré à l'identique au pop).
    `snapshot` doit être l'état PRÉ-mutation (copie profonde côté appelant).
    """
    d = _dir(source_id)
    try:
        d.mkdir(parents=True, exist_ok=True)
        existing = _entries(source_id)
        n = _next_index(existing)
        payload = {"reco_id": reco_id, "path": path,
                   "label": label, "snapshot": snapshot}
        (d / f"{n:06d}__{reco_id}.json").write_text(
            json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        # Purge des plus anciennes au-delà de la profondeur max.
        for p in _entries(source_id)[:-_MAX_DEPTH]:
            try:
                p.unlink()
            except OSError:
                pass
    except OSError as exc:
        # L'annulation est un filet de sécurité best-effort : si on ne peut pas
        # empiler (disque plein, droits…), la décision s'applique quand même —
        # on ne casse PAS le flux de relecture pour un undo indisponible.
        log.warning("Undo: empilement %s impossible (%s)", reco_id, exc)


def has_undo(source_id: str) -> bool:
    return bool(_entries(source_id))


def pop_and_restore(source_id: str) -> dict:
    """Dépile la dernière décision et restaure la reco sur disque.

    Retourne ``{"restored": bool, "reco_id": str, "guid": str}``.
    """
    ents = _entries(source_id)
    if not ents:
        return {"restored": False, "reco_id": "", "guid": ""}
    last = ents[-1]
    try:
        data = json.loads(last.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        log.warning("Undo: entrée illisible %s (%s), jetée", last.name, exc)
        try:
            last.unlink()
        except OSError:
            pass
        return {"restored": False, "reco_id": "", "guid": ""}
    reco_id = data.get("reco_id", "")
    snapshot = data.get("snapshot")
    path = data.get("path")
    guid = (snapshot or {}).get("episodeGuid", "")
    if snapshot is not None and path:
        try:
            write_json_if_changed(Path(path), snapshot)
        except OSError as exc:
            log.warning("Undo: restauration %s échouée (%s)", reco_id, exc)
            return {"restored": False, "reco_id": reco_id, "guid": guid}
    try:
        last.unlink()
    except OSError:
        pass
    log.info("Undo: %s restaurée depuis l'instantané", reco_id)
    return {"restored": True, "reco_id": reco_id, "guid": guid}
