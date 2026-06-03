"""Tests du serveur de relecture local (tools/review_server.py).

On teste essentiellement les fonctions de rendu HTML et les helpers purs.
Pour les handlers HTTP, on instancie le Handler avec des sockets factices et on
appelle do_GET / do_POST directement (sans démarrer de serveur).
"""
from __future__ import annotations

import io
import json
import urllib.parse
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
            "types": ["film"],
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
            "types": ["livre"],
            "title": "Solo",
            "timestamp": "01:02:03",
            "status": "validated",
            "recommendedBy": "Alice",
            "extractors": ["claude"],
        },
        {
            "id": "ubm-003",
            "episodeGuid": "ep-001",
            "types": ["musique"],
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
    r = {"id": "x", "title": "Truc", "types": ["film"], "status": "draft"}
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
        "types": ["film"],
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
    r = {"id": "x", "title": "T", "types": ["film"], "status": "draft",
         "extractors": ["claude"], "timestamp": "00:01:00"}
    ep = {"guid": "g", "title": "Ep", "youtubeUrl": None}
    out = rs._reco_card(r, ep, [], "src")
    # Pas d'URL YouTube -> lien off (.tc.off)
    assert "tc off" in out
    assert "claude" in out
    assert "solo" in out


def test_reco_card_no_timestamp_no_yt():
    r = {"id": "x", "title": "T", "types": ["film"], "status": "validated"}
    ep = {"guid": "g", "title": "Ep"}
    out = rs._reco_card(r, ep, [], "src")
    assert "row done" in out  # statut validated -> classe done


def test_reco_card_discarded():
    r = {"id": "x", "title": "T", "types": ["film"], "status": "discarded"}
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

    def __init__(self, source_id: str, path: str, body: bytes = b"",
                 accept: str = ""):
        # On NE PAS appeler super().__init__ pour éviter le parsing HTTP.
        self.source_id = source_id
        self.path = path
        self.rfile = io.BytesIO(body)
        self.wfile = io.BytesIO()
        self.headers = {"Content-Length": str(len(body)), "Accept": accept}
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


def test_handler_post_payload_too_large(fake_source):
    """Content-Length > 1 MiB -> 413 Payload too large."""
    h = _FakeHandler(fake_source, "/save", b"id=ubm-001")
    # Surcharge Content-Length pour simuler un payload énorme sans charger 1 MiB.
    h.headers = {"Content-Length": str((1 << 20) + 1)}
    h.do_POST()
    assert h._status == 413


def test_handler_post_invalid_reco_id(fake_source):
    """Un reco_id avec caractères interdits (path traversal, espaces…) est rejeté."""
    body = b"id=../etc/passwd&action=validate"
    h = _FakeHandler(fake_source, "/save", body)
    h.do_POST()
    assert h._status == 303
    assert h._sent_headers["Location"] == "/"
    # La reco existante ne doit PAS avoir été modifiée
    from common import read_json, recos_dir_for
    reco = read_json(recos_dir_for(fake_source) / "ubm-001.json")
    assert reco["status"] == "draft"


def test_handler_security_headers_set(fake_source):
    h = _FakeHandler(fake_source, "/")
    h.do_GET()
    assert h._sent_headers.get("X-Content-Type-Options") == "nosniff"
    assert h._sent_headers.get("X-Frame-Options") == "DENY"
    assert "youtube.com" in h._sent_headers.get("Content-Security-Policy", "")


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


# ===== Édition inline + Ré-enrichissement ===================================
def _write_reco(recos_dir: Path, reco: dict) -> Path:
    p = recos_dir / f"{reco['id']}.json"
    p.write_text(json.dumps(reco), encoding="utf-8")
    return p


def test_edit_mode_renders_form(fake_source):
    """GET /ep?guid=…&edit=Y : la carte Y est en mode édition."""
    # Patche une reco avec externalIds + watchProviders pour exercer <details>.
    from common import recos_dir_for
    p = recos_dir_for(fake_source) / "ubm-edit.json"
    p.write_text(json.dumps({
        "id": "ubm-edit", "episodeGuid": "ep-001", "types": ["film"],
        "title": "EditMe", "creator": "X", "status": "draft",
        "externalIds": {"tmdb": "42"},
        "watchProviders": [{"label": "Netflix", "url": "https://nf/x"}],
    }), encoding="utf-8")
    rs._invalidate_reco_path_cache(fake_source)

    h = _FakeHandler(fake_source, "/ep?guid=ep-001&edit=ubm-edit")
    h.do_GET()
    body = h.wfile.getvalue().decode("utf-8")
    assert 'name="title"' in body
    assert 'name="creator"' in body
    assert 'name="types" value="film"' in body
    assert "<details>" in body
    assert 'name="ext_tmdb"' in body
    # Les autres cartes restent en mode normal
    assert "Solo" in body


def test_edit_invalid_id_no_edit_mode(fake_source):
    """GET /ep?guid=X&edit=<invalide> : aucun crash, pas de mode édition."""
    h = _FakeHandler(fake_source, "/ep?guid=ep-001&edit=../etc/passwd")
    h.do_GET()
    assert h._status == 200
    body = h.wfile.getvalue().decode("utf-8")
    # Pas de formulaire d'édition
    assert 'name="title"' not in body


def test_post_edit_updates_title_creator_types(fake_source):
    body = b"id=ubm-001&title=Mortel%20S2&creator=Nouveau&types=film&types=serie"
    h = _FakeHandler(fake_source, "/edit", body)
    h.do_POST()
    assert h._status == 303
    assert h._sent_headers["Location"].startswith("/ep?guid=ep-001")
    from common import read_json, recos_dir_for
    reco = read_json(recos_dir_for(fake_source) / "ubm-001.json")
    assert reco["title"] == "Mortel S2"
    assert reco["creator"] == "Nouveau"
    assert reco["types"] == ["film", "serie"]


def test_post_edit_no_types_rejected(fake_source):
    """Types vides → redirige vers la page épisode + flash d'erreur (H6)."""
    body = b"id=ubm-001&title=X"
    h = _FakeHandler(fake_source, "/edit", body)
    h.do_POST()
    assert h._status == 303
    loc = h._sent_headers["Location"]
    assert loc.startswith("/ep?guid=ep-001")
    assert "kind=error" in loc
    assert "type" in urllib.parse.unquote(loc).lower()
    # Non modifié
    from common import read_json, recos_dir_for
    reco = read_json(recos_dir_for(fake_source) / "ubm-001.json")
    assert reco["title"] == "Mortel"


def test_post_edit_empty_title_rejected(fake_source):
    """Titre vide → redirige vers la page épisode + flash d'erreur (H6)."""
    body = b"id=ubm-001&title=&types=film"
    h = _FakeHandler(fake_source, "/edit", body)
    h.do_POST()
    assert h._status == 303
    loc = h._sent_headers["Location"]
    assert loc.startswith("/ep?guid=ep-001")
    assert "kind=error" in loc
    assert "titre" in urllib.parse.unquote(loc).lower()
    from common import read_json, recos_dir_for
    reco = read_json(recos_dir_for(fake_source) / "ubm-001.json")
    assert reco["title"] == "Mortel"


def test_post_edit_empty_creator_drops_key(fake_source):
    body = b"id=ubm-001&title=Mortel&creator=&types=film"
    h = _FakeHandler(fake_source, "/edit", body)
    h.do_POST()
    from common import read_json, recos_dir_for
    reco = read_json(recos_dir_for(fake_source) / "ubm-001.json")
    assert "creator" not in reco


def test_post_edit_updates_ext_tmdb(fake_source, tmp_path):
    from common import recos_dir_for, read_json
    p = recos_dir_for(fake_source) / "ubm-004.json"
    p.write_text(json.dumps({
        "id": "ubm-004", "episodeGuid": "ep-001", "types": ["film"],
        "title": "X", "status": "draft",
        "externalIds": {"tmdb": "old-id"},
    }), encoding="utf-8")
    rs._invalidate_reco_path_cache(fake_source)
    body = b"id=ubm-004&title=X&types=film&ext_tmdb=new-id"
    h = _FakeHandler(fake_source, "/edit", body)
    h.do_POST()
    reco = read_json(p)
    assert reco["externalIds"]["tmdb"] == "new-id"


def test_post_edit_clearing_ext_removes_key(fake_source):
    from common import recos_dir_for, read_json
    p = recos_dir_for(fake_source) / "ubm-005.json"
    p.write_text(json.dumps({
        "id": "ubm-005", "episodeGuid": "ep-001", "types": ["film"],
        "title": "X", "status": "draft",
        "externalIds": {"tmdb": "abc", "imdb": "tt123"},
    }), encoding="utf-8")
    rs._invalidate_reco_path_cache(fake_source)
    body = b"id=ubm-005&title=X&types=film&ext_tmdb=&ext_imdb=tt123"
    h = _FakeHandler(fake_source, "/edit", body)
    h.do_POST()
    reco = read_json(p)
    assert "tmdb" not in reco["externalIds"]
    assert reco["externalIds"]["imdb"] == "tt123"


def test_post_edit_watch_providers_preserve_and_drop(fake_source):
    from common import recos_dir_for, read_json
    p = recos_dir_for(fake_source) / "ubm-006.json"
    p.write_text(json.dumps({
        "id": "ubm-006", "episodeGuid": "ep-001", "types": ["film"],
        "title": "X", "status": "draft",
        "watchProviders": [
            {"label": "Netflix", "url": "https://netflix.com/x"},
            {"label": "Canal+", "url": "https://canal.tv/x"},
        ],
    }), encoding="utf-8")
    rs._invalidate_reco_path_cache(fake_source)
    # On garde Netflix, on vide Canal+ → exclu
    body = (b"id=ubm-006&title=X&types=film"
            b"&wp_label_0=Netflix&wp_url_0=https://netflix.com/x"
            b"&wp_label_1=Canal%2B&wp_url_1=")
    h = _FakeHandler(fake_source, "/edit", body)
    h.do_POST()
    reco = read_json(p)
    assert reco["watchProviders"] == [
        {"label": "Netflix", "url": "https://netflix.com/x"}
    ]


def test_post_edit_clearing_all_ext_drops_externalIds_key(fake_source):
    """Vider le SEUL champ ext présent → la clé externalIds disparait."""
    from common import recos_dir_for, read_json
    p = recos_dir_for(fake_source) / "ubm-007.json"
    p.write_text(json.dumps({
        "id": "ubm-007", "episodeGuid": "ep-001", "types": ["film"],
        "title": "X", "status": "draft",
        "externalIds": {"tmdb": "abc"},
    }), encoding="utf-8")
    rs._invalidate_reco_path_cache(fake_source)
    body = b"id=ubm-007&title=X&types=film&ext_tmdb="
    h = _FakeHandler(fake_source, "/edit", body)
    h.do_POST()
    reco = read_json(p)
    assert "externalIds" not in reco


def test_post_edit_no_providers_drops_watchProviders_key(fake_source):
    """Ne soumettre aucun wp_label_<i> → watchProviders est supprimé."""
    from common import recos_dir_for, read_json
    p = recos_dir_for(fake_source) / "ubm-008.json"
    p.write_text(json.dumps({
        "id": "ubm-008", "episodeGuid": "ep-001", "types": ["film"],
        "title": "X", "status": "draft",
        "watchProviders": [{"label": "Netflix", "url": "https://nf/x"}],
    }), encoding="utf-8")
    rs._invalidate_reco_path_cache(fake_source)
    body = b"id=ubm-008&title=X&types=film"  # aucun wp_*
    h = _FakeHandler(fake_source, "/edit", body)
    h.do_POST()
    reco = read_json(p)
    assert "watchProviders" not in reco


def test_post_reenrich_music_exception_graceful(fake_source, monkeypatch):
    """L'enricher Music lève → warning, JSON non corrompu, 303 OK."""
    from common import recos_dir_for, read_json
    p = recos_dir_for(fake_source) / "ubm-009.json"
    p.write_text(json.dumps({
        "id": "ubm-009", "episodeGuid": "ep-001", "types": ["musique"],
        "title": "Tube", "status": "draft",
    }), encoding="utf-8")
    rs._invalidate_reco_path_cache(fake_source)

    def kaboom(reco, *, session, spotify_token=None, force=False):
        raise RuntimeError("Deezer down")

    import enrich_music
    monkeypatch.setattr(enrich_music, "enrich_one", kaboom)
    h = _FakeHandler(fake_source, "/reenrich", b"id=ubm-009")
    h.do_POST()
    assert h._status == 303
    reco = read_json(p)
    assert reco["title"] == "Tube"
    assert "_enrich_status" not in reco


def test_post_edit_invalid_reco_id(fake_source):
    body = b"id=../bad&title=X&types=film"
    h = _FakeHandler(fake_source, "/edit", body)
    h.do_POST()
    assert h._status == 303
    assert h._sent_headers["Location"] == "/"


def test_post_reenrich_film_calls_tmdb(fake_source, monkeypatch):
    calls = []

    def fake_enrich_one(reco, *, session, api_key=None, force=False):
        calls.append({"reco_id": reco.get("id"), "force": force, "api_key": api_key})
        reco["externalIds"] = {"tmdb": "999"}
        reco["_enrich_status"] = "ok"
        return reco

    import enrich_tmdb
    monkeypatch.setattr(enrich_tmdb, "enrich_one", fake_enrich_one)
    body = b"id=ubm-001"
    h = _FakeHandler(fake_source, "/reenrich", body)
    h.do_POST()
    assert h._status == 303
    loc = h._sent_headers["Location"]
    assert loc.startswith("/ep?guid=ep-001")
    # Flash de succès doit accompagner la redirection (UX).
    assert "flash=" in loc
    assert "kind=success" in loc
    assert "TMDB" in urllib.parse.unquote(loc)
    assert len(calls) == 1
    assert calls[0]["force"] is True
    from common import read_json, recos_dir_for
    reco = read_json(recos_dir_for(fake_source) / "ubm-001.json")
    assert reco["externalIds"]["tmdb"] == "999"
    assert "_enrich_status" not in reco


def test_post_reenrich_not_found_emits_warning_flash(fake_source, monkeypatch):
    def fake_not_found(reco, *, session, api_key=None, force=False):
        reco["_enrich_status"] = "not_found"
        return reco
    import enrich_tmdb
    monkeypatch.setattr(enrich_tmdb, "enrich_one", fake_not_found)
    h = _FakeHandler(fake_source, "/reenrich", b"id=ubm-001")
    h.do_POST()
    loc = h._sent_headers["Location"]
    assert "kind=warning" in loc
    assert "non%20trouv" in loc  # "non trouvé" url-encodé


def test_post_reenrich_exception_emits_error_flash(fake_source, monkeypatch):
    import enrich_tmdb
    monkeypatch.setattr(enrich_tmdb, "enrich_one",
                        lambda r, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    h = _FakeHandler(fake_source, "/reenrich", b"id=ubm-001")
    h.do_POST()
    loc = h._sent_headers["Location"]
    assert "kind=error" in loc
    assert "RuntimeError" in urllib.parse.unquote(loc)


def test_post_reenrich_401_message_says_api_key_invalid(fake_source, monkeypatch):
    """HTTP 401 (clé invalide/expirée) → message UI clair, pas générique."""
    import enrich_tmdb
    def kaboom(reco, **k):
        raise enrich_tmdb.TMDBAPIError("TMDB /search → HTTP 401", status_code=401)
    monkeypatch.setattr(enrich_tmdb, "enrich_one", kaboom)
    h = _FakeHandler(fake_source, "/reenrich", b"id=ubm-001",
                     accept="application/json")
    h.do_POST()
    payload = json.loads(h.wfile.getvalue().decode("utf-8"))
    assert payload["kind"] == "error"
    assert "clé API invalide" in payload["message"]


def test_post_reenrich_429_message_says_rate_limit(fake_source, monkeypatch):
    import enrich_tmdb
    def kaboom(reco, **k):
        raise enrich_tmdb.TMDBAPIError("TMDB → 429", status_code=429)
    monkeypatch.setattr(enrich_tmdb, "enrich_one", kaboom)
    h = _FakeHandler(fake_source, "/reenrich", b"id=ubm-001",
                     accept="application/json")
    h.do_POST()
    payload = json.loads(h.wfile.getvalue().decode("utf-8"))
    assert "rate-limit" in payload["message"]


def test_post_reenrich_not_found_includes_title(fake_source, monkeypatch):
    """not_found mentionne le titre exact de l'œuvre pour aider l'utilisateur."""
    import enrich_tmdb
    def not_found(reco, **k):
        reco["_enrich_status"] = "not_found"
        return reco
    monkeypatch.setattr(enrich_tmdb, "enrich_one", not_found)
    h = _FakeHandler(fake_source, "/reenrich", b"id=ubm-001",
                     accept="application/json")
    h.do_POST()
    payload = json.loads(h.wfile.getvalue().decode("utf-8"))
    assert payload["kind"] == "warning"
    # Le fixture stocke ubm-001 = "Mortel"
    assert "Mortel" in payload["message"]
    assert "non trouvée" in payload["message"]


def test_post_reenrich_500_message_says_http(fake_source, monkeypatch):
    """Autre code HTTP (5xx) → message générique avec le code."""
    import enrich_tmdb
    def kaboom(reco, **k):
        raise enrich_tmdb.TMDBAPIError("TMDB → 503", status_code=503)
    monkeypatch.setattr(enrich_tmdb, "enrich_one", kaboom)
    h = _FakeHandler(fake_source, "/reenrich", b"id=ubm-001",
                     accept="application/json")
    h.do_POST()
    payload = json.loads(h.wfile.getvalue().decode("utf-8"))
    assert "HTTP 503" in payload["message"]


def test_post_reenrich_network_error_message(fake_source, monkeypatch):
    """Erreur réseau (status_code None) → message dédié, distinct du HTTP error."""
    import enrich_tmdb
    def kaboom(reco, **k):
        raise enrich_tmdb.TMDBAPIError("DNS fail")  # pas de status_code
    monkeypatch.setattr(enrich_tmdb, "enrich_one", kaboom)
    h = _FakeHandler(fake_source, "/reenrich", b"id=ubm-001",
                     accept="application/json")
    h.do_POST()
    payload = json.loads(h.wfile.getvalue().decode("utf-8"))
    assert payload["kind"] == "error"
    assert "réseau" in payload["message"]


def test_post_edit_emits_success_flash(fake_source):
    body = b"id=ubm-001&title=Nouveau&types=film"
    h = _FakeHandler(fake_source, "/edit", body)
    h.do_POST()
    loc = h._sent_headers["Location"]
    assert loc.startswith("/ep?guid=ep-001")
    assert "kind=success" in loc
    assert "enregistr" in urllib.parse.unquote(loc)


def test_post_reenrich_json_response(fake_source, monkeypatch):
    """Accept: application/json → réponse JSON avec card_html, pas de 303."""
    def fake_one(reco, *, session, api_key=None, force=False):
        reco["externalIds"] = {"tmdb": "42"}
        reco["_enrich_status"] = "ok"
        return reco
    import enrich_tmdb
    monkeypatch.setattr(enrich_tmdb, "enrich_one", fake_one)
    h = _FakeHandler(fake_source, "/reenrich", b"id=ubm-001",
                     accept="application/json")
    h.do_POST()
    assert h._status == 200
    assert h._sent_headers["Content-Type"].startswith("application/json")
    payload = json.loads(h.wfile.getvalue().decode("utf-8"))
    assert payload["kind"] == "success"
    assert "TMDB" in payload["message"]
    assert payload["card_html"].startswith("\n    <li class=\"row")


def test_post_edit_json_response(fake_source):
    """Accept: JSON sur /edit → JSON + card_html."""
    body = b"id=ubm-001&title=Nouveau&types=film"
    h = _FakeHandler(fake_source, "/edit", body, accept="application/json")
    h.do_POST()
    assert h._status == 200
    payload = json.loads(h.wfile.getvalue().decode("utf-8"))
    assert payload["kind"] == "success"
    assert "Nouveau" in payload["card_html"]


def test_post_invalid_id_json_response(fake_source):
    """Accept JSON + reco_id invalide → JSON kind=error, status 200 (UI gère)."""
    h = _FakeHandler(fake_source, "/edit", b"id=../bad",
                     accept="application/json")
    h.do_POST()
    assert h._status == 200
    payload = json.loads(h.wfile.getvalue().decode("utf-8"))
    assert payload["kind"] == "error"
    assert payload["card_html"] == ""


def test_get_card_returns_fragment(fake_source):
    """GET /card?id=ubm-001 → fragment HTML (li.row) sans le shell de page."""
    h = _FakeHandler(fake_source, "/card?id=ubm-001")
    h.do_GET()
    assert h._status == 200
    body = h.wfile.getvalue().decode("utf-8")
    assert "<li class=\"row" in body
    # Fragment seul : pas le shell complet (pas de <body>, pas de <h1>).
    assert "<body>" not in body
    assert "<h1>" not in body


def test_get_card_invalid_id(fake_source):
    h = _FakeHandler(fake_source, "/card?id=../bad")
    h.do_GET()
    assert h._status == 404


def test_get_card_unknown_id(fake_source):
    h = _FakeHandler(fake_source, "/card?id=ubm-zzz")
    h.do_GET()
    assert h._status == 404


def test_shell_includes_client_js_and_toast_zone():
    """La coquille HTML doit injecter le JS client + le container toast."""
    out = rs._shell("Test", "subtitle", "<p>inner</p>")
    assert 'id="toast-zone"' in out
    assert "<script>" in out
    assert "fetch(action" in out


def test_kind_for_empty_returns_info():
    """Garde-fou : statuts vides → kind 'info' (fallback défensif)."""
    from review_edit import _kind_for
    assert _kind_for([]) == "info"


def test_get_ep_renders_flash_banner(fake_source):
    h = _FakeHandler(
        fake_source,
        "/ep?guid=ep-001&flash=Bravo&kind=success",
        b"",
    )
    h.do_GET()
    assert h._status == 200
    body = h.wfile.getvalue().decode("utf-8")
    assert 'class="flash flash-success"' in body
    assert "Bravo" in body


def test_get_ep_flash_kind_invalid_falls_back_to_info(fake_source):
    h = _FakeHandler(
        fake_source, "/ep?guid=ep-001&flash=hi&kind=<script>", b"",
    )
    h.do_GET()
    body = h.wfile.getvalue().decode("utf-8")
    assert 'flash-info' in body
    # Le kind injecté `<script>` ne doit JAMAIS être interpolé tel quel dans
    # un attribut/balise (le shell contient un <script> légitime pour le JS
    # client, c'est attendu — mais pas avec le payload).
    assert "flash-<script>" not in body
    assert 'class="flash flash-<' not in body


def test_post_reenrich_music_calls_enricher(fake_source, monkeypatch):
    from common import recos_dir_for, read_json
    p = recos_dir_for(fake_source) / "ubm-mus.json"
    p.write_text(json.dumps({
        "id": "ubm-mus", "episodeGuid": "ep-001", "types": ["musique"],
        "title": "Air", "status": "draft",
    }), encoding="utf-8")
    rs._invalidate_reco_path_cache(fake_source)
    calls = []

    def fake_music(reco, *, session, spotify_token=None, force=False):
        calls.append({"force": force, "token": spotify_token})
        reco["externalIds"] = {"deezer": "https://deezer.com/x"}
        reco["_enrich_status"] = "ok"
        return reco

    import enrich_music
    monkeypatch.setattr(enrich_music, "enrich_one", fake_music)
    body = b"id=ubm-mus"
    h = _FakeHandler(fake_source, "/reenrich", body)
    h.do_POST()
    assert calls and calls[0]["force"] is True
    reco = read_json(p)
    assert reco["externalIds"]["deezer"] == "https://deezer.com/x"


def test_post_reenrich_multi_type_calls_both(fake_source, monkeypatch):
    from common import recos_dir_for, read_json
    p = recos_dir_for(fake_source) / "ubm-fa.json"
    p.write_text(json.dumps({
        "id": "ubm-fa", "episodeGuid": "ep-001", "types": ["film", "album"],
        "title": "Mix", "status": "draft",
    }), encoding="utf-8")
    rs._invalidate_reco_path_cache(fake_source)

    tmdb_calls, music_calls = [], []

    def fake_tmdb(reco, *, session, api_key=None, force=False):
        tmdb_calls.append(force)
        reco["_enrich_status"] = "ok"
        return reco

    def fake_music(reco, *, session, spotify_token=None, force=False):
        music_calls.append(force)
        reco["_enrich_status"] = "ok"
        return reco

    import enrich_tmdb, enrich_music  # noqa: E401
    monkeypatch.setattr(enrich_tmdb, "enrich_one", fake_tmdb)
    monkeypatch.setattr(enrich_music, "enrich_one", fake_music)
    body = b"id=ubm-fa"
    h = _FakeHandler(fake_source, "/reenrich", body)
    h.do_POST()
    assert tmdb_calls == [True]
    assert music_calls == [True]


def test_post_reenrich_non_targetable_is_noop(fake_source, monkeypatch):
    """Une reco de type 'livre' n'est traitée par aucun enricher."""
    from common import read_json, recos_dir_for
    calls = []

    def boom(*args, **kwargs):
        calls.append(1)
        raise AssertionError("ne devrait pas être appelé")

    import enrich_tmdb, enrich_music  # noqa: E401
    monkeypatch.setattr(enrich_tmdb, "enrich_one", boom)
    monkeypatch.setattr(enrich_music, "enrich_one", boom)
    body = b"id=ubm-002"  # type=livre
    h = _FakeHandler(fake_source, "/reenrich", body)
    h.do_POST()
    assert h._status == 303
    assert h._sent_headers["Location"].startswith("/ep?guid=ep-001")
    assert calls == []
    # JSON inchangé
    reco = read_json(recos_dir_for(fake_source) / "ubm-002.json")
    assert reco["title"] == "Solo"


def test_post_reenrich_api_exception_graceful(fake_source, monkeypatch):
    """L'API lève → log warning, 303 vers /ep, JSON non corrompu."""
    from common import read_json, recos_dir_for

    def kaboom(reco, *, session, api_key=None, force=False):
        raise RuntimeError("API down")

    import enrich_tmdb
    monkeypatch.setattr(enrich_tmdb, "enrich_one", kaboom)
    body = b"id=ubm-001"
    h = _FakeHandler(fake_source, "/reenrich", body)
    h.do_POST()
    assert h._status == 303
    assert h._sent_headers["Location"].startswith("/ep?guid=ep-001")
    reco = read_json(recos_dir_for(fake_source) / "ubm-001.json")
    assert reco["title"] == "Mortel"
    assert "_enrich_status" not in reco


def test_post_reenrich_invalid_id(fake_source):
    body = b"id=../bad"
    h = _FakeHandler(fake_source, "/reenrich", body)
    h.do_POST()
    assert h._status == 303
    assert h._sent_headers["Location"] == "/"


def test_reco_card_shows_edit_and_reenrich_buttons(fake_source):
    """La carte d'une reco enrichissable affiche les 2 boutons."""
    r = {"id": "x", "title": "T", "types": ["film"], "status": "draft"}
    ep = {"guid": "g", "title": "Ep"}
    out = rs._reco_card(r, ep, [], fake_source)
    assert "btn-edit" in out
    assert "btn-reenrich" in out
    assert "/reenrich" in out


def test_reco_card_no_reenrich_for_book(fake_source):
    """Reco de type livre (non enrichissable) : pas de bouton reenrich."""
    r = {"id": "x", "title": "T", "types": ["livre"], "status": "draft"}
    ep = {"guid": "g", "title": "Ep"}
    out = rs._reco_card(r, ep, [], fake_source)
    assert "btn-edit" in out
    assert "btn-reenrich" not in out


# ===== Guests panel + /rename-guest =========================================
def test_get_ep_includes_guests_panel(fake_source):
    h = _FakeHandler(fake_source, "/ep?guid=ep-001")
    h.do_GET()
    body = h.wfile.getvalue().decode("utf-8")
    assert 'class="guests"' in body
    assert '/rename-guest' in body
    assert "ajouter un invité" in body


def test_post_rename_guest_add_redirects_with_flash(fake_source):
    body = b"guid=ep-001&action=add&new=Charlie"
    h = _FakeHandler(fake_source, "/rename-guest", body)
    h.do_POST()
    assert h._status == 303
    loc = h._sent_headers["Location"]
    assert loc.startswith("/ep?guid=ep-001")
    assert "kind=success" in loc
    # L'invité a bien été ajouté dans l'épisode
    from common import find_episode_by_guid, read_json
    ep = read_json(find_episode_by_guid(fake_source, "ep-001"))
    assert "Charlie" in ep.get("guests", [])


def test_post_rename_guest_rename_propagates(fake_source):
    """Renomme Alice → Alicia : tous les recommendedBy sont mis à jour."""
    body = b"guid=ep-001&old=Alice&new=Alicia"
    h = _FakeHandler(fake_source, "/rename-guest", body)
    h.do_POST()
    from common import read_json, recos_dir_for
    r2 = read_json(recos_dir_for(fake_source) / "ubm-002.json")
    assert r2["recommendedBy"] == "Alicia"


def test_post_rename_guest_delete_removes_everywhere(fake_source):
    body = b"guid=ep-001&old=Alice&action=delete"
    h = _FakeHandler(fake_source, "/rename-guest", body)
    h.do_POST()
    from common import read_json, recos_dir_for
    r2 = read_json(recos_dir_for(fake_source) / "ubm-002.json")
    assert "recommendedBy" not in r2


def test_post_rename_guest_invalid_guid_redirects_to_root(fake_source):
    """M6 : un guid avec caractères interdits → /."""
    body = b"guid=../etc/passwd&action=add&new=X"
    h = _FakeHandler(fake_source, "/rename-guest", body)
    h.do_POST()
    assert h._status == 303
    assert h._sent_headers["Location"] == "/"


def test_post_rename_guest_unknown_guid_redirects_to_root(fake_source):
    body = b"guid=ep-999&action=add&new=X"
    h = _FakeHandler(fake_source, "/rename-guest", body)
    h.do_POST()
    assert h._status == 303
    assert h._sent_headers["Location"] == "/"


def test_post_rename_guest_add_host_blocked(fake_source):
    """H1 : ajouter Alice (qui est hôte du podcast) → refusé."""
    body = b"guid=ep-001&action=add&new=Alice"
    h = _FakeHandler(fake_source, "/rename-guest", body)
    h.do_POST()
    loc = h._sent_headers["Location"]
    assert "kind=warning" in loc
    assert "h" in urllib.parse.unquote(loc).lower()  # "hôte" url-encoded


def test_post_rename_guest_missing_guid_redirects_to_root(fake_source):
    body = b"action=add&new=X"
    h = _FakeHandler(fake_source, "/rename-guest", body)
    h.do_POST()
    assert h._sent_headers["Location"] == "/"


# ===== /ep avec overrides + customLinks dans le formulaire ==================
def test_get_ep_with_edit_includes_overrides_section(fake_source):
    """Le formulaire d'édition (sur une reco film) inclut le block override JustWatch."""
    h = _FakeHandler(fake_source, "/ep?guid=ep-001&edit=ubm-001")
    h.do_GET()
    body = h.wfile.getvalue().decode("utf-8")
    assert "JustWatch" in body
    assert "Modifier un lien automatique" in body


def test_post_edit_writes_custom_links_via_form(fake_source):
    body = (b"id=ubm-001&title=Mortel&types=film"
            b"&cl_label_0=FNAC&cl_url_0=https%3A%2F%2Ffnac.com%2Fx&cl_logo_0=")
    h = _FakeHandler(fake_source, "/edit", body)
    h.do_POST()
    from common import read_json, recos_dir_for
    reco = read_json(recos_dir_for(fake_source) / "ubm-001.json")
    assert reco["customLinks"] == [
        {"label": "FNAC", "url": "https://fnac.com/x"}
    ]


def test_post_edit_writes_link_overrides_via_form(fake_source):
    body = (b"id=ubm-001&title=Mortel&types=film"
            b"&lo_JustWatch=https%3A%2F%2Fjustwatch.com%2Fexact")
    h = _FakeHandler(fake_source, "/edit", body)
    h.do_POST()
    from common import read_json, recos_dir_for
    reco = read_json(recos_dir_for(fake_source) / "ubm-001.json")
    assert reco["linkOverrides"] == {"JustWatch": "https://justwatch.com/exact"}


def test_post_edit_with_empty_title_responds_with_error_flash(fake_source):
    """H6 : titre vide → flash d'erreur (kind=error), redirige vers l'épisode."""
    body = b"id=ubm-001&title=&types=film"
    h = _FakeHandler(fake_source, "/edit", body)
    h.do_POST()
    loc = h._sent_headers["Location"]
    assert loc.startswith("/ep?guid=ep-001")
    assert "kind=error" in loc


def test_consume_flash_from_url_strips_params_in_client_js():
    """Le JS embarqué contient bien la fonction qui nettoie les params PRG."""
    out = rs._shell("Test", "sub", "<p/>")
    assert "consumeFlashFromUrl" in out


def test_reco_card_filters_placeholder_guests_from_candidates(fake_source):
    """Un nom 'non spécifié' présent dans ep.guests ne doit pas devenir une checkbox."""
    r = {"id": "x", "title": "T", "types": ["film"], "status": "draft"}
    ep = {"guid": "g", "title": "Ep", "guests": ["non spécifié", "Charlie"]}
    out = rs._reco_card(r, ep, [], fake_source)
    assert "Charlie" in out
    assert "non spécifié" not in out


def test_reco_card_filters_placeholder_in_recommendedBy(fake_source):
    """recommendedBy='non spécifié' n'est pas proposé."""
    r = {"id": "x", "title": "T", "types": ["film"], "status": "draft",
         "recommendedBy": "non spécifié"}
    ep = {"guid": "g", "title": "Ep"}
    out = rs._reco_card(r, ep, [], fake_source)
    assert 'value="non spécifié"' not in out


def test_reco_card_dedups_guests_already_in_candidates(fake_source):
    """Un nom déjà candidate (via hosts/parse) n'est pas ré-ajouté depuis ep.guests."""
    r = {"id": "x", "title": "T", "types": ["film"], "status": "draft"}
    ep = {"guid": "g", "title": "avec Charlie", "guests": ["Charlie"]}
    out = rs._reco_card(r, ep, ["Kyan"], fake_source)
    # Charlie doit apparaître une seule fois
    assert out.count('value="Charlie"') == 1


def test_reco_path_returns_cached_after_warming(fake_source):
    """Premier appel : rebuild. Deuxième appel : retombe sur cache (couverture
    branche `if cached and cached.exists(): return cached`)."""
    p1 = rs._reco_path(fake_source, "ubm-001")
    assert p1 is not None
    p2 = rs._reco_path(fake_source, "ubm-001")
    assert p1 == p2


def test_rebuild_reco_path_cache_skips_corrupt_json(fake_source):
    """Un JSON illisible dans le dossier recos est tolérré (lignes 111-112)."""
    from common import recos_dir_for
    bad = recos_dir_for(fake_source) / "_corrompu.json"
    bad.write_text("{not valid json", encoding="utf-8")
    rs._invalidate_reco_path_cache(fake_source)
    rs._rebuild_reco_path_cache(fake_source)
    # Les autres recos restent indexées normalement.
    assert rs._reco_path(fake_source, "ubm-001") is not None


def test_get_card_for_orphan_reco_returns_404(fake_source):
    """Une reco dont episodeGuid pointe vers un épisode inconnu → 404 sur /card."""
    from common import recos_dir_for
    orphan = recos_dir_for(fake_source) / "ubm-orphan.json"
    orphan.write_text(json.dumps({
        "id": "ubm-orphan", "episodeGuid": "ep-zzz", "types": ["film"],
        "title": "Orphan", "status": "draft",
    }), encoding="utf-8")
    rs._invalidate_reco_path_cache(fake_source)
    h = _FakeHandler(fake_source, "/card?id=ubm-orphan")
    h.do_GET()
    assert h._status == 404


def test_render_index_done_class_when_all_validated(fake_source):
    """Si toutes les recos sont validées → classe `done` sur la miniature."""
    from common import recos_dir_for
    # Marque toutes les recos de ep-001 comme validated
    for fn in ["ubm-001.json", "ubm-003.json"]:
        p = recos_dir_for(fake_source) / fn
        d = json.loads(p.read_text(encoding="utf-8"))
        d["status"] = "validated"
        p.write_text(json.dumps(d), encoding="utf-8")
    out = rs._render_index(fake_source)
    # Avant : 1 draft → not done. Après : 0 draft → "thumb done".
    assert "thumb done" in out


def test_post_edit_json_with_error_returns_error_kind(fake_source):
    """POST /edit avec titre vide en JSON → kind=error dans payload."""
    body = b"id=ubm-001&title=&types=film"
    h = _FakeHandler(fake_source, "/edit", body, accept="application/json")
    h.do_POST()
    assert h._status == 200
    payload = json.loads(h.wfile.getvalue().decode("utf-8"))
    assert payload["kind"] == "error"


def test_rebuild_cache_clears_existing_entries(fake_source):
    """Couvre la branche `del _RECO_PATH_CACHE[k]` (ligne 117) :
    le cache contient déjà des entrées pour la source, rebuild les retire."""
    # Warm-up : remplit le cache.
    assert rs._reco_path(fake_source, "ubm-001") is not None
    assert any(k[0] == fake_source for k in rs._RECO_PATH_CACHE)
    rs._rebuild_reco_path_cache(fake_source)
    # Cache encore peuplé après rebuild (les entrées sont juste refraîchies)
    assert any(k[0] == fake_source for k in rs._RECO_PATH_CACHE)


def test_style_oserror_returns_empty_string(monkeypatch, tmp_path):
    """Couvre `except OSError → return ""` dans _style."""
    import review_render
    review_render._style.cache_clear()
    monkeypatch.setattr(review_render, "_CSS_PATH", tmp_path / "does-not-exist.css")
    assert review_render._style() == ""
    review_render._style.cache_clear()


def test_reco_card_collects_sibling_recommenders(fake_source):
    """Une reco dont un sibling a un recommendedBy : la liste de candidates
    inclut ce nom (ligne 289)."""
    r = {"id": "x", "title": "T", "types": ["film"], "status": "draft"}
    ep = {"guid": "g", "title": "Ep"}
    siblings = [{"id": "y", "recommendedBy": "Camille"}]
    out = rs._reco_card(r, ep, [], fake_source, siblings=siblings)
    assert 'value="Camille"' in out


def test_post_edit_invalid_payload_with_unreadable_reco(fake_source, monkeypatch):
    """Couvre `except (OSError, ValueError)` autour de read_json sur reject."""
    from common import recos_dir_for
    # On rejette via title vide ET on fait planter read_json après coup.
    real_read = rs.read_json
    def picky_read(p):
        if "ubm-001" in str(p):
            raise OSError("simu disk fail")
        return real_read(p)
    monkeypatch.setattr(rs, "read_json", picky_read)
    body = b"id=ubm-001&title=&types=film"
    h = _FakeHandler(fake_source, "/edit", body)
    h.do_POST()
    # On accepte un 303 même en l'absence de guid lisible.
    assert h._status == 303
    # guid manquant → redirige /
    assert h._sent_headers["Location"] == "/"


def test_send_json_post_rebuild_exception_swallowed(fake_source, monkeypatch):
    """Lignes 603-604 : si la reconstruction de la carte plante, on renvoie
    quand même un JSON sans card_html, sans propagation d'exception."""
    # On force _reco_card à planter pendant la rebuild post-/edit.
    real_card = rs._reco_card
    calls = []
    def boom(*a, **kw):
        calls.append(1)
        if calls == [1]:
            raise RuntimeError("rebuild fail")
        return real_card(*a, **kw)
    monkeypatch.setattr(rs, "_reco_card", boom)
    body = b"id=ubm-001&title=NewTitle&types=film"
    h = _FakeHandler(fake_source, "/edit", body, accept="application/json")
    h.do_POST()
    payload = json.loads(h.wfile.getvalue().decode("utf-8"))
    assert payload["kind"] == "success"
    assert payload["card_html"] == ""


def test_get_ep_unknown_guid_returns_back_link(fake_source):
    """GET /ep?guid=inconnu renvoie un message + lien de retour."""
    h = _FakeHandler(fake_source, "/ep?guid=inconnu")
    h.do_GET()
    body = h.wfile.getvalue().decode("utf-8")
    assert "introuvable" in body
