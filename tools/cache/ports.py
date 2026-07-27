"""cache.ports — Protocols (DIP) pour le cache.

``JsonLoader`` est conservé : utile pour injecter une source de fichiers
JSON in-memory dans les tests sans monkeypatch.

``CacheBackend`` est conservé pour rétrocompat mais documenté comme
**décoratif** : son API est trop minimale (``build()``) pour permettre
une vraie bascule de backend ; en pratique une bascule SQLite → autre
moteur (Meilisearch, Tantivy) impliquerait de réécrire le reader, le
SearchService et la couche d'invalidation. Voir CR archi P0-1 et ADR
0020 § « Critères de bascule ».
"""
from __future__ import annotations

from pathlib import Path
from typing import Iterable, Protocol, runtime_checkable


@runtime_checkable
class JsonLoader(Protocol):
    """Itère les JSON d'un dossier et fournit leur mtime.

    Implémentation par défaut : `cache.builder._FsJsonLoader` (filesystem).
    Les tests peuvent injecter une version in-memory si nécessaire.
    """

    def iter_files(self, root: Path) -> Iterable[Path]:
        """Itère les chemins absolus des fichiers JSON sous `root`."""
        ...

    def read(self, path: Path) -> dict:
        """Lit et parse un fichier JSON UTF-8."""
        ...

    def mtime(self, path: Path) -> float:
        """Renvoie le mtime POSIX (secondes float) du fichier."""
        ...


@runtime_checkable
class CacheBackend(Protocol):
    """Backend de cache (SQLite par défaut). API minimale ISP.

    Note CR archi P0-1 : ce Protocol est volontairement étroit. Une
    bascule de backend implique une réécriture (cf. ADR 0020). Ne pas
    s'appuyer sur cette interface pour de la composition réelle.
    """

    def build(self, source_id: str | None) -> object:
        """Reconstruit le cache (complet ou pour une source). Retourne BuildStats."""
        ...
