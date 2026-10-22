"""
store.py — accès SQLite de la télémétrie (stdlib `sqlite3`, aucune dépendance).

Une connexion par `Store`, en autocommit : chaque observation est écrite seule,
hors de toute transaction métier. La chaîne de venus et la page de relecture
écrivent dans la même base depuis deux conteneurs : journal WAL et attente de
verrou (`busy_timeout`) l'absorbent. Le WAL exige un disque LOCAL — sur un
partage réseau, `RECO_METRICS_JOURNAL=delete`.
"""
from __future__ import annotations

import contextlib
import json
import os
import re
import sqlite3
import threading
import time
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from telemetry.schema import MIGRATIONS, SCHEMA_VERSION

BUSY_TIMEOUT_MS = 5000


def _statements(script: str) -> Iterable[str]:
    """Découpe un script DDL en instructions (aucune ne contient de `;`)."""
    for morceau in script.split(";"):
        lignes = [ligne for ligne in morceau.splitlines() if not ligne.strip().startswith("--")]
        instruction = "\n".join(lignes).strip()
        if instruction:
            yield instruction


_TABLES = frozenset({"workflow_runs", "stage_attempts", "llm_batches", "batch_requests",
                     "llm_calls", "review_events"})
_IDENTIFIANT = re.compile(r"^[a-z][a-z0-9_]*$")


def _noms(table: str, colonnes: Iterable[str]) -> list[str]:
    """Tables et colonnes viennent du code, jamais d'une entrée : on le vérifie."""
    colonnes = list(colonnes)
    if table not in _TABLES or not all(_IDENTIFIANT.match(c) for c in colonnes):
        raise ValueError(f"identifiant SQL refusé : {table} {colonnes}")
    return colonnes


def _encode(colonne: str, valeur: Any) -> Any:
    if colonne.endswith("_json") and not isinstance(valeur, str):
        return json.dumps(valeur, ensure_ascii=False, sort_keys=True, default=str)
    return valeur


class Store:
    def __init__(self, path: Path, *, journal: str | None = None) -> None:
        self.path = path
        neuve = not path.exists()
        path.parent.mkdir(parents=True, exist_ok=True)
        self._verrou = threading.Lock()
        self.conn = sqlite3.connect(str(path), timeout=BUSY_TIMEOUT_MS / 1000,
                                    isolation_level=None, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys=ON")
        self.conn.execute(f"PRAGMA busy_timeout={BUSY_TIMEOUT_MS}")
        mode = (journal or os.environ.get("RECO_METRICS_JOURNAL") or "wal").lower()
        if mode in {"wal", "delete", "truncate"}:
            self._journal(mode)
        if neuve and os.name == "posix":
            # La base ne contient ni clé ni transcription, mais elle n'a pas à
            # être lisible par les autres comptes de la machine.
            with contextlib.suppress(OSError):
                path.chmod(0o600)
        self.migrate()

    def _journal(self, mode: str) -> None:
        """Pose le mode de journal ; il est mémorisé dans le fichier.

        Le changer exige un verrou exclusif que SQLite n'attend pas : deux
        processus qui créent la base ensemble se le disputent. On ne le change
        donc que s'il diffère, et on réessaie un court moment.
        """
        for essai in range(50):
            try:
                if self.conn.execute("PRAGMA journal_mode").fetchone()[0] != mode:
                    self.conn.execute(f"PRAGMA journal_mode={mode}")
                return
            except sqlite3.OperationalError:
                if essai == 49:
                    raise
                time.sleep(0.1)

    # --- schéma ---------------------------------------------------------------
    def version(self) -> int:
        return int(self.conn.execute("PRAGMA user_version").fetchone()[0])

    def migrate(self) -> int:
        """Amène la base à `SCHEMA_VERSION`. Rejouable, sûr à plusieurs processus.

        La version est relue SOUS verrou d'écriture : deux processus qui
        démarrent ensemble ne jouent pas deux fois la même migration.
        """
        if self.version() >= SCHEMA_VERSION:
            return 0
        with self._verrou:
            self.conn.execute("BEGIN IMMEDIATE")
            try:
                depart = self.version()
                for numero in range(depart, SCHEMA_VERSION):
                    for instruction in _statements(MIGRATIONS[numero]):
                        self.conn.execute(instruction)
                    self.conn.execute(f"PRAGMA user_version={numero + 1}")
                self.conn.execute("COMMIT")
            except BaseException:
                self.conn.execute("ROLLBACK")
                raise
        return SCHEMA_VERSION - depart

    # --- écritures ------------------------------------------------------------
    def insert(self, table: str, row: Mapping[str, Any], *, ignore: bool = False) -> bool:
        """Ajoute une ligne. Avec `ignore`, un doublon de clé n'écrit rien (False)."""
        colonnes = _noms(table, row)
        sql = (f"INSERT {'OR IGNORE ' if ignore else ''}INTO {table} "  # noqa: S608 — noms vérifiés par _noms
               f"({', '.join(colonnes)}) VALUES ({', '.join('?' for _ in colonnes)})")
        with self._verrou:
            cur = self.conn.execute(sql, [_encode(c, row[c]) for c in colonnes])
        return cur.rowcount == 1

    def finish(self, table: str, ident: str, fields: Mapping[str, Any]) -> bool:
        """Finalise une ligne `started`, UNE fois : une seconde fin n'écrit rien."""
        return self.update(table, ident, fields, une_fois=True)

    def update(self, table: str, ident: str, fields: Mapping[str, Any], *,
               une_fois: bool = False) -> bool:
        colonnes = _noms(table, fields)
        sql = (f"UPDATE {table} SET {', '.join(f'{c} = ?' for c in colonnes)} "  # noqa: S608
               f"WHERE id = ?{' AND ended_at IS NULL' if une_fois else ''}")
        with self._verrou:
            cur = self.conn.execute(sql, [_encode(c, fields[c]) for c in colonnes] + [ident])
        return cur.rowcount == 1

    def execute(self, sql: str, params: Iterable[Any] = ()) -> int:
        with self._verrou:
            return self.conn.execute(sql, list(params)).rowcount

    # --- lectures -------------------------------------------------------------
    def query(self, sql: str, params: Iterable[Any] = ()) -> list[dict[str, Any]]:
        with self._verrou:
            return [dict(r) for r in self.conn.execute(sql, list(params)).fetchall()]

    def close(self) -> None:
        with contextlib.suppress(sqlite3.Error):
            self.conn.close()
