"""
registry.py — SSOT des entités et chaînes de migrations disponibles.

Auto-discovery : pour chaque entité dans `KNOWN_ENTITIES`, scanne le
sous-package `tools/migrations/{entity}/` et importe tous les modules
nommés `v{X}_to_v{X+1}.py`. Chaque module DOIT exposer **une seule**
classe terminant par `Migration` qui implémente le `Protocol`
`migrations.runner.Migration`.

Le registre n'a pas d'état interne : `discover_migration_chain` re-scanne
à chaque appel (peu fréquent, cache LRU si besoin un jour).

Principe SOLID :
  - **O**CP : ajouter une migration = créer un fichier ; zéro modif ici.
  - **S**RP : ce module ne fait QUE de la découverte/chaînage, pas de IO.
"""
from __future__ import annotations

import functools
import importlib
import pkgutil
import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover
    from .runner import Migration


# Entités versionnées supportées par la Phase 1. Toute nouvelle entité
# se déclare ici (ouverture-fermeture : on ajoute, on ne modifie pas).
KNOWN_ENTITIES: frozenset[str] = frozenset({"item", "mention", "source"})

# Version courante (SSOT) — Phase 1 reste à 1 pour les 3 entités.
# Une nouvelle entité s'ajoute ici en même temps que dans `KNOWN_ENTITIES`.
CURRENT_VERSION: dict[str, int] = {"item": 1, "mention": 1, "source": 1}

# Nom de fichier des migrations : `v{X}_to_v{Y}.py` avec X < Y. Le regex est
# volontairement strict (pas de zero-padding `v01_to_v02`) — un nom hors-pattern
# est silencieusement skippé (cf. tests).
_MODULE_NAME_RE = re.compile(r"^v(0|[1-9]\d*)_to_v(0|[1-9]\d*)$")


class UnknownEntityError(ValueError):
    """L'entité demandée n'est pas dans `KNOWN_ENTITIES`."""


class UnsupportedTargetVersionError(ValueError):
    """`target_version` invalide (< 1) ou hors des migrations disponibles."""


class InvalidMigrationChainError(RuntimeError):
    """La chaîne de migrations découverte présente un trou ou un chevauchement."""


def list_known_entities() -> tuple[str, ...]:
    """Renvoie la liste triée des entités versionnées connues."""
    return tuple(sorted(KNOWN_ENTITIES))


def get_known_entities() -> tuple[str, ...]:
    """Alias de `list_known_entities` — usage CLI (SSOT pour `argparse choices`)."""
    return list_known_entities()


def _ensure_known_entity(entity: str) -> None:
    if entity not in KNOWN_ENTITIES:
        known = ", ".join(sorted(KNOWN_ENTITIES))
        raise UnknownEntityError(
            f"Entité inconnue: {entity!r}. Entités supportées: {known}."
        )


@functools.lru_cache(maxsize=None)
def _discover_all_migrations(entity: str) -> tuple["Migration", ...]:
    """Importe tous les modules `v{X}_to_v{X+1}.py` du sous-package entité.

    Renvoie un tuple immuable d'instances de migrations triées par
    `SOURCE_VERSION` puis valide la cohérence de la chaîne :

      - chaque étape doit avoir `TARGET_VERSION == SOURCE_VERSION + 1`
        (pas de "saut" v1 → v3) ;
      - les `SOURCE_VERSION` doivent être consécutifs et sans doublon.

    Skippe silencieusement les modules dont le nom ne matche pas le regex
    (ex. `__init__.py`, `helpers.py`, `v01_to_v2.py` zero-padded).

    Le résultat est caché via `lru_cache` (la découverte par `importlib`
    est idempotente entre runs). Utiliser `_discover_all_migrations.cache_clear()`
    dans les tests qui injectent des modules à la volée.
    """
    # `__package__` résout dynamiquement le préfixe (`tools.migrations` quand
    # importé depuis le repo racine, `migrations` via pytest pythonpath).
    pkg_name = f"{__package__}.{entity}"
    pkg = importlib.import_module(pkg_name)
    discovered: list[Migration] = []
    for mod_info in pkgutil.iter_modules(pkg.__path__):
        m = _MODULE_NAME_RE.match(mod_info.name)
        if m is None:
            continue
        module = importlib.import_module(f"{pkg_name}.{mod_info.name}")
        # Récupère la classe Migration exportée — convention : une classe
        # par module qui termine par "Migration".
        mig_cls = None
        for attr in dir(module):
            obj = getattr(module, attr)
            if (
                isinstance(obj, type)
                and attr.endswith("Migration")
                and getattr(obj, "ENTITY", None) == entity
            ):
                mig_cls = obj
                break
        if mig_cls is None:
            continue
        discovered.append(mig_cls())
    discovered.sort(key=lambda mig: mig.SOURCE_VERSION)
    _validate_chain(entity, discovered)
    return tuple(discovered)


def _validate_chain(entity: str, chain: list["Migration"]) -> None:
    """Vérifie que la chaîne triée est sans trou ni saut.

    - Chaque migration doit faire +1 (`TARGET_VERSION == SOURCE_VERSION + 1`).
    - Pas de doublon de `SOURCE_VERSION` ni d'écart entre étapes consécutives.
    Lève `InvalidMigrationChainError` avec un message diagnostique.
    """
    for mig in chain:
        if mig.TARGET_VERSION != mig.SOURCE_VERSION + 1:
            raise InvalidMigrationChainError(
                f"Migration {type(mig).__name__} pour {entity!r}: "
                f"saut v{mig.SOURCE_VERSION}->v{mig.TARGET_VERSION} "
                f"(attendu +1)."
            )
    for prev, cur in zip(chain, chain[1:]):
        if cur.SOURCE_VERSION != prev.TARGET_VERSION:
            raise InvalidMigrationChainError(
                f"Chaîne {entity!r} discontinue: "
                f"{type(prev).__name__}(->v{prev.TARGET_VERSION}) suivi de "
                f"{type(cur).__name__}(v{cur.SOURCE_VERSION}->)."
            )


def discover_migration_chain(
    entity: str, target_version: int,
) -> list["Migration"]:
    """Renvoie la chaîne ordonnée de migrations pour aller v1 → target.

    Raises:
        UnknownEntityError: entité non listée dans `KNOWN_ENTITIES`.
        UnsupportedTargetVersionError: `target_version < 1` ou aucune
            migration ne couvre la version demandée.

    Si `target_version == 1`, renvoie `[]` (no-op).
    """
    _ensure_known_entity(entity)
    if target_version < 1:
        raise UnsupportedTargetVersionError(
            f"target_version doit être >= 1, reçu {target_version}."
        )
    if target_version == 1:
        return []
    all_migs = _discover_all_migrations(entity)
    if not all_migs:
        raise UnsupportedTargetVersionError(
            f"Aucune migration disponible pour entité {entity!r}."
        )
    max_target = max(mig.TARGET_VERSION for mig in all_migs)
    if target_version > max_target:
        raise UnsupportedTargetVersionError(
            f"target_version={target_version} > version maximale "
            f"disponible ({max_target}) pour entité {entity!r}."
        )
    # Filtre la chaîne nécessaire (v1 → ... → target).
    chain = [m for m in all_migs if m.TARGET_VERSION <= target_version]
    return chain


__all__ = [
    "CURRENT_VERSION",
    "InvalidMigrationChainError",
    "KNOWN_ENTITIES",
    "UnknownEntityError",
    "UnsupportedTargetVersionError",
    "discover_migration_chain",
    "get_known_entities",
    "list_known_entities",
]
