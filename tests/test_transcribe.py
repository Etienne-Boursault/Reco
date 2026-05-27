"""Tests de transcribe.py.

Aucun appel réseau réel : faster_whisper, yt_dlp et requests sont mockés.
"""
from __future__ import annotations

import json
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import responses

import transcribe as tr


# ===== Helpers purs =========================================================
@pytest.mark.parametrize(
    "secs,expected",
    [
        (0, "00:00:00"),
        (59, "00:00:59"),
        (3723, "01:02:03"),
        (3723.9, "01:02:03"),
    ],
)
def test_format_timestamp(secs, expected):
    assert tr._format_timestamp(secs) == expected


# ===== _download_http =======================================================
@responses.activate
def test_download_http_writes_file(tmp_path):
    url = "https://cdn.example.com/audio.mp3"
    responses.add(responses.GET, url, body=b"ABCDEF" * 100, status=200,
                  content_type="audio/mpeg")
    dest = tmp_path / "out.mp3"
    result = tr._download_http(url, dest)
    assert result == dest
    assert dest.exists()
    assert dest.read_bytes() == b"ABCDEF" * 100
    # Le fichier temporaire .part doit avoir été renommé
    assert not (tmp_path / "out.mp3.part").exists()


@responses.activate
def test_download_http_skip_if_cached(tmp_path):
    dest = tmp_path / "cached.mp3"
    dest.write_bytes("déjà là".encode("utf-8"))
    # Pas de mock responses ajouté : si requests.get était appelé, ça lèverait.
    result = tr._download_http("https://example.com/x.mp3", dest)
    assert result == dest
    assert dest.read_bytes() == "déjà là".encode("utf-8")


@responses.activate
def test_download_http_redownloads_if_empty(tmp_path):
    dest = tmp_path / "empty.mp3"
    dest.write_bytes(b"")  # fichier vide -> on retéléchage
    url = "https://example.com/x.mp3"
    responses.add(responses.GET, url, body=b"ok", status=200)
    tr._download_http(url, dest)
    assert dest.read_bytes() == b"ok"


@responses.activate
def test_download_http_raises_on_http_error(tmp_path):
    url = "https://example.com/missing.mp3"
    responses.add(responses.GET, url, status=404)
    with pytest.raises(Exception):
        tr._download_http(url, tmp_path / "x.mp3")


# ===== _download_youtube ====================================================
def test_download_youtube_returns_mp3(tmp_path, monkeypatch):
    """Mocke yt_dlp.YoutubeDL : sa méthode .download() crée le fichier mp3."""
    dest_base = tmp_path / "video"

    class FakeYDL:
        def __init__(self, opts):
            self.opts = opts

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def download(self, urls):
            # Crée le fichier mp3 attendu
            (dest_base.with_suffix(".mp3")).write_bytes(b"fake-audio")

    fake_mod = types.ModuleType("yt_dlp")
    fake_mod.YoutubeDL = FakeYDL
    monkeypatch.setitem(sys.modules, "yt_dlp", fake_mod)

    result = tr._download_youtube("https://yt/v=x", dest_base)
    assert result == dest_base.with_suffix(".mp3")
    assert result.exists()


def test_download_youtube_fallback_to_other_extension(tmp_path, monkeypatch):
    """yt-dlp produit un m4a au lieu d'un mp3 : on prend ce qu'il y a."""
    dest_base = tmp_path / "video"

    class FakeYDL:
        def __init__(self, opts):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def download(self, urls):
            (dest_base.with_suffix(".m4a")).write_bytes(b"fake")

    fake_mod = types.ModuleType("yt_dlp")
    fake_mod.YoutubeDL = FakeYDL
    monkeypatch.setitem(sys.modules, "yt_dlp", fake_mod)

    result = tr._download_youtube("https://yt/v=x", dest_base)
    assert result.suffix == ".m4a"


def test_download_youtube_raises_when_nothing_produced(tmp_path, monkeypatch):
    dest_base = tmp_path / "video"

    class FakeYDL:
        def __init__(self, opts):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def download(self, urls):
            pass  # ne crée rien

    fake_mod = types.ModuleType("yt_dlp")
    fake_mod.YoutubeDL = FakeYDL
    monkeypatch.setitem(sys.modules, "yt_dlp", fake_mod)

    with pytest.raises(RuntimeError, match="aucun fichier"):
        tr._download_youtube("https://yt/v=x", dest_base)


# ===== _resolve_audio =======================================================
@responses.activate
def test_resolve_audio_http(tmp_path, monkeypatch):
    monkeypatch.setattr(tr, "AUDIO_DIR", tmp_path)
    url = "https://acast.example.com/ep.mp3?token=abc"
    responses.add(responses.GET, url, body=b"audio", status=200)
    ep = {"guid": "G", "audioUrl": url}
    out = tr._resolve_audio("src", ep)
    assert out.suffix == ".mp3"
    assert out.read_bytes() == b"audio"


def test_resolve_audio_youtube_when_no_http(tmp_path, monkeypatch):
    monkeypatch.setattr(tr, "AUDIO_DIR", tmp_path)
    called = {}

    def fake_download_yt(url, dest_base):
        called["url"] = url
        called["dest"] = dest_base
        path = dest_base.with_suffix(".mp3")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"x")
        return path

    monkeypatch.setattr(tr, "_download_youtube", fake_download_yt)
    ep = {"guid": "G", "youtubeUrl": "https://yt/x"}
    out = tr._resolve_audio("src", ep)
    assert called["url"] == "https://yt/x"
    assert out.exists()


def test_resolve_audio_prefer_youtube(tmp_path, monkeypatch):
    monkeypatch.setattr(tr, "AUDIO_DIR", tmp_path)
    called = {}

    def fake_download_yt(url, dest_base):
        called["dest"] = dest_base
        # Le nom doit comporter "-yt" pour ne pas écraser le cache Acast.
        assert dest_base.name.endswith("-yt")
        path = dest_base.with_suffix(".mp3")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"x")
        return path

    monkeypatch.setattr(tr, "_download_youtube", fake_download_yt)
    ep = {"guid": "G", "audioUrl": "https://acast/x.mp3", "youtubeUrl": "https://yt/x"}
    out = tr._resolve_audio("src", ep, prefer_youtube=True)
    assert called["dest"].name.endswith("-yt")


def test_resolve_audio_no_url_raises(tmp_path, monkeypatch):
    monkeypatch.setattr(tr, "AUDIO_DIR", tmp_path)
    with pytest.raises(ValueError, match="ni audioUrl ni youtubeUrl"):
        tr._resolve_audio("src", {"guid": "G"})


# ===== _transcribe_audio ====================================================
def _install_fake_whisper(monkeypatch, segments=None, language="fr", proba=0.99):
    """Installe un module faux faster_whisper avec un WhisperModel mocké."""
    segs = segments or [
        types.SimpleNamespace(start=0.0, end=2.0, text=" Bonjour "),
        types.SimpleNamespace(start=2.5, end=5.0, text=" tout le monde."),
    ]

    class FakeModel:
        def __init__(self, name, device=None, compute_type=None):
            self.name = name

        def transcribe(self, path, language=None, vad_filter=False, beam_size=5):
            info = types.SimpleNamespace(language=language or "fr",
                                         language_probability=proba)
            return iter(segs), info

    fake_mod = types.ModuleType("faster_whisper")
    fake_mod.WhisperModel = FakeModel
    monkeypatch.setitem(sys.modules, "faster_whisper", fake_mod)


def test_transcribe_audio_formats_lines(tmp_path, monkeypatch):
    _install_fake_whisper(monkeypatch)
    audio = tmp_path / "a.mp3"
    audio.write_bytes(b"")
    text = tr._transcribe_audio(audio, "small", "fr")
    lines = text.strip().split("\n")
    assert lines[0] == "[00:00:00] Bonjour"
    assert lines[1] == "[00:00:02] tout le monde."
    assert text.endswith("\n")


# ===== transcribe_episode ===================================================
@pytest.fixture
def ep_setup(tmp_path, monkeypatch):
    """Prépare une arbo avec un épisode JSON + chemins redirigés."""
    import common

    src = "demo"
    episodes_dir = tmp_path / "episodes" / src
    transcripts_dir = tmp_path / "transcripts"
    audio_dir = tmp_path / "audio"
    episodes_dir.mkdir(parents=True)
    transcripts_dir.mkdir(parents=True)
    audio_dir.mkdir(parents=True)

    monkeypatch.setattr(common, "EPISODES_DIR", tmp_path / "episodes")
    monkeypatch.setattr(common, "TRANSCRIPTS_DIR", transcripts_dir)
    monkeypatch.setattr(common, "AUDIO_DIR", audio_dir)
    monkeypatch.setattr(tr, "AUDIO_DIR", audio_dir)

    ep_data = {
        "guid": "ep-1",
        "title": "Titre",
        "audioUrl": "https://cdn.test/a.mp3",
        "transcriptStatus": "none",
    }
    ep_path = episodes_dir / "ep-1.json"
    ep_path.write_text(json.dumps(ep_data), encoding="utf-8")
    return {
        "src": src,
        "ep_path": ep_path,
        "transcripts_dir": transcripts_dir,
        "audio_dir": audio_dir,
    }


@responses.activate
def test_transcribe_episode_full_flow(ep_setup, monkeypatch):
    _install_fake_whisper(monkeypatch)
    responses.add(responses.GET, "https://cdn.test/a.mp3", body=b"audio", status=200)

    produced = tr.transcribe_episode(ep_setup["src"], ep_setup["ep_path"],
                                     "small", "fr", force=False)
    assert produced is True
    # La transcription est écrite
    tpath = ep_setup["transcripts_dir"] / ep_setup["src"] / "ep-1.txt"
    assert tpath.exists()
    assert "Bonjour" in tpath.read_text(encoding="utf-8")
    # Le JSON de l'épisode est mis à jour
    data = json.loads(ep_setup["ep_path"].read_text(encoding="utf-8"))
    assert data["transcriptStatus"] == "auto"


def test_transcribe_episode_cached_skip(ep_setup, monkeypatch):
    """Si la transcription existe déjà et que force=False, on ne retranscrit pas."""
    # Pré-écrire la transcription
    tpath = ep_setup["transcripts_dir"] / ep_setup["src"] / "ep-1.txt"
    tpath.parent.mkdir(parents=True, exist_ok=True)
    tpath.write_text("vieux contenu", encoding="utf-8")

    # _transcribe_audio NE doit PAS être appelé
    sentinel = MagicMock(side_effect=AssertionError("ne doit pas être appelé"))
    monkeypatch.setattr(tr, "_transcribe_audio", sentinel)

    produced = tr.transcribe_episode(ep_setup["src"], ep_setup["ep_path"],
                                     "small", "fr", force=False)
    assert produced is False
    # Le statut "none" est passé à "auto"
    data = json.loads(ep_setup["ep_path"].read_text(encoding="utf-8"))
    assert data["transcriptStatus"] == "auto"


def test_transcribe_episode_force_retranscribes(ep_setup, monkeypatch):
    """force=True : on retranscrit même si le cache existe."""
    tpath = ep_setup["transcripts_dir"] / ep_setup["src"] / "ep-1.txt"
    tpath.parent.mkdir(parents=True, exist_ok=True)
    tpath.write_text("vieux", encoding="utf-8")

    monkeypatch.setattr(tr, "_resolve_audio",
                        lambda src, ep, prefer_youtube=False: Path("ignore"))
    monkeypatch.setattr(tr, "_transcribe_audio",
                        lambda audio, model, lang: "[00:00:00] nouveau\n")

    produced = tr.transcribe_episode(ep_setup["src"], ep_setup["ep_path"],
                                     "small", "fr", force=True)
    assert produced is True
    assert tpath.read_text(encoding="utf-8") == "[00:00:00] nouveau\n"


def test_transcribe_episode_preserves_validated_status(ep_setup, monkeypatch):
    """Un statut « validated » ne doit pas être régressé à « auto »."""
    data = json.loads(ep_setup["ep_path"].read_text(encoding="utf-8"))
    data["transcriptStatus"] = "validated"
    ep_setup["ep_path"].write_text(json.dumps(data), encoding="utf-8")

    monkeypatch.setattr(tr, "_resolve_audio",
                        lambda src, ep, prefer_youtube=False: Path("ignore"))
    monkeypatch.setattr(tr, "_transcribe_audio",
                        lambda audio, model, lang: "[00:00:00] x\n")

    tr.transcribe_episode(ep_setup["src"], ep_setup["ep_path"], "small", "fr", force=False)
    data = json.loads(ep_setup["ep_path"].read_text(encoding="utf-8"))
    assert data["transcriptStatus"] == "validated"


# ===== _find_episode_by_guid ================================================
def test_find_episode_by_guid_found(ep_setup):
    p = tr._find_episode_by_guid(ep_setup["src"], "ep-1")
    assert p == ep_setup["ep_path"]


def test_find_episode_by_guid_missing(ep_setup):
    with pytest.raises(FileNotFoundError, match="Aucun épisode"):
        tr._find_episode_by_guid(ep_setup["src"], "inconnu")


# ===== main =================================================================
def test_main_guid_mode(ep_setup, monkeypatch):
    called = {}

    def fake_transcribe(src, path, model, lang, force, yt):
        called.update(src=src, path=path, model=model, lang=lang, force=force, yt=yt)

    monkeypatch.setattr(tr, "transcribe_episode", fake_transcribe)
    monkeypatch.setattr(sys, "argv", [
        "transcribe.py", "--source", ep_setup["src"], "--guid", "ep-1",
        "--model", "tiny", "--language", "fr",
    ])
    tr.main()
    assert called["src"] == ep_setup["src"]
    assert called["model"] == "tiny"
    assert called["lang"] == "fr"
    assert called["force"] is False


def test_main_all_mode(ep_setup, monkeypatch):
    calls = []

    def fake_transcribe(src, path, model, lang, force, yt):
        calls.append(path.name)

    monkeypatch.setattr(tr, "transcribe_episode", fake_transcribe)
    monkeypatch.setattr(sys, "argv", [
        "transcribe.py", "--source", ep_setup["src"], "--all",
    ])
    tr.main()
    assert calls == ["ep-1.json"]


def test_main_all_mode_with_limit(ep_setup, monkeypatch):
    # Ajoute un 2e épisode pour tester --limit
    ep2 = ep_setup["ep_path"].parent / "ep-2.json"
    ep2.write_text(json.dumps({"guid": "ep-2", "title": "T2"}), encoding="utf-8")
    calls = []
    monkeypatch.setattr(tr, "transcribe_episode",
                        lambda *a, **kw: calls.append(a[1].name))
    monkeypatch.setattr(sys, "argv", [
        "transcribe.py", "--source", ep_setup["src"], "--all", "--limit", "1",
    ])
    tr.main()
    assert len(calls) == 1


def test_main_all_mode_handles_errors(ep_setup, monkeypatch):
    """Une erreur sur un épisode n'arrête pas la boucle."""
    ep2 = ep_setup["ep_path"].parent / "ep-2.json"
    ep2.write_text(json.dumps({"guid": "ep-2", "title": "T2"}), encoding="utf-8")
    calls = []

    def boom_then_ok(src, path, model, lang, force, yt):
        calls.append(path.name)
        if path.name == "ep-1.json":
            raise RuntimeError("boom")

    monkeypatch.setattr(tr, "transcribe_episode", boom_then_ok)
    monkeypatch.setattr(sys, "argv", [
        "transcribe.py", "--source", ep_setup["src"], "--all",
    ])
    tr.main()
    assert calls == ["ep-1.json", "ep-2.json"]


def test_main_guids_file(ep_setup, monkeypatch, tmp_path):
    """Mode --guids-file : ne transcrit que les guids listés."""
    ep2 = ep_setup["ep_path"].parent / "ep-2.json"
    ep2.write_text(json.dumps({"guid": "ep-2", "title": "T2"}), encoding="utf-8")

    gfile = tmp_path / "guids.txt"
    gfile.write_text("ep-2\n", encoding="utf-8")

    calls = []
    monkeypatch.setattr(tr, "transcribe_episode",
                        lambda *a, **kw: calls.append(a[1].name))
    monkeypatch.setattr(sys, "argv", [
        "transcribe.py", "--source", ep_setup["src"], "--guids-file", str(gfile),
    ])
    tr.main()
    assert calls == ["ep-2.json"]


def test_main_language_empty(ep_setup, monkeypatch):
    captured = {}
    monkeypatch.setattr(tr, "transcribe_episode",
                        lambda *a, **kw: captured.setdefault("lang", a[3]))
    monkeypatch.setattr(sys, "argv", [
        "transcribe.py", "--source", ep_setup["src"], "--guid", "ep-1",
        "--language", "",
    ])
    tr.main()
    assert captured["lang"] is None
