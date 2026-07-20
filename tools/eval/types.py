"""Types & Protocols partagés du harness d'évaluation.

Ce module est l'unique source de vérité pour :

- ``ExtractedReco`` : abstraction injectée dans le harness (DIP). Le harness
  ne consomme jamais un ``dict`` brut.
- ``EvalConfig`` : configuration injectable (seuil fuzzy, tolérance ts,
  encodage CSV, etc.). Frozen → reproductibilité d'un run.
- ``EvalDetail`` : ligne détaillée d'un verdict (frozen+slots).
- ``EvalMetrics`` : agrégat de scores (frozen, ``Mapping`` figés via
  ``MappingProxyType``).
- ``RunManifest`` : trace persistée d'un run d'évaluation (frozen).
- ``ExtractionSource`` / ``EvalReporter`` : Protocols.
- ``ReportFormat`` : enum strict des formats supportés.

Toutes les invariants sont documentés en docstring de chaque dataclass.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from types import MappingProxyType
from typing import Any, Final, Iterable, Mapping, Protocol, runtime_checkable

__all__ = [
    "DEFAULT_FUZZY_THRESHOLD",
    "DEFAULT_TIMESTAMP_TOLERANCE_SEC",
    "EvalConfig",
    "EvalDetail",
    "EvalMetrics",
    "EvalReporter",
    "ExtractedReco",
    "ExtractionSource",
    "ReportFormat",
    "RunManifest",
]


# --- Constantes module (Final) ---------------------------------------------
DEFAULT_FUZZY_THRESHOLD: Final[float] = 0.85
DEFAULT_TIMESTAMP_TOLERANCE_SEC: Final[int] = 5
DEFAULT_CREATOR_BOOST_THRESHOLD: Final[float] = 0.8
DEFAULT_CREATOR_PENALTY_THRESHOLD: Final[float] = 0.4
DEFAULT_CREATOR_BOOST: Final[float] = 0.1
DEFAULT_CREATOR_PENALTY: Final[float] = 0.15


class ReportFormat(StrEnum):
    """Formats de rapport supportés par le CLI.

    Invariant : tout nom listé ici doit avoir une entrée dans
    ``tools.eval.reporters.REPORTERS`` (vérifié par tests).
    """

    CSV = "csv"
    MARKDOWN = "markdown"


@dataclass(frozen=True, slots=True)
class ExtractedReco:
    """Une reco extraite par un pipeline (LLM ou règles).

    Invariant : ``title`` est non-vide (sinon, c'est un bruit à filtrer en
    amont). ``timestamp`` accepte ``"HH:MM:SS"`` ou ``"MM:SS"`` ; le
    harness normalise.

    Frozen + slots → hashable, mémoire minimale, immuable.
    """

    title: str
    creator: str | None = None
    timestamp: str | None = None
    extra: Mapping[str, Any] = field(default_factory=lambda: MappingProxyType({}))

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ExtractedReco":
        """Construit un ``ExtractedReco`` depuis un dict tolérant."""
        title = str(data.get("title", "")).strip()
        if not title:
            raise ValueError("ExtractedReco: `title` requis et non-vide.")
        creator_raw = data.get("creator")
        ts_raw = data.get("timestamp")
        extras = {k: v for k, v in data.items()
                  if k not in ("title", "creator", "timestamp")}
        return cls(
            title=title,
            creator=str(creator_raw) if creator_raw is not None else None,
            timestamp=str(ts_raw) if ts_raw is not None else None,
            extra=MappingProxyType(extras),
        )


@dataclass(frozen=True, slots=True)
class EvalConfig:
    """Configuration figée d'un run d'évaluation.

    Tout paramètre numérique du harness passe par cet objet — pas de
    magic number ailleurs. Frozen → la config d'un run ne mute jamais.
    """

    fuzzy_threshold: float = DEFAULT_FUZZY_THRESHOLD
    timestamp_tolerance_sec: int = DEFAULT_TIMESTAMP_TOLERANCE_SEC
    creator_boost_threshold: float = DEFAULT_CREATOR_BOOST_THRESHOLD
    creator_penalty_threshold: float = DEFAULT_CREATOR_PENALTY_THRESHOLD
    creator_boost: float = DEFAULT_CREATOR_BOOST
    creator_penalty: float = DEFAULT_CREATOR_PENALTY

    def __post_init__(self) -> None:
        if not 0.0 < self.fuzzy_threshold <= 1.0:
            raise ValueError("fuzzy_threshold ∈ ]0, 1].")
        if self.timestamp_tolerance_sec < 0:
            raise ValueError("timestamp_tolerance_sec ≥ 0.")

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "EvalConfig":
        """Construit une ``EvalConfig`` depuis un dict (futur YAML/JSON)."""
        known = {
            "fuzzy_threshold", "timestamp_tolerance_sec",
            "creator_boost_threshold", "creator_penalty_threshold",
            "creator_boost", "creator_penalty",
        }
        kwargs: dict[str, Any] = {k: data[k] for k in known if k in data}
        return cls(**kwargs)


@dataclass(frozen=True, slots=True)
class EvalDetail:
    """Une ligne de détail = verdict pour une paire (expected, extracted).

    Invariant : ``verdict`` est une valeur de ``MatchVerdict``. ``score``
    ∈ [0, 1] ou None pour les buckets "missing"/"extra".
    """

    verdict: str
    expected_title: str | None = None
    matched_title: str | None = None
    score: float | None = None
    episode_guid: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Sérialise vers un dict (compat reporters existants)."""
        d: dict[str, Any] = {"verdict": self.verdict}
        if self.expected_title is not None:
            d["expected_title"] = self.expected_title
        if self.matched_title is not None:
            d["matched_title"] = self.matched_title
        if self.score is not None:
            d["score"] = self.score
        if self.episode_guid is not None:
            d["episode_guid"] = self.episode_guid
        return d


_EMPTY_MAP: Final[Mapping[str, Any]] = MappingProxyType({})


@dataclass(frozen=True, slots=True)
class EvalMetrics:
    """Agrégat de scores d'un run (frozen). Tous les Mapping sont figés."""

    n_expected: int
    n_extracted: int
    n_exact_match: int
    n_fuzzy_match: int
    n_missed: int
    n_spurious: int
    n_wrong_timestamp: int
    precision: float
    recall: float
    f1: float
    details: tuple[EvalDetail, ...] = ()
    per_episode: Mapping[str, "EvalMetrics"] = field(
        default_factory=lambda: MappingProxyType({}),
    )

    def __post_init__(self) -> None:
        # Re-wrap en MappingProxyType si un dict mutable est passé.
        if not isinstance(self.per_episode, MappingProxyType):
            object.__setattr__(
                self, "per_episode", MappingProxyType(dict(self.per_episode)),
            )

    def to_summary_dict(self) -> dict[str, Any]:
        """Dict des scores agrégés (pour manifest / log JSONL)."""
        return {
            "n_expected": self.n_expected,
            "n_extracted": self.n_extracted,
            "n_exact_match": self.n_exact_match,
            "n_fuzzy_match": self.n_fuzzy_match,
            "n_missed": self.n_missed,
            "n_spurious": self.n_spurious,
            "n_wrong_timestamp": self.n_wrong_timestamp,
            "precision": self.precision,
            "recall": self.recall,
            "f1": self.f1,
        }


@dataclass(frozen=True, slots=True)
class RunManifest:
    """Manifest persisté d'un run d'évaluation.

    Invariant : ``timestamp`` est ISO-8601 UTC, injecté (jamais
    ``datetime.now()`` au point d'usage — la déterminisme prime).
    """

    run_id: str
    timestamp: str
    git_sha: str
    config_hash: str
    golden_set_hash: str
    scores: Mapping[str, Any] = field(default_factory=lambda: MappingProxyType({}))
    sources: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.scores, MappingProxyType):
            object.__setattr__(
                self, "scores", MappingProxyType(dict(self.scores)),
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "timestamp": self.timestamp,
            "git_sha": self.git_sha,
            "config_hash": self.config_hash,
            "golden_set_hash": self.golden_set_hash,
            "scores": dict(self.scores),
            "sources": list(self.sources),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "RunManifest":
        return cls(
            run_id=str(data["run_id"]),
            timestamp=str(data["timestamp"]),
            git_sha=str(data.get("git_sha", "")),
            config_hash=str(data.get("config_hash", "")),
            golden_set_hash=str(data.get("golden_set_hash", "")),
            scores=MappingProxyType(dict(data.get("scores", {}))),
            sources=tuple(data.get("sources", ())),
        )

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, sort_keys=True,
                          indent=2)


@runtime_checkable
class ExtractionSource(Protocol):
    """Source d'extractions consommée par le harness.

    Abstraction du dataset extrait — découple le harness du format JSON
    (legacy dict, future DB, future API…).
    """

    def for_episode(self, episode_guid: str) -> Iterable[ExtractedReco]:
        """Itère sur les extractions associées à un ``episode_guid``."""
        ...

    def episode_guids(self) -> Iterable[str]:
        """Itère sur les guids couverts par la source."""
        ...


@runtime_checkable
class EvalReporter(Protocol):
    """Reporter d'un ``EvalMetrics`` vers un format texte cible."""

    def render(self, metrics: "EvalMetrics", *, title: str = ...) -> str:
        """Sérialise ``metrics`` en string."""
        ...

    def write(
        self,
        metrics: "EvalMetrics",
        path: str | Path,
        *,
        title: str = ...,
    ) -> Path:
        """Écrit le rapport à ``path``. Retourne le ``Path`` écrit."""
        ...
