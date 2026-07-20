"""extraction_history.py — Historique des extractions d'une reco.

Chaque reco peut être trouvée par plusieurs combinaisons
`(transcriptModel, transcriptSource, llmProvider, llmModel)` au fil du temps
(re-extractions, comparaisons multi-LLM, transcripts Acast puis YouTube, etc.).

Ce module stocke cet historique de façon dédupliquée et chronologique, et
expose des helpers purs pour dériver l'état d'affichage (timestamp, source)
à partir de cet historique.

Règles métier :
  - Entrée unique par signature `(transcriptModel, transcriptSource,
    llmProvider, llmModel)` — on met à jour `at` / `timestamp_at_extraction`
    plutôt que d'empiler des doublons.
  - Ordre chronologique strict (`at` croissant).
  - Drapeau de fiabilité (top-level `timestamp` / `transcriptSource`) =
    DERNIÈRE entrée YouTube, ou à défaut la plus récente entrée.
  - `extractors` est dérivé de l'historique : `sorted({e.llmProvider for ...})`.
  - Valeurs inconnues = chaîne literal `"(assumed)"` (jamais `None`).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Literal

ASSUMED = "(assumed)"

TranscriptSource = Literal["acast", "youtube"]
LlmProvider = Literal["anthropic", "openai"]


@dataclass(frozen=True)
class ExtractionEntry:
    """Une trace d'extraction unique pour une reco.

    `at` : ISO datetime de l'extraction (UTC).
    `timestamp_at_extraction` : horodatage « HH:MM:SS » trouvé par le LLM
      dans cette extraction (peut différer entre extractions si la
      transcription a évolué).
    """

    at: str
    transcriptModel: str
    transcriptSource: TranscriptSource
    llmProvider: LlmProvider
    llmModel: str
    worker: str
    timestamp_at_extraction: str

    def signature(self) -> tuple:
        """Clé de dédup : ce qui rend une extraction *unique*."""
        return (
            self.transcriptModel,
            self.transcriptSource,
            self.llmProvider,
            self.llmModel,
        )


def to_dict(entry: ExtractionEntry) -> dict:
    """Sérialise une entry vers un dict JSON-friendly."""
    return asdict(entry)


def from_dict(d: dict) -> ExtractionEntry:
    """Désérialise un dict vers une `ExtractionEntry`.

    Tolère les anciens snapshots où certains champs manquent : on retombe
    sur `"(assumed)"`.
    """
    return ExtractionEntry(
        at=d["at"],
        transcriptModel=d.get("transcriptModel") or ASSUMED,
        transcriptSource=d.get("transcriptSource") or "acast",
        llmProvider=d.get("llmProvider") or "anthropic",
        llmModel=d.get("llmModel") or ASSUMED,
        worker=d.get("worker") or ASSUMED,
        timestamp_at_extraction=d.get("timestamp_at_extraction") or "00:00:00",
    )


def merge_history(
    existing: list[ExtractionEntry], new: ExtractionEntry
) -> list[ExtractionEntry]:
    """Insère `new` dans `existing` (dédup par signature, tri par `at`).

    Si la signature existe déjà :
      - si `new.at` >= existing.at → on remplace `at` ET `timestamp_at_extraction`
        par les valeurs de `new` (la dernière extraction prime ; égalité = on
        considère que la nouvelle est au moins aussi à jour, utile quand
        l'horodatage est tronqué à la seconde).
      - sinon → on conserve l'entrée existante (extraction plus ancienne).
    Sinon, on ajoute. Toujours retrie par `at` croissant.
    """
    sig = new.signature()
    merged: list[ExtractionEntry] = []
    found = False
    for entry in existing:
        if entry.signature() == sig:
            found = True
            if new.at >= entry.at:
                # Met à jour at + timestamp_at_extraction (priorité au plus récent).
                merged.append(
                    ExtractionEntry(
                        at=new.at,
                        transcriptModel=entry.transcriptModel,
                        transcriptSource=entry.transcriptSource,
                        llmProvider=entry.llmProvider,
                        llmModel=entry.llmModel,
                        worker=new.worker,
                        timestamp_at_extraction=new.timestamp_at_extraction,
                    )
                )
            else:
                merged.append(entry)
        else:
            merged.append(entry)
    if not found:
        merged.append(new)
    merged.sort(key=lambda e: e.at)
    return merged


def derive_extractors(history: list[ExtractionEntry]) -> list[str]:
    """Retourne la liste triée des providers présents dans l'historique."""
    return sorted({e.llmProvider for e in history})


def pick_latest_yt(history: list[ExtractionEntry]) -> ExtractionEntry | None:
    """Renvoie la plus récente entrée YouTube, ou None si aucune."""
    yt_entries = [e for e in history if e.transcriptSource == "youtube"]
    if not yt_entries:
        return None
    return max(yt_entries, key=lambda e: e.at)


def pick_display_state(history: list[ExtractionEntry]) -> dict:
    """Calcule le `(timestamp, transcriptSource)` à exposer au top-level.

    Règle : YouTube fait toujours autorité (intro YT). On prend la plus
    récente entrée YT si elle existe, sinon la plus récente entrée tout
    court (équivalent à `history[-1]` puisque l'historique est trié).
    """
    if not history:
        return {"timestamp": "00:00:00", "transcriptSource": "acast"}
    yt = pick_latest_yt(history)
    chosen = yt if yt is not None else history[-1]
    return {
        "timestamp": chosen.timestamp_at_extraction,
        "transcriptSource": chosen.transcriptSource,
    }
