"""
recorder.py — qui écrit les observations, et que faire quand l'écriture échoue.

Deux implémentations du même contrat :
  - `SQLiteTelemetryRecorder` : la base `tools/output/telemetry/reco_metrics.sqlite`
    (ou `RECO_METRICS_DB`) ;
  - `NoopTelemetryRecorder` : n'écrit rien (tests, `RECO_METRICS_ENABLED=0`).

Politique d'échec. Une métrique perdue ne doit ni corrompre une reco, ni casser
la chaîne, ni passer inaperçue :
  - mode normal : l'erreur est journalisée, l'observation comptée PERDUE
    (`lost`), et le run en garde le total (`lost_observations`) ;
  - `RECO_METRICS_STRICT=1` (calibrations, tests) : l'erreur lève
    `TelemetryError` et arrête l'exécution avant toute publication.
Une perte n'est jamais maquillée en zéro.
"""
from __future__ import annotations

import logging
import os
import sqlite3
from collections.abc import Callable, Iterable, Mapping
from pathlib import Path
from typing import Any, TypeVar

log = logging.getLogger("reco.telemetry")

T = TypeVar("T")

ENV_DB = "RECO_METRICS_DB"
ENV_ENABLED = "RECO_METRICS_ENABLED"
ENV_STRICT = "RECO_METRICS_STRICT"


class TelemetryError(RuntimeError):
    """Écriture de télémétrie impossible en mode strict."""


def _vrai(valeur: str | None, defaut: bool) -> bool:
    if valeur is None or not valeur.strip():
        return defaut
    return valeur.strip().lower() not in {"0", "false", "non", "no", "off"}


def default_db_path() -> Path:
    """Chemin de la base, lu À L'APPEL (un test qui déplace OUTPUT_DIR est suivi)."""
    explicite = os.environ.get(ENV_DB, "").strip()
    if explicite:
        return Path(explicite)
    import common
    return common.OUTPUT_DIR / "telemetry" / "reco_metrics.sqlite"


class TelemetryRecorder:
    """Contrat commun. Chaque écriture rend un booléen : écrite ou non."""

    enabled = False
    strict = False

    def __init__(self) -> None:
        self.lost = 0

    def start_run(self, row: Mapping[str, Any]) -> bool:
        return False

    def finish_run(self, run_id: str, fields: Mapping[str, Any]) -> bool:
        return False

    def start_stage(self, row: Mapping[str, Any]) -> bool:
        return False

    def finish_stage(self, attempt_id: str, fields: Mapping[str, Any]) -> bool:
        return False

    def record_llm_call(self, row: Mapping[str, Any]) -> bool:
        return False

    def record_batch(self, row: Mapping[str, Any]) -> bool:
        return False

    def update_batch(self, batch_id: str, fields: Mapping[str, Any]) -> bool:
        return False

    def map_batch_requests(self, rows: Iterable[Mapping[str, Any]]) -> int:
        return 0

    def record_review_event(self, row: Mapping[str, Any]) -> bool:
        return False

    def prior_attempts(self, source_id: str, episode_guid: str | None,
                       stage: str) -> list[dict[str, Any]]:
        return []

    def batch_mapping(self, batch_id: str) -> dict[str, dict[str, Any]]:
        return {}


class NoopTelemetryRecorder(TelemetryRecorder):
    """N'enregistre rien. Ce n'est pas une perte : la mesure est désactivée."""


class SQLiteTelemetryRecorder(TelemetryRecorder):
    enabled = True

    def __init__(self, path: Path | None = None, *, strict: bool = False) -> None:
        super().__init__()
        self.path = path or default_db_path()
        self.strict = strict
        self._store: Any = None
        self._indisponible = False
        self._cause: BaseException = OSError("base non ouverte")

    # --- garde ----------------------------------------------------------------
    def _store_ou_rien(self) -> Any:
        if self._store is None and not self._indisponible:
            from telemetry.store import Store
            try:
                self._store = Store(self.path)
            except (sqlite3.Error, OSError) as exc:
                self._indisponible = True
                self._cause = exc
        return self._store

    def _echec(self, operation: str, exc: BaseException) -> None:
        self.lost += 1
        if self.strict:
            raise TelemetryError(f"télémétrie : {operation} impossible ({exc})") from exc
        log.error("Télémétrie : %s impossible (%s: %s) — observation perdue.",
                  operation, type(exc).__name__, exc)

    def _garde(self, operation: str, defaut: T, action: Callable[[Any], T]) -> T:
        store = self._store_ou_rien()
        if store is None:
            self._echec(f"{operation} (base {self.path} indisponible)", self._cause)
            return defaut
        try:
            return action(store)
        except (sqlite3.Error, OSError, ValueError, TypeError) as exc:
            self._echec(operation, exc)
            return defaut

    # --- écritures ------------------------------------------------------------
    def start_run(self, row: Mapping[str, Any]) -> bool:
        return self._garde("début de run", False, lambda s: s.insert("workflow_runs", row))

    def finish_run(self, run_id: str, fields: Mapping[str, Any]) -> bool:
        return self._garde("fin de run", False,
                           lambda s: s.finish("workflow_runs", run_id, fields))

    def start_stage(self, row: Mapping[str, Any]) -> bool:
        return self._garde("début d'étape", False, lambda s: s.insert("stage_attempts", row))

    def finish_stage(self, attempt_id: str, fields: Mapping[str, Any]) -> bool:
        return self._garde("fin d'étape", False,
                           lambda s: s.finish("stage_attempts", attempt_id, fields))

    def record_llm_call(self, row: Mapping[str, Any]) -> bool:
        # `ignore` : une collecte de lot rejouée ne compte pas deux fois
        # (index unique provider + batch_id + custom_id).
        return self._garde("appel LLM", False,
                           lambda s: s.insert("llm_calls", row, ignore=True))

    def record_batch(self, row: Mapping[str, Any]) -> bool:
        return self._garde("lot", False, lambda s: s.insert("llm_batches", row, ignore=True))

    def update_batch(self, batch_id: str, fields: Mapping[str, Any]) -> bool:
        return self._garde("suivi de lot", False,
                           lambda s: s.update("llm_batches", batch_id, fields))

    def map_batch_requests(self, rows: Iterable[Mapping[str, Any]]) -> int:
        lignes = list(rows)
        return self._garde("correspondance de lot", 0, lambda s: sum(
            s.insert("batch_requests", r, ignore=True) for r in lignes))

    def record_review_event(self, row: Mapping[str, Any]) -> bool:
        return self._garde("événement de relecture", False,
                           lambda s: s.insert("review_events", row))

    # --- lectures utiles à l'exécution --------------------------------------
    def prior_attempts(self, source_id: str, episode_guid: str | None,
                       stage: str) -> list[dict[str, Any]]:
        if not episode_guid:
            return []
        return self._garde("lecture des tentatives", [], lambda s: s.query(
            "SELECT id, status, intent, started_at FROM stage_attempts "
            "WHERE source_id = ? AND episode_guid = ? AND stage = ? ORDER BY started_at",
            [source_id, episode_guid, stage]))

    def batch_mapping(self, batch_id: str) -> dict[str, dict[str, Any]]:
        lignes = self._garde("lecture d'un lot", [], lambda s: s.query(
            "SELECT * FROM batch_requests WHERE batch_id = ?", [batch_id]))
        return {ligne["custom_id"]: ligne for ligne in lignes}


_CACHE: dict[tuple[str, bool], TelemetryRecorder] = {}


def get_recorder() -> TelemetryRecorder:
    """L'enregistreur selon l'environnement, partagé dans le processus."""
    if not _vrai(os.environ.get(ENV_ENABLED), True):
        return NoopTelemetryRecorder()
    strict = _vrai(os.environ.get(ENV_STRICT), False)
    cle = (str(default_db_path()), strict)
    if cle not in _CACHE:
        _CACHE[cle] = SQLiteTelemetryRecorder(Path(cle[0]), strict=strict)
    return _CACHE[cle]


def reset_cache() -> None:
    """Oublie les enregistreurs ouverts (tests, changement de base)."""
    for recorder in _CACHE.values():
        store = getattr(recorder, "_store", None)
        if store is not None:
            store.close()
    _CACHE.clear()
