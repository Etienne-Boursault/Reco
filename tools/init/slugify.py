"""tools.init.slugify — slugify ASCII strict pour les IDs de source.

Le slug DOIT matcher la regex Zod de ``src/content.config.ts`` :
``^[a-z0-9]+(?:-[a-z0-9]+)*$`` (minuscules + chiffres, tirets internes
uniquement, pas de double tiret, pas de leading/trailing dash).
"""
from __future__ import annotations

import re
import unicodedata

SLUG_MAX_LEN = 32
SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def slugify(value: str) -> str:
    """Transforme un texte en slug ASCII Zod-valide.

    Vide ou non-ASCII pur → ``"x"`` (placeholder).
    """
    if not value:
        return "x"
    value = unicodedata.normalize("NFKD", value)
    value = value.encode("ascii", "ignore").decode("ascii")
    value = value.lower()
    value = _NON_ALNUM.sub("-", value).strip("-")
    if not value:
        return "x"
    if len(value) > SLUG_MAX_LEN:
        value = value[:SLUG_MAX_LEN].rstrip("-")
    return value or "x"


def is_valid_slug(value: str) -> bool:
    """Vérifie que ``value`` est un slug Zod-valide (longueur incluse)."""
    if not value or len(value) > SLUG_MAX_LEN:
        return False
    return SLUG_RE.match(value) is not None


__all__ = ["SLUG_MAX_LEN", "SLUG_RE", "is_valid_slug", "slugify"]
