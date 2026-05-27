"""Tests du serveur de relecture local (tools/review_server.py).

On teste essentiellement les fonctions de rendu HTML et les helpers purs.
Pour les handlers HTTP, on instancie le Handler avec des sockets factices et on
appelle do_GET / do_POST directement (sans démarrer de serveur).
"""
from __future__ import annotations

import io
import json
from pathlib import Path
from unittest.mock import patch

import pytest

import review_server as rs


# ===== Fixtures =============================================================
@pytest.fixture(autouse=True)
def _clear_review_server_caches():
    """Le cache module-level `_RECO_PATH_CACHE` (et le LRU `_load_transcript`)
    persistent entre tests : on les vide avant chaque test pour éviter de
    récupérer des Paths obsolètes pointant vers un tmp_path précédent."""
    rs._RECO_PATH_CACHE.clear()
    rs._load_transcript.cache_clear()
    yield
    rs._RECO_PATH_CACHE.clear()
    rs._load_transcript.cache_clear()


@pytest.fixture
def fake_source(tmp_path, monkeypatch):
    """Construit une arborescence de contenu minimale + redirige les chemins."""
    # On reroute les constantes de chemins de common vers tmp_path.
    import common

    src_id = "demo-source"
    sources_dir = tmp_path / "sources"
    episodes_dir = tmp_path / "episodes" / src_id
    recos_dir = tmp_path / "recos" / src_id
    transcripts_dir = tmp_path / "transcripts"
    for d in (sources_dir, episodes_dir, recos_dir, transcripts_dir):
        d.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(common, "SOURCES_DIR", sources_dir)
    monkeypatch.setattr(common, "EPISODES_DIR", tmp_path / "episodes")
    monkeypatch.setattr(common, "RECOS_DIR", tmp_path / "recos")
    monkeypatch.setattr(common, "TRANSCRIPTS_DIR", transcripts_dir)

    # Source
    (sources_dir / f"{src_id}.json").write_text(
        json.dumps({"title": "Démo Podcast", "hosts": ["Alice", "Bob"]}),
        encoding="utf-8",
    )
    # Episode 1 (avec recos)
    ep1 = {
        "guid": "ep-001",
        "title": "Un épisode avec Charlie Tartempion",
        "youtubeTitle": "S1·E1 — Spécial",
        "youtubeUrl": "https://www.youtube.com/watch?v=ABCDEFGHIJK",
        "season": 1,
        "number": 1,
        "audioDuration": 3600,
        "youtubeDuration": 3610,
    }
    (episodes_dir / "ep-001.json").write_text(json.dumps(ep1), encoding="utf-8")
    # Episode 2 (sans reco, sans saison)
    ep2 = {
        "guid": "ep-002",
        "title": "Épisode sans rien",
        "number": 7,
    }
    (episodes_dir / "ep-002.json").write_text(json.dumps(ep2), encoding="utf-8")

    # Recos pour ep-001 : un draft confirmé par 2 LLMs, un validated, un discarded
    recos = [
        {
            "id": "ubm-001",
            "episodeGuid": "ep-001",
            "type": "film",
            "title": "Mortel",
            "creator": "F. Garcia",
            "timestamp": "00:10:30",
            "quote": "Une série géniale",
            "status": "draft",
            "extractors": ["claude", "gpt"],
        },
        {
            "id": "ubm-002",
            "episodeGuid": "ep-001",
            "type": "livre",
            "title": "Solo",
            "timestamp": "01:02:03",
            "status": "validated",
            "recommendedBy": "Alice",
            "extractors": ["claude"],
        },
        {
            "id": "ubm-003",
            "episodeGuid": "ep-001",
            "type": "musique",
            "title": "Hozier",
            "status": "discarded",
        },
    ]
    for r in recos:
        (recos_dir / f"{r['id']}.json").write_text(json.dumps(r), encoding="utf-8")

    # Transcription pour ep-001
    transcript = (
        "[00:10:25] Avant la reco.\n"
        "[00:10:28] Juste avant.\n"
        "[00:10:30] Voici Mortel.\n"
        "[00:10:35] Après.\n"
    )
    (transcripts_dir / src_id).mkdir(parents=True, exist_ok=True)
    (transcripts_dir / src_id / "ep-001.txt").write_text(transcript, encoding="utf-8")

    # Vider le cache LRU pour ne pas garder des transcripts d'autres tests
    rs._load_transcript.cache_clear()
    return src_id


# ===== Helpers purs =========================================================
@pytest.mark.parametrize(
    "title,hosts,expected",
    [
        ("Avec Charlie Tartempion", ["Alice"], ["Charlie Tartempion"]),
        ("Alice et Bob avec Charlie et Diane", ["Alice", "Bob"], ["Charlie", "Diane"]),
        ("Episode spécial", ["Alice"], []),
        # Le titre commence par les hôtes (pas de "avec") -> on prend le tout.
        ("Alice, Bob & Charlie parlent", ["Alice", "Bob"], ["Charlie"]),
    ],
)
def test_parse_guests(title, hosts, expected):
    assert rs._parse_guests(title, hosts) == expected


def test_parse_guests_uppercase_normalized():
    """Un nom tout en majuscules est ramené en title-case."""
    guests = rs._parse_guests("avec MARIE DUPONT", ["Alice"])
    assert guests == ["Marie Dupont"]


def test_parse_guests_empty_title():
    assert rs._parse_guests("", ["Alice"]) == []
    assert rs._parse_guests(None, ["Alice"]) == []


@pytest.mark.parametrize(
    "ts,expected",
    [
        ("00:00:30", 30),
        ("01:02:03", 3723),
        ("10:30", 630),
        ("42", 42),
        (None, None),
        ("", None),
        ("pas-un-nombre", None),
    ],
)
def test_ts_seconds(ts, expected):
    assert rs._ts_seconds(ts) == expected


def test_fmt():
    assert rs._fmt(0) == "00:00:00"
    assert rs._fmt(3723) == "01:02:03"
    assert rs._fmt(59) == "00:00:59"


@pytest.mark.parametrize(
    "url,expected",
    [
        ("https://www.youtube.com/watch?v=ABCDEFGHIJK", "ABCDEFGHIJK"),
        ("https://youtu.be/abc", ""),  # pas de ?v=
        ("", ""),
        (None, ""),
    ],
)
def test_yt_id(url, expected):
    assert rs._yt_id(url) == expected


def test_embed_url():
    out = rs._embed_url("https://www.youtube.com/watch?v=XYZ", 42)
    assert "embed/XYZ" in out
    assert "start=42" in out
    assert "autoplay=1" in out


def test_embed_url_no_video_id():
    assert rs._embed_url("https://example.com", 10) == ""


def test_load_transcript_missing(fake_source, monkeypatch):
    rs._load_transcript.cache_clear()
    items = rs._load_transcript(fake_source, "guid-inconnu")
    assert items == ()


def test_load_transcript_parsed(fake_source):
    rs._load_transcript.cache_clear()
    items = rs._load_transcript(fake_source, "ep-001")
    assert len(items) == 4
    assert items[0] == (10 * 60 + 25, "Avant la reco.")


def test_context_around_empty():
    assert rs._context_around((), 10) == []


def test_context_around_picks_neighbors():
    items = tuple((i * 10, f"ligne {i}") for i in range(10))
    ctx = rs._context_around(items, 50, n_before=2, n_after=1)
    # Plus proche : index 5 (50s). Avant=2, après=1 -> 4 lignes au total.
    assert len(ctx) == 4
    assert ctx[0][1] == "ligne 3"
    assert ctx[-1][1] == "ligne 6"


# ===== Rendu HTML ===========================================================
def test_shell_escapes_title():
    out = rs._shell("<bad>", "sub", "<div/>")
    assert "&lt;bad&gt;" in out
    assert "<div/>" in out


def test_reco_card_minimal():
    """Reco minimale : pas de timestamp, pas de citation, pas d'extractors."""
    r = {"id": "x", "title": "Truc", "type": "film", "status": "draft"}
    ep = {"guid": "g", "title": "Ep", "youtubeUrl": "https://www.youtube.com/watch?v=V"}
    out = rs._reco_card(r, ep, ["Alice"], "src")
    assert "Truc" in out
    assert "Alice" in out  # checkbox host
    assert "Valider" in out


def test_reco_card_full(fake_source):
    """Reco complète avec contexte transcript, embed, extractors multiples."""
    rs._load_transcript.cache_clear()
    r = {
        "id": "ubm-001",
        "title": "Mortel",
        "type": "film",
        "creator": "F. Garcia",
        "timestamp": "00:10:30",
        "quote": "extra",
        "status": "draft",
        "extractors": ["claude", "gpt"],
        "recommendedBy": "Alice",
    }
    ep = {
        "guid": "ep-001",
        "title": "avec Charlie Tartempion",
        "youtubeUrl": "https://www.youtube.com/watch?v=ABCDEFGHIJK",
    }
    out = rs._reco_card(r, ep, ["Alice", "Bob"], fake_source)
    assert "embed/ABCDEFGHIJK" in out
    assert "start=630" in out
    assert "2 LLMs" in out
    assert "ctx-here" in out  # contexte transcript présent
    assert "Voici Mortel." in out
    assert "« extra »" in out
    # Checkbox Alice cochée
    assert 'value="Alice" checked' in out
    # Charlie Tartempion (invité) présent
    assert "Charlie Tartempion" in out


def test_reco_card_solo_extractor():
    r = {"id": "x", "title": "T", "type": "film", "status": "draft",
         "extractors": ["claude"], "timestamp": "00:01:00"}
    ep = {"guid": "g", "title": "Ep", "youtubeUrl": None}
    out = rs._reco_card(r, ep, [], "src")
    # Pas d'URL YouTube -> lien off (.tc.off)
    assert "tc off" in out
    assert "claude" in out
    assert "solo" in out


def test_reco_card_no_timestamp_no_yt():
    r = {"id": "x", "title": "T", "type": "film", "status": "validated"}
    ep = {"guid": "g", "title": "Ep"}
    out = rs._reco_card(r, ep, [], "src")
    assert "row done" in out  # statut validated -> classe done


def test_reco_card_discarded():
    r = {"id": "x", "title": "T", "type": "film", "status": "discarded"}
    ep = {"guid": "g", "title": "Ep"}
    out = rs._reco_card(r, ep, [], "src")
    assert "row discarded" in out


def test_ep_header_with_season_and_durations():
    ep = {"season": 1, "number": 5, "youtubeTitle": "Titre",
          "youtubeUrl": "https://yt/?v=X", "audioDuration": 3600,
          "youtubeDuration": 4000}
    recs = [{"status": "draft"}, {"status": "validated"}]
    out = rs._ep_header(ep, recs)
    assert "S1·E1" not in out  # E5, pas E1
    assert "S1·E5" in out
    assert "Δ" in out
    assert "color:#e08a8a" in out  # diff > 300s -> warning rouge
    assert "2 recos · 1 à valider" in out


def test_ep_header_number_only():
    ep = {"number": 7, "title": "T"}
    out = rs._ep_header(ep, [])
    assert "#7" in out


def test_ep_header_no_id_no_durations():
    """Aucune saison ni numéro : pas de badge ; pas de durées : pas de bloc dur."""
    ep = {"title": "Sans rien"}
    out = rs._ep_header(ep, [])
    assert "epnum" not in out
    assert "🎧" not in out


# ===== _load_groups, _render_index, _render_episode =========================
def test_load_groups(fake_source):
    source, episodes, groups = rs._load_groups(fake_source)
    assert source["title"] == "Démo Podcast"
    assert "ep-001" in episodes
    assert "ep-002" in episodes
    # Tri : drafts d'abord puis validated puis discarded
    statuses = [r.get("status") for r in groups["ep-001"]]
    assert statuses == ["draft", "validated", "discarded"]


def test_render_index(fake_source):
    rs._load_transcript.cache_clear()
    out = rs._render_index(fake_source)
    assert "Démo Podcast" in out
    assert "S1·E1" in out
    assert "#7" in out
    # ep-002 sans reco -> classe empty
    assert "thumb empty" in out
    assert "1 à valider" in out  # 1 draft pour ep-001
    assert "0 reco" in out  # ep-002 vide


def test_render_index_empty(tmp_path, monkeypatch):
    """Une source sans aucun épisode."""
    import common
    src_id = "vide"
    sources_dir = tmp_path / "sources"
    sources_dir.mkdir()
    monkeypatch.setattr(common, "SOURCES_DIR", sources_dir)
    monkeypatch.setattr(common, "EPISODES_DIR", tmp_path / "episodes")
    monkeypatch.setattr(common, "RECOS_DIR", tmp_path / "recos")
    (sources_dir / f"{src_id}.json").write_text(
        json.dumps({"title": "Vide", "hosts": []}), encoding="utf-8"
    )
    out = rs._render_index(src_id)
    assert "Aucune reco" in out


def test_render_episode(fake_source):
    rs._load_transcript.cache_clear()
    out = rs._render_episode(fake_source, "ep-001")
    assert "ytplayer" in out  # iframe partagée
    assert "Mortel" in out
    assert "Solo" in out


def test_render_episode_unknown(fake_source):
    out = rs._render_episode(fake_source, "guid-inexistant")
    assert "Épisode introuvable" in out


def test_reco_path_found(fake_source):
    path = rs._reco_path(fake_source, "ubm-002")
    assert path is not None
    assert path.name == "ubm-002.json"


def test_reco_path_not_found(fake_source):
    assert rs._reco_path(fake_source, "n-existe-pas") is None


# ===== Handler do_GET / do_POST =============================================
class _FakeHandler(rs.Handler):
    """Sous-classe le Handler pour bypasser BaseHTTPRequestHandler.__init__
    (qui voudrait lire depuis le socket)."""

    def __init__(self, source_id: str, path: str, body: bytes = b""):
        # On NE PAS appeler super().__init__ pour éviter le parsing HTTP.
        self.source_id = source_id
        self.path = path
        self.rfile = io.BytesIO(body)
        self.wfile = io.BytesIO()
        self.headers = {"Content-Length": str(len(body))}
        self._status = None
        self._sent_headers: dict[str, str] = {}

    def send_response(self, code, *a, **kw):
        self._status = code

    def send_header(self, k, v):
        self._sent_headers[k] = v

    def end_headers(self):
        pass


def test_handler_get_root(fake_source):
    h = _FakeHandler(fake_source, "/")
    h.do_GET()
    assert h._status == 200
    body = h.wfile.getvalue().decode("utf-8")
    assert "Démo Podcast" in body


def test_handler_get_episode(fake_source):
    h = _FakeHandler(fake_source, "/ep?guid=ep-001")
    h.do_GET()
    assert h._status == 200
    body = h.wfile.getvalue().decode("utf-8")
    assert "Mortel" in body


def test_handler_get_404(fake_source):
    h = _FakeHandler(fake_source, "/lol")
    h.do_GET()
    assert h._status == 404


def test_handler_post_validate(fake_source):
    body = b"id=ubm-001&who=Alice&who=Bob&other=Charlie&action=validate"
    h = _FakeHandler(fake_source, "/save", body)
    h.do_POST()
    assert h._status == 303
    # Doit rediriger vers la page de l'épisode
    assert h._sent_headers["Location"].startswith("/ep?guid=ep-001")
    # Vérifie l'écriture
    from common import recos_dir_for, read_json
    reco = read_json(recos_dir_for(fake_source) / "ubm-001.json")
    assert reco["status"] == "validated"
    assert reco["recommendedBy"] == "Alice & Bob & Charlie"


def test_handler_post_validate_no_names_removes_field(fake_source):
    """Validation sans cocher personne : retire le champ recommendedBy existant."""
    body = b"id=ubm-002&action=validate"
    h = _FakeHandler(fake_source, "/save", body)
    h.do_POST()
    from common import recos_dir_for, read_json
    reco = read_json(recos_dir_for(fake_source) / "ubm-002.json")
    assert reco["status"] == "validated"
    assert "recommendedBy" not in reco


def test_handler_post_discard(fake_source):
    body = b"id=ubm-001&action=discard"
    h = _FakeHandler(fake_source, "/save", body)
    h.do_POST()
    from common import recos_dir_for, read_json
    reco = read_json(recos_dir_for(fake_source) / "ubm-001.json")
    assert reco["status"] == "discarded"


def test_handler_post_unknown_id(fake_source):
    """Reco id inconnu : redirige vers / (pas vers /ep)."""
    body = b"id=inconnu&action=validate"
    h = _FakeHandler(fake_source, "/save", body)
    h.do_POST()
    assert h._status == 303
    assert h._sent_headers["Location"] == "/"


def test_handler_log_message_silent(fake_source):
    """log_message est volontairement silencieux (pas d'exception)."""
    h = _FakeHandler(fake_source, "/")
    h.log_message("format", "arg")  # doit juste ne rien faire


# ===== main =================================================================
def test_main_parses_args_and_serves(monkeypatch):
    """On vérifie juste que main() construit le serveur avec les bons paramètres,
    sans entrer dans la boucle réelle."""
    captured = {}

    class _FakeServer:
        def __init__(self, addr, handler):
            captured["addr"] = addr
            captured["handler"] = handler

        def serve_forever(self):
            raise KeyboardInterrupt  # on simule un Ctrl+C immédiat

    monkeypatch.setattr(rs, "HTTPServer", _FakeServer)
    monkeypatch.setattr("sys.argv", ["review_server.py", "--source", "demo", "--port", "9999"])
    rs.main()
    assert captured["addr"] == ("127.0.0.1", 9999)
