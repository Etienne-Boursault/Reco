"""embeddings.dedup — Détection cross-épisode de doublons sémantiques.

Cas d'usage canonique (cf. mémoire projet, "Tombeau des lucioles" vs
"Grave of the Fireflies") : deux items textuellement très différents qui
référencent la même œuvre.

Algorithme : brute O(n²) sur la matrice normalisée — accepté jusqu'à
~10k items (cf. ADR 0033 § Critères de bascule). Au-delà : FAISS HNSW.
Pour une source à 2k items : 2k² = 4M comparaisons, <100ms numpy.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from embeddings.ports import EmbeddingStorePort, StoredEmbedding
from embeddings.similarity import normalize_rows


@dataclass(frozen=True, slots=True)
class DedupPair:
    """Suggestion de fusion entre deux items proches sémantiquement.

    ``a`` et ``b`` sont triés (``a < b`` lexicographiquement) pour que la
    paire soit canonique : pas de doublon ``(a,b)`` + ``(b,a)`` dans la
    sortie.
    """

    source_id: str
    a: str
    b: str
    score: float

    def to_dict(self, *, titles: dict[str, str] | None = None) -> dict[str, object]:
        d: dict[str, object] = {
            "a": self.a,
            "b": self.b,
            "score": round(self.score, 4),
        }
        if titles is not None:
            d["titles"] = [titles.get(self.a, ""), titles.get(self.b, "")]
        return d


class CrossEpisodeDedup:
    """Détecteur de paires d'items sémantiquement quasi-identiques.

    Threshold par défaut : 0.85 (cf. ADR 0033). À étalonner sur corpus
    réel — un threshold trop bas inonderait l'humain de faux positifs.
    """

    def __init__(self, store: EmbeddingStorePort) -> None:
        self._store = store

    def _load_matrix(
        self, source_id: str, *, model: str | None
    ) -> tuple[list[str], np.ndarray, list[StoredEmbedding]]:
        rows = list(self._store.iter_source(source_id, model=model))
        if not rows:
            return [], np.zeros((0, 0), dtype=np.float32), rows
        dim = rows[0].dim
        # Sanity : tous les vecteurs partagent la même dim (sinon mismatch
        # de modèle, à signaler en amont via une exception explicite).
        for r in rows:
            if r.dim != dim:
                raise ValueError(
                    f"dimension mismatch dans source={source_id!r}: "
                    f"item {r.id} dim={r.dim} ≠ référence {dim}. "
                    f"Filtre par --model ou rebuild."
                )
        ids = [r.id for r in rows]
        matrix = np.vstack([r.vector for r in rows]).astype(np.float32, copy=False)
        return ids, matrix, rows

    def suggest(
        self,
        source_id: str,
        *,
        threshold: float = 0.85,
        model: str | None = None,
        max_pairs: int | None = None,
    ) -> list[DedupPair]:
        """Retourne les paires ``(a, b)`` triées par score décroissant.

        Args:
          source_id  : slug de la source.
          threshold  : seuil inclus (>= threshold).
          model      : filtre optionnel sur le nom de modèle.
          max_pairs  : limite optionnelle (None = pas de limite).

        Filtre les paires où ``a == b`` (diagonale) et déduplique
        ``(a,b)`` / ``(b,a)`` via tri lexicographique.
        """
        ids, matrix, _rows = self._load_matrix(source_id, model=model)
        n = len(ids)
        if n < 2:
            return []
        if not (-1.0 <= threshold <= 1.0):
            raise ValueError(f"threshold doit être dans [-1,1], reçu {threshold}")

        # Matrice normalisée → produit scalaire = cosine. Upper triangle
        # uniquement (i<j) pour éviter doublons et diagonale.
        normed = normalize_rows(matrix)
        sim = normed @ normed.T
        # Masque triangulaire supérieur strict.
        idx_i, idx_j = np.triu_indices(n, k=1)
        scores = sim[idx_i, idx_j]
        # Filtre seuil.
        mask = scores >= threshold
        sel_i = idx_i[mask]
        sel_j = idx_j[mask]
        sel_s = scores[mask]

        pairs: list[DedupPair] = []
        for i, j, s in zip(sel_i, sel_j, sel_s):
            a, b = ids[i], ids[j]
            if a == b:  # pragma: no cover - jamais avec triu strict
                continue
            # Forme canonique : a < b lexicographique.
            if a > b:  # pragma: no cover - dépend de l'ordre d'itération SQLite
                a, b = b, a
            pairs.append(
                DedupPair(source_id=source_id, a=a, b=b, score=float(s))
            )

        pairs.sort(key=lambda p: (-p.score, p.a, p.b))
        if max_pairs is not None and max_pairs >= 0:
            return pairs[:max_pairs]
        return pairs
