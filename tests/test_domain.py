"""Tests des entités du domaine (tools/domain.py).

Les dataclasses sont passives : on vérifie surtout qu'on peut les instancier
avec les valeurs par défaut (essentiel pour un futur refactor vers usecase
classes qui dépendront de ces dataclasses).
"""
from __future__ import annotations

from domain import Episode, Reco, Source, TranscriptSegment


def test_source_minimal_fields():
    s = Source(id="un-bon-moment", title="Un Bon Moment")
    assert s.id == "un-bon-moment"
    assert s.title == "Un Bon Moment"
    assert s.rss_url is None
    assert s.hosts == []  # default_factory
    assert s.theme == {}


def test_source_full_fields():
    s = Source(
        id="ubm", title="UBM",
        rss_url="https://feed.example",
        youtube_channel="https://yt.example",
        hosts=["Alice", "Bob"],
        theme={"accent": "#ff6b35"},
    )
    assert s.hosts == ["Alice", "Bob"]
    assert s.theme["accent"] == "#ff6b35"


def test_episode_minimal_fields():
    e = Episode(guid="abc", source_id="ubm", title="Titre")
    assert e.guid == "abc"
    assert e.audio_duration is None
    assert e.season is None
    assert e.number is None
    assert e.status == "active"


def test_episode_all_fields():
    e = Episode(
        guid="abc", source_id="ubm", title="t",
        audio_url="https://a", audio_duration=3600,
        youtube_url="https://y", youtube_title="yt", youtube_duration=3700,
        season=5, number=32,
        status="discarded",
    )
    assert e.season == 5 and e.number == 32
    assert e.status == "discarded"


def test_reco_default_status_is_draft():
    r = Reco(id="ubm-001", source_id="ubm", episode_guid="abc",
             title="Mortel", types=["serie"])
    assert r.status == "draft"
    assert r.recommended_by is None
    assert r.extractors == []


def test_reco_recommended_by_accepts_string():
    r = Reco(id="ubm-001", source_id="ubm", episode_guid="abc",
             title="Mortel", types=["serie"], recommended_by="Kyan")
    assert r.recommended_by == "Kyan"


def test_reco_types_cover_all_content_kinds():
    """Couvre les types nouveaux pour rester synchronisés avec content.config.ts."""
    for t in ("bd", "album", "spectacle", "lieu", "artiste", "video"):
        r = Reco(id="x", source_id="s", episode_guid="g", title="T", types=[t])
        assert r.types == [t]


def test_reco_supports_multiple_types():
    """Une reco peut porter plusieurs types (livre ET film par ex.)."""
    r = Reco(id="x", source_id="s", episode_guid="g", title="Dune",
             types=["livre", "film"])
    assert r.types == ["livre", "film"]


def test_reco_with_extractors():
    r = Reco(id="ubm-001", source_id="ubm", episode_guid="abc",
             title="Mortel", types=["serie"],
             extractors=["anthropic", "openai"])
    assert len(r.extractors) == 2


def test_transcript_segment_immutable():
    """TranscriptSegment est frozen (immuable) — important pour les caches."""
    seg = TranscriptSegment(start_seconds=42, text="bonjour")
    assert seg.start_seconds == 42
    # frozen=True interdit l'assignation après création
    import dataclasses
    try:
        seg.start_seconds = 99  # type: ignore[misc]
        assert False, "TranscriptSegment devrait être frozen"
    except dataclasses.FrozenInstanceError:
        pass  # comportement attendu
