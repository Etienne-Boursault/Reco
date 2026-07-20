"""Tests pour le registre des migrations (`tools/migrations/registry.py`).

Le registre est la SSOT des versions de schéma supportées par entité.
Il découvre les migrations disponibles par auto-discovery (importlib) sur
les sous-modules `tools/migrations/{entity}/v{X}_to_v{X+1}.py`.

Garanties testées :
  - liste les entités connues (item/mention/source)
  - renvoie une chaîne de migrations pour aller à une `target_version`
  - lève une erreur claire sur une entité inconnue
  - lève une erreur si `target_version` <= la plus basse migration disponible
"""
from __future__ import annotations

import pytest

from migrations.registry import (
    KNOWN_ENTITIES,
    UnknownEntityError,
    UnsupportedTargetVersionError,
    discover_migration_chain,
    list_known_entities,
)


# ---------------------------------------------------------------------------
# Listing
# ---------------------------------------------------------------------------


def test_registry_lists_all_known_migrations():
    """Le registre expose au minimum les 3 entités cibles de Phase 1."""
    entities = list_known_entities()
    assert set(entities) >= {"item", "mention", "source"}
    # KNOWN_ENTITIES est une constante immuable (frozenset)
    assert isinstance(KNOWN_ENTITIES, frozenset)
    assert "item" in KNOWN_ENTITIES


# ---------------------------------------------------------------------------
# Chaînage des migrations
# ---------------------------------------------------------------------------


def test_registry_returns_chain_for_target_version():
    """Pour l'entité `item`, target=2 → chaîne contenant la migration v1→v2."""
    chain = discover_migration_chain("item", target_version=2)
    assert len(chain) == 1
    mig = chain[0]
    assert mig.SOURCE_VERSION == 1
    assert mig.TARGET_VERSION == 2
    assert mig.ENTITY == "item"


def test_registry_returns_chain_for_mention_and_source():
    """Toutes les entités supportées exposent au moins une migration v1→v2."""
    for entity in ("mention", "source"):
        chain = discover_migration_chain(entity, target_version=2)
        assert len(chain) == 1
        assert chain[0].ENTITY == entity
        assert chain[0].SOURCE_VERSION == 1
        assert chain[0].TARGET_VERSION == 2


def test_registry_empty_chain_when_target_is_one():
    """Si la cible est la version courante (1), la chaîne est vide (no-op)."""
    chain = discover_migration_chain("item", target_version=1)
    assert chain == []


# ---------------------------------------------------------------------------
# Erreurs
# ---------------------------------------------------------------------------


def test_unknown_entity_raises_clear_error():
    """Une entité inconnue lève `UnknownEntityError` avec un message clair."""
    with pytest.raises(UnknownEntityError) as exc:
        discover_migration_chain("inexistant", target_version=2)
    msg = str(exc.value)
    assert "inexistant" in msg
    assert "item" in msg  # message liste les entités connues


def test_target_version_below_one_raises():
    """target_version < 1 est rejeté."""
    with pytest.raises(UnsupportedTargetVersionError):
        discover_migration_chain("item", target_version=0)


def test_target_version_above_available_raises():
    """target_version > max(disponible) lève UnsupportedTargetVersionError."""
    # Aujourd'hui on a seulement v1→v2 pour `item` ; demander v=99 doit casser.
    with pytest.raises(UnsupportedTargetVersionError):
        discover_migration_chain("item", target_version=99)


# ---------------------------------------------------------------------------
# Auto-discovery — robustesse aux modules invalides
# ---------------------------------------------------------------------------


@pytest.fixture
def fake_entity_pkg(tmp_path, monkeypatch):
    """Fixture qui injecte un sous-package `migrations.<entity>` factice
    en `sys.modules`, le déclare dans `KNOWN_ENTITIES`, et garantit le
    cleanup en sortie de test (même en cas d'exception).

    Refactor du pattern manuel précédent (try/finally implicite via yield).
    Vide aussi le cache LRU du registry pour éviter la pollution croisée.
    """
    import sys
    import types
    import importlib

    from migrations import registry as reg_mod

    created: list[str] = []

    def _make(entity: str) -> tuple[types.ModuleType, "object"]:
        # Vide le cache pour la nouvelle entité — sinon l'auto-discovery
        # renverrait un résultat caché d'un test précédent.
        reg_mod._discover_all_migrations.cache_clear()
        full = f"migrations.{entity}"
        pkg = types.ModuleType(full)
        pkg.__path__ = [str(tmp_path)]
        sys.modules[full] = pkg
        created.append(full)
        monkeypatch.setattr(reg_mod, "KNOWN_ENTITIES", frozenset({entity}))
        return pkg, reg_mod

    yield _make

    # Cleanup garanti — pas de pollution entre tests.
    for name in created:
        sys.modules.pop(name, None)
        for sub in list(sys.modules):
            if sub.startswith(f"{name}."):
                del sys.modules[sub]
    importlib.invalidate_caches()
    reg_mod._discover_all_migrations.cache_clear()


def test_discovery_skips_non_matching_module_names(fake_entity_pkg, tmp_path):
    """Un module hors-pattern (ex. `helpers.py`) est ignoré par le scan."""
    _, reg_mod = fake_entity_pkg("fake_entity")
    # Module valide.
    (tmp_path / "v1_to_v2.py").write_text(
        "class V1ToV2Migration:\n"
        "    SOURCE_VERSION = 1\n    TARGET_VERSION = 2\n"
        "    ENTITY = 'fake_entity'\n"
        "    def migrate_one(self, d): return d\n",
        encoding="utf-8",
    )
    # Fichier hors-pattern : doit être skippé sans crash.
    (tmp_path / "helpers.py").write_text("X = 1\n", encoding="utf-8")
    # Module valide-au-nom mais sans classe Migration : doit être skippé.
    (tmp_path / "v2_to_v3.py").write_text("X = 1\n", encoding="utf-8")
    chain = reg_mod._discover_all_migrations("fake_entity")
    assert len(chain) == 1
    assert chain[0].SOURCE_VERSION == 1


def test_discovery_skips_zero_padded_module_names(fake_entity_pkg, tmp_path):
    """`v01_to_v2.py` (zero-padded) est volontairement skippé.

    Le regex est strict (sans `\\d{1,}` open-ended) : tout nom non-canonique
    est ignoré pour ne pas se faire piéger par un naming inconsistant.
    """
    _, reg_mod = fake_entity_pkg("fake_entity")
    # Module zero-padded : doit être skippé.
    (tmp_path / "v01_to_v2.py").write_text(
        "class V1ToV2Migration:\n"
        "    SOURCE_VERSION = 1\n    TARGET_VERSION = 2\n"
        "    ENTITY = 'fake_entity'\n"
        "    def migrate_one(self, d): return d\n",
        encoding="utf-8",
    )
    chain = reg_mod._discover_all_migrations("fake_entity")
    assert chain == ()


def test_discover_chain_raises_when_no_migration_available(fake_entity_pkg):
    """Une entité sans aucune migration sur disque → UnsupportedTargetVersionError."""
    _, reg_mod = fake_entity_pkg("empty_entity")
    with pytest.raises(UnsupportedTargetVersionError):
        reg_mod.discover_migration_chain("empty_entity", target_version=2)


# ---------------------------------------------------------------------------
# Validation chaîne (B1) — fail-fast sur saut ou trou
# ---------------------------------------------------------------------------


def test_chain_validation_rejects_skip(fake_entity_pkg, tmp_path):
    """Une migration v1→v3 (saut +2) est rejetée à la découverte."""
    _, reg_mod = fake_entity_pkg("fake_entity")
    (tmp_path / "v1_to_v3.py").write_text(
        "class V1ToV3Migration:\n"
        "    SOURCE_VERSION = 1\n    TARGET_VERSION = 3\n"
        "    ENTITY = 'fake_entity'\n"
        "    def migrate_one(self, d): return d\n",
        encoding="utf-8",
    )
    with pytest.raises(reg_mod.InvalidMigrationChainError, match="saut"):
        reg_mod._discover_all_migrations("fake_entity")


def test_chain_validation_rejects_gap(fake_entity_pkg, tmp_path):
    """Une chaîne v1→v2 puis v3→v4 (trou à v2→v3) est rejetée."""
    _, reg_mod = fake_entity_pkg("fake_entity")
    (tmp_path / "v1_to_v2.py").write_text(
        "class V1ToV2Migration:\n"
        "    SOURCE_VERSION = 1\n    TARGET_VERSION = 2\n"
        "    ENTITY = 'fake_entity'\n"
        "    def migrate_one(self, d): return d\n",
        encoding="utf-8",
    )
    (tmp_path / "v3_to_v4.py").write_text(
        "class V3ToV4Migration:\n"
        "    SOURCE_VERSION = 3\n    TARGET_VERSION = 4\n"
        "    ENTITY = 'fake_entity'\n"
        "    def migrate_one(self, d): return d\n",
        encoding="utf-8",
    )
    with pytest.raises(reg_mod.InvalidMigrationChainError, match="discontinue"):
        reg_mod._discover_all_migrations("fake_entity")


def test_chain_validation_accepts_consecutive(fake_entity_pkg, tmp_path):
    """Chaîne v1→v2→v3→v4 consécutive : OK, triée par SOURCE_VERSION."""
    _, reg_mod = fake_entity_pkg("fake_entity")
    for src, tgt in [(1, 2), (2, 3), (3, 4)]:
        (tmp_path / f"v{src}_to_v{tgt}.py").write_text(
            f"class V{src}ToV{tgt}Migration:\n"
            f"    SOURCE_VERSION = {src}\n    TARGET_VERSION = {tgt}\n"
            f"    ENTITY = 'fake_entity'\n"
            f"    def migrate_one(self, d): return d\n",
            encoding="utf-8",
        )
    chain = reg_mod._discover_all_migrations("fake_entity")
    assert [(m.SOURCE_VERSION, m.TARGET_VERSION) for m in chain] == [
        (1, 2), (2, 3), (3, 4),
    ]


# ---------------------------------------------------------------------------
# SSOT helpers (B10, D4)
# ---------------------------------------------------------------------------


def test_current_version_dict_is_ssot():
    """`CURRENT_VERSION` documente la version courante par entité.

    Toute entité de `KNOWN_ENTITIES` y a une entrée (cohérence SSOT).
    """
    from migrations.registry import CURRENT_VERSION, KNOWN_ENTITIES
    assert set(CURRENT_VERSION) == set(KNOWN_ENTITIES)
    # Phase 1 : tout est encore à v1.
    assert all(v >= 1 for v in CURRENT_VERSION.values())


def test_get_known_entities_returns_sorted_tuple():
    """`get_known_entities` = SSOT pour `argparse choices` du CLI."""
    from migrations.registry import get_known_entities
    entities = get_known_entities()
    assert entities == tuple(sorted(entities))
    assert {"item", "mention", "source"} <= set(entities)


# ---------------------------------------------------------------------------
# Cache discovery (C4)
# ---------------------------------------------------------------------------


def test_discover_all_migrations_is_cached():
    """Deux appels successifs renvoient la même instance (lru_cache)."""
    from migrations.registry import _discover_all_migrations
    _discover_all_migrations.cache_clear()
    a = _discover_all_migrations("item")
    b = _discover_all_migrations("item")
    assert a is b  # cache hit garanti
