"""embeddings.ports — Protocols (DIP) pour encoder + store.

Tous les algorithmes (dedup, recommend, CLI) dépendent UNIQUEMENT de ces
deux Protocols, jamais d'une implémentation concrète. Les tests injectent
des fakes déterministes (vecteurs en clair) sans toucher au réseau ni à
sentence-transformers / fastembed.
"""
from __future__ import annotations

from typing import Iterator, Protocol, Sequence, runtime_checkable

import numpy as np


@runtime_checkable
class Encoder(Protocol):
    """Encode un lot de textes en vecteurs float32.

    Contrat :
        - ``encode(texts)`` retourne un ``np.ndarray`` de shape
          ``(len(texts), dim)`` ``dtype=float32``.
        - ``dim`` est constant pour une instance donnée.
        - ``model_name`` est l'identifiant à stocker dans la table
          ``items_embeddings.model`` (versionning + invalidation).
    """

    model_name: str
    dim: int

    def encode(self, texts: Sequence[str]) -> np.ndarray:
        """Encode une séquence de textes. Shape: (N, dim), dtype float32."""
        ...


@runtime_checkable
class EmbeddingStorePort(Protocol):
    """Store persistant pour les embeddings d'items.

    Le PK est ``(source_id, id)``. Un changement de ``source_hash``
    invalide l'embedding (re-encode).
    """

    def init_schema(self) -> None: ...

    def upsert(
        self,
        *,
        source_id: str,
        id: str,
        model: str,
        dim: int,
        vector: np.ndarray,
        source_hash: str,
        embedded_at: str,
    ) -> None: ...

    def get(self, source_id: str, item_id: str) -> "StoredEmbedding | None": ...

    def get_source_hash(self, source_id: str, item_id: str) -> str | None: ...

    def iter_source(
        self, source_id: str, *, model: str | None = None
    ) -> Iterator["StoredEmbedding"]: ...

    def count(self, source_id: str | None = None) -> int: ...

    def close(self) -> None: ...


# Petit alias d'avant-plan : on importe la dataclass concrete depuis store
# au runtime (typing only), mais on l'expose dans le module pour les tests.
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class StoredEmbedding:
    """Ligne ``items_embeddings`` projetée — immutable."""

    source_id: str
    id: str
    model: str
    dim: int
    vector: np.ndarray
    source_hash: str
    embedded_at: str


