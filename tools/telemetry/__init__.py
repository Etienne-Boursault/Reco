"""
telemetry — mesure des exécutions du pipeline et de la relecture.

Observations append-only dans une base SQLite dédiée, hors du catalogue :
enregistrer une métrique ne demande aucun commit. Contrat et limites :
`docs/workflow-metrics.md`.

Réglages (environnement) :
  RECO_METRICS_ENABLED  1 par défaut ; 0 désactive (enregistreur nul)
  RECO_METRICS_DB       chemin de la base (défaut tools/output/telemetry/reco_metrics.sqlite)
  RECO_METRICS_STRICT   1 : une observation impossible à écrire arrête l'exécution
  RECO_PIPELINE_PROFILE profil déclaré de la configuration (ex. ubm-s6-prod-2026-10)
  RECO_RUN_INTENT       intention par défaut d'un run lancé à la main
"""
from telemetry.context import (
    INTENTS,
    WORKFLOW_VERSION,
    RunHandle,
    StageHandle,
    current_run,
    current_stage,
    fingerprint,
    now_iso,
    safe_error,
    stage,
    workflow_run,
)
from telemetry.recorder import (
    NoopTelemetryRecorder,
    SQLiteTelemetryRecorder,
    TelemetryError,
    TelemetryRecorder,
    get_recorder,
    reset_cache,
)

__all__ = [
    "INTENTS", "WORKFLOW_VERSION", "NoopTelemetryRecorder", "RunHandle",
    "SQLiteTelemetryRecorder", "StageHandle", "TelemetryError", "TelemetryRecorder",
    "current_run", "current_stage", "fingerprint", "get_recorder", "now_iso",
    "reset_cache", "safe_error", "stage", "workflow_run",
]
