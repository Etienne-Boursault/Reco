"""
mention_repo.py — Backend JSON-on-disk pour `MentionRepository`.

Un fichier par Mention : ``<base_dir>/<source_id>/<mention_id>.json``.
Mêmes garanties que `ItemRepoJson` : écriture atomic, lecture défensive,
validation du `mention_id` au boundary (anti path-traversal).
"""
from __future__ import annotations

from collections.abc import Iterable, Iterator
from pathlib import Path

from domain.mention import Mention
from domain.ports import MentionRepository

from ._base import (
    load_json_safely,
    validate_id,
    validate_source_id,
    write_json_idempotent,
)
from .serialization.mention_codec import mention_from_dict, mention_to_dict


def _validate_mention_id(mention_id: str) -> None:
    validate_id("mention_id", mention_id)


def _validate_source_id(source_id: str) -> None:
    validate_source_id(source_id)


class MentionRepoJson(MentionRepository):
    """Persistance JSON des `Mention` pour une source donnée."""

    def __init__(self, base_dir: Path, source_id: str) -> None:
        _validate_source_id(source_id)
        self.base_dir = base_dir
        self.source_id = source_id
        self._dir = base_dir / source_id

    def _path_for(self, mention_id: str) -> Path:
        _validate_mention_id(mention_id)
        return self._dir / f"{mention_id}.json"

    def _load(self, path: Path) -> Mention | None:
        return load_json_safely(path, mention_from_dict)

    def iter_all(self) -> Iterator[Mention]:
        """Itère sur toutes les mentions de la source (streaming, ordre stable)."""
        if not self._dir.exists():
            return
        for path in sorted(self._dir.glob("*.json")):
            m = self._load(path)
            if m is not None:
                yield m

    def list_all(self) -> list[Mention]:
        return list(self.iter_all())

    # -- API ----------------------------------------------------------------

    def get(self, mention_id: str) -> Mention | None:
        path = self._path_for(mention_id)
        if not path.exists():
            return None
        return self._load(path)

    def exists(self, mention_id: str) -> bool:
        return self._path_for(mention_id).exists()

    def list_for_item(self, item_id: str) -> list[Mention]:
        return [m for m in self.iter_all() if m.item_id == item_id]

    def list_for_episode(self, source_id: str, guid: str) -> list[Mention]:
        return [
            m for m in self.iter_all()
            if m.source_ref.source_id == source_id
            and m.source_ref.episode_guid == guid
        ]

    def upsert(self, mention: Mention) -> bool:
        """Écrit la mention. Idempotent (cf. `ItemRepoJson.upsert` — C1)."""
        path = self._path_for(mention.id)
        return write_json_idempotent(path, mention_to_dict(mention))

    def bulk_upsert(self, mentions: Iterable[Mention]) -> tuple[int, int]:
        """Upsert en batch. Renvoie `(created, updated)`."""
        created = 0
        updated = 0
        for mention in mentions:
            existed = self.exists(mention.id)
            wrote = self.upsert(mention)
            if not existed:
                created += 1
            elif wrote:
                updated += 1
        return created, updated

    def delete(self, mention_id: str) -> bool:
        path = self._path_for(mention_id)
        if not path.exists():
            return False
        try:
            path.unlink()
            return True
        except OSError:
            return False


__all__ = ["MentionRepoJson"]
