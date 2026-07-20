"""audit_core.sidecar — segments de chemin sûrs + helpers atomiques.

SSOT de la validation de segments de chemin pour les sidecars d'audit.
Avant : 3 patterns divergents (``enrich_audit`` strict / ``match_audit``
laxiste / ``lint`` n'en a pas besoin).
Après : ``_safe_segment`` strict, modèle ``enrich_audit``.

Politique :

- Whitelist stricte : ``^[a-z0-9][a-z0-9_-]{0,128}$``.
- Rejet du NUL byte.
- Rejet des noms réservés Windows (``con``, ``prn``, ``aux``, ``nul``,
  ``com1..9``, ``lpt1..9``) — comparaison case-insensitive.

Compat data :

- Les ``source_id`` Reco sont des slugs minuscules (``un-bon-moment``) :
  conformes.
- Les ``episode.guid`` Acast sont des hex/ULIDs : conformes.
- Les ``item.id`` sont des slugs alphanum-tirets-underscores : conformes.

Si un jour un dataset utilise des caractères hors set, on devra slugifier
en amont (cf. ``common.slugify``), surtout pas relâcher cette regex.
"""
from __future__ import annotations

import re
from pathlib import Path

_SAFE_SEGMENT_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,128}$")

_WIN_RESERVED: frozenset[str] = frozenset({
    "con", "nul", "aux", "prn",
    "com1", "com2", "com3", "com4", "com5",
    "com6", "com7", "com8", "com9",
    "lpt1", "lpt2", "lpt3", "lpt4", "lpt5",
    "lpt6", "lpt7", "lpt8", "lpt9",
})


def _safe_segment(name: str, value: str) -> str:
    """Valide qu'un segment de chemin est sûr.

    Args:
        name: étiquette du segment (pour les messages d'erreur).
        value: la valeur à valider.

    Returns:
        ``value`` inchangé si valide.

    Raises:
        ValueError: si ``value`` n'est pas une str, est vide, contient
            un NUL, ne matche pas la whitelist, ou est un nom réservé
            Windows.
    """
    if not isinstance(value, str) or not value:
        raise ValueError(
            f"{name} doit être une str non vide, reçu {value!r}"
        )
    if "\x00" in value:
        raise ValueError(f"{name} contient un NUL byte: {value!r}")
    if not _SAFE_SEGMENT_RE.match(value):
        raise ValueError(
            f"{name} invalide pour sidecar: {value!r}; "
            f"attendu ^[a-z0-9][a-z0-9_-]{{0,128}}$"
        )
    if value.lower() in _WIN_RESERVED:
        raise ValueError(f"{name} est un nom réservé Windows: {value!r}")
    return value


def ensure_output_within(base: Path, target: Path) -> Path:
    """Vérifie que ``target`` est contenu dans ``base`` (anti-traversal).

    Utile pour les CLI qui acceptent un ``--output`` libre : on bloque
    les tentatives de sortie type ``../../etc/passwd``.

    Returns:
        ``target.resolve()`` si OK.

    Raises:
        ValueError: si ``target`` n'est pas dans ``base``.
    """
    base_r = base.resolve()
    try:
        target_r = target.resolve()
    except OSError as exc:  # pragma: no cover — defensive
        raise ValueError(f"target illisible: {target!r}") from exc
    try:
        target_r.relative_to(base_r)
    except ValueError as exc:
        raise ValueError(
            f"target {target!r} hors de base {base!r}"
        ) from exc
    return target_r


__all__ = ["_safe_segment", "ensure_output_within"]
