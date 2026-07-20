"""tools.init.validators — validations légères AVANT écriture.

La validation faisant autorité reste Zod côté Astro (au build) ; ces
helpers attrapent les erreurs en amont pour donner un feedback CLI
immédiat à l'utilisateur·rice du wizard.
"""
from __future__ import annotations

import re

HEX_COLOR_RE = re.compile(r"^#[0-9a-fA-F]{6}$")
URL_RE = re.compile(r"^https?://[^\s]+$", re.IGNORECASE)
RECO_PREFIX_RE = re.compile(r"^[a-z0-9]{2,8}$")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def is_valid_hex_color(value: str) -> bool:
    """Code hex 6 chars préfixé # (cohérent avec le schéma Zod)."""
    return bool(value) and HEX_COLOR_RE.match(value) is not None


def is_valid_url(value: str) -> bool:
    """URL ``http(s)://…`` minimaliste (Zod validera la forme complète)."""
    return bool(value) and URL_RE.match(value) is not None


def is_valid_reco_prefix(value: str) -> bool:
    """Préfixe reco : 2 à 8 chars alphanumériques minuscules."""
    return bool(value) and RECO_PREFIX_RE.match(value) is not None


def is_valid_email(value: str) -> bool:
    """Email basique (suffisant pour un fallback ``mailto:``)."""
    return bool(value) and EMAIL_RE.match(value) is not None


__all__ = [
    "EMAIL_RE",
    "HEX_COLOR_RE",
    "RECO_PREFIX_RE",
    "URL_RE",
    "is_valid_email",
    "is_valid_hex_color",
    "is_valid_reco_prefix",
    "is_valid_url",
]
