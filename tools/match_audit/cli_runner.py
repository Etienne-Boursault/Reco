"""``cli_runner`` — logique métier extraite du CLI (testable, sans argparse).

Le CLI ``tools/audit_yt_acast.py`` n'est qu'une fine couche d'argparse
autour de ces fonctions (CR archi #15).
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Literal, Mapping

import common  # type: ignore[attr-defined]

from tools.match_audit.audit_trail import (
    JsonlAuditTrail,
    NoopAuditTrail,
)
from tools.match_audit.protocols import AuditTrail  # Protocol
from tools.match_audit.duration_check import DurationCheck
from tools.match_audit.flag_writer import (
    clear_match_suspect_flag,
    set_match_suspect_flag,
)
from tools.match_audit.intro_text_similarity import IntroTextSimilarityCheck
from tools.match_audit.protocols import TranscriptKind, TranscriptRepo
from tools.match_audit.service import (
    MatchAuditService,
    SourceAuditReport,
)
from tools.match_audit.settings import MatchAuditSettings
from tools.match_audit.sidecar import (
    delete_sidecar,
    list_sidecars,
    sidecar_path,
    write_sidecar,
)
from tools.match_audit.title_similarity import TitleSimilarityCheck
from tools.match_audit.types import severity_value

LOG_FORMATS = ("text", "json")
OUTPUT_FORMATS = ("json", "markdown", "human")
MODES = ("check", "apply")


# ---------------------------------------------------------------------------
# TranscriptRepo standard (lit ``TRANSCRIPTS_DIR/<source>/<slug>.<kind>.txt``)
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class FileTranscriptRepo:
    """Repo TranscriptRepo qui lit les transcripts depuis le disque.

    CR senior C3 / CR archi #10 — un SEUL Protocol, un kind paramétré ;
    **plus de fallback ``.txt`` ambigu** qui pouvait renvoyer le MÊME
    fichier pour Acast et pour YT et produire un faux "intro identique".
    Si le ``<slug>.<kind>.txt`` n'existe pas, on retourne ``None``
    (le check intro skippe — pas de faux verdict).
    """

    source_id: str
    base_dir: Path | None = None

    def _base(self) -> Path:
        return self.base_dir if self.base_dir is not None else common.TRANSCRIPTS_DIR

    def get(self, guid: str, kind: TranscriptKind) -> str | None:
        if kind not in ("acast", "youtube"):
            return None
        if not guid:
            return None
        path = self._base() / self.source_id / f"{common.slugify(guid)}.{kind}.txt"
        # Sécurité TOCTOU (CR senior C3) : on teste is_file après resolve()
        # — un symlink pointant ailleurs est traité comme s'il n'existait pas.
        try:
            real = path.resolve(strict=False)
        except OSError:
            return None
        if not real.is_file():
            return None
        try:
            return real.read_text(encoding="utf-8")
        except OSError:
            return None


# ---------------------------------------------------------------------------
# Service factory (CR archi #4 + #5)
# ---------------------------------------------------------------------------


def default_service(
    source_id: str,
    *,
    settings: MatchAuditSettings | None = None,
    transcript_repo: TranscriptRepo | None = None,
    base_transcripts_dir: Path | None = None,
) -> MatchAuditService:
    """Compose le service avec les checks par défaut.

    Lecture des seuils depuis ``settings`` (qui peut venir de ``SourceConfig``
    ou de la CLI — cf. ``MatchAuditSettings.from_source_extra``). Si rien
    n'est passé, on prend les défauts du module.
    """
    s = settings or MatchAuditSettings()
    repo = transcript_repo or FileTranscriptRepo(
        source_id=source_id, base_dir=base_transcripts_dir,
    )
    enabled = s.enabled_checks
    checks: list[Any] = []
    if enabled is None or "duration_mismatch" in enabled:
        checks.append(DurationCheck(tolerance=s.duration_tolerance))
    if enabled is None or "intro_mismatch" in enabled:
        checks.append(
            IntroTextSimilarityCheck(
                transcript_repo=repo,
                threshold=s.intro_threshold,
                intro_chars=s.intro_chars,
            ),
        )
    if enabled is None or "title_drift" in enabled:
        checks.append(TitleSimilarityCheck(threshold=s.title_threshold))
    return MatchAuditService(checks=checks)


# ---------------------------------------------------------------------------
# Episode loading
# ---------------------------------------------------------------------------


def load_episodes(source_id: str) -> list[tuple[Path, dict]]:
    """Charge tous les épisodes JSON d'une source.

    - Skip + warn les JSON illisibles (cf. ``test_cli_corrupt_json_skipped``).
    - Skip + warn les payloads qui ne sont PAS un dict (CR senior M6).
    """
    epdir = common.EPISODES_DIR / source_id
    if not epdir.exists():
        return []
    out: list[tuple[Path, dict]] = []
    for p in sorted(epdir.glob("*.json")):
        try:
            data = common.read_json(p)
        except (OSError, json.JSONDecodeError):
            common.log.warning("Skip JSON illisible : %s", p)
            continue
        if not isinstance(data, dict):
            common.log.warning("Skip payload non-dict : %s", p)
            continue
        out.append((p, data))
    return out


def index_paths_by_guid(eps: Iterable[tuple[Path, dict]]) -> dict[str, Path]:
    """Index ``guid -> path`` ; SKIP les payloads sans guid valide
    (CR senior C1 — pas d'index par chaîne vide qui mélangerait plusieurs
    épisodes).
    """
    out: dict[str, Path] = {}
    for p, ep in eps:
        guid = ep.get("guid")
        if not isinstance(guid, str) or not guid:
            common.log.warning("Skip épisode sans guid : %s", p)
            continue
        out[guid] = p
    return out


# ---------------------------------------------------------------------------
# Formats de rendu (CR senior H7, CR archi #25)
# ---------------------------------------------------------------------------


def _md_escape(value: str) -> str:
    """Échappe les méta-caractères Markdown — union complète (ADR 0019 S-03).

    Délègue à ``audit_core.reporters.escape_md`` (SSOT). Couvre désormais
    ``\\``, ``*``, ``_``, backtick, ``[``, ``]``, ``|`` plus normalisation
    ``\\n``/``\\r`` en espace.
    """
    from audit_core.reporters import escape_md  # local import — éviter cycle
    return escape_md(value)


def report_as_dict(report: SourceAuditReport) -> dict[str, Any]:
    """Représentation JSON-friendly du rapport."""
    return {
        "source_id": report.source_id,
        "total": report.total,
        "audited_count": report.audited_count,
        "suspect_count": report.suspect_count,
        "clean_count": report.clean_count,
        "warning_only_count": report.warning_only_count,
        "skipped_no_guid": report.skipped_no_guid,
        "skipped_no_transcript": report.skipped_no_transcript,
        "skipped_no_duration": report.skipped_no_duration,
        "skipped_no_title": report.skipped_no_title,
        "audited_episode_guids": list(report.audited_episode_guids),
        "results": [
            {
                "episode_guid": r.episode_guid,
                "is_suspect": r.is_suspect,
                "suspicions": [
                    {
                        "kind": s.kind,
                        "detail": s.detail,
                        "severity": severity_value(s.severity),
                    }
                    for s in r.suspicions
                ],
            }
            for r in report.results
            if r.has_findings  # ne logue que les épisodes intéressants
        ],
    }


def format_json(report: SourceAuditReport) -> str:
    return json.dumps(
        report_as_dict(report), ensure_ascii=False, indent=2,
    ) + "\n"


def format_markdown(report: SourceAuditReport) -> str:
    lines: list[str] = []
    lines.append(f"# Audit match YT↔Acast — `{_md_escape(report.source_id)}`")
    lines.append("")
    lines.append(f"- Total : {report.total} épisodes")
    lines.append(f"- Audités : {report.audited_count}")
    lines.append(f"- Suspects : {report.suspect_count}")
    lines.append(f"- Clean : {report.clean_count}")
    lines.append(f"- Warnings seuls : {report.warning_only_count}")
    lines.append(f"- Skipped (sans guid) : {report.skipped_no_guid}")
    lines.append(f"- Skipped (sans durée) : {report.skipped_no_duration}")
    lines.append(f"- Skipped (sans titre) : {report.skipped_no_title}")
    lines.append(f"- Skipped (sans transcript) : {report.skipped_no_transcript}")
    lines.append("")
    interesting = [r for r in report.results if r.has_findings]
    if not interesting:
        lines.append("_Aucun épisode flagué._")
        return "\n".join(lines) + "\n"
    lines.append("| Episode GUID | Suspect | Détails |")
    lines.append("|---|---|---|")
    for r in interesting:
        flag = "OUI" if r.is_suspect else "warn"
        details = "; ".join(
            f"{_md_escape(s.kind)}({severity_value(s.severity)}): "
            f"{_md_escape(s.detail)}"
            for s in r.suspicions
        )
        lines.append(
            f"| `{_md_escape(r.episode_guid)}` | {flag} | {details} |",
        )
    return "\n".join(lines) + "\n"


def format_human(report: SourceAuditReport) -> str:
    """Une ligne par épisode flaggué — convivial CLI."""
    out: list[str] = []
    out.append(
        f"[{report.source_id}] audités={report.audited_count} "
        f"suspects={report.suspect_count} clean={report.clean_count} "
        f"warnings_seuls={report.warning_only_count} "
        f"skipped(guid={report.skipped_no_guid}, "
        f"dur={report.skipped_no_duration}, "
        f"title={report.skipped_no_title}, "
        f"transcript={report.skipped_no_transcript})",
    )
    for r in report.results:
        if not r.has_findings:
            continue
        details = "; ".join(
            f"{s.kind}({severity_value(s.severity)}): {s.detail}"
            for s in r.suspicions
        )
        out.append(f"  {r.episode_guid} suspect={r.is_suspect} — {details}")
    return "\n".join(out) + "\n"


# ---------------------------------------------------------------------------
# JSONL logging (CR senior H6)
# ---------------------------------------------------------------------------


def emit_jsonl_events(report: SourceAuditReport, *, sink: Any) -> None:
    """Émet un événement par épisode audité avec findings, vers ``sink``.

    ``sink`` peut être ``sys.stdout`` ou un fichier ouvert en append.
    """
    for r in report.results:
        if not r.has_findings:
            continue
        event = {
            "event": "match_audit.finding",
            "source_id": report.source_id,
            "episode_guid": r.episode_guid,
            "suspect": r.is_suspect,
            "suspicions": [
                {
                    "kind": s.kind,
                    "detail": s.detail,
                    "severity": severity_value(s.severity),
                }
                for s in r.suspicions
            ],
        }
        sink.write(json.dumps(event, ensure_ascii=False) + "\n")


# ---------------------------------------------------------------------------
# Run / apply / undo
# ---------------------------------------------------------------------------


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z",
    )


def trail_dir_for(source_id: str, *, base_dir: Path | None = None) -> Path:
    from tools.match_audit.sidecar import sidecar_dir_for
    return sidecar_dir_for(source_id, base_dir=base_dir)


def trail_path_for_run(
    source_id: str,
    *,
    base_dir: Path | None = None,
    timestamp: str | None = None,
) -> Path:
    ts = (timestamp or _utcnow_iso()).replace(":", "").replace("-", "")
    return trail_dir_for(source_id, base_dir=base_dir) / f"_run_{ts}.jsonl"


@dataclass(frozen=True)
class RunOptions:
    source_id: str
    mode: Literal["check", "apply"]
    output_format: Literal["json", "markdown", "human"] = "human"
    log_format: Literal["text", "json"] = "text"
    settings: MatchAuditSettings = field(default_factory=MatchAuditSettings)
    sidecar_base_dir: Path | None = None
    base_transcripts_dir: Path | None = None
    audited_at: str | None = None
    fail_on_suspect: bool = False


@dataclass(frozen=True)
class RunResult:
    report: SourceAuditReport
    output_text: str
    files_changed: int
    sidecars_written: int
    trail_path: Path | None
    exit_code: int


def run_audit(opts: RunOptions) -> RunResult:
    """Boucle d'audit principale (mode-agnostique).

    - charge les épisodes ;
    - bâtit le service ;
    - en ``check`` : ne touche à rien ;
    - en ``apply`` : flag les épisodes, écrit les sidecars, journalise.
    """
    eps = load_episodes(opts.source_id)
    paths_by_guid = index_paths_by_guid(eps)

    service = default_service(
        opts.source_id,
        settings=opts.settings,
        base_transcripts_dir=opts.base_transcripts_dir,
    )
    report = service.audit_source(opts.source_id, [ep for _, ep in eps])

    files_changed = 0
    sidecars_written = 0
    trail_path: Path | None = None

    if opts.mode == "apply":
        audited_at = opts.audited_at or _utcnow_iso()
        trail_path = trail_path_for_run(
            opts.source_id,
            base_dir=opts.sidecar_base_dir,
            timestamp=audited_at,
        )
        trail: AuditTrail = JsonlAuditTrail(trail_path)
        # 1) Pose / retire le flag dans le JSON épisode (miroir bool).
        for r in report.results:
            p = paths_by_guid.get(r.episode_guid)
            if p is None:
                continue
            changed = set_match_suspect_flag(p, r.is_suspect)
            if changed:
                files_changed += 1
            trail.record({
                "event": "match_audit.flag",
                "episode_guid": r.episode_guid,
                "path": str(p),
                "suspect": r.is_suspect,
                "changed": changed,
                "at": audited_at,
            })
        # 2) Écrit un sidecar pour chaque épisode AVEC findings (pas pour
        #    les clean — on évite de polluer le dossier de sidecars vides).
        for r in report.results:
            if not r.has_findings:
                continue
            path = write_sidecar(
                r,
                opts.source_id,
                base_dir=opts.sidecar_base_dir,
                audited_at=audited_at,
            )
            sidecars_written += 1
            trail.record({
                "event": "match_audit.sidecar",
                "episode_guid": r.episode_guid,
                "sidecar": str(path),
                "at": audited_at,
            })
    else:
        trail = NoopAuditTrail()

    # Rendu
    fmt = opts.output_format
    if fmt == "json":
        output_text = format_json(report)
    elif fmt == "markdown":
        output_text = format_markdown(report)
    else:
        output_text = format_human(report)

    # Exit code (CR senior M5)
    if opts.fail_on_suspect and report.suspect_count > 0:
        exit_code = 1
    else:
        exit_code = 0

    return RunResult(
        report=report,
        output_text=output_text,
        files_changed=files_changed,
        sidecars_written=sidecars_written,
        trail_path=trail_path,
        exit_code=exit_code,
    )


# ---------------------------------------------------------------------------
# --undo-last (CR archi #6)
# ---------------------------------------------------------------------------


def undo_last_apply(
    source_id: str,
    *,
    sidecar_base_dir: Path | None = None,
) -> dict[str, int]:
    """Supprime tous les sidecars + retire les flags du dernier --apply.

    Logique :
      1) Cherche le DERNIER ``_run_*.jsonl`` dans le dossier sidecar de la
         source.
      2) Relit les events ``match_audit.flag`` et ``match_audit.sidecar``
         pour retirer le flag dans le JSON et supprimer le sidecar
         correspondant.
      3) Supprime le fichier de trail consommé.

    Retourne un dict avec ``{flags_cleared, sidecars_deleted, trail_path}``.
    """
    d = trail_dir_for(source_id, base_dir=sidecar_base_dir)
    if not d.exists():
        return {"flags_cleared": 0, "sidecars_deleted": 0}
    runs = sorted(d.glob("_run_*.jsonl"))
    if not runs:
        return {"flags_cleared": 0, "sidecars_deleted": 0}
    last = runs[-1]
    flags_cleared = 0
    sidecars_deleted = 0
    trail = JsonlAuditTrail(last)
    for event in trail.iter_events():
        kind = event.get("event")
        if kind == "match_audit.flag" and event.get("changed") and event.get("suspect"):
            p = Path(event["path"])
            if p.exists():
                if clear_match_suspect_flag(p):
                    flags_cleared += 1
        elif kind == "match_audit.sidecar":
            sp = Path(event["sidecar"])
            if sp.exists():
                try:
                    sp.unlink()
                    sidecars_deleted += 1
                except OSError:  # pragma: no cover — defensive
                    pass
    try:
        last.unlink()
    except OSError:  # pragma: no cover — defensive
        pass
    return {
        "flags_cleared": flags_cleared,
        "sidecars_deleted": sidecars_deleted,
        "trail_path": str(last),
    }


__all__ = [
    "FileTranscriptRepo",
    "LOG_FORMATS",
    "MODES",
    "OUTPUT_FORMATS",
    "RunOptions",
    "RunResult",
    "default_service",
    "emit_jsonl_events",
    "format_human",
    "format_json",
    "format_markdown",
    "index_paths_by_guid",
    "load_episodes",
    "report_as_dict",
    "run_audit",
    "trail_path_for_run",
    "undo_last_apply",
]
