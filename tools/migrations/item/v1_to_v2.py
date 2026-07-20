"""
v1_to_v2.py — Placeholder de migration `Item` v1 → v2.

⚠️ Pas de vraie transformation métier ici : la donnée est strictement
préservée à l'identique, seul `schemaVersion` est bumpé. Sert de **template**
pour les futures migrations (cf. `docs/adr/0010-schema-versioning.md`).

Pour créer une vraie migration v2 → v3 plus tard :
  1. Bumper `Item.schema_version` côté domaine.
  2. Créer `tools/migrations/item/v2_to_v3.py` exposant une classe
     `V2ToV3Migration` avec `SOURCE_VERSION=2`, `TARGET_VERSION=3`,
     `ENTITY="item"` et une `migrate_one(data) -> data` pure.
  3. Le `MigrationRunner` la pickera automatiquement (auto-discovery).
"""
from __future__ import annotations

from typing import Any


class V1ToV2Migration:
    """No-op de démonstration. Pure (zéro IO, n'altère pas l'entrée)."""

    SOURCE_VERSION: int = 1
    TARGET_VERSION: int = 2
    ENTITY: str = "item"

    def migrate_one(self, data: dict[str, Any]) -> dict[str, Any]:
        current = int(data.get("schemaVersion", 1))
        if current != self.SOURCE_VERSION:
            raise ValueError(
                f"V1ToV2Migration[item]: donnée à v{current}, "
                f"attendait v{self.SOURCE_VERSION}."
            )
        out = dict(data)  # copie défensive
        out["schemaVersion"] = self.TARGET_VERSION
        return out


__all__ = ["V1ToV2Migration"]
