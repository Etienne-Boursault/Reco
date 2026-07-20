"""
duplicate_canonical.py — Détecte les `Item` doublons (même œuvre
représentée par plusieurs ids).

Deux règles séparées (CR archi #13, M1) :

  - ``DuplicateCanonicalKeyRule`` : Items distincts avec même
    ``canonical_key``.
  - ``DuplicateExternalIdRule`` : Items distincts avec même
    ``externalIds.<id_kind>`` (paramétrable — par défaut ``tmdb``,
    forward-compat ``imdb`` / ``spotify`` / ``musicbrainz``).

Chaque cluster émet **un seul** issue (CR senior C2) avec un
``cluster_id`` stable (hash trié des membres) et la liste des membres
en `message`. Évite l'explosion 1 issue / membre / cluster.

Protection (C2) : canonical_key falsy (vide, None) est ignorée — un
canonical_key invalide est un autre symptôme (champ obligatoire absent
géré par ``required_fields``).
"""
from __future__ import annotations

import hashlib
from collections import defaultdict
from collections.abc import Iterator
from typing import Any

from domain.services.identity import canonical_key

from .base import LintContext, LintIssue, LintRule, Severity


def _cluster_id(members: list[str]) -> str:
    """ID stable d'un cluster : SHA-1 court des ids triés."""
    payload = "|".join(sorted(members)).encode("utf-8")
    return hashlib.sha1(payload, usedforsecurity=False).hexdigest()[:12]


class DuplicateCanonicalKeyRule(LintRule):
    name = "duplicate_canonical"
    severity = Severity.ERROR
    description = (
        "Plusieurs Items distincts partagent la même canonical_key "
        "(1 issue par cluster, cf. CR C2)."
    )

    def check(self, ctx: LintContext) -> Iterator[LintIssue]:
        by_canonical: dict[str, list[str]] = defaultdict(list)
        for item in ctx.items:
            ck = canonical_key(item.title, item.creator)
            if not ck:
                continue  # C2 : canonical_key falsy → ignoré
            by_canonical[ck].append(item.id)
        for ck, ids in by_canonical.items():
            if len(ids) <= 1:
                continue
            sorted_ids = sorted(ids)
            cid = _cluster_id(sorted_ids)
            yield LintIssue(
                rule=self.name, severity=self.severity,
                entity_type="cluster", entity_id=cid,
                field="canonical_key",
                message=(
                    f"canonical_key={ck!r} partagée par {len(sorted_ids)} "
                    f"items : {sorted_ids}"
                ),
                cluster_id=cid,
            )


class DuplicateExternalIdRule(LintRule):
    name = "duplicate_external_id"
    severity = Severity.ERROR
    description = (
        "Plusieurs Items distincts partagent le même externalIds.<kind>."
    )

    def __init__(self, id_kind: str = "tmdb") -> None:
        if not isinstance(id_kind, str) or not id_kind.strip():
            raise ValueError("id_kind doit être une str non vide")
        self._kind = id_kind

    @property
    def id_kind(self) -> str:
        return self._kind

    def check(self, ctx: LintContext) -> Iterator[LintIssue]:
        by_eid: dict[Any, list[str]] = defaultdict(list)
        for item in ctx.items:
            value = getattr(item.external_ids, self._kind, None)
            # Bool est sous-type d'int → on l'exclut explicitement pour tmdb.
            if value is None or isinstance(value, bool):
                continue
            by_eid[value].append(item.id)
        for value, ids in by_eid.items():
            if len(ids) <= 1:
                continue
            sorted_ids = sorted(ids)
            cid = _cluster_id(sorted_ids)
            yield LintIssue(
                rule=self.name, severity=self.severity,
                entity_type="cluster", entity_id=cid,
                field=f"externalIds.{self._kind}",
                message=(
                    f"externalIds.{self._kind}={value!r} partagé par "
                    f"{len(sorted_ids)} items : {sorted_ids}"
                ),
                cluster_id=cid,
            )


# Backward-compat : alias historique (tests existants).
DuplicateCanonicalRule = DuplicateCanonicalKeyRule


__all__ = [
    "DuplicateCanonicalKeyRule",
    "DuplicateCanonicalRule",  # legacy alias
    "DuplicateExternalIdRule",
]
