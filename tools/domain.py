"""
domain.py — Entités du domaine et ports (Clean Architecture).

Ce module est le **cœur métier indépendant** du pipeline Reco. Il sert
aujourd'hui de **référence type / documentation vivante** des objets
métier (Source, Episode, Reco, TranscriptSegment) et des interfaces
attendues (les `Protocol` sont des **ports** au sens hexagonal — ils
balisent l'évolution future vers des use cases et adaptateurs séparés).

Le pipeline actuel manipule directement des `dict` JSON (cf. `common.py`)
et n'instancie pas (encore) ces dataclasses : elles servent de contrat
documenté, et les `RecoType` / `RecoStatus` sont l'unique source de
vérité côté Python pour les valeurs admises (à garder synchronisée avec
`src/content.config.ts`).

Principes appliqués :
  - **Single Responsibility** : chaque dataclass = une entité, chaque
    Protocol = un port (une intention claire).
  - **Open/Closed** : on ajoute un podcast en créant une `Source` +
    un adaptateur pour son flux — pas en modifiant le coeur.
  - **Dependency Inversion** : les futurs use cases dépendront de ces
    Protocols, pas d'implémentations concrètes (Anthropic, OpenAI,
    yt-dlp, requests…).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Literal, Protocol


# ===== Entités ==============================================================
# Synchronisé avec `src/content.config.ts` (z.enum `recoType`).
RecoStatus = Literal["draft", "validated", "discarded"]
RecoType = Literal[
    "film", "serie", "livre", "bd",
    "musique", "album", "podcast", "jeu",
    "spectacle", "lieu", "artiste", "video", "autre",
]


@dataclass
class Source:
    """Un podcast (= une « source »). Multi-podcast = plusieurs Source."""
    id: str                       # slug stable, ex. "un-bon-moment"
    title: str
    rss_url: str | None = None
    youtube_channel: str | None = None
    website: str | None = None
    hosts: list[str] = field(default_factory=list)
    theme: dict = field(default_factory=dict)


@dataclass
class Episode:
    """Un épisode de podcast. `guid` = clé unique stable (issue du RSS)."""
    guid: str
    source_id: str
    title: str
    audio_url: str | None = None
    audio_duration: int | None = None        # secondes
    youtube_url: str | None = None
    youtube_title: str | None = None
    youtube_duration: int | None = None       # secondes
    season: int | None = None                  # ex. saison 5 du podcast
    number: int | None = None                  # ex. épisode 42
    status: str = "active"                     # active | discarded


@dataclass
class Reco:
    """Une recommandation extraite d'un transcript."""
    id: str                                    # ex. "ubm-0001"
    source_id: str
    episode_guid: str
    title: str
    type: RecoType
    creator: str | None = None
    timestamp: str | None = None               # HH:MM:SS dans le transcript
    quote: str | None = None
    recommended_by: str | None = None          # nom (cf. `recommendedBy` côté JSON)
    status: RecoStatus = "draft"
    extractors: list[str] = field(default_factory=list)  # LLMs qui l'ont trouvée


@dataclass(frozen=True)
class TranscriptSegment:
    """Un segment de transcription (timecode + texte)."""
    start_seconds: int
    text: str


# ===== Ports (interfaces) ===================================================
class EpisodeRepository(Protocol):
    """Lit / écrit des Episode (persistence agnostique)."""
    def list_all(self, source_id: str) -> list[Episode]: ...
    def get(self, source_id: str, guid: str) -> Episode | None: ...
    def upsert(self, ep: Episode) -> bool: ...
    def delete(self, source_id: str, guid: str) -> bool: ...


class RecoRepository(Protocol):
    """Lit / écrit des Reco."""
    def list_for_episode(self, source_id: str, episode_guid: str) -> list[Reco]: ...
    def list_all(self, source_id: str) -> list[Reco]: ...
    def upsert(self, reco: Reco) -> bool: ...
    def delete(self, reco_id: str) -> bool: ...


class TranscriptStore(Protocol):
    """Lit / écrit des transcriptions (texte avec timecodes)."""
    def load(self, source_id: str, guid: str) -> list[TranscriptSegment]: ...
    def save(self, source_id: str, guid: str, segments: Iterable[TranscriptSegment]) -> None: ...
    def exists(self, source_id: str, guid: str) -> bool: ...
    def path(self, source_id: str, guid: str) -> Path: ...


class RSSClient(Protocol):
    """Récupère la liste des épisodes depuis un flux RSS de podcast."""
    def fetch_episodes(self, rss_url: str, source_id: str) -> list[Episode]: ...


class YouTubeClient(Protocol):
    """Accès lecture seule à une chaîne YouTube + ses miniatures + audio."""
    def list_channel_videos(self, channel_url: str) -> list[dict]: ...
    def get_video_id(self, url: str) -> str | None: ...
    def download_thumbnail(self, video_id: str) -> bytes | None: ...
    def download_audio(self, video_url: str, dest: Path) -> Path: ...


class TranscriberEngine(Protocol):
    """Convertit un fichier audio (wav 16k mono) en segments avec timecodes."""
    def transcribe(self, wav_path: Path, language: str = "fr") -> list[TranscriptSegment]: ...


class LLMExtractor(Protocol):
    """Extrait des recommandations depuis un transcript en utilisant un LLM."""
    name: str                                  # ex. "anthropic", "openai"
    def extract(self, episode: Episode, segments: list[TranscriptSegment]) -> list[Reco]: ...


class VisionOCR(Protocol):
    """OCR d'image → numéro d'épisode (utilisé sur les miniatures YouTube)."""
    def read_episode_number(self, image_jpeg: bytes) -> int | None: ...


__all__ = [
    "Source", "Episode", "Reco", "TranscriptSegment",
    "RecoStatus", "RecoType",
    "EpisodeRepository", "RecoRepository", "TranscriptStore",
    "RSSClient", "YouTubeClient", "TranscriberEngine", "LLMExtractor", "VisionOCR",
]
