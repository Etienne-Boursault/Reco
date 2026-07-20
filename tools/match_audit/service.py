"""``MatchAuditService`` — orchestre les checks.

OCP : ajouter un nouveau check = ajouter une callable (ou un ``MatchCheck``
classe) à la liste. Pas de modification de la classe.

Vocabulaire (CR archi #20) : ``should_flag`` = critère d'application du
flag ``matchSuspect=true`` (au moins une suspicion de severity=ERROR).
On garde ``is_suspect`` comme alias rétrocompat.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Callable, Iterable, Mapping, Sequence

from tools.match_audit.protocols import EpisodeView, MatchCheck
from tools.match_audit.types import MatchSuspicion, Severity

# Une fonction OU une instance ``MatchCheck`` (classe avec .check) est acceptée.
CheckFunction = Callable[[Any], MatchSuspicion | None]
CheckLike = CheckFunction | MatchCheck


def compute_should_flag(suspicions: Sequence[MatchSuspicion]) -> bool:
    """Stratégie explicite : on flag SSI au moins une suspicion est ``ERROR``.

    Extraite en fonction libre pour rester testable et réutilisable
    (CR archi #20).
    """
    return any(s.severity == Severity.ERROR for s in suspicions)


@dataclass(frozen=True)
class MatchAuditResult:
    """Verdict pour un seul épisode.

    Invariants validés à la construction (CR senior H3) :
      - ``episode_guid`` non vide ;
      - ``suspicions`` est un tuple ;
      - ``is_suspect`` cohérent avec ``compute_should_flag(suspicions)``.
    """

    episode_guid: str
    is_suspect: bool
    suspicions: tuple[MatchSuspicion, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.episode_guid, str) or not self.episode_guid:
            raise ValueError("MatchAuditResult.episode_guid doit être non vide")
        if not isinstance(self.suspicions, tuple):
            raise ValueError("MatchAuditResult.suspicions doit être un tuple")
        expected = compute_should_flag(self.suspicions)
        if self.is_suspect != expected:
            raise ValueError(
                f"MatchAuditResult.is_suspect={self.is_suspect} incohérent "
                f"avec compute_should_flag(suspicions)={expected}",
            )

    @property
    def should_flag(self) -> bool:
        """Alias clair : ``True`` ssi le flag ``matchSuspect`` doit être posé."""
        return self.is_suspect

    @property
    def has_findings(self) -> bool:
        """``True`` ssi au moins une suspicion (warning ou error)."""
        return bool(self.suspicions)


@dataclass(frozen=True)
class SourceAuditReport:
    """Verdict agrégé sur une source entière.

    Compteurs explicites (CR senior M7, CR archi #13) :
      - ``audited_count``  : épisodes effectivement audités (avec verdict).
      - ``clean_count``    : audités SANS suspicion.
      - ``suspect_count``  : audités flaggués (au moins 1 suspicion ERROR).
      - ``warning_only_count`` : audités avec warnings mais sans flag.
      - ``skipped_no_guid`` : payload sans ``guid`` valide (CR senior C1).
      - ``skipped_no_transcript`` / ``_no_duration`` / ``_no_title`` :
        compteurs de non-applicabilité (sert au reporting de couverture).

    Invariant (CR archi #31) : ``len(results) == audited_count`` et
    ``audited_count + skipped_no_guid == total``.
    """

    source_id: str
    total: int
    results: tuple[MatchAuditResult, ...] = ()
    skipped_no_guid: int = 0
    skipped_no_transcript: int = 0
    skipped_no_duration: int = 0
    skipped_no_title: int = 0
    audited_episode_guids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.results, tuple):
            raise ValueError("SourceAuditReport.results doit être un tuple")
        if len(self.results) + self.skipped_no_guid != self.total:
            raise ValueError(
                "SourceAuditReport invariant cassé : "
                f"len(results)={len(self.results)} + "
                f"skipped_no_guid={self.skipped_no_guid} != total={self.total}",
            )

    @property
    def audited_count(self) -> int:
        return len(self.results)

    @property
    def suspect_count(self) -> int:
        return sum(1 for r in self.results if r.is_suspect)

    @property
    def clean_count(self) -> int:
        return sum(1 for r in self.results if not r.has_findings)

    @property
    def warning_only_count(self) -> int:
        return sum(
            1 for r in self.results if r.has_findings and not r.is_suspect
        )


class MatchAuditService:
    """Applique une chaîne de checks à un épisode.

    Un épisode est marqué ``should_flag=True`` (alias ``is_suspect``) dès
    qu'au moins un check retourne une ``MatchSuspicion`` de severity
    ``ERROR``. Les ``WARNING`` sont conservés dans ``suspicions`` mais ne
    déclenchent PAS le flag (signal informatif uniquement).

    Aligné avec ``EnrichAuditService`` (CR senior H4) : un service vide
    refuse la construction.
    """

    def __init__(self, checks: Iterable[CheckLike]) -> None:
        checks_t = tuple(checks)
        if not checks_t:
            raise ValueError("MatchAuditService : au moins un check requis")
        self._checks: tuple[CheckLike, ...] = checks_t

    @property
    def checks(self) -> tuple[CheckLike, ...]:
        """Exposition immuable de la chaîne de checks (CR archi #30)."""
        return self._checks

    # -- Audit unitaire ----------------------------------------------------

    def _invoke(self, check: CheckLike, ep_or_view: Any) -> MatchSuspicion | None:
        # Préfère l'API .check(EpisodeView) si dispo (Protocol MatchCheck),
        # sinon retombe sur la callable rétro-compat (dict / view).
        if hasattr(check, "check") and callable(check.check):  # type: ignore[union-attr]
            view = ep_or_view if isinstance(ep_or_view, EpisodeView) else None
            if view is None and isinstance(ep_or_view, Mapping):  # pragma: no cover
                view = EpisodeView.from_dict(ep_or_view)
            if view is None:  # pragma: no cover — defensive
                return None
            return check.check(view)  # type: ignore[union-attr]
        return check(ep_or_view)  # type: ignore[misc]

    def audit_episode(
        self,
        ep: Mapping[str, Any] | EpisodeView,
    ) -> MatchAuditResult | None:
        """Audite un épisode. Retourne ``None`` si guid invalide (CR C1)."""
        if isinstance(ep, EpisodeView):
            view = ep
            payload = ep.raw
        elif isinstance(ep, Mapping):
            view = EpisodeView.from_dict(ep)
            payload = ep
        else:
            return None
        if view is None:
            return None

        suspicions: list[MatchSuspicion] = []
        # Passe le PAYLOAD original aux callables legacy (qui s'attendent
        # à un dict pour `.get(...)`), et la VIEW aux Protocol checks.
        for check in self._checks:
            res = self._invoke(check, payload if not hasattr(check, "check") else view)
            if res is not None:
                suspicions.append(res)

        susp_t = tuple(suspicions)
        return MatchAuditResult(
            episode_guid=view.guid,
            is_suspect=compute_should_flag(susp_t),
            suspicions=susp_t,
        )

    # -- Audit source -------------------------------------------------------

    def audit_source(
        self,
        source_id: str,
        episodes: Iterable[Mapping[str, Any] | EpisodeView],
    ) -> SourceAuditReport:
        eps = list(episodes)
        results: list[MatchAuditResult] = []
        skipped_no_guid = 0
        skipped_no_transcript = 0
        skipped_no_duration = 0
        skipped_no_title = 0
        audited_guids: list[str] = []

        for ep in eps:
            r = self.audit_episode(ep)
            if r is None:
                skipped_no_guid += 1
                continue
            results.append(r)
            audited_guids.append(r.episode_guid)
            payload = ep.raw if isinstance(ep, EpisodeView) else ep
            if not isinstance(payload, Mapping):  # pragma: no cover — defensive
                continue
            if payload.get("audioDuration") is None or payload.get(
                "youtubeDuration",
            ) is None:
                skipped_no_duration += 1
            if not payload.get("title") or not payload.get("youtubeTitle"):
                skipped_no_title += 1
            # Indicateur "transcript indisponible" : on n'a pas accès aux
            # transcripts ici (DIP — c'est le check qui les lit). On lit
            # un drapeau optionnel ``transcriptStatus`` pour signaler.
            if payload.get("transcriptStatus") == "none":
                skipped_no_transcript += 1

        return SourceAuditReport(
            source_id=source_id,
            total=len(eps),
            results=tuple(results),
            skipped_no_guid=skipped_no_guid,
            skipped_no_transcript=skipped_no_transcript,
            skipped_no_duration=skipped_no_duration,
            skipped_no_title=skipped_no_title,
            audited_episode_guids=tuple(audited_guids),
        )


__all__ = [
    "CheckFunction",
    "CheckLike",
    "MatchAuditResult",
    "MatchAuditService",
    "SourceAuditReport",
    "compute_should_flag",
]
