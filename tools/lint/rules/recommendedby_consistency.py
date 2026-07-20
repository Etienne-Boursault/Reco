"""
recommendedby_consistency.py — Vérifie que ``reco.recommendedBy`` est
cohérent avec les hosts/guests de l'épisode pointé.

Politique :
  - WARNING (pas ERROR) car un invité peut être mentionné en passant
    sans figurer dans la fiche épisode (cf. ADR 0012).
  - Comparaison **NFKC + casefold** sur le set
    ``hosts ∪ guests ∪ guestsParsed`` (CR senior H8 — corrige `Mélanie
    Doutey` NFD vs NFC).
  - Sentinels (« Inconnu », « Invité », « Plusieurs invités »…) :
    silencieux (whitelistés) — CR senior C3.
  - Co-recos : `recommendedBy` peut être `"Alice & Bob"`, `"Alice, Bob"`,
    `"Alice et Bob"`, `"Alice + Bob"` — on split et flag seulement si
    AUCUN membre n'est connu (CR senior C3).
  - ``orphan_episode_ref`` : INFO quand ``episodeGuid`` référence un
    épisode introuvable (CR senior L11).
  - Respecte les overrides ``LintContext.overrides`` (CR senior H4).
"""
from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterator
from typing import Any

from .base import LintContext, LintIssue, LintRule, Severity


# Sentinels normalisés (NFKC + casefold) à whitelister.
_SENTINELS_RAW = (
    "Inconnu", "Invité", "Invitée", "Intervenant", "Intervenante",
    "Plusieurs invités", "Tout le monde", "intervenant", "invité",
)

# Split co-recos : `&`, `,`, ` et `, `+`.
_SPLIT_RE = re.compile(r"\s*(?:&|\+|,|\bet\b)\s*", re.IGNORECASE)


def _normalize_name(value: Any) -> str:
    """NFKC + strip + casefold (H8).

    Garantit que ``"Mélanie"`` (NFD : M + e + ́ + l...) == ``"Mélanie"``
    (NFC précomposé). casefold() est plus large que lower() (cas grec/ß).
    """
    if not isinstance(value, str):
        return ""
    return unicodedata.normalize("NFKC", value).strip().casefold()


_SENTINELS_NORM: frozenset[str] = frozenset(
    _normalize_name(s) for s in _SENTINELS_RAW
)


def _split_names(value: str) -> tuple[str, ...]:
    """Split un ``recommendedBy`` en membres normalisés (sans vide)."""
    parts = _SPLIT_RE.split(value)
    return tuple(_normalize_name(p) for p in parts if p and p.strip())


def _episode_known_names(ep: dict[str, Any]) -> set[str]:
    """Union normalisée des hosts/guests/guestsParsed d'un épisode."""
    names: set[str] = set()
    for key in ("hosts", "guests", "guestsParsed"):
        v = ep.get(key)
        if isinstance(v, (list, tuple)):
            for n in v:
                norm = _normalize_name(n)
                if norm:
                    names.add(norm)
    return names


class RecommendedByConsistencyRule(LintRule):
    name = "recommendedby_consistency"
    severity = Severity.WARNING
    description = (
        "`recommendedBy` ne correspond à aucun host/guest de l'épisode "
        "(NFKC + casefold, co-recos splittés, sentinels whitelistés)."
    )

    def check(self, ctx: LintContext) -> Iterator[LintIssue]:
        # Pré-calculer le set de hosts par défaut depuis la config source
        # (utile quand l'épisode n'a ni guests ni guestsParsed).
        source_hosts: set[str] = set()
        if ctx.source_config is not None:
            for h in ctx.source_config.hosts:
                norm = _normalize_name(h)
                if norm:
                    source_hosts.add(norm)

        for reco in ctx.recos:
            rb = reco.get("recommendedBy")
            if not isinstance(rb, str) or not rb.strip():
                continue
            eid_value = reco.get("id") or "<unknown>"
            eid = (
                eid_value if isinstance(eid_value, str) and eid_value.strip()
                else "<unknown>"
            )
            if ctx.is_overridden(entity_id=eid, field="recommendedBy"):
                continue  # H4

            ep_guid = reco.get("episodeGuid")
            ep = ctx.episode_by_guid(ep_guid) if isinstance(ep_guid, str) else None

            # L11 : si guid présent mais épisode introuvable → INFO orphan.
            if (
                isinstance(ep_guid, str) and ep_guid
                and ep is None
            ):
                yield LintIssue(
                    rule="orphan_episode_ref", severity=Severity.INFO,
                    entity_type="reco", entity_id=eid,
                    field="episodeGuid",
                    message=(
                        f"episodeGuid={ep_guid!r} ne correspond à aucun "
                        "épisode chargé"
                    ),
                )

            known = set(source_hosts)
            if ep is not None:
                known |= _episode_known_names(ep)
            if not known:
                continue  # impossible de vérifier

            # Split co-recos (C3).
            members = _split_names(rb)
            if not members:
                continue
            # Sentinels : si TOUS les membres sont des sentinels, on est
            # silencieux. Si au moins UN sentinel + au moins un membre
            # connu, OK. Sinon, on flag si AUCUN membre connu.
            non_sentinel = [m for m in members if m not in _SENTINELS_NORM]
            if not non_sentinel:
                continue  # 100% sentinels → silencieux
            if any(m in known for m in non_sentinel):
                continue  # au moins un co-reco trouvé
            yield LintIssue(
                rule=self.name, severity=self.severity,
                entity_type="reco", entity_id=eid, field="recommendedBy",
                message=(
                    f"`recommendedBy`={rb!r} absent des hosts/guests "
                    f"de l'épisode {ep_guid!r}"
                ),
            )


__all__ = ["RecommendedByConsistencyRule"]
