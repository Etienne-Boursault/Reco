"""Registry des sources — orchestration entre loader et consommateurs.

SRP : ce module assemble le loader avec un cache. Il expose une API
stable pour les modules métier (``get_source(id)`` / ``list_sources()``).

Pas d'I/O direct : tout passe par ``loader.load_source_config``.

Thread-safety : le cache est protégé par un ``RLock`` (les appels
concurrents depuis review_server + scripts CLI sont fréquents). Le
singleton par défaut utilise aussi un verrou pour son initialisation
paresseuse.
"""

from __future__ import annotations

import logging
import threading
from pathlib import Path

from tools.config import loader as _loader  # accès aux attrs (DEFAULT_SOURCES_DIR re-lu à chaque init)
from tools.config.loader import (
    ConfigLoadError,
    load_source_config,
)
from tools.config.schema import SourceConfig

__all__ = [
    "SourceRegistry",
    "clear_default_registry_cache",
    "get_registry",
    "get_source",
    "list_sources",
]

_log = logging.getLogger("reco.config")


class SourceRegistry:
    """Registre instanciable (utile en test ou pour un dossier custom).

    Cache simple par ``source_id`` — invalidable via ``clear_cache()`` quand
    un fichier source vient d'être modifié à chaud.
    """

    def __init__(self, sources_dir: Path | None = None) -> None:
        # On lit `DEFAULT_SOURCES_DIR` du module `loader` à chaque init pour
        # respecter d'éventuels monkeypatch en tests (cf. issue #9).
        self.sources_dir: Path = (
            sources_dir if sources_dir is not None else _loader.DEFAULT_SOURCES_DIR
        )
        self._cache: dict[str, SourceConfig] = {}
        # RLock pour autoriser get_source → list_sources → get_source
        # depuis un même thread sans deadlock.
        self._lock = threading.RLock()

    # ------------------------------------------------------------------
    def get_source(self, source_id: str) -> SourceConfig:
        """Renvoie la config (depuis le cache si déjà lue)."""
        # Lecture sans verrou : dict.get est atomique en CPython (GIL).
        cached = self._cache.get(source_id)
        if cached is not None:
            return cached
        cfg = load_source_config(source_id, sources_dir=self.sources_dir)
        with self._lock:
            # Double-check : un autre thread peut avoir gagné la course
            # de chargement. On garde sa version (idempotent).
            existing = self._cache.get(source_id)
            if existing is not None:
                return existing
            self._cache[source_id] = cfg
        return cfg

    # ------------------------------------------------------------------
    def list_sources(self, *, include_disabled: bool = False) -> list[SourceConfig]:
        """Liste les sources valides du dossier (triées par id).

        - Les configs invalides (JSON cassé, schéma non conforme) sont
          IGNORÉES et un warning est loggé — on ne casse pas la liste
          complète pour une seule entrée fautive.
        - Les fichiers ``_*.json`` (préfixe underscore) sont ignorés
          silencieusement (convention "brouillon").
        - Les sources ``enabled=False`` sont exclues par défaut (utiliser
          ``include_disabled=True`` pour tout voir).
        """
        if not self.sources_dir.exists():
            return []

        out: list[SourceConfig] = []
        for path in sorted(self.sources_dir.glob("*.json")):
            if path.name.startswith("_"):
                continue
            sid = path.stem
            try:
                cfg = self.get_source(sid)
            except ConfigLoadError as exc:
                _log.warning("Source ignorée — %s : %s", path.name, exc)
                continue
            if not cfg.enabled and not include_disabled:
                continue
            out.append(cfg)
        return sorted(out, key=lambda c: c.id)

    # ------------------------------------------------------------------
    def clear_cache(self) -> None:
        """Vide le cache (à appeler après modif disque hors-process)."""
        with self._lock:
            self._cache.clear()


# ---------------------------------------------------------------------------
# Singleton par défaut (pointe vers la SSOT projet).
# ---------------------------------------------------------------------------

_default_registry: SourceRegistry | None = None
_default_lock = threading.Lock()


def get_registry(sources_dir: Path | None = None) -> SourceRegistry:
    """Factory injectable.

    - Sans argument : renvoie le singleton par défaut (SSOT projet),
      en l'initialisant si besoin (thread-safe).
    - Avec ``sources_dir`` : renvoie une instance fraîche dédiée (utile
      en test). N'affecte pas le singleton.
    """
    if sources_dir is not None:
        return SourceRegistry(sources_dir=sources_dir)
    global _default_registry
    if _default_registry is None:
        with _default_lock:
            if _default_registry is None:  # double-checked locking
                _default_registry = SourceRegistry()
    return _default_registry


def get_source(
    source_id: str,
    *,
    registry: SourceRegistry | None = None,
) -> SourceConfig:
    """Helper module-level : registry par défaut (SSOT projet).

    Args:
        source_id: l'id de la source à charger.
        registry: registry à utiliser. Défaut = singleton projet.
    """
    return (registry or get_registry()).get_source(source_id)


def list_sources(
    *,
    registry: SourceRegistry | None = None,
    include_disabled: bool = False,
) -> list[SourceConfig]:
    """Helper module-level : liste les sources du projet."""
    return (registry or get_registry()).list_sources(
        include_disabled=include_disabled
    )


def clear_default_registry_cache() -> None:
    """Réinitialise complètement le registry par défaut.

    On RECRÉE l'instance (et pas seulement son cache) pour que
    ``DEFAULT_SOURCES_DIR`` soit ré-évalué — utile dans les tests qui
    monkeypatchent le chemin par défaut entre deux assertions.
    """
    global _default_registry
    with _default_lock:
        _default_registry = None
