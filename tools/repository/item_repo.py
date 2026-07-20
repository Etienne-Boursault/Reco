"""
item_repo.py — Backend JSON-on-disk pour `ItemRepository`.

Un fichier par Item : ``<base_dir>/<source_id>/<item_id>.json``.
Écritures atomiques (`common.atomic_write_text` — Windows-safe).
Lecture défensive : un fichier corrompu/illisible est SKIPPED, pas une erreur.

Single-threaded by design (cf. `docs/yagni.md`).

Substituable à n'importe quel `ItemRepository` (LSP).
"""
from __future__ import annotations

from collections.abc import Iterable, Iterator, Mapping
from pathlib import Path
from types import MappingProxyType

from domain.item import Item, ItemType
from domain.ports import ItemRepository
from domain.services.identity import canonical_key

from ._base import (
    load_json_safely,
    validate_id,
    validate_source_id,
    write_json_idempotent,
)
from .serialization.item_codec import item_from_dict, item_to_dict


def _validate_item_id(item_id: str) -> None:
    """Garde-fou : rejette tout id qui pourrait sortir du dossier `_dir`."""
    validate_id("item_id", item_id)


def _validate_source_id(source_id: str) -> None:
    """Garde-fou path-traversal sur le slug de source."""
    validate_source_id(source_id)


class ItemRepoJson(ItemRepository):
    """Persistance JSON des `Item` pour une source donnée.

    Layout disque : ``<base_dir>/<source_id>/<item_id>.json``.

    Args:
        base_dir: Racine de la collection items (ex. ``src/content/items``).
        source_id: Slug du podcast/source (ex. ``"un-bon-moment"``).
    """

    def __init__(self, base_dir: Path, source_id: str) -> None:
        _validate_source_id(source_id)
        self.base_dir = base_dir
        self.source_id = source_id
        self._dir = base_dir / source_id

    # -- Path helpers (privés) ----------------------------------------------

    def _path_for(self, item_id: str) -> Path:
        _validate_item_id(item_id)
        return self._dir / f"{item_id}.json"

    # -- Lecture ------------------------------------------------------------

    def get(self, item_id: str) -> Item | None:
        path = self._path_for(item_id)
        if not path.exists():
            return None
        return load_json_safely(path, item_from_dict)

    def exists(self, item_id: str) -> bool:
        """True si le fichier existe. N'ouvre pas le fichier (pas de désérialisation)."""
        return self._path_for(item_id).exists()

    def iter_all(self) -> Iterator[Item]:
        """Itère sur tous les items (streaming).

        Ordre stable (tri par nom de fichier). Les fichiers corrompus sont
        skipped silencieusement (cf. politique `get`).
        """
        if not self._dir.exists():
            return
        for path in sorted(self._dir.glob("*.json")):
            item = load_json_safely(path, item_from_dict)
            if item is not None:
                yield item

    def list_all(self) -> list[Item]:
        return list(self.iter_all())

    def existing_index(self) -> Mapping[str, tuple[str, tuple[ItemType, ...]]]:
        """Index ``{item_id: (canonical_key, types)}`` pour `find_matching_item`.

        Ordre stable (clé = item_id trié) — garantit la reproductibilité
        des matches en cas d'égalité. Mapping **immuable** (MappingProxyType).
        """
        index: dict[str, tuple[str, tuple[ItemType, ...]]] = {}
        for item in self.iter_all():
            index[item.id] = (
                canonical_key(item.title, item.creator),
                item.types,
            )
        return MappingProxyType(index)

    # -- Écriture -----------------------------------------------------------

    def upsert(self, item: Item) -> bool:
        """Écrit l'item. Idempotent : renvoie False si le contenu disque
        est déjà sémantiquement identique (no-op), True si une écriture
        a eu lieu.

        Idempotence robuste (C1) : la comparaison se fait d'abord textuellement
        puis sémantiquement (dict désérialisé == nouveau payload), ce qui
        permet de tolérer une variation de formatage (indent, ordre des clés)
        sans déclencher de ré-écriture.

        Atomic : tmp → fsync → rename (cf. `common.atomic_write_text`).
        En cas d'échec de l'écriture, le fichier existant n'est pas
        modifié (atomic_write_text gère le cleanup du tmp).

        Non thread-safe — un seul writer à la fois (cf. Protocol).
        """
        path = self._path_for(item.id)
        return write_json_idempotent(path, item_to_dict(item))

    def bulk_upsert(self, items: Iterable[Item]) -> tuple[int, int]:
        """Upsert en batch. Renvoie `(created, updated)`.

        Backend JSON : équivalent à boucler `upsert`. Un item est considéré
        "created" si le fichier n'existait pas avant l'écriture.
        """
        created = 0
        updated = 0
        for item in items:
            existed = self.exists(item.id)
            wrote = self.upsert(item)
            if not existed:
                created += 1
            elif wrote:
                updated += 1
        return created, updated

    def delete(self, item_id: str) -> bool:
        """Supprime l'item. True si supprimé, False s'il n'existait pas.

        Raises:
            ValueError: si `item_id` invalide (validation anti path-traversal).
        """
        path = self._path_for(item_id)
        if not path.exists():
            return False
        try:
            path.unlink()
            return True
        except OSError:
            return False


__all__ = ["ItemRepoJson"]
