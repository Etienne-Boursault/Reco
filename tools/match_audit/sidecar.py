"""Sidecar files — verdicts d'audit isolés du domaine épisode.

Cf. ADR 0015 (sidecar pattern). Layout :

    tools/output/match_audit/<source>/<guid>.json

Le sidecar contient le détail complet (``suspicions[]``, ``auditedAt``),
tandis que le JSON d'épisode ne reçoit qu'un MIROIR booléen
``matchSuspect: true`` pour rester forward-compat avec les consommateurs
Astro (le badge UI). On garde donc le best des deux mondes : domaine pur,
détails extensibles côté pipeline.
"""
from __future__ import annotations

import json
import logging
from collections.abc import Iterator
from datetime import datetime, timezone
from pathlib import Path

from audit_core.sidecar import _safe_segment

from common import OUTPUT_DIR, atomic_write_text, slugify  # type: ignore[attr-defined]

from tools.match_audit.service import MatchAuditResult
from tools.match_audit.types import severity_value

#: Version courante du schéma sidecar match_audit. R-01 (ADR 0019) :
#: tous les sidecars écrits depuis Sprint 2 portent ``schemaVersion: 1``.
#: Lecture rétro-compat : un sidecar SANS ``schemaVersion`` est lu comme
#: ``schemaVersion=0`` (legacy, accepté avec warning log).
SIDECAR_SCHEMA_VERSION: int = 1

_log = logging.getLogger("reco.match_audit.sidecar")

MATCH_AUDIT_DIR: Path = OUTPUT_DIR / "match_audit"


def _safe(component: str, label: str) -> str:
    """Wrapper rétro-compat : délègue à ``audit_core.sidecar._safe_segment``.

    Nouvelle politique (S-01 ADR 0019) : whitelist stricte
    ``^[a-z0-9][a-z0-9_-]{0,128}$`` + rejet NUL + Windows-reserved.
    Le pattern laxiste ``r"[/\\\\]|\\.\\."`` est remplacé.
    """
    return _safe_segment(label, component)


def sidecar_path(
    source_id: str,
    episode_guid: str,
    *,
    base_dir: Path | None = None,
) -> Path:
    """Chemin du sidecar pour un (source, guid) donné."""
    _safe(source_id, "source_id")
    _safe(episode_guid, "episode_guid")
    root = base_dir if base_dir is not None else MATCH_AUDIT_DIR
    return root / source_id / f"{slugify(episode_guid)}.json"


def sidecar_dir_for(
    source_id: str, *, base_dir: Path | None = None,
) -> Path:
    _safe(source_id, "source_id")
    root = base_dir if base_dir is not None else MATCH_AUDIT_DIR
    return root / source_id


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z",
    )


def write_sidecar(
    result: MatchAuditResult,
    source_id: str,
    *,
    base_dir: Path | None = None,
    audited_at: str | None = None,
) -> Path:
    """Sérialise un ``MatchAuditResult`` en sidecar JSON (atomique).

    Format (ordre préservé, ``sort_keys=False``) :

    ```json
    {
      "episodeGuid": "abc",
      "matchSuspect": true,
      "suspicions": [
        {"kind": "duration_mismatch", "detail": "...", "severity": "error"}
      ],
      "auditedAt": "2026-06-10T12:34:56Z"
    }
    ```
    """
    path = sidecar_path(source_id, result.episode_guid, base_dir=base_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schemaVersion": SIDECAR_SCHEMA_VERSION,  # R-01 (ADR 0019)
        "episodeGuid": result.episode_guid,
        "matchSuspect": result.is_suspect,
        "suspicions": [
            {
                "kind": s.kind,
                "detail": s.detail,
                "severity": severity_value(s.severity),
            }
            for s in result.suspicions
        ],
        "auditedAt": audited_at or _utcnow_iso(),
    }
    text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    atomic_write_text(path, text)
    return path


def read_sidecar(
    source_id: str,
    episode_guid: str,
    *,
    base_dir: Path | None = None,
) -> dict | None:
    """Lit un sidecar. ``None`` si absent / illisible."""
    path = sidecar_path(source_id, episode_guid, base_dir=base_dir)
    if not path.exists():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(raw, dict):
        return None
    # R-01 rétro-compat (ADR 0019) : sidecar sans schemaVersion = legacy v0.
    # Accepté avec un warning loggué une fois.
    sv = raw.get("schemaVersion", 0)
    if sv == 0:
        _log.warning(
            "Sidecar match_audit legacy (sans schemaVersion) lu : %s",
            path,
        )
    return raw


def list_sidecars(
    source_id: str, *, base_dir: Path | None = None,
) -> list[Path]:
    d = sidecar_dir_for(source_id, base_dir=base_dir)
    if not d.exists():
        return []
    return sorted(d.glob("*.json"))


def iter_sidecars(
    source_id: str, *, base_dir: Path | None = None,
) -> Iterator[dict]:
    for p in list_sidecars(source_id, base_dir=base_dir):
        try:
            raw = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(raw, dict):
            yield raw


def delete_sidecar(
    source_id: str,
    episode_guid: str,
    *,
    base_dir: Path | None = None,
) -> bool:
    path = sidecar_path(source_id, episode_guid, base_dir=base_dir)
    if not path.exists():
        return False
    try:
        path.unlink()
        return True
    except OSError:  # pragma: no cover — Windows permissions edge
        return False


__all__ = [
    "MATCH_AUDIT_DIR",
    "SIDECAR_SCHEMA_VERSION",
    "delete_sidecar",
    "iter_sidecars",
    "list_sidecars",
    "read_sidecar",
    "sidecar_dir_for",
    "sidecar_path",
    "write_sidecar",
]
