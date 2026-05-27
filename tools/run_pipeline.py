"""
run_pipeline.py — Étape 4 : orchestrateur du pipeline « Reco ».

Enchaîne les étapes du pipeline de collecte pour une source donnée :
  1. fetch     : récupère les épisodes depuis le RSS ;
  2. transcribe: télécharge l'audio et transcrit (faster-whisper) ;
  3. extract   : extrait les recos via l'API Anthropic.

Chaque étape est indépendante et ré-exécutable. L'orchestrateur est robuste :
une erreur sur un épisode est journalisée et n'interrompt pas le traitement des
épisodes suivants.

Usage :
    python run_pipeline.py --source un-bon-moment
    python run_pipeline.py --source un-bon-moment --limit 5
    python run_pipeline.py --source un-bon-moment --steps fetch,transcribe
    python run_pipeline.py --source un-bon-moment --steps extract --dry-run
    python run_pipeline.py --source un-bon-moment --model medium
"""

from __future__ import annotations

import argparse

from common import list_episode_files, log, read_json

# Étapes valides et ordre canonique.
ALL_STEPS = ["fetch", "transcribe", "extract"]


def _parse_steps(raw: str) -> list[str]:
    """Valide la liste d'étapes demandée et la remet dans l'ordre canonique."""
    requested = [s.strip().lower() for s in raw.split(",") if s.strip()]
    unknown = [s for s in requested if s not in ALL_STEPS]
    if unknown:
        raise ValueError(
            f"Étape(s) inconnue(s) : {', '.join(unknown)}. "
            f"Valides : {', '.join(ALL_STEPS)}."
        )
    return [s for s in ALL_STEPS if s in requested]


def run(source_id: str, steps: list[str], limit: int | None, whisper_model: str,
        extract_model: str, batch: bool, language: str | None, dry_run: bool,
        force: bool) -> None:
    """Exécute les étapes demandées dans l'ordre."""
    # Imports paresseux : on ne charge les deps lourdes que si l'étape est demandée.
    log.info("=== Pipeline Reco — source « %s » — étapes : %s ===",
             source_id, ", ".join(steps))

    # Indicateurs d'échec de chaque étape pour la synthèse finale.
    fetch_failed = False
    transcribe_failed = False
    extract_failed = False

    # --- Étape 1 : fetch ---------------------------------------------------
    if "fetch" in steps:
        log.info("--- [1/?] FETCH ---")
        from fetch_episodes import fetch_episodes  # noqa: PLC0415
        try:
            fetch_episodes(source_id, limit=limit)
        except Exception as exc:  # noqa: BLE001
            fetch_failed = True
            log.error("Étape fetch échouée : %s", exc)

    # On (re)liste les épisodes après fetch.
    episode_paths = list_episode_files(source_id)
    if limit is not None:
        episode_paths = episode_paths[:limit]

    # --- Étape 2 : transcribe ---------------------------------------------
    if "transcribe" in steps:
        log.info("--- [2/?] TRANSCRIBE (%d épisode[s]) ---", len(episode_paths))
        from transcribe import transcribe_episode  # noqa: PLC0415
        for path in episode_paths:
            try:
                transcribe_episode(source_id, path, whisper_model, language, force)
            except Exception as exc:  # noqa: BLE001 — on continue.
                transcribe_failed = True
                log.error("Transcription échouée sur %s : %s", path.name, exc)

    # --- Étape 3 : extract -------------------------------------------------
    if "extract" in steps:
        log.info("--- [3/?] EXTRACT (%d épisode[s], modèle %s%s) ---",
                 len(episode_paths), extract_model, ", batch" if batch else "")
        from common import make_anthropic_client  # noqa: PLC0415
        from extract_recos import (  # noqa: PLC0415
            extract_all_batch, extract_for_episode,
        )
        client = None
        if not dry_run:
            try:
                client = make_anthropic_client()
            except Exception as exc:  # noqa: BLE001
                extract_failed = True
                log.error("Impossible d'initialiser le client Anthropic : %s", exc)
                log.error("Étape extract abandonnée.")
                _log_pipeline_summary(fetch_failed, transcribe_failed, extract_failed)
                return

        if batch and not dry_run:
            # Un seul lot pour tous les épisodes (−50 % de coût).
            try:
                extract_all_batch(source_id, episode_paths, client, extract_model)
            except Exception as exc:  # noqa: BLE001
                extract_failed = True
                log.error("Extraction par batch échouée : %s", exc)
        else:
            for path in episode_paths:
                guid = read_json(path).get("guid", "?")
                try:
                    extract_for_episode(source_id, path, client, dry_run, extract_model)
                except Exception as exc:  # noqa: BLE001 — on continue.
                    extract_failed = True
                    log.error("Extraction échouée sur %s (%s) : %s", path.name, guid, exc)

    _log_pipeline_summary(fetch_failed, transcribe_failed, extract_failed)
    log.info("=== Pipeline terminé. ===")


def _log_pipeline_summary(fetch_failed: bool, transcribe_failed: bool,
                          extract_failed: bool) -> None:
    """Affiche un récap des étapes en échec, si applicable."""
    failed = [name for name, flag in (
        ("fetch", fetch_failed),
        ("transcribe", transcribe_failed),
        ("extract", extract_failed),
    ) if flag]
    if failed:
        log.warning("Synthèse : étape(s) en échec → %s.", ", ".join(failed))


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Orchestrateur du pipeline de collecte Reco (fetch -> transcribe -> extract)."
    )
    parser.add_argument("--source", required=True,
                        help="Identifiant de la source (ex: un-bon-moment).")
    parser.add_argument("--limit", type=int, default=None,
                        help="Limite le nombre d'épisodes traités.")
    parser.add_argument("--steps", default=",".join(ALL_STEPS),
                        help=f"Étapes à exécuter, séparées par des virgules "
                             f"(défaut: {','.join(ALL_STEPS)}).")
    parser.add_argument("--whisper-model", default="small",
                        help="Modèle Whisper pour la transcription (défaut: small).")
    parser.add_argument("--extract-model", default="claude-sonnet-4-6",
                        help="Modèle LLM pour l'extraction (défaut: claude-sonnet-4-6).")
    parser.add_argument("--batch", action="store_true",
                        help="Extraction via Message Batches API (-50%% de coût).")
    parser.add_argument("--language", default="fr",
                        help="Langue de transcription (défaut: fr ; vide = auto).")
    parser.add_argument("--dry-run", action="store_true",
                        help="Extraction : n'appelle pas l'API, n'écrit rien.")
    parser.add_argument("--force", action="store_true",
                        help="Transcription : ignore le cache et retranscrit.")
    args = parser.parse_args()

    steps = _parse_steps(args.steps)
    run(
        source_id=args.source,
        steps=steps,
        limit=args.limit,
        whisper_model=args.whisper_model,
        extract_model=args.extract_model,
        batch=args.batch,
        language=args.language or None,
        dry_run=args.dry_run,
        force=args.force,
    )


if __name__ == "__main__":
    main()
