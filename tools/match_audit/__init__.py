"""tools.match_audit — Audit a posteriori des matchs YouTube ↔ Acast.

Détecte les épisodes pour lesquels le match YouTube est probablement
erroné (cf. mémoire ``reco-cleanup-collisions``). Stratégie : appliquer
plusieurs heuristiques indépendantes (durée, intro, titre) et flagger
``matchSuspect=true`` sur l'épisode + écrire un sidecar détaillé.

API publique :
    Value objects + service     : MatchAuditResult, MatchAuditService,
                                  MatchSuspicion, SourceAuditReport,
                                  Severity, compute_should_flag.
    Settings                    : MatchAuditSettings.
    Checks (functions, legacy)  : check_duration, check_intro_similarity,
                                  check_title_similarity.
    Checks (Protocol classes)   : DurationCheck, IntroTextSimilarityCheck,
                                  TitleSimilarityCheck.
    Strategies                  : SequenceMatcherStrategy.
    Persistance                 : set_match_suspect_flag,
                                  clear_match_suspect_flag,
                                  write_sidecar, read_sidecar,
                                  sidecar_path.
    CLI runner                  : default_service, run_audit, RunOptions,
                                  undo_last_apply.

Voir ADRs 0013 (rationale audit) et 0015 (sidecar pattern).
"""
from tools.match_audit.audit_trail import JsonlAuditTrail, NoopAuditTrail
from tools.match_audit.cli_runner import (
    FileTranscriptRepo,
    RunOptions,
    RunResult,
    default_service,
    run_audit,
    undo_last_apply,
)
from tools.match_audit.duration_check import DurationCheck, check_duration
from tools.match_audit.flag_writer import (
    CommonEpisodeRepo,
    clear_match_suspect_flag,
    set_match_suspect_flag,
)
from tools.match_audit.intro_text_similarity import (
    IntroTextSimilarityCheck,
    check_intro_similarity,
)
from tools.match_audit.service import (
    MatchAuditResult,
    MatchAuditService,
    SourceAuditReport,
    compute_should_flag,
)
from tools.match_audit.settings import MatchAuditSettings
from tools.match_audit.sidecar import (
    delete_sidecar,
    list_sidecars,
    read_sidecar,
    sidecar_path,
    write_sidecar,
)
from tools.match_audit.strategies import SequenceMatcherStrategy
from tools.match_audit.title_similarity import (
    TitleSimilarityCheck,
    check_title_similarity,
)
from tools.match_audit.types import (
    KNOWN_KINDS,
    MatchSuspicion,
    Severity,
)

# Registre des checks livrés (CR archi #18) — pour aider à composer un
# service custom (``MatchAuditService(checks=DEFAULT_CHECKS)``).
DEFAULT_CHECK_FUNCTIONS: tuple = (
    check_duration,
    check_title_similarity,
)  # intro_similarity exige un transcript_repo, voir default_service.

__all__ = [
    "CommonEpisodeRepo",
    "DEFAULT_CHECK_FUNCTIONS",
    "DurationCheck",
    "FileTranscriptRepo",
    "IntroTextSimilarityCheck",
    "JsonlAuditTrail",
    "KNOWN_KINDS",
    "MatchAuditResult",
    "MatchAuditService",
    "MatchAuditSettings",
    "MatchSuspicion",
    "NoopAuditTrail",
    "RunOptions",
    "RunResult",
    "SequenceMatcherStrategy",
    "Severity",
    "SourceAuditReport",
    "TitleSimilarityCheck",
    "check_duration",
    "check_intro_similarity",
    "check_title_similarity",
    "clear_match_suspect_flag",
    "compute_should_flag",
    "default_service",
    "delete_sidecar",
    "list_sidecars",
    "read_sidecar",
    "run_audit",
    "set_match_suspect_flag",
    "sidecar_path",
    "undo_last_apply",
    "write_sidecar",
]
