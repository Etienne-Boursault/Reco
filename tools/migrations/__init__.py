"""
tools.migrations — Migrations versionnées de schéma (P1.3).

Mécanisme de migration forward-only entre versions de `schemaVersion`
par entité (`item`, `mention`, `source`). Chaque transition v_X → v_X+1
est un module isolé sous `tools/migrations/{entity}/v{X}_to_v{X+1}.py`
qui expose une classe implémentant le `Protocol` `Migration` :

    class Migration(Protocol):
        SOURCE_VERSION: int
        TARGET_VERSION: int
        ENTITY: str  # "item" | "mention" | "source"
        def migrate_one(self, data: dict) -> dict: ...

Le `MigrationRunner` orchestre l'exécution sur un dataset (auto-discovery
par `importlib`, idempotent, dry-run par défaut).

Pas de rollback (forward-only). Voir `docs/adr/0010-schema-versioning.md`.
"""
from __future__ import annotations

from .registry import (
    KNOWN_ENTITIES,
    UnknownEntityError,
    UnsupportedTargetVersionError,
    discover_migration_chain,
    list_known_entities,
)
from .runner import Migration, MigrationRunner, MigrationStats

__all__ = [
    "KNOWN_ENTITIES",
    "Migration",
    "MigrationRunner",
    "MigrationStats",
    "UnknownEntityError",
    "UnsupportedTargetVersionError",
    "discover_migration_chain",
    "list_known_entities",
]
