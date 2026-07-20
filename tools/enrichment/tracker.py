"""Tracker `enrichedAt` — calcul des champs stale par item.

Modèle :
  - Chaque Item/reco porte un dict optionnel `enrichedAt: {field: ISO8601}`.
  - Un champ est "stale" si :
       a) il est ABSENT de `enrichedAt` (jamais enrichi), OU
       b) `now - enrichedAt[field] > older_than`.

API minimaliste, indépendante de l'IO (testable pure).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone


def _parse_iso(value: str) -> datetime:
    """Parse un ISO8601 en datetime aware UTC.

    Tolère le suffixe 'Z' (Python <3.11 le rejetait).
    """
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def now_iso() -> str:
    """Timestamp ISO8601 UTC avec suffixe 'Z' (format historique du projet)."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass(frozen=True)
class EnrichedAtTracker:
    """Lit/écrit le sous-objet `enrichedAt` d'un item.

    Stateless — chaque méthode prend l'item courant. Le tracker ne modifie
    JAMAIS l'item directement (le `field_refresher` s'en charge) ; il ne
    fait qu'observer/calculer.
    """

    older_than: timedelta
    now: datetime  # injectable pour tests déterministes

    def is_stale(self, item: dict, field: str) -> bool:
        """True si `field` doit être (re)enrichi."""
        ea = item.get("enrichedAt") or {}
        ts = ea.get(field)
        if not ts:
            return True
        try:
            dt = _parse_iso(ts)
        except (ValueError, TypeError):
            # Timestamp corrompu → on considère stale (sera réécrit).
            return True
        return (self.now - dt) > self.older_than


def stale_fields(
    item: dict,
    candidate_fields: list[str],
    *,
    older_than: timedelta,
    now: datetime,
) -> list[str]:
    """Helper fonctionnel : renvoie la liste des champs stale parmi les candidats.

    Ordre préservé (utile pour la stabilité des logs).
    """
    tracker = EnrichedAtTracker(older_than=older_than, now=now)
    return [f for f in candidate_fields if tracker.is_stale(item, f)]
