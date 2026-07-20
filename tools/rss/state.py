"""rss.state — PollingState JSON sidecar (atomic, schemaVersion, LRU bornée).

Le sidecar vit dans `tools/output/rss/<source>/state.json` (gitignored).
Sert à l'idempotence du poll : sans cet état, chaque run notifierait
l'intégralité du flux à chaque appel.

Garanties :
- `schemaVersion = 1` → toute évolution future bumpe l'entier et propose
  un upgrade idempotent en lecture (cf. ADR 0010).
- `seenGuids` est borné à `MAX_SEEN_GUIDS` (10_000) en politique LRU :
  les plus vieux sont évincés lorsque la liste dépasse le seuil. Évite
  une croissance non bornée sur des podcasts à 500+ épisodes.
- Écriture atomique via `common.atomic_write_text` (cf. ADR 0009).
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

from common import atomic_write_text

POLLING_STATE_SCHEMA_VERSION = 1
MAX_SEEN_GUIDS = 10_000


@dataclass(frozen=True, slots=True)
class PollingState:
    """État de polling d'un flux RSS pour une source.

    `seen_guids` est ordonnée : éléments les plus récents EN FIN. La
    politique LRU pour la borne `MAX_SEEN_GUIDS` éviente donc le DÉBUT
    de la liste (les plus vieux).
    """

    source_id: str
    last_checked_at: str = ""
    last_etag: str | None = None
    last_modified: str | None = None
    seen_guids: tuple[str, ...] = ()
    metadata: dict[str, str] = field(default_factory=dict)
    schema_version: int = POLLING_STATE_SCHEMA_VERSION

    def with_observed(
        self,
        *,
        guids: list[str],
        checked_at: str,
        etag: str | None = None,
        last_modified: str | None = None,
        metadata: dict[str, str] | None = None,
    ) -> PollingState:
        """Renvoie un nouvel état après observation d'un fetch.

        `guids` est la liste des GUIDs vus dans le flux ce run-ci, dans
        l'ordre flux (typiquement plus récent en tête). On les ajoute en
        FIN de `seen_guids` (ordre LRU : on évince le DÉBUT), seulement
        s'ils ne sont pas déjà connus. Puis on tronque à `MAX_SEEN_GUIDS`.
        """
        existing = set(self.seen_guids)
        # Inverse l'ordre pour que le PLUS RÉCENT du flux finisse en
        # tout dernier (= MRU). On préserve les anciens GUIDs au début
        # mais on les évince en priorité quand on dépasse la borne.
        merged = list(self.seen_guids)
        for g in reversed(guids):
            if g and g not in existing:
                merged.append(g)
                existing.add(g)
        if len(merged) > MAX_SEEN_GUIDS:
            merged = merged[-MAX_SEEN_GUIDS:]
        return replace(
            self,
            seen_guids=tuple(merged),
            last_checked_at=checked_at,
            last_etag=etag if etag is not None else self.last_etag,
            last_modified=(
                last_modified if last_modified is not None else self.last_modified
            ),
            metadata=metadata if metadata is not None else dict(self.metadata),
        )


def state_path_for(source_id: str, *, state_dir: Path) -> Path:
    """Chemin du sidecar JSON pour une source."""
    return state_dir / source_id / "state.json"


def load_state(source_id: str, *, state_dir: Path) -> PollingState:
    """Charge l'état d'une source, ou renvoie un état vierge si absent.

    Robuste aux fichiers corrompus / illisibles : renvoie un état vierge
    et log un warning (à charge de l'appelant) — un poll RSS ne doit pas
    crasher pour autant.
    """
    path = state_path_for(source_id, state_dir=state_dir)
    if not path.exists():
        return PollingState(source_id=source_id)
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return PollingState(source_id=source_id)
    if not isinstance(raw, dict):
        return PollingState(source_id=source_id)
    return PollingState(
        source_id=str(raw.get("sourceId", source_id)),
        last_checked_at=str(raw.get("lastCheckedAt", "") or ""),
        last_etag=raw.get("lastEtag") or None,
        last_modified=raw.get("lastModified") or None,
        seen_guids=tuple(str(g) for g in (raw.get("seenGuids") or []) if g),
        metadata=dict(raw.get("metadata") or {}),
        schema_version=int(raw.get("schemaVersion", POLLING_STATE_SCHEMA_VERSION)),
    )


def _serialize(state: PollingState) -> str:
    payload: dict[str, Any] = {
        "schemaVersion": state.schema_version,
        "sourceId": state.source_id,
        "lastCheckedAt": state.last_checked_at,
        "lastEtag": state.last_etag,
        "lastModified": state.last_modified,
        "seenGuids": list(state.seen_guids),
        "metadata": dict(state.metadata),
    }
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def save_state(state: PollingState, *, state_dir: Path) -> Path:
    """Écrit l'état atomiquement et renvoie le chemin écrit."""
    path = state_path_for(state.source_id, state_dir=state_dir)
    atomic_write_text(path, _serialize(state))
    return path
