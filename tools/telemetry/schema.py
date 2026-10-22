"""
schema.py — schéma de la base de télémétrie, migré par `PRAGMA user_version`.

Base dédiée, distincte des trois caches SQLite (enrichissement, HTTP,
embeddings) : vider un cache ne doit jamais effacer une observation.

Une migration ne fait qu'AJOUTER (tables, colonnes, index). Une observation
enregistrée n'est jamais réécrite : seuls `ended_at`, `status` et les mesures de
fin d'une tentative sont posés, une seule fois, à sa finalisation (cf.
`store.Store.finish_stage`).

Conventions :
  - horodatages UTC ISO-8601 (`started_at`, `ended_at`) pour l'affichage ;
  - durées en millisecondes ENTIÈRES, mesurées par horloge monotone dans le
    même processus (`elapsed_ms`) ;
  - `NULL` = non mesuré ; `0` = mesuré à zéro. Jamais l'un pour l'autre ;
  - montants en `TEXT` décimal (`Decimal`), jamais arrondis appel par appel.
"""
from __future__ import annotations

# Chaque entrée fait passer la base de la version i à i + 1.
MIGRATIONS: list[str] = [
    # --- v1 : runs, tentatives, appels LLM, lots, événements de relecture ----
    """
    CREATE TABLE workflow_runs (
      id TEXT PRIMARY KEY,
      source_id TEXT NOT NULL,
      trigger TEXT NOT NULL,                 -- cli | scheduler | review | library
      command TEXT,                          -- script et étape (« traiter_nouveaux_episodes:extraire »)
      intent TEXT NOT NULL,                  -- standard_first_pass | retry | ... | unknown
      pipeline_profile TEXT,
      workflow_version TEXT NOT NULL,
      git_commit TEXT,
      config_fingerprint TEXT NOT NULL,
      config_json TEXT NOT NULL DEFAULT '{}',
      machine_json TEXT NOT NULL DEFAULT '{}',
      parent_run_id TEXT,
      started_at TEXT NOT NULL,
      ended_at TEXT,
      elapsed_ms INTEGER,
      cpu_time_ms INTEGER,
      status TEXT NOT NULL,                  -- started | succeeded | partial | failed | interrupted
      lost_observations INTEGER,
      telemetry_version INTEGER NOT NULL DEFAULT 1
    );

    CREATE TABLE stage_attempts (
      id TEXT PRIMARY KEY,
      workflow_run_id TEXT NOT NULL REFERENCES workflow_runs(id),
      source_id TEXT NOT NULL,
      episode_guid TEXT,
      correlation_id TEXT,
      season INTEGER,
      stage TEXT NOT NULL,
      intent TEXT NOT NULL,
      retry_of_attempt_id TEXT,
      status TEXT NOT NULL,                  -- started | succeeded | failed | skipped | cancelled | interrupted
      skip_reason TEXT,
      started_at TEXT NOT NULL,
      ended_at TEXT,
      elapsed_ms INTEGER,
      cpu_time_ms INTEGER,
      media_origin TEXT,                     -- youtube | acast | other | unknown
      media_identifier TEXT,
      media_checksum TEXT,
      media_duration_ms INTEGER,
      transcript_id_or_hash TEXT,
      provider TEXT,
      model TEXT,
      prompt_version TEXT,
      prompt_sha256 TEXT,
      recipe_version TEXT,
      config_fingerprint TEXT,
      config_json TEXT NOT NULL DEFAULT '{}',
      measurements_json TEXT NOT NULL DEFAULT '{}',
      error_code TEXT,
      error_category TEXT,
      error_message_safe TEXT,
      telemetry_complete INTEGER NOT NULL DEFAULT 0
    );

    CREATE TABLE llm_batches (
      id TEXT PRIMARY KEY,                   -- identifiant du lot chez le fournisseur
      provider TEXT NOT NULL,
      model TEXT NOT NULL,
      workflow_run_id TEXT REFERENCES workflow_runs(id),
      request_count INTEGER NOT NULL,
      submitted_at TEXT NOT NULL,
      submit_elapsed_ms INTEGER,
      last_status TEXT,
      ended_at TEXT,
      wait_ms INTEGER,
      result_processing_ms INTEGER
    );

    -- Correspondance custom_id -> épisode, écrite AVANT de scruter le lot :
    -- un lot interrompu reste attribuable à la reprise.
    CREATE TABLE batch_requests (
      batch_id TEXT NOT NULL REFERENCES llm_batches(id),
      custom_id TEXT NOT NULL,
      stage_attempt_id TEXT NOT NULL REFERENCES stage_attempts(id),
      episode_guid TEXT NOT NULL,
      chunk_index INTEGER,
      chunk_count INTEGER,
      chars_in_chunk INTEGER,
      PRIMARY KEY (batch_id, custom_id)
    );

    CREATE TABLE llm_calls (
      id TEXT PRIMARY KEY,
      stage_attempt_id TEXT NOT NULL REFERENCES stage_attempts(id),
      provider TEXT NOT NULL,
      model TEXT NOT NULL,
      transport TEXT NOT NULL,               -- sync | batch
      batch_id TEXT,
      batch_custom_id TEXT,
      chunk_index INTEGER,
      chunk_count INTEGER,
      chars_in_chunk INTEGER,
      provider_request_id TEXT,
      status TEXT NOT NULL,                  -- succeeded | failed | billing_uncertain
      parse_status TEXT,                     -- json | non_json | empty
      candidates_raw INTEGER,
      elapsed_ms INTEGER,
      input_tokens INTEGER,
      output_tokens INTEGER,
      cache_read_input_tokens INTEGER,
      cache_write_input_tokens INTEGER,
      reasoning_tokens INTEGER,
      usage_source TEXT NOT NULL,            -- provider | estimated | unavailable
      request_json TEXT NOT NULL DEFAULT '{}',
      pricing_snapshot_id TEXT,
      cost_decimal TEXT,                     -- jetons x tarif daté, NULL si l'un manque
      observed_cost_decimal TEXT,            -- facture rapprochée, NULL tant qu'elle ne l'est pas
      cost_currency TEXT,
      cost_owner TEXT,                       -- user_byok | reco_managed | local_machine | unknown
      error_code TEXT,
      recorded_at TEXT NOT NULL,
      provider_usage_json TEXT NOT NULL DEFAULT '{}'
    );

    CREATE TABLE review_events (
      id TEXT PRIMARY KEY,
      source_id TEXT NOT NULL,
      episode_guid TEXT,
      reco_id TEXT NOT NULL,
      source_stage_attempt_id TEXT,
      actor_kind TEXT NOT NULL,              -- human | agent | system | unknown
      actor_id_hash TEXT,
      action TEXT NOT NULL,
      changed_fields_json TEXT NOT NULL DEFAULT '[]',
      derived_categories_json TEXT NOT NULL DEFAULT '[]',
      review_session_id TEXT,
      active_duration_ms INTEGER,
      status_before TEXT,
      status_after TEXT,
      occurred_at TEXT NOT NULL,
      provenance_quality TEXT NOT NULL,      -- exact | inferred | unknown
      metadata_json TEXT NOT NULL DEFAULT '{}'
    );

    CREATE INDEX idx_stage_runs ON stage_attempts(workflow_run_id, episode_guid, stage);
    CREATE INDEX idx_stage_cohorts ON stage_attempts(source_id, season, intent, status, stage);
    CREATE INDEX idx_stage_episode ON stage_attempts(source_id, episode_guid, stage, started_at);
    CREATE INDEX idx_calls_attempt ON llm_calls(stage_attempt_id);
    CREATE UNIQUE INDEX idx_calls_batch_entry ON llm_calls(provider, batch_id, batch_custom_id)
      WHERE batch_id IS NOT NULL;
    CREATE INDEX idx_review_episode ON review_events(source_id, episode_guid, occurred_at);
    """,
]

SCHEMA_VERSION = len(MIGRATIONS)
