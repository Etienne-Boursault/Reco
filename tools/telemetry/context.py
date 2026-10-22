"""
context.py — runs et tentatives d'étape, sans toucher aux signatures existantes.

    with telemetry.workflow_run("un-bon-moment", trigger="scheduler",
                                command="traiter_nouveaux_episodes:extraire",
                                intent="standard_first_pass") as run:
        with run.stage("extract", episode_guid=guid, season=6) as etape:
            ...                         # le code métier, inchangé
            etape.measure("unique_candidates", 12, "count")

Le run et l'étape courants voyagent par `contextvars` : une fonction appelée
profondément (l'adaptateur LLM, la transcription) écrit dans l'étape courante
via `current_stage()` sans qu'on lui passe rien. Hors de toute étape, elle
reçoit une étape nulle qui n'écrit rien.

Un run imbriqué n'en crée pas un second : une CLI lancée seule ouvre son run,
appelée par un orchestrateur elle rejoint le sien.

Intention d'une tentative (`intent`). Elle n'est jamais déduite de la saison,
du succès ou de l'absence de `--force`. Un run qui DÉCLARE le chemin nominal
(`standard_first_pass`, la chaîne de venus) qualifie chaque tentative d'après
l'historique de la base : aucune tentative antérieure -> première passe ; la
dernière a échoué -> `retry`, rattachée à elle ; une passe a déjà réussi ->
`unknown` (un retraitement nominal n'existe pas). Ailleurs, l'intention est
celle déclarée par le run, `unknown` par défaut.
"""
from __future__ import annotations

import contextlib
import functools
import hashlib
import json
import os
import platform
import re
import socket
import time
import uuid
from collections.abc import Iterator, Mapping
from contextvars import ContextVar
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from telemetry.recorder import TelemetryRecorder, get_recorder

WORKFLOW_VERSION = "pipeline-v1"
INTENTS = frozenset({"standard_first_pass", "retry", "manual_rerun", "experiment",
                     "source_migration", "backfill", "unknown"})
ENV_PROFILE = "RECO_PIPELINE_PROFILE"
ENV_INTENT = "RECO_RUN_INTENT"

# Colonnes qu'une étape peut renseigner en cours de route (posées à sa fin).
STAGE_FIELDS = frozenset({
    "media_origin", "media_identifier", "media_checksum", "media_duration_ms",
    "transcript_id_or_hash", "provider", "model", "prompt_version", "prompt_sha256",
    "recipe_version", "season", "episode_guid"})
# Ce sans quoi une tentative réussie n'est pas exploitable par l'estimateur.
REQUIRED_FIELDS: dict[str, tuple[str, ...]] = {
    "transcribe": ("media_origin", "model", "media_duration_ms"),
    "extract": ("provider", "model"),
}

_RUN: ContextVar[RunHandle | None] = ContextVar("reco_telemetry_run", default=None)
_STAGE: ContextVar[StageHandle | None] = ContextVar("reco_telemetry_stage", default=None)
_URL = re.compile(r"https?://\S+")
_SECRET = re.compile(r"(?i)(key|token|secret|password|authorization)\S*\s*[:=]\s*\S+")


def now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds")


def fingerprint(config: Mapping[str, Any]) -> str:
    """SHA-256 d'une représentation canonique des paramètres fonctionnels."""
    canon = json.dumps(config, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canon.encode("utf-8")).hexdigest()


def safe_error(exc: BaseException) -> dict[str, Any]:
    """Catégorie et résumé expurgé : ni URL, ni secret, ni texte long."""
    texte = _SECRET.sub(r"\1=<masqué>", _URL.sub("<url>", str(exc)))
    code = getattr(exc, "status_code", None)
    return {"error_code": str(code) if code is not None else None,
            "error_category": type(exc).__name__,
            "error_message_safe": texte[:160] or None}


@functools.cache
def git_commit() -> str | None:
    """Commit du dépôt, lu dans `.git` (pas de sous-processus ; None hors dépôt)."""
    import common
    racine = common.TOOLS_DIR.parent / ".git"
    try:
        tete = (racine / "HEAD").read_text(encoding="utf-8").strip()
        if not tete.startswith("ref: "):
            return tete or None
        ref = tete[5:]
        fichier = racine / ref
        if fichier.exists():
            return fichier.read_text(encoding="utf-8").strip() or None
        for ligne in (racine / "packed-refs").read_text(encoding="utf-8").splitlines():
            if ligne.endswith(" " + ref):
                return ligne.split(" ", 1)[0]
    except OSError:
        return None
    return None


def _modele_cpu() -> str | None:
    try:
        for ligne in Path("/proc/cpuinfo").read_text(encoding="utf-8").splitlines():
            if ligne.lower().startswith("model name"):
                return ligne.split(":", 1)[1].strip()
    except OSError:
        pass
    return platform.processor() or None


@functools.cache
def machine_profile() -> dict[str, Any]:
    """Profil reproductible de la machine. Le nom d'hôte n'est gardé qu'en empreinte."""
    return {
        "machine_id": hashlib.sha256(socket.gethostname().encode()).hexdigest()[:12],
        "worker": os.environ.get("RECO_WORKER") or None,
        "os": platform.system(), "arch": platform.machine(),
        "cpu_model": _modele_cpu(), "cpu_count": os.cpu_count(),
        "python": platform.python_version(),
    }


class StageHandle:
    def __init__(self, recorder: TelemetryRecorder, row: dict[str, Any]) -> None:
        self.recorder = recorder
        self.id: str = row["id"]
        self.stage: str = row["stage"]
        self.source_id: str = row["source_id"]
        self.intent: str = row["intent"]
        self.fields: dict[str, Any] = {k: row.get(k) for k in STAGE_FIELDS}
        self.measurements: dict[str, dict[str, Any]] = {}
        self.status: str | None = None
        self.skip_reason: str | None = None
        self.calls = 0
        self.calls_without_usage = 0
        self._lost_before = recorder.lost

    def measure(self, name: str, value: Any, unit: str) -> None:
        """Une mesure nommée, avec son unité. `None` = non mesuré, gardé tel quel."""
        self.measurements[name] = {"value": value, "unit": unit}

    def add(self, name: str, value: int | float, unit: str) -> None:
        """Cumule une mesure (octets, secondes de réparation…) au fil de l'étape."""
        courante = self.measurements.get(name, {}).get("value") or 0
        self.measure(name, courante + value, unit)

    def set(self, **fields: Any) -> None:
        inconnus = set(fields) - STAGE_FIELDS
        if inconnus:
            raise ValueError(f"champs d'étape inconnus : {sorted(inconnus)}")
        self.fields.update(fields)

    def skip(self, reason: str) -> None:
        """Rien n'a été exécuté (cache, entrée manquante, dry-run) : pas de coût."""
        self.status, self.skip_reason = "skipped", reason

    def fail(self, reason: str) -> None:
        """Échec constaté sans exception (le code métier l'a déjà absorbé)."""
        self.status = "failed"
        self.measurements.setdefault("failure", {"value": reason, "unit": "reason"})

    def _complete(self, status: str) -> bool:
        if status == "skipped":
            return self.recorder.lost == self._lost_before
        if status != "succeeded" or self.recorder.lost != self._lost_before:
            return False
        if any(self.fields.get(k) is None for k in REQUIRED_FIELDS.get(self.stage, ())):
            return False
        return not (self.stage == "extract" and (self.calls == 0 or self.calls_without_usage))


class _NullStage(StageHandle):
    """Étape de repli hors de tout run : accepte tout, n'écrit rien."""

    def __init__(self) -> None:
        from telemetry.recorder import NoopTelemetryRecorder
        super().__init__(NoopTelemetryRecorder(), {"id": "", "stage": "", "source_id": "",
                                                   "intent": "unknown"})

    def set(self, **fields: Any) -> None:
        return None


class RunHandle:
    def __init__(self, recorder: TelemetryRecorder, row: dict[str, Any]) -> None:
        self.recorder = recorder
        self.id: str = row["id"]
        self.source_id: str = row["source_id"]
        self.intent: str = row["intent"]
        self.failed_stages = 0

    def _intent_for(self, stage: str, episode_guid: str | None) -> tuple[str, str | None]:
        if self.intent != "standard_first_pass":
            return self.intent, None
        anterieures = [a for a in self.recorder.prior_attempts(self.source_id, episode_guid, stage)
                       if a["status"] != "skipped"]
        if not anterieures:
            return "standard_first_pass", None
        if any(a["status"] == "succeeded" for a in anterieures):
            return "unknown", None
        return "retry", anterieures[-1]["id"]

    @contextlib.contextmanager
    def stage(self, stage: str, *, episode_guid: str | None = None, season: int | None = None,
              intent: str | None = None, config: Mapping[str, Any] | None = None,
              retry_of_attempt_id: str | None = None, **fields: Any) -> Iterator[StageHandle]:
        if intent is None:
            intent, retry_of = self._intent_for(stage, episode_guid)
            retry_of_attempt_id = retry_of_attempt_id or retry_of
        if intent not in INTENTS:
            raise ValueError(f"intention inconnue : {intent}")
        config = dict(config or {})
        row = {"id": str(uuid.uuid4()), "workflow_run_id": self.id, "source_id": self.source_id,
               "episode_guid": episode_guid, "season": season, "stage": stage, "intent": intent,
               "correlation_id": f"{self.source_id}:{episode_guid}" if episode_guid else None,
               "retry_of_attempt_id": retry_of_attempt_id, "status": "started",
               "started_at": now_iso(), "config_json": config,
               "config_fingerprint": fingerprint(config) if config else None, **fields}
        self.recorder.start_stage(row)
        handle = StageHandle(self.recorder, row)
        jeton = _STAGE.set(handle)
        debut, cpu = time.perf_counter_ns(), time.process_time_ns()
        fin: dict[str, Any] = {}
        try:
            yield handle
            status = handle.status or "succeeded"
        except BaseException as exc:
            status = "failed" if isinstance(exc, Exception) else "interrupted"
            fin.update(safe_error(exc))
            raise
        finally:
            _STAGE.reset(jeton)
            if status == "failed":
                self.failed_stages += 1
            fin.update(handle.fields)
            fin.update({"status": status, "skip_reason": handle.skip_reason,
                        "ended_at": now_iso(),
                        "elapsed_ms": (time.perf_counter_ns() - debut) // 1_000_000,
                        "cpu_time_ms": (time.process_time_ns() - cpu) // 1_000_000,
                        "measurements_json": handle.measurements,
                        "telemetry_complete": int(handle._complete(status))})
            self.recorder.finish_stage(handle.id, fin)


@contextlib.contextmanager
def workflow_run(source_id: str, *, trigger: str, command: str, intent: str | None = None,
                 config: Mapping[str, Any] | None = None, parent_run_id: str | None = None,
                 recorder: TelemetryRecorder | None = None) -> Iterator[RunHandle]:
    """Ouvre un run racine, ou rejoint celui qui est déjà ouvert."""
    deja = _RUN.get()
    if deja is not None:
        yield deja
        return
    intent = intent or os.environ.get(ENV_INTENT) or "unknown"
    if intent not in INTENTS:
        raise ValueError(f"intention inconnue : {intent}")
    recorder = recorder or get_recorder()
    config = {"workflow_version": WORKFLOW_VERSION, **dict(config or {})}
    row = {"id": str(uuid.uuid4()), "source_id": source_id, "trigger": trigger,
           "command": command, "intent": intent,
           "pipeline_profile": os.environ.get(ENV_PROFILE) or None,
           "workflow_version": WORKFLOW_VERSION, "git_commit": git_commit(),
           "config_fingerprint": fingerprint(config), "config_json": config,
           "machine_json": machine_profile(), "parent_run_id": parent_run_id,
           "started_at": now_iso(), "status": "started"}
    recorder.start_run(row)
    handle = RunHandle(recorder, row)
    jeton = _RUN.set(handle)
    debut, cpu, pertes = time.perf_counter_ns(), time.process_time_ns(), recorder.lost
    status = "succeeded"
    try:
        yield handle
    except BaseException as exc:
        status = "failed" if isinstance(exc, Exception) else "interrupted"
        raise
    finally:
        _RUN.reset(jeton)
        if status == "succeeded" and handle.failed_stages:
            status = "partial"
        perdues = recorder.lost - pertes
        recorder.finish_run(handle.id, {
            "status": status, "ended_at": now_iso(),
            "elapsed_ms": (time.perf_counter_ns() - debut) // 1_000_000,
            "cpu_time_ms": (time.process_time_ns() - cpu) // 1_000_000,
            "lost_observations": recorder.lost - pertes})
        if perdues:
            import logging
            logging.getLogger("reco.telemetry").warning(
                "%d observation(s) de télémétrie perdue(s) pendant ce run.", perdues)


@contextlib.contextmanager
def stage(name: str, *, source_id: str, command: str | None = None,
          **kwargs: Any) -> Iterator[StageHandle]:
    """Une étape dans le run courant ; hors run, dans un run implicite à elle seule."""
    run = _RUN.get()
    if run is None:
        with workflow_run(source_id, trigger="library", command=command or name) as racine, \
                racine.stage(name, **kwargs) as handle:
            yield handle
        return
    with run.stage(name, **kwargs) as handle:
        yield handle


def current_run() -> RunHandle | None:
    return _RUN.get()


def current_stage() -> StageHandle:
    """L'étape en cours, ou une étape nulle : l'appelant n'a jamais à tester."""
    return _STAGE.get() or _NullStage()
