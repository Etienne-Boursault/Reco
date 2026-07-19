"""Fakes partagés pour les tests d'embeddings.

Pas dans ``tests/embeddings/__init__.py`` parce qu'un package du même nom
shadowerait ``tools/embeddings/`` dans ``sys.path``.
"""
from __future__ import annotations

import hashlib
from typing import Sequence

import numpy as np


class FakeEncoder:
    """Encoder déterministe : SHA-256(text) → vecteur float32."""

    def __init__(self, model_name: str = "fake-test", dim: int = 16) -> None:
        self.model_name = model_name
        self.dim = dim

    def _vec(self, text: str) -> np.ndarray:
        seed = hashlib.sha256(text.encode("utf-8")).digest()
        buf = (seed * ((self.dim // len(seed)) + 1))[: self.dim]
        return np.array([(b - 128) / 128.0 for b in buf], dtype=np.float32)

    def encode(self, texts: Sequence[str]) -> np.ndarray:
        if not texts:
            return np.zeros((0, self.dim), dtype=np.float32)
        return np.vstack([self._vec(t) for t in texts]).astype(np.float32)


class StaticEncoder:
    """Encoder qui mappe text -> vecteur pré-défini."""

    def __init__(self, mapping: dict[str, np.ndarray], dim: int) -> None:
        self.model_name = "static-test"
        self.dim = dim
        self._map = mapping

    def encode(self, texts: Sequence[str]) -> np.ndarray:
        if not texts:
            return np.zeros((0, self.dim), dtype=np.float32)
        return np.vstack([self._map[t] for t in texts]).astype(np.float32)
