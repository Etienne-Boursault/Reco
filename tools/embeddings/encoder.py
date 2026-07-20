"""embeddings.encoder — Construction d'input texte + adaptateur fastembed.

Stratégie (cf. ADR 0033) :

  * Modèle par défaut : ``BAAI/bge-small-en-v1.5`` (alias court
    ``all-MiniLM-L6-v2`` dans la spec roadmap — exposé via constante).
    On garde ``DEFAULT_MODEL = "BAAI/bge-small-en-v1.5"`` (dim 384) côté
    fastembed pour la portabilité CPU/RAM (~50MB), avec une option pour
    bascule sentence-transformers si besoin futur.
  * Aucun téléchargement de modèle dans les tests : ``FastEmbedEncoder``
    est importé/instancié paresseusement par la CLI, jamais à l'import du
    module. Les tests injectent un fake encoder (DI Protocol).
  * Input à embedder : ``title | creator | types | (description)`` —
    le quote est exclu (souvent générique).
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Final, Sequence

import numpy as np

# Modèle par défaut — fastembed/BGE small. dim=384, ~50MB, CPU-friendly.
# Alias historique mentionné dans roadmap : "all-MiniLM-L6-v2" (dim 384).
# On garde l'alias dispo pour les ADR/docs mais l'identifiant réel pour
# fastembed est celui-ci :
DEFAULT_MODEL: Final[str] = "BAAI/bge-small-en-v1.5"
DEFAULT_DIM: Final[int] = 384

# Limite description pour ne pas exploser le budget tokens (~256 char ~ 60 tokens).
_DESC_MAX_CHARS: Final[int] = 256


@dataclass(frozen=True, slots=True)
class EmbeddingInput:
    """Champs canoniques d'un item à embedder.

    Immutable + ``slots`` pour mémoire/hashing prévisibles. Aucun des
    champs n'est obligatoire — un item sans creator/description reste
    encodable (titre seul).
    """

    title: str
    creator: str | None = None
    types: tuple[str, ...] = field(default_factory=tuple)
    description: str | None = None


def build_input_text(inp: EmbeddingInput) -> str:
    """Concatène les champs en un seul string canonique pour l'embedder.

    Format : ``"<title> | <creator> | <types_joined> | <description_tronquée>"``.

    * Les champs vides/``None`` sont omis (séparateur supprimé).
    * Les types sont joints par ``", "`` dans l'ordre fourni.
    * La description est tronquée à 256 caractères (mots préservés).
    * Le titre est obligatoire — si vide, on lève ``ValueError`` (un
      embedding d'item sans titre n'a aucun sens et pollue le store).
    """
    title = (inp.title or "").strip()
    if not title:
        raise ValueError("EmbeddingInput.title est requis (non vide).")
    parts: list[str] = [title]
    creator = (inp.creator or "").strip()
    if creator:
        parts.append(creator)
    if inp.types:
        joined = ", ".join(t for t in (s.strip() for s in inp.types) if t)
        if joined:
            parts.append(joined)
    desc = (inp.description or "").strip()
    if desc:
        if len(desc) > _DESC_MAX_CHARS:
            # Tronque proprement à la dernière espace dans la fenêtre.
            cut = desc[:_DESC_MAX_CHARS]
            last_space = cut.rfind(" ")
            if last_space > _DESC_MAX_CHARS // 2:
                cut = cut[:last_space]
            desc = cut + "…"
        parts.append(desc)
    return " | ".join(parts)


def source_hash(text: str) -> str:
    """SHA-256 hex du texte canonique. Sert d'invalidation côté store.

    Sensible aux changements de casse/accents/ponctuation — c'est le but :
    on veut re-embedder dès que la représentation textuelle bouge.
    """
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class FastEmbedEncoder:
    """Adaptateur :class:`Encoder` pour `fastembed.TextEmbedding`.

    Lazy-import de ``fastembed`` (lourd, ~80MB de poids + torch=false donc
    onnxruntime). Si la lib n'est pas installée, on lève une erreur
    actionnable avec la commande pip à exécuter.

    En tests : NE PAS instancier cette classe. Utiliser un fake encoder
    qui retourne des vecteurs déterministes (cf. tests/embeddings/).
    """

    def __init__(
        self,
        model_name: str = DEFAULT_MODEL,
        *,
        dim: int = DEFAULT_DIM,
    ) -> None:
        self.model_name = model_name
        self.dim = dim
        self._model = self._load(model_name)

    @staticmethod
    def _load(model_name: str):  # pragma: no cover - dépend de fastembed
        try:
            from fastembed import TextEmbedding  # noqa: PLC0415
        except ImportError as exc:
            raise RuntimeError(
                "Le module `fastembed` est requis pour l'encodage. "
                "Installe-le via `pip install fastembed` (ou ajoute-le à "
                "tools/requirements.txt). Les tests doivent mocker l'Encoder."
            ) from exc
        return TextEmbedding(model_name=model_name)

    def encode(self, texts: Sequence[str]) -> np.ndarray:  # pragma: no cover
        vectors = list(self._model.embed(list(texts)))
        if not vectors:
            return np.zeros((0, self.dim), dtype=np.float32)
        arr = np.asarray(vectors, dtype=np.float32)
        if arr.shape[1] != self.dim:
            # Met à jour l'auto-détection si le modèle a une dim différente.
            self.dim = int(arr.shape[1])
        return arr
