"""embeddings.settings — config injectable (P3.5-B / ADR 0033).

Avant : ``embed_items.py`` hardcodait tous ses defaults dans
``argparse`` (model, batch, dedup threshold, db_path). Un fork ne pouvait
ajuster ces paramètres qu'en patchant le CLI ou en passant les flags
systématiquement — viole l'ADR 0001 (SSOT) qui veut tout config par source
dans ``SourceConfig.extra``.

Après : ``EmbeddingsSettings`` factorise les seuils et permet la lecture
depuis ``SourceConfig.extra["embeddings"]`` via le helper
``audit_core.settings.from_source_extra``. Les flags CLI restent
opérationnels (overrides) pour usage opérationnel ad hoc.

Forward-compat : un fork peut désormais ajuster les seuils par source via
le fichier de config Astro plutôt que par flags CLI globaux.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

from audit_core.settings import from_source_extra as _from_source_extra
from common import OUTPUT_DIR
from embeddings.encoder import DEFAULT_MODEL as _DEFAULT_ENCODER_MODEL

#: Modèle par défaut, ré-exposé pour symétrie avec les autres Settings.
DEFAULT_MODEL: Final[str] = _DEFAULT_ENCODER_MODEL
DEFAULT_BATCH_SIZE: Final[int] = 64
DEFAULT_DEDUP_THRESHOLD: Final[float] = 0.85
DEFAULT_DB_PATH: Final[Path] = OUTPUT_DIR / "embeddings" / "embeddings.sqlite"
#: Cap caractères description avant embedding — voir encoder._DESC_MAX_CHARS.
DEFAULT_DESC_MAX_CHARS: Final[int] = 256


@dataclass(frozen=True, slots=True)
class EmbeddingsSettings:
    """Config injectable pour ``embed_items``.

    Tous les seuils ont un défaut raisonnable ; aucun fork n'a besoin de
    les configurer pour démarrer.

    Attributs :
        model_name: identifiant du modèle d'embeddings (fastembed).
        batch_size: taille des batches d'encodage.
        dedup_threshold: seuil de similarité pour la dédup cross-épisode
            (∈ [-1, 1] ; cosine bornée, négatif autorisé pour tests).
        db_path: chemin de la base SQLite ``items_embeddings``.
        desc_max_chars: cap caractères description avant truncation
            (forward-compat ; encoder utilise sa propre constante interne
            par défaut).
    """

    model_name: str = DEFAULT_MODEL
    batch_size: int = DEFAULT_BATCH_SIZE
    dedup_threshold: float = DEFAULT_DEDUP_THRESHOLD
    db_path: Path = DEFAULT_DB_PATH
    desc_max_chars: int = DEFAULT_DESC_MAX_CHARS

    def __post_init__(self) -> None:
        if not isinstance(self.model_name, str) or not self.model_name.strip():
            raise ValueError("model_name doit être une str non vide")
        if not isinstance(self.batch_size, int) or isinstance(self.batch_size, bool):
            raise ValueError("batch_size doit être un int")
        if self.batch_size <= 0:
            raise ValueError(f"batch_size doit être > 0 (reçu {self.batch_size})")
        if not isinstance(self.dedup_threshold, (int, float)) or isinstance(
            self.dedup_threshold, bool,
        ):
            raise ValueError("dedup_threshold doit être un nombre")
        if not -1.0 <= float(self.dedup_threshold) <= 1.0:
            raise ValueError(
                f"dedup_threshold hors borne [-1,1]: {self.dedup_threshold}"
            )
        if not isinstance(self.desc_max_chars, int) or isinstance(
            self.desc_max_chars, bool,
        ):
            raise ValueError("desc_max_chars doit être un int")
        if self.desc_max_chars <= 0:
            raise ValueError(
                f"desc_max_chars doit être > 0 (reçu {self.desc_max_chars})"
            )
        # Path validation : on accepte str/Path et on rend hashable côté frozen.
        if not isinstance(self.db_path, Path):
            # Forward-compat : si le payload livre une str, coerce.
            object.__setattr__(self, "db_path", Path(self.db_path))

    @classmethod
    def from_source_extra(
        cls,
        extra: Mapping[str, Any] | None,
        *,
        overrides: Mapping[str, Any] | None = None,
    ) -> "EmbeddingsSettings":
        """Construit depuis ``SourceConfig.extra["embeddings"]``.

        Délègue à ``audit_core.settings.from_source_extra`` (SSOT — ADR 0019).
        Les ``overrides`` (typiquement des flags CLI) gagnent sur la config.
        """
        return _from_source_extra(
            extra,
            "embeddings",
            cls,
            overrides=overrides,
        )


__all__ = [
    "DEFAULT_BATCH_SIZE",
    "DEFAULT_DB_PATH",
    "DEFAULT_DEDUP_THRESHOLD",
    "DEFAULT_DESC_MAX_CHARS",
    "DEFAULT_MODEL",
    "EmbeddingsSettings",
]
