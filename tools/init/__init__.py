"""tools.init — wizard CLI ``reco init`` (cf. ADR 0038).

Génère un fichier ``src/content/sources/<slug>.json`` conforme au schéma
Zod (cf. ``src/content.config.ts``) à partir de questions interactives ou
de flags CLI (mode ``--ci``).
"""
from __future__ import annotations

WIZARD_VERSION = "0.1.0"

__all__ = ["WIZARD_VERSION"]
