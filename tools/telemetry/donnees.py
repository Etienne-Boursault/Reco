"""
donnees.py — les observations d'une source, chargées pour les rapports.

Lecture seule : une base absente donne un jeu vide, sans créer de fichier. Le
catalogue (épisodes, recos) est lu à part : c'est lui qui dit la saison d'un
épisode et son état final, jamais la télémétrie seule.
"""
from __future__ import annotations

import json
import sqlite3
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

_TABLES = ("workflow_runs", "stage_attempts", "llm_calls", "llm_batches",
           "review_events", "review_activity")


def _json(valeur: Any, defaut: Any) -> Any:
    if not isinstance(valeur, str):
        return defaut
    try:
        return json.loads(valeur)
    except ValueError:
        return defaut


def instant(iso: str) -> datetime:
    return datetime.fromisoformat(iso)


@dataclass
class Donnees:
    source_id: str
    runs: list[dict[str, Any]] = field(default_factory=list)
    attempts: list[dict[str, Any]] = field(default_factory=list)
    calls: list[dict[str, Any]] = field(default_factory=list)
    batches: list[dict[str, Any]] = field(default_factory=list)
    events: list[dict[str, Any]] = field(default_factory=list)
    activity: list[dict[str, Any]] = field(default_factory=list)
    schema_version: int | None = None

    @classmethod
    def charger(cls, source_id: str, chemin: Path) -> Donnees:
        donnees = cls(source_id)
        if not chemin.exists():
            return donnees
        conn = sqlite3.connect(f"file:{chemin.as_posix()}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        try:
            donnees.schema_version = conn.execute("PRAGMA user_version").fetchone()[0]
            existantes = {r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'")}
            lignes: dict[str, list[dict[str, Any]]] = {}
            for table in _TABLES:
                if table not in existantes:
                    lignes[table] = []
                    continue
                if table == "llm_calls":
                    sql = ("SELECT c.* FROM llm_calls c JOIN stage_attempts s "
                           "ON s.id = c.stage_attempt_id WHERE s.source_id = ?")
                elif table == "llm_batches":
                    sql = ("SELECT b.* FROM llm_batches b JOIN workflow_runs r "
                           "ON r.id = b.workflow_run_id WHERE r.source_id = ?")
                else:
                    sql = f"SELECT * FROM {table} WHERE source_id = ?"  # noqa: S608 — table fixe
                lignes[table] = [dict(r) for r in conn.execute(sql, [source_id])]
        finally:
            conn.close()
        donnees.runs, donnees.attempts = lignes["workflow_runs"], lignes["stage_attempts"]
        donnees.calls, donnees.batches = lignes["llm_calls"], lignes["llm_batches"]
        donnees.events, donnees.activity = lignes["review_events"], lignes["review_activity"]
        for tentative in donnees.attempts:
            tentative["measurements"] = {
                k: v.get("value") for k, v in _json(tentative.get("measurements_json"), {}).items()
                if isinstance(v, dict)}
            tentative["config"] = _json(tentative.get("config_json"), {})
        return donnees

    def appels_de(self) -> dict[str, list[dict[str, Any]]]:
        par_tentative: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for appel in self.calls:
            par_tentative[appel["stage_attempt_id"]].append(appel)
        return par_tentative

    def tentatives_par_episode(self) -> dict[str, list[dict[str, Any]]]:
        par_episode: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for tentative in self.attempts:
            if tentative.get("episode_guid"):
                par_episode[tentative["episode_guid"]].append(tentative)
        for liste in par_episode.values():
            liste.sort(key=lambda t: t["started_at"])
        return par_episode


def catalogue(source_id: str) -> dict[str, dict[str, Any]]:
    """Épisodes du catalogue, avec leur état final (statuts des recos)."""
    import common
    episodes: dict[str, dict[str, Any]] = {}
    for chemin in common.list_episode_files(source_id):
        try:
            ep = common.read_json(chemin)
        except (OSError, ValueError):
            continue
        if ep.get("guid"):
            episodes[ep["guid"]] = {"guid": ep["guid"], "season": ep.get("season"),
                                    "number": ep.get("number"),
                                    "transcriptSource": ep.get("transcriptSource"),
                                    "transcriptModel": ep.get("transcriptModel"),
                                    "recos": defaultdict(int)}
    dossier = common.recos_dir_for(source_id)
    if dossier.exists():
        for chemin in dossier.glob("*.json"):
            try:
                reco = common.read_json(chemin)
            except (OSError, ValueError):
                continue
            ep = episodes.get(reco.get("episodeGuid"))
            if ep is not None:
                ep["recos"][reco.get("status") or "draft"] += 1
    for ep in episodes.values():
        ep["recos"] = dict(sorted(ep["recos"].items()))
    return episodes
