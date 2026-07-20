"""
ports.py — Ports hexagonaux pour la nouvelle couche `Item` / `Mention`.

Les `Protocol` exposés ici décrivent les **contrats** que les adapters
(persistence JSON, repository SQL, etc.) doivent respecter. La couche
domaine reste indépendante de toute implémentation IO.

Conformément à la Clean Architecture, ces ports sont consommés par les
services applicatifs (`tools/extract_recos.py`, `tools/enrich_*.py`,
etc.) qui reçoivent une implémentation concrète à la construction.

Garanties de performance (à respecter par toute implémentation) :
  - `existing_index` : O(N) où N = nb d'items. Appelé **1 fois par batch**.
  - `iter_all` : streaming (générateur), évite de matérialiser N en mémoire.
  - `list_for_item` / `list_for_episode` : peut être O(N) en backend JSON ;
    un backend SQLite est censé indexer ces accès.
  - `bulk_upsert` : doit être au moins aussi rapide que N upsert individuels ;
    le backend peut batcher les écritures.

Thread-safety : aucune implémentation n'est garantie thread-safe.
La couche application reste single-threaded (cf. `docs/yagni.md`).
"""
from __future__ import annotations

from collections.abc import Iterable, Iterator, Mapping
from typing import Protocol, runtime_checkable

from .item import Item, ItemType
from .mention import Mention


@runtime_checkable
class ItemRepository(Protocol):
    """Persistence des `Item` (œuvres référencées)."""

    def get(self, item_id: str) -> Item | None:
        """Renvoie l'item d'`item_id` ou None.

        Raises:
            ValueError: si `item_id` ne respecte pas le format attendu
                (^[a-z0-9-]{1,64}$). Une lecture sur disque corrompue
                renvoie None (lecture défensive).
        """
        ...

    def exists(self, item_id: str) -> bool:
        """Renvoie True ssi un item de cet id est persisté.

        Plus efficace que `get(...) is not None` (pas de désérialisation).
        """
        ...

    def list_all(self) -> list[Item]:
        """Renvoie tous les items connus.

        Ordre stable (mêmes appels → même ordre — D4). Le backend JSON
        trie par nom de fichier ; un backend SQL est censé ordonner
        explicitement (ex. `ORDER BY id`).
        """
        ...

    def iter_all(self) -> Iterator[Item]:
        """Streaming version de `list_all` — évite la matérialisation.

        L'ordre d'itération est stable (mêmes appels → même ordre).
        """
        ...

    def upsert(self, item: Item) -> bool:
        """Insère ou met à jour `item`. True si effectivement écrit
        (False si idempotent — contenu déjà identique sur disque).

        Non thread-safe — un seul writer à la fois.
        """
        ...

    def bulk_upsert(self, items: Iterable[Item]) -> tuple[int, int]:
        """Insère/met à jour en batch. Renvoie `(created, updated)`.

        Pour un backend JSON : équivalent à boucler `upsert` ; un backend
        SQLite peut batcher les écritures en une seule transaction.
        """
        ...

    def delete(self, item_id: str) -> bool:
        """Supprime l'item. True si supprimé, False s'il n'existait pas.

        Raises:
            ValueError: si `item_id` invalide (anti path-traversal).
        """
        ...

    def existing_index(self) -> Mapping[str, tuple[str, tuple[ItemType, ...]]]:
        """Retourne `{item_id: (canonical_key, types)}` pour
        `find_matching_item`. Doit être stable (mêmes appels → même ordre)
        et **immuable** (cf. `types.MappingProxyType`).

        Performance: O(N). Appelé **1 fois par batch** côté application.
        """
        ...


@runtime_checkable
class MentionRepository(Protocol):
    """Persistence des `Mention` (occurrences d'items dans des épisodes)."""

    def get(self, mention_id: str) -> Mention | None:
        """Renvoie la mention de `mention_id` ou None.

        Raises:
            ValueError: si `mention_id` invalide.
        """
        ...

    def exists(self, mention_id: str) -> bool:
        """True ssi une mention de cet id est persistée."""
        ...

    def list_all(self) -> list[Mention]:
        """Renvoie toutes les mentions de la source.

        Ordre stable (mêmes appels → même ordre — D4).
        """
        ...

    def iter_all(self) -> Iterator[Mention]:
        """Streaming version de `list_all`."""
        ...

    def list_for_item(self, item_id: str) -> list[Mention]:
        """Renvoie toutes les mentions pointant vers `item_id`.

        Performance: O(N) en backend JSON (scan complet). Un backend
        SQLite est censé indexer `item_id`.
        """
        ...

    def list_for_episode(self, source_id: str, guid: str) -> list[Mention]:
        """Renvoie toutes les mentions extraites d'un épisode donné.

        Performance: O(N) en backend JSON, O(log N) attendu en SQLite.
        """
        ...

    def upsert(self, mention: Mention) -> bool:
        """Insère ou met à jour `mention`. True si effectivement écrit.

        Non thread-safe.
        """
        ...

    def bulk_upsert(self, mentions: Iterable[Mention]) -> tuple[int, int]:
        """Insère/met à jour en batch. Renvoie `(created, updated)`."""
        ...

    def delete(self, mention_id: str) -> bool:
        """Supprime la mention. True si supprimée, False sinon.

        Raises:
            ValueError: si `mention_id` invalide.
        """
        ...


__all__ = ["ItemRepository", "MentionRepository"]
