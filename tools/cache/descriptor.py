"""cache.descriptor — EntityDescriptor (OCP pattern).

Documenté dans **ADR 0026 — Cache entity descriptor pattern**.

Pour l'instant, builder/reader manipulent encore items/mentions/episodes
directement (le coût de refacto vs gain immédiat n'est pas favorable :
3 entités, schéma stable). Le descriptor est introduit en tant que
contrat formel pour préparer l'ajout d'une 4e entité (ex. ``persons``,
``shows``) sans dupliquer 5 fichiers.

Voir ADR 0026 pour la roadmap : adoption incrémentale entité par entité.
"""
from __future__ import annotations

from dataclasses import dataclass
from sqlite3 import Row
from typing import Any, Callable


@dataclass(frozen=True, slots=True)
class EntityDescriptor:
    """Décrit une entité cachée (table physique + FTS5 + I/O).

    Attributs :
      name              : nom de l'entité (``"items"``, ``"mentions"``...).
      table_ddl         : ``CREATE TABLE`` complet.
      fts_ddl           : ``CREATE VIRTUAL TABLE`` FTS5 ou ``None`` si pas
                          d'index full-text.
      json_to_row       : fonction (data, source_id, json_path, mtime) →
                          tuple aligné sur ``INSERT INTO <name> (...)``.
      row_to_dataclass  : fonction (sqlite3.Row) → dataclass projetée.
      insert_sql        : SQL ``INSERT INTO ... VALUES (?, ?, ...)`` aligné
                          avec ``json_to_row``.
    """

    name: str
    table_ddl: str
    fts_ddl: str | None
    insert_sql: str
    json_to_row: Callable[..., tuple[Any, ...]]
    row_to_dataclass: Callable[[Row], Any]


__all__ = ["EntityDescriptor"]
