"""embeddings — package : encoder, store SQLite, similarity, dedup, recos.

Roadmap item #15 / ADR 0033. Voir `docs/adr/0033-semantic-embeddings.md`.

API publique :
  - :class:`encoder.EmbeddingInput` / :func:`encoder.build_input_text`
  - :class:`store.EmbeddingStore` (SQLite, table ``items_embeddings``)
  - :func:`similarity.cosine_similarity` / :func:`similarity.top_k`
  - :class:`dedup.CrossEpisodeDedup`
  - :class:`recommend.SimilarityRecommender`
  - :class:`ports.Encoder` / :class:`ports.EmbeddingStorePort` (Protocols DIP)
"""
from __future__ import annotations

from embeddings.encoder import (
    DEFAULT_MODEL,
    EmbeddingInput,
    build_input_text,
    source_hash,
)
from embeddings.ports import Encoder, EmbeddingStorePort

__all__ = [
    "DEFAULT_MODEL",
    "EmbeddingInput",
    "Encoder",
    "EmbeddingStorePort",
    "build_input_text",
    "source_hash",
]
