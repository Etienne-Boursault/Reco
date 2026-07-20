"""Persistance des verdicts d'audit en **sidecar files** versionnés.

Layout disque : ``tools/output/enrich_audit/<source>/<item_id>.json``.

Archive (CR archi P1 #16) : avant un ``clear_source``, les sidecars existants
sont déplacés dans
``tools/output/enrich_audit/.archive/<source>/<ISO8601>/``. Permet ``--undo-last``.

Format sidecar (CR archi P1 #10, #14) :
```json
{
  "schemaVersion": 1,
  "itemId": "abc12345",
  "tmdbId": 1577,
  "auditedAt": "2026-06-10T12:00:00Z",
  "auditorVersion": "0.2.0",
  "enrichmentSuspect": true,
  "suspicions": [
    {"kind": "title_mismatch", "detail": "…", "severity": "warning",
     "confidence": 0.83}
  ]
}
```

Pourquoi sidecar plutôt qu'un flag dans l'entité ``Item`` ? Cf. ADR 0014 —
on garde le domaine Item pur et on isole l'output d'un audit dans son propre
bucket (extensible, jetable, sans migration schema_version Item).

Écriture atomique via ``common.atomic_write_text`` (Windows-safe), même
politique que ``ItemRepoJson``.
"""
from __future__ import annotations

import json
import logging
import shutil
from datetime import datetime, timezone
from pathlib import Path

from audit_core.sidecar import _safe_segment  # SSOT — cf. ADR 0019

from common import OUTPUT_DIR, atomic_write_text  # type: ignore[attr-defined]

from .service import AuditResult
from .types import (
    AUDITOR_VERSION,
    SIDECAR_SCHEMA_VERSION,
    Severity,
    Suspicion,
)

_log = logging.getLogger("reco.enrich_audit.flag_writer")

ENRICH_AUDIT_DIR: Path = OUTPUT_DIR / "enrich_audit"
ARCHIVE_DIR_NAME = ".archive"

# Note ADR 0019 (C-04) : ``_safe_segment`` est désormais réexporté depuis
# ``audit_core.sidecar`` (SSOT — modèle strict identique à l'ancien local).
# La sémantique est inchangée pour enrich_audit (whitelist déjà alignée).


def sidecar_path(source_id: str, item_id: str, *, base_dir: Path | None = None) -> Path:
    """Calcule le chemin du sidecar.

    `base_dir` : injectable pour les tests (sandbox tmp_path).
    """
    _safe_segment("source_id", source_id)
    _safe_segment("item_id", item_id)
    root = base_dir if base_dir is not None else ENRICH_AUDIT_DIR
    return root / source_id / f"{item_id}.json"


def archive_dir(
    source_id: str,
    *,
    base_dir: Path | None = None,
    timestamp: str | None = None,
) -> Path:
    """Calcule le dossier d'archive d'une source pour un timestamp donné."""
    _safe_segment("source_id", source_id)
    ts = timestamp or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    root = base_dir if base_dir is not None else ENRICH_AUDIT_DIR
    return root / ARCHIVE_DIR_NAME / source_id / ts


def _suspicion_to_dict(s: Suspicion) -> dict:
    out: dict = {
        "kind": s.kind,
        "detail": s.detail,
        "severity": s.severity.value,
    }
    if s.confidence is not None:
        out["confidence"] = s.confidence
    return out


def _suspicion_from_dict(d: dict) -> Suspicion:
    severity_raw = d.get("severity", "warning")
    try:
        severity = Severity(severity_raw)
    except ValueError as exc:
        raise ValueError(f"severity invalide: {severity_raw!r}") from exc
    confidence_raw = d.get("confidence")
    if confidence_raw is None:
        confidence: float | None = None
    else:
        confidence = float(confidence_raw)
    return Suspicion(
        kind=str(d["kind"]),
        detail=str(d.get("detail", "")),
        severity=severity,
        confidence=confidence,
    )


def write_sidecar(
    result: AuditResult,
    source_id: str,
    *,
    base_dir: Path | None = None,
    audited_at: str | None = None,
    tmdb_id: int | None = None,
    tmdb_data_date: str | None = None,
) -> Path:
    """Sérialise un `AuditResult` en JSON et l'écrit (atomique, mkdir parents).

    Args:
        result: verdict à écrire.
        source_id: slug source.
        base_dir: override pour tests.
        audited_at: ISO8601 UTC. **Injecté** (jamais ``Date.now()`` côté
            module — cf. CR archi #14, idempotence/tests). Si ``None``,
            calcule maintenant.
        tmdb_id: pour debug (CR senior L8). Optionnel.
        tmdb_data_date: date à laquelle la donnée TMDB sous-jacente a été
            récupérée. Pour Phase 2 #17 ré-enrich proactif.

    Renvoie le chemin écrit.
    """
    path = sidecar_path(source_id, result.item_id, base_dir=base_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    ts = audited_at or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    payload: dict = {
        "schemaVersion": SIDECAR_SCHEMA_VERSION,
        "auditorVersion": AUDITOR_VERSION,
        "auditedAt": ts,
        "itemId": result.item_id,
        "enrichmentSuspect": result.is_suspect,
        "suspicions": [_suspicion_to_dict(s) for s in result.suspicions],
    }
    if tmdb_id is not None:
        payload["tmdbId"] = int(tmdb_id)
    if tmdb_data_date is not None:
        payload["tmdbDataDate"] = tmdb_data_date
    text = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    atomic_write_text(path, text)
    return path


def read_sidecar(
    source_id: str,
    item_id: str,
    *,
    base_dir: Path | None = None,
) -> AuditResult | None:
    """Recharge un `AuditResult` depuis disque. ``None`` si absent ou
    illisible.

    Source de vérité pour ``is_suspect`` : **les suspicions**
    (CR senior C2). ``enrichmentSuspect`` est ignoré à la lecture mais
    un warning est loggé en cas d'incohérence (`sidecar_malformed`).
    """
    path = sidecar_path(source_id, item_id, base_dir=base_dir)
    if not path.exists():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:  # noqa: BLE001
        _log.warning("Sidecar illisible %s : %s", path, exc)
        return None
    if not isinstance(raw, dict):
        _log.warning("Sidecar non-objet %s", path)
        return None
    susps_raw = raw.get("suspicions") or []
    if not isinstance(susps_raw, list):
        _log.warning("Sidecar suspicions non-list %s", path)
        return None
    try:
        suspicions = tuple(
            _suspicion_from_dict(d) for d in susps_raw if isinstance(d, dict)
        )
    except (KeyError, ValueError) as exc:
        _log.warning("Sidecar suspicion invalide %s : %s", path, exc)
        return None

    # CR senior C2/C3 : invariant `is_suspect = bool(suspicions)`. Si le
    # flag persisté est incohérent, on log un warning et on prend la
    # vérité dérivée.
    persisted_flag = raw.get("enrichmentSuspect")
    derived_flag = bool(suspicions)
    if isinstance(persisted_flag, bool) and persisted_flag != derived_flag:
        _log.warning(
            "Sidecar %s : enrichmentSuspect=%s incohérent avec "
            "len(suspicions)=%d → on prend la valeur dérivée",
            path, persisted_flag, len(suspicions),
        )
    return AuditResult(
        item_id=str(raw.get("itemId") or item_id),
        is_suspect=derived_flag,
        suspicions=suspicions,
    )


def list_sidecars(source_id: str, *, base_dir: Path | None = None) -> list[Path]:
    """Liste les sidecars existants pour une source. Ordre stable (tri).

    Ignore le dossier d'archive interne (`.archive`).
    """
    _safe_segment("source_id", source_id)
    root = (base_dir if base_dir is not None else ENRICH_AUDIT_DIR) / source_id
    if not root.exists():
        return []
    return sorted(root.glob("*.json"))


def clear_source(
    source_id: str,
    *,
    base_dir: Path | None = None,
    archive: bool = True,
    archive_timestamp: str | None = None,
) -> int:
    """Vide les sidecars d'une source. Renvoie le nombre traité.

    Args:
        archive: si ``True`` (défaut), déplace les sidecars vers
            ``.archive/<source>/<ISO8601>/`` au lieu de les supprimer
            (CR archi P1 #16 — réversible via `restore_archive`).
        archive_timestamp: injecté pour les tests (sinon now UTC).

    Idempotent : ne lève pas si le dossier n'existe pas.
    """
    paths = list_sidecars(source_id, base_dir=base_dir)
    if not paths:
        return 0

    if archive:
        archive_root = archive_dir(
            source_id, base_dir=base_dir, timestamp=archive_timestamp,
        )
        archive_root.mkdir(parents=True, exist_ok=True)
        count = 0
        for p in paths:
            try:
                shutil.move(str(p), str(archive_root / p.name))
                count += 1
            except OSError as exc:  # noqa: BLE001  # pragma: no cover
                _log.warning("Archive échouée %s → %s : %s", p, archive_root, exc)
        return count

    # Mode no-archive : delete direct (utilisé pour tests / nettoyages forcés).
    count = 0
    for p in paths:
        try:
            p.unlink()
            count += 1
        except OSError:
            pass
    return count


def list_archives(source_id: str, *, base_dir: Path | None = None) -> list[Path]:
    """Liste les snapshots d'archive d'une source, du + récent au + ancien."""
    _safe_segment("source_id", source_id)
    root = (base_dir if base_dir is not None else ENRICH_AUDIT_DIR) / ARCHIVE_DIR_NAME / source_id
    if not root.exists():
        return []
    return sorted(
        (p for p in root.iterdir() if p.is_dir()),
        reverse=True,
    )


def restore_archive(
    source_id: str,
    *,
    base_dir: Path | None = None,
    archive_timestamp: str | None = None,
) -> int:
    """Restaure le dernier snapshot d'archive (CR archi P1 #16 — `--undo-last`).

    Args:
        archive_timestamp: si fourni, restaure ce snapshot spécifique
            (sinon dernier). Renvoie le nombre de fichiers restaurés.

    Stratégie : on déplace l'archive choisie dans le dossier source
    (en écrasant les sidecars courants). Pas idempotent à 100 % (un
    re-restore après modif partielle peut perdre des fichiers ajoutés
    entretemps) — c'est documenté.
    """
    if archive_timestamp is not None:
        archive_root = archive_dir(
            source_id, base_dir=base_dir, timestamp=archive_timestamp,
        )
        if not archive_root.exists():
            return 0
    else:
        archives = list_archives(source_id, base_dir=base_dir)
        if not archives:
            return 0
        archive_root = archives[0]

    target_root = (base_dir if base_dir is not None else ENRICH_AUDIT_DIR) / source_id
    target_root.mkdir(parents=True, exist_ok=True)
    count = 0
    for p in archive_root.glob("*.json"):
        try:
            shutil.move(str(p), str(target_root / p.name))
            count += 1
        except OSError as exc:  # noqa: BLE001  # pragma: no cover
            _log.warning("Restore archive échouée %s : %s", p, exc)
    # Si le dossier d'archive est vide, on peut le supprimer.
    try:
        archive_root.rmdir()
    except OSError:  # pragma: no cover
        pass
    return count


__all__ = [
    "ARCHIVE_DIR_NAME",
    "ENRICH_AUDIT_DIR",
    "archive_dir",
    "clear_source",
    "list_archives",
    "list_sidecars",
    "read_sidecar",
    "restore_archive",
    "sidecar_path",
    "write_sidecar",
]
