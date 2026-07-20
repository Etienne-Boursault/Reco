"""Placeholder Mention v1 → v2. Voir `tools/migrations/item/v1_to_v2.py`."""
from __future__ import annotations

from typing import Any


class V1ToV2Migration:
    """No-op placeholder pour `Mention`."""

    SOURCE_VERSION: int = 1
    TARGET_VERSION: int = 2
    ENTITY: str = "mention"

    def migrate_one(self, data: dict[str, Any]) -> dict[str, Any]:
        current = int(data.get("schemaVersion", 1))
        if current != self.SOURCE_VERSION:
            raise ValueError(
                f"V1ToV2Migration[mention]: donnée à v{current}, "
                f"attendait v{self.SOURCE_VERSION}."
            )
        out = dict(data)
        out["schemaVersion"] = self.TARGET_VERSION
        return out


__all__ = ["V1ToV2Migration"]
