"""Tests de `tools/traiter_nouveaux_episodes.py` — la chaîne automatique sur venus.

Transcription, extraction, client d'API et verrou sont des doubles : aucun
modèle ne tourne, aucun appel n'est facturé.
"""
from __future__ import annotations

import contextlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

import traiter_nouveaux_episodes as tne

SOURCE = "demo-source"


@pytest.fixture
def content(tmp_path, monkeypatch):
    import common

    for name, sub in (("SOURCES_DIR", "sources"), ("EPISODES_DIR", "episodes"),
                      ("OUTPUT_DIR", "output"), ("TRANSCRIPTS_DIR", "output/transcripts"),
                      ("AUDIO_DIR", "output/audio")):
        monkeypatch.setattr(common, name, tmp_path / sub)
    (tmp_path / "sources").mkdir()
    (tmp_path / "episodes" / SOURCE).mkdir(parents=True)
    (tmp_path / "sources" / f"{SOURCE}.json").write_text(
        json.dumps({"id": SOURCE, "title": "Démo", "hosts": ["A"]}), encoding="utf-8")
    return tmp_path


def _episode(root: Path, guid: str, status: str = "none", transcript: bool = False) -> Path:
    import common

    path = root / "episodes" / SOURCE / f"{common.slugify(guid)}.json"
    path.write_text(json.dumps({"sourceId": SOURCE, "guid": guid, "title": f"Titre {guid}",
                                "transcriptStatus": status}), encoding="utf-8")
    if transcript:
        t = common.transcript_path_for(SOURCE, guid)
        t.parent.mkdir(parents=True, exist_ok=True)
        t.write_text("[00:00:01] bonjour\n", encoding="utf-8")
    return path


class Inbox(list):
    def __call__(self, text: str) -> None:
        self.append(text)


@pytest.fixture
def inbox():
    return Inbox()


def _no_lock():
    return contextlib.nullcontext()


def _sans_precision(*_a, **_k):
    """La réécoute des citations ne trouve rien à corriger."""
    return SimpleNamespace(precisees=[])


# ===== detecter ==============================================================
def test_detecter_announces_new_episodes_and_unrecognized_videos(content, inbox):
    _episode(content, "yt-new")
    result = SimpleNamespace(created=["yt-new"],
                             unrecognized=[{"id": "clip", "title": "Un extrait"}])

    assert tne.detecter(SOURCE, inbox, fetch=lambda _s: result) == 0

    assert "Nouvel épisode détecté : Titre yt-new" in inbox[0]
    assert "« Un extrait »" in inbox[1] and "watch?v=clip" in inbox[1]


# ===== transcrire ============================================================
def test_transcrire_only_touches_youtube_episodes_not_yet_transcribed(content, inbox):
    _episode(content, "yt-todo")
    _episode(content, "yt-done", status="auto")
    _episode(content, "6a47e41c08da", status="none")  # épisode Acast : jamais
    calls = []

    tne.transcrire(SOURCE, inbox, tne.load_state(SOURCE),
                   transcriber=lambda s, p, m, lang, force, amorce:
                   calls.append((p.name, m, lang, amorce)))

    assert calls == [("yt-todo.json", "large-v3-turbo", "fr",
                      "Bonjour et bienvenue dans Démo, avec A. Aujourd'hui : Titre yt-todo.")]


def test_audio_is_removed_once_transcribed(content, inbox):
    import common

    _episode(content, "yt-todo")
    audio = common.AUDIO_DIR / SOURCE / "yt-todo-yt.m4a"
    audio.parent.mkdir(parents=True)
    audio.write_bytes(b"x")

    tne.transcrire(SOURCE, inbox, tne.load_state(SOURCE), transcriber=lambda *a, **k: None)

    assert not audio.exists()


def test_a_lasting_transcription_failure_is_reported_once(content, inbox):
    _episode(content, "yt-todo")
    state = tne.load_state(SOURCE)

    def broken(*_args, **_kwargs):
        raise RuntimeError("yt-dlp : Sign in to confirm")

    tne.transcrire(SOURCE, inbox, state, transcriber=broken)
    tne.transcrire(SOURCE, inbox, state, transcriber=broken)
    assert len(inbox) == 1 and "Sign in to confirm" in inbox[0]

    tne.transcrire(SOURCE, inbox, state, transcriber=lambda *a, **k: None)
    assert state["lastErrors"] == {}


def test_the_amorce_uses_the_hosts_and_the_episode_title_without_its_suffix():
    source = {"title": "Un Bon Moment", "hosts": ["Kyan Khojandi", "Navo"],
              "youtubeTitleSuffixPatterns": ["un bon moment"]}
    episode = {"guid": "yt-1", "title": "Orelsan, le boss final (Un Bon Moment, S6-E1)"}

    assert tne.amorce_pour(source, episode) == (
        "Bonjour et bienvenue dans Un Bon Moment, avec Kyan Khojandi, Navo. "
        "Aujourd'hui : Orelsan, le boss final.")


# ===== a-extraire / extraire =================================================
def test_only_transcribed_youtube_episodes_not_yet_extracted_are_pending(content):
    _episode(content, "yt-ready", status="auto", transcript=True)
    _episode(content, "yt-no-file", status="auto")
    _episode(content, "yt-waiting")
    _episode(content, "yt-already", status="auto", transcript=True)
    _episode(content, "acast-old", status="auto", transcript=True)
    state = {"extracted": ["yt-already"], "lastErrors": {}}

    pending = tne.a_extraire(SOURCE, state)

    assert [ep["guid"] for _, ep in pending] == ["yt-ready"]


def test_extraire_marks_the_episode_and_sends_the_validation_link(content, inbox):
    _episode(content, "yt--abc", status="auto", transcript=True)
    state = tne.load_state(SOURCE)
    seen = []

    def extractor(source_id, path, client, dry_run, *, model, source):
        seen.append((path.name, client, dry_run, model, source["title"]))
        return 7

    rc = tne.extraire(SOURCE, inbox, state, review_url="http://10.8.0.1:8000/",
                      client_factory=lambda: "client", extractor=extractor,
                      lock=_no_lock, model="claude-test", preciseur=_sans_precision)

    assert rc == 0
    assert seen == [("yt-abc.json", "client", False, "claude-test", "Démo")]
    assert state["extracted"] == ["yt--abc"]
    assert inbox == [("✅ Titre yt--abc : 7 reco(s) à valider.\n"
                      "http://10.8.0.1:8000/ep?guid=yt--abc")]

    tne.extraire(SOURCE, inbox, state, review_url="u", client_factory=lambda: "client",
                 extractor=extractor, lock=_no_lock, model="m", preciseur=_sans_precision)
    assert len(seen) == 1  # jamais ré-extrait, donc jamais refacturé


def test_precised_quotes_are_announced_and_the_audio_is_dropped(content, inbox):
    import common

    _episode(content, "yt-ready", status="auto", transcript=True)
    audio = common.AUDIO_DIR / SOURCE / "yt-ready-yt.m4a"
    audio.parent.mkdir(parents=True)
    audio.write_bytes(b"x")
    vues = []

    def preciseur(source_id, guid, *, apply):
        vues.append((guid, apply))
        return SimpleNamespace(precisees=[object(), object()])

    tne.extraire(SOURCE, inbox, tne.load_state(SOURCE), review_url="u",
                 client_factory=lambda: "c", extractor=lambda *a, **k: 4,
                 lock=_no_lock, model="m", preciseur=preciseur)

    assert vues == [("yt-ready", True)]
    assert "2 citation(s) précisée(s)" in inbox[0]
    assert not audio.exists()


def test_a_failing_quote_pass_does_not_lose_the_episode(content, inbox):
    _episode(content, "yt-ready", status="auto", transcript=True)

    def preciseur(*_a, **_k):
        raise RuntimeError("audio introuvable")

    state = tne.load_state(SOURCE)
    tne.extraire(SOURCE, inbox, state, review_url="u", client_factory=lambda: "c",
                 extractor=lambda *a, **k: 4, lock=_no_lock, model="m", preciseur=preciseur)

    assert state["extracted"] == ["yt-ready"]
    assert "4 reco(s) à valider" in inbox[0] and "citation" not in inbox[0]


def test_an_invalid_api_key_is_reported_once_and_nothing_is_marked(content, inbox):
    _episode(content, "yt-ready", status="auto", transcript=True)
    state = tne.load_state(SOURCE)

    def refused():
        raise RuntimeError("401 invalid x-api-key")

    for _ in range(2):
        assert tne.extraire(SOURCE, inbox, state, review_url="u", client_factory=refused,
                            extractor=lambda *a, **k: 0, lock=_no_lock, model="m") == 1

    assert len(inbox) == 1 and "401" in inbox[0]
    assert state["extracted"] == []


def test_a_failing_episode_does_not_block_the_next_one(content, inbox):
    _episode(content, "yt-a", status="auto", transcript=True)
    _episode(content, "yt-b", status="auto", transcript=True)
    state = tne.load_state(SOURCE)

    def extractor(source_id, path, *_a, **_k):
        if path.name == "yt-a.json":
            raise RuntimeError("500 overloaded")
        return 3

    tne.extraire(SOURCE, inbox, state, review_url="u", client_factory=lambda: "c",
                 extractor=extractor, lock=_no_lock, model="m", preciseur=_sans_precision)

    assert state["extracted"] == ["yt-b"]
    assert "overloaded" in inbox[0] and "3 reco(s)" in inbox[1]


def test_extraction_waits_when_the_review_server_holds_the_lock(content, inbox):
    from review_lock import ServerLockBusy

    _episode(content, "yt-ready", status="auto", transcript=True)
    state = tne.load_state(SOURCE)

    @contextlib.contextmanager
    def busy():
        raise ServerLockBusy("review_server actif")
        yield  # pragma: no cover

    rc = tne.extraire(SOURCE, inbox, state, review_url="u", client_factory=lambda: "c",
                      extractor=lambda *a, **k: 1, lock=busy, model="m")

    assert rc == 1 and state["extracted"] == []
    assert "verrou" in inbox[0]


# ===== CLI ===================================================================
def test_a_extraire_exit_code_drives_the_host_script(content):
    assert tne.main(["a-extraire", "--source", SOURCE]) == 1
    _episode(content, "yt-ready", status="auto", transcript=True)
    assert tne.main(["a-extraire", "--source", SOURCE]) == 0


def test_state_survives_between_steps(content, monkeypatch):
    _episode(content, "yt-todo")

    def broken(*_a, **_k):
        raise RuntimeError("panne")

    monkeypatch.setattr(tne, "build_notify", lambda _c: lambda _t: None)
    monkeypatch.setattr("transcribe.transcribe_episode", broken)

    tne.main(["transcrire", "--source", SOURCE, "--notify", "none"])

    saved = json.loads(tne.state_path(SOURCE).read_text(encoding="utf-8"))
    assert "transcription:yt-todo" in saved["lastErrors"]
