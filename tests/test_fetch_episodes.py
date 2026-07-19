"""Tests de tools/fetch_episodes.py — parsing RSS, idempotence, gestion d'erreurs."""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
import responses

import fetch_episodes
from fetch_episodes import (
    _build_episode,
    _clean_description,
    _extract_audio_url,
    _extract_number,
    _filename_for,
    _parse_date,
    _parse_duration,
    _stable_guid,
    fetch_episodes as run_fetch,
)


# ===== _parse_date ========================================================
def test_parse_date_uses_published_parsed():
    entry = SimpleNamespace(published_parsed=time.struct_time((2024, 3, 15, 10, 0, 0, 0, 0, 0)))
    assert _parse_date(entry) == "2024-03-15"


def test_parse_date_falls_back_to_updated_parsed():
    # `published_parsed` absent → on prend `updated_parsed`.
    entry = SimpleNamespace(
        published_parsed=None,
        updated_parsed=time.struct_time((2023, 1, 1, 0, 0, 0, 0, 0, 0)),
    )
    assert _parse_date(entry) == "2023-01-01"


def test_parse_date_returns_none_when_no_field():
    entry = SimpleNamespace()
    assert _parse_date(entry) is None


def test_parse_date_invalid_struct_time_returns_none():
    """L3 (revue 2026-07-19) — un struct_time mal formé (mois=0) ne doit pas
    faire lever datetime() : on renvoie None plutôt que casser le fetch."""
    entry = SimpleNamespace(
        published_parsed=time.struct_time((2024, 0, 0, 0, 0, 0, 0, 0, 0)))
    assert _parse_date(entry) is None


def test_parse_date_out_of_range_day_returns_none():
    """Jour hors bornes (32) → None (robustesse sur flux bancals)."""
    entry = SimpleNamespace(
        published_parsed=time.struct_time((2024, 13, 32, 0, 0, 0, 0, 0, 0)))
    assert _parse_date(entry) is None


# ===== _extract_number ====================================================
@pytest.mark.parametrize("title,expected", [
    ("Caballero (#312)", 312),
    ("Ep 42 — invité X", 42),
    ("Épisode 7 — pilote", 7),
    ("Ep.99 — direct", 99),
    ("Simple titre sans numéro", None),
])
def test_extract_number_from_title(title, expected):
    assert _extract_number({"title": title}) == expected


def test_extract_number_prefers_itunes_episode():
    # La balise itunes l'emporte sur ce que dirait le titre.
    assert _extract_number({"itunes_episode": "55", "title": "ep 99"}) == 55


def test_extract_number_invalid_itunes_falls_back_to_title():
    assert _extract_number({"itunes_episode": "abc", "title": "Ep 12"}) == 12


def test_extract_number_ignores_year_in_itunes_tag():
    """Tag <itunes:episode> contenant une année (2024) → ignoré."""
    # Avec un titre sans numéro → None.
    assert _extract_number({"itunes_episode": "2024", "title": "Hors-série"}) is None


def test_extract_number_ignores_year_pattern_in_title():
    """« Épisode 2024 » est probablement l'année, pas un numéro d'épisode."""
    assert _extract_number({"title": "Episode 2024 — bilan"}) is None


def test_extract_number_keeps_low_numbers():
    """Un numéro plausible (<1990) est conservé."""
    assert _extract_number({"itunes_episode": "1989"}) == 1989


def test_extract_number_empty_dict_returns_none():
    # Entrée RSS sans titre, description, ni `itunes_episode` : aucun numéro
    # à extraire. (Le nom précédent évoquait des entrées non-dict, mais
    # `_extract_number` appelle `.get` — on teste donc un dict vide,
    # cas réaliste où le parseur RSS renvoie une entry minimale.)
    assert _extract_number({}) is None


# ===== _parse_duration ====================================================
@pytest.mark.parametrize("raw,expected", [
    ("3600", 3600),
    ("60:00", 3600),
    ("1:00:00", 3600),
    ("1:30:15", 5415),
    ("45:30", 2730),
    (None, None),
    ("", None),
    ("nawak", None),
    ("12:ab", None),
    # 0 ou négatif : valeurs inutilisables → None.
    ("0", None),
    ("0:00", None),
    ("0:00:00", None),
])
def test_parse_duration_various_formats(raw, expected):
    assert _parse_duration(raw) == expected


# ===== _extract_audio_url =================================================
def test_extract_audio_url_prefers_audio_enclosure():
    entry = {"enclosures": [{"href": "https://x/a.mp3", "type": "audio/mpeg"}]}
    assert _extract_audio_url(entry) == "https://x/a.mp3"


def test_extract_audio_url_accepts_unknown_type():
    # Type vide → on accepte quand même (cas Acast historique).
    entry = {"enclosures": [{"url": "https://x/a.mp3", "type": ""}]}
    assert _extract_audio_url(entry) == "https://x/a.mp3"


def test_extract_audio_url_skips_non_audio():
    entry = {
        "enclosures": [{"href": "https://x/img.jpg", "type": "image/jpeg"}],
        "links": [],
    }
    assert _extract_audio_url(entry) is None


def test_extract_audio_url_falls_back_to_links_enclosure():
    entry = {
        "enclosures": [],
        "links": [{"rel": "enclosure", "href": "https://x/a.mp3"}],
    }
    assert _extract_audio_url(entry) == "https://x/a.mp3"


def test_extract_audio_url_empty():
    # Cas où aucune source n'est exploitable.
    assert _extract_audio_url({"enclosures": [], "links": []}) is None


# ===== _stable_guid =======================================================
def test_stable_guid_uses_id():
    assert _stable_guid({"id": "  acast-guid-1  "}) == "acast-guid-1"


def test_stable_guid_falls_back_to_link():
    assert _stable_guid({"link": "https://x/ep/42"}) == "https://x/ep/42"


def test_stable_guid_falls_back_to_title_slug():
    g = _stable_guid({"title": "Bérengère KRIEF"})
    assert g and g.startswith("title-") and "berengere" in g


def test_stable_guid_returns_none_when_nothing():
    assert _stable_guid({}) is None


# ===== _clean_description =================================================
def test_clean_description_strips_html_and_acast_footer():
    raw = (
        "<p>Bonjour <b>monde</b></p>"
        "<p>Hébergé par Acast. Visitez acast.com/privacy</p>"
    )
    cleaned = _clean_description(raw)
    assert "Bonjour monde" in cleaned
    assert "Acast" not in cleaned


def test_clean_description_handles_hr_split():
    raw = "<p>Contenu principal</p><hr/><p>Hébergé par Acast.</p>"
    cleaned = _clean_description(raw)
    assert "Contenu principal" in cleaned
    assert "Acast" not in cleaned


def test_clean_description_decodes_html_entities():
    assert "L'été" in _clean_description("L&#39;&eacute;t&eacute;")


def test_clean_description_collapses_blank_lines():
    raw = "<p>A</p><br/><br/><br/><p>B</p>"
    cleaned = _clean_description(raw)
    # Au plus une ligne vide entre A et B.
    assert "\n\n\n" not in cleaned


# ===== _build_episode =====================================================
class _Entry(dict):
    """Imite feedparser : accès par attribut ET par clé."""
    def __getattr__(self, name):
        try:
            return self[name]
        except KeyError as exc:
            raise AttributeError(name) from exc


def test_build_episode_complete():
    entry = _Entry(
        id="guid-1",
        title="Caballero (Un Bon Moment, S5-E32)",
        itunes_episode="32",
        itunes_duration="1:02:03",
        enclosures=[{"href": "https://x/a.mp3", "type": "audio/mpeg"}],
        summary="<p>Résumé</p>",
        published_parsed=time.struct_time((2024, 4, 1, 0, 0, 0, 0, 0, 0)),
    )
    ep = _build_episode("ubm", entry)
    assert ep is not None
    assert ep["sourceId"] == "ubm"
    assert ep["guid"] == "guid-1"
    assert ep["season"] == 5
    assert ep["number"] == 32  # Le motif SX-EX écrase le itunes_episode (par design).
    assert ep["date"] == "2024-04-01"
    assert ep["audioUrl"] == "https://x/a.mp3"
    assert ep["audioDuration"] == 3723
    assert ep["description"] == "Résumé"
    assert ep["guests"] == []
    assert ep["transcriptStatus"] == "none"


def test_build_episode_returns_none_without_guid_source():
    # Aucun id/link/title → pas de guid stable → None.
    assert _build_episode("ubm", {}) is None


def test_build_episode_uses_default_title_when_missing():
    ep = _build_episode("ubm", {"id": "g-1"})
    assert ep is not None and ep["title"] == "Sans titre"


def test_build_episode_without_enclosures_or_duration():
    entry = {"id": "g-2", "title": "Brut"}
    ep = _build_episode("ubm", entry)
    assert ep is not None
    assert "audioUrl" not in ep
    assert "audioDuration" not in ep
    assert "description" not in ep
    assert "date" not in ep


# ===== _filename_for ======================================================
def test_filename_for_uses_number_padding():
    assert _filename_for({"number": 7, "guid": "g"}) == "ep-007.json"


def test_filename_for_falls_back_to_slug_guid():
    assert _filename_for({"guid": "Bérengère"}) == "berengere.json"


# ===== fetch_episodes (intégration avec feedparser mocké) =================
def _make_fake_feed(entries: list[dict], bozo: bool = False, bozo_exc: Any = None):
    """Construit un faux objet feedparser avec `.entries` / `.bozo`."""
    feed = SimpleNamespace(entries=entries, bozo=bozo, bozo_exception=bozo_exc)
    return feed


@pytest.fixture
def isolated_dirs(tmp_path, monkeypatch):
    """Isole SOURCES_DIR / EPISODES_DIR dans un tmp_path pour ne rien polluer.

    Stub aussi `requests.get` : le pipeline télécharge le flux RSS via
    `requests.get(rss_url)` puis passe `resp.text` à `feedparser.parse`.
    Les tests gardent leur stub de `feedparser.parse` ignorant l'argument.
    """
    import common
    sources = tmp_path / "sources"
    episodes = tmp_path / "episodes"
    sources.mkdir()
    episodes.mkdir()
    monkeypatch.setattr(common, "SOURCES_DIR", sources)
    monkeypatch.setattr(common, "EPISODES_DIR", episodes)

    # `.content` (bytes) ET `.text` : le pipeline passe désormais les OCTETS à
    # feedparser (M2 — évite le mojibake ISO-8859-1 sur un text/xml sans charset).
    fake_resp = SimpleNamespace(
        text="<rss/>", content=b"<rss/>", raise_for_status=lambda: None,
    )
    monkeypatch.setattr(fetch_episodes.requests, "get",
                        lambda url, **kw: fake_resp)
    return SimpleNamespace(sources=sources, episodes=episodes, root=tmp_path)


def _write_source(sources_dir: Path, source_id: str, data: dict) -> None:
    (sources_dir / f"{source_id}.json").write_text(
        json.dumps(data, ensure_ascii=False), encoding="utf-8"
    )


def test_fetch_episodes_raises_without_rss(isolated_dirs):
    _write_source(isolated_dirs.sources, "ubm", {"id": "ubm"})  # pas de rssUrl
    with pytest.raises(ValueError, match="rssUrl"):
        run_fetch("ubm")


def test_fetch_episodes_bozo_with_no_entries_raises(isolated_dirs, monkeypatch):
    _write_source(isolated_dirs.sources, "ubm", {"id": "ubm", "rssUrl": "https://x/rss"})
    fake_feed = _make_fake_feed([], bozo=True, bozo_exc="oops")
    monkeypatch.setattr(fetch_episodes.feedparser, "parse", lambda url: fake_feed)
    with pytest.raises(RuntimeError, match="parsing RSS"):
        run_fetch("ubm")


def test_fetch_episodes_passes_bytes_to_feedparser(isolated_dirs, monkeypatch):
    """M2 (revue 2026-07-19) — on passe les OCTETS (resp.content) à feedparser,
    pas resp.text : sinon un flux text/xml sans charset est décodé en
    ISO-8859-1 (mojibake des accents) AVANT feedparser."""
    _write_source(isolated_dirs.sources, "ubm", {"id": "ubm", "rssUrl": "https://x/rss"})
    captured = {}

    def _capture(arg):
        captured["arg"] = arg
        return _make_fake_feed([], bozo=False)

    monkeypatch.setattr(fetch_episodes.feedparser, "parse", _capture)
    run_fetch("ubm")
    assert isinstance(captured["arg"], bytes)


def test_fetch_episodes_writes_new_files(isolated_dirs, monkeypatch):
    _write_source(isolated_dirs.sources, "ubm", {"id": "ubm", "rssUrl": "https://x/rss"})
    entries = [
        {
            "id": "g-1",
            "title": "Caballero (Un Bon Moment, S5-E32)",
            "itunes_duration": "60:00",
            "enclosures": [{"href": "https://x/1.mp3", "type": "audio/mpeg"}],
            "published_parsed": time.struct_time((2024, 4, 1, 0, 0, 0, 0, 0, 0)),
            "summary": "<p>R1</p>",
        },
        {
            "id": "g-2",
            "title": "Invité libre #99",
            "enclosures": [{"href": "https://x/2.mp3", "type": "audio/mpeg"}],
            "published_parsed": time.struct_time((2024, 4, 8, 0, 0, 0, 0, 0, 0)),
        },
        {
            # Entrée sans guid exploitable → ignorée.
            "title": None,
        },
    ]
    monkeypatch.setattr(
        fetch_episodes.feedparser, "parse",
        lambda url: _make_fake_feed(entries),
    )
    written = run_fetch("ubm")
    assert written == 2
    out_dir = isolated_dirs.episodes / "ubm"
    files = sorted(p.name for p in out_dir.glob("*.json"))
    # ep-032.json (S5-E32) et ep-099.json (#99 dans le titre).
    assert "ep-032.json" in files
    assert "ep-099.json" in files


def test_fetch_episodes_limit_truncates(isolated_dirs, monkeypatch):
    _write_source(isolated_dirs.sources, "ubm", {"id": "ubm", "rssUrl": "https://x/rss"})
    entries = [
        {"id": f"g-{i}", "title": f"#{i}",
         "enclosures": [{"href": f"https://x/{i}.mp3", "type": "audio/mpeg"}]}
        for i in range(1, 6)
    ]
    monkeypatch.setattr(
        fetch_episodes.feedparser, "parse",
        lambda url: _make_fake_feed(entries),
    )
    written = run_fetch("ubm", limit=2)
    assert written == 2


def test_fetch_episodes_rss_override_used(isolated_dirs, monkeypatch):
    _write_source(isolated_dirs.sources, "ubm", {"id": "ubm"})  # pas de rssUrl
    received = {}

    def fake_get(url, **kw):
        received["url"] = url
        return SimpleNamespace(text="<rss/>", content=b"<rss/>",
                               raise_for_status=lambda: None)

    monkeypatch.setattr(fetch_episodes.requests, "get", fake_get)
    monkeypatch.setattr(fetch_episodes.feedparser, "parse",
                        lambda _txt: _make_fake_feed([]))
    # Pas de bozo et pas d'entries → 0 écrit, mais on a quand même appelé requests.
    written = run_fetch("ubm", rss_override="https://override/rss")
    assert written == 0
    assert received["url"] == "https://override/rss"


def test_fetch_episodes_idempotent_no_rewrite(isolated_dirs, monkeypatch):
    """Deuxième passage sur le même flux → 0 écriture."""
    _write_source(isolated_dirs.sources, "ubm", {"id": "ubm", "rssUrl": "https://x/rss"})
    entries = [
        {"id": "g-1", "title": "Ep 1",
         "enclosures": [{"href": "https://x/1.mp3", "type": "audio/mpeg"}]}
    ]
    monkeypatch.setattr(
        fetch_episodes.feedparser, "parse",
        lambda url: _make_fake_feed(entries),
    )
    assert run_fetch("ubm") == 1
    assert run_fetch("ubm") == 0  # idempotence


def test_fetch_episodes_preserves_transcript_and_guests(isolated_dirs, monkeypatch):
    """Sur réécriture, on préserve transcriptStatus=auto, guests manuels, youtubeUrl."""
    _write_source(isolated_dirs.sources, "ubm", {"id": "ubm", "rssUrl": "https://x/rss"})
    out_dir = isolated_dirs.episodes / "ubm"
    out_dir.mkdir(parents=True, exist_ok=True)
    # Fichier existant avec état avancé du pipeline.
    existing = {
        "sourceId": "ubm",
        "guid": "g-1",
        "title": "Ancien titre",
        "transcriptStatus": "auto",
        "guests": [{"name": "Manuel"}],
        "youtubeUrl": "https://www.youtube.com/watch?v=DEJA",
    }
    (out_dir / "ep-001.json").write_text(json.dumps(existing), encoding="utf-8")

    entries = [
        {"id": "g-1", "title": "Nouveau titre #1",
         "enclosures": [{"href": "https://x/1.mp3", "type": "audio/mpeg"}]}
    ]
    monkeypatch.setattr(
        fetch_episodes.feedparser, "parse",
        lambda url: _make_fake_feed(entries),
    )
    assert run_fetch("ubm") == 1
    merged = json.loads((out_dir / "ep-001.json").read_text(encoding="utf-8"))
    assert merged["title"] == "Nouveau titre #1"
    assert merged["transcriptStatus"] == "auto"     # préservé
    assert merged["guests"] == [{"name": "Manuel"}]  # préservé
    assert merged["youtubeUrl"].endswith("=DEJA")    # préservé


def test_fetch_episodes_invalid_rss_url_raises(isolated_dirs):
    """URL ne commençant pas par http(s):// → ValueError explicite."""
    _write_source(isolated_dirs.sources, "ubm",
                  {"id": "ubm", "rssUrl": "ftp://nope/rss"})
    with pytest.raises(ValueError, match="invalide"):
        run_fetch("ubm")


def test_fetch_episodes_http_failure_raises(isolated_dirs, monkeypatch):
    """`requests.get` qui plante → RuntimeError clair."""
    import requests as requests_lib
    _write_source(isolated_dirs.sources, "ubm",
                  {"id": "ubm", "rssUrl": "https://x/rss"})

    def boom(url, **kw):
        raise requests_lib.ConnectionError("offline")

    monkeypatch.setattr(fetch_episodes.requests, "get", boom)
    with pytest.raises(RuntimeError, match="Téléchargement RSS"):
        run_fetch("ubm")


def test_fetch_episodes_corrupt_existing_logs_warning(isolated_dirs, monkeypatch, caplog):
    """Le fichier d'épisode corrompu déclenche un log.warning explicite."""
    _write_source(isolated_dirs.sources, "ubm", {"id": "ubm", "rssUrl": "https://x/rss"})
    out_dir = isolated_dirs.episodes / "ubm"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "broken.json").write_text("{ pas du JSON", encoding="utf-8")

    monkeypatch.setattr(
        fetch_episodes.feedparser, "parse",
        lambda _txt: _make_fake_feed([]),
    )
    import logging
    with caplog.at_level(logging.WARNING, logger="reco"):
        run_fetch("ubm")
    assert any("corrompu" in r.message.lower() for r in caplog.records)


def test_fetch_episodes_skips_corrupt_existing_index(isolated_dirs, monkeypatch):
    """Un fichier corrompu dans le dossier d'épisodes n'empêche pas le fetch."""
    _write_source(isolated_dirs.sources, "ubm", {"id": "ubm", "rssUrl": "https://x/rss"})
    out_dir = isolated_dirs.episodes / "ubm"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "broken.json").write_text("{ pas du JSON", encoding="utf-8")

    entries = [
        {"id": "g-1", "title": "Ep 1",
         "enclosures": [{"href": "https://x/1.mp3", "type": "audio/mpeg"}]}
    ]
    monkeypatch.setattr(
        fetch_episodes.feedparser, "parse",
        lambda url: _make_fake_feed(entries),
    )
    # Le fetch doit fonctionner et créer un nouveau fichier.
    assert run_fetch("ubm") == 1


def test_main_invokes_fetch_episodes(monkeypatch):
    captured = {}

    def fake(source, limit=None, rss_override=None):
        captured.update(dict(source=source, limit=limit, rss=rss_override))
        return 0

    monkeypatch.setattr(fetch_episodes, "fetch_episodes", fake)
    monkeypatch.setattr(sys, "argv",
                        ["fetch_episodes.py", "--source", "ubm",
                         "--limit", "3", "--rss", "https://x/rss"])
    fetch_episodes.main()
    assert captured == {"source": "ubm", "limit": 3, "rss": "https://x/rss"}


def test_main_requires_source(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["fetch_episodes.py"])
    with pytest.raises(SystemExit):
        fetch_episodes.main()


def test_fetch_episodes_collision_falls_back_to_guid_slug(isolated_dirs, monkeypatch):
    """Si ep-NNN.json existe déjà mais pour un AUTRE guid, repli sur slug(guid)."""
    _write_source(isolated_dirs.sources, "ubm", {"id": "ubm", "rssUrl": "https://x/rss"})
    out_dir = isolated_dirs.episodes / "ubm"
    out_dir.mkdir(parents=True, exist_ok=True)
    # Fichier orphelin existant qui prend la place de ep-001.json mais avec un AUTRE guid
    # (et qui n'est PAS indexé car _existing_index ne le verra qu'avec son guid 'autre').
    # On force la collision : ep-001.json existe avec guid="autre", non listé dans le flux.
    (out_dir / "ep-001.json").write_text(
        json.dumps({"guid": "autre", "title": "Squatteur"}), encoding="utf-8"
    )

    entries = [
        {"id": "g-1", "title": "Ep 1",
         "enclosures": [{"href": "https://x/1.mp3", "type": "audio/mpeg"}]}
    ]
    monkeypatch.setattr(
        fetch_episodes.feedparser, "parse",
        lambda url: _make_fake_feed(entries),
    )
    assert run_fetch("ubm") == 1
    # Le nouveau fichier doit utiliser le slug du guid, PAS écraser ep-001.
    files = sorted(p.name for p in out_dir.glob("*.json"))
    assert "ep-001.json" in files
    assert any(name.startswith("g-1") for name in files)
