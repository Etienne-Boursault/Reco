"""Tests des helpers de match YouTube (tools/match_youtube.py)."""
from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

import match_youtube as my
from common import extract_youtube_id as _video_id  # alias local pour les tests
from match_youtube import (
    _apply_video_meta,
    _normalize,
    _parse_se,
    _select_best_video,
    _similarity,
    match_youtube,
)


# ===== _normalize =========================================================
def test_normalize_strips_accents_and_lowercases():
    assert _normalize("Bérengère") == _normalize("BERENGERE") == _normalize("berengere")


def test_normalize_removes_punctuation():
    a = _normalize("Mortel, S1-E1")
    b = _normalize("mortel s1e1")
    # On veut au moins que les lettres significatives soient égales.
    assert "mortel" in a and "mortel" in b


def test_normalize_empty_string():
    assert _normalize("") == ""


# ===== _similarity ========================================================
def test_similarity_identical_is_max():
    assert _similarity("hello world", "hello world") == 1.0


def test_similarity_close_strings_higher_than_unrelated():
    """Score relatif : 1 lettre près > zéro recouvrement."""
    close = _similarity("hello world", "helo world")
    far = _similarity("hello world", "azerty qsdf")
    assert close > far


def test_similarity_word_inclusion_boosts_score():
    """Le RSS court contenu dans le titre YT complet doit dépasser 0.85
    (cf. règle d'inclusion dans _similarity pour les « avec Waly » → « Un Bon Moment avec WALY DIA »)."""
    # Tous les tokens significatifs (>1 char, hors stopwords) de a sont dans b
    rss = "avec waly"
    yt = "un bon moment avec waly dia"
    assert _similarity(rss, yt) >= 0.9


def test_similarity_unrelated_strings_low():
    assert _similarity("abcdef", "zyxwvu") < 0.3


def test_similarity_handles_empty_strings():
    """Pas de garantie sémantique forte sur le cas empty/empty, juste qu'on
    ne crashe pas et que le score est dans [0, 1]."""
    score = _similarity("", "")
    assert 0.0 <= score <= 1.0


# ===== _parse_se ==========================================================
@pytest.mark.parametrize("title,expected", [
    ("Caballero et JeanJass (Un Bon Moment, S5-E32)", (5, 32)),
    ("Pierre Niney (S5-E15)", (5, 15)),
    ("avec Kheiron (S1-E10)", (1, 10)),
    ("avec HAROUN",       (None, None)),
    ("Hozier discography", (None, None)),
])
def test_parse_se_extracts_season_episode(title, expected):
    assert _parse_se(title) == expected


def test_parse_se_handles_lowercase():
    assert _parse_se("Episode (s5-e32)") == (5, 32)


def test_parse_se_handles_various_separators():
    # Variantes vues dans la nature : S5·E32, S5.E32, S5–E32.
    for sep in ("-", "·", ".", "–"):
        assert _parse_se(f"(S5{sep}E32)") == (5, 32)


# ===== _video_id ==========================================================
def test_video_id_extracts_from_watch_url():
    assert _video_id("https://www.youtube.com/watch?v=dQw4w9WgXcQ") == "dQw4w9WgXcQ"


def test_video_id_handles_extra_params():
    assert _video_id("https://www.youtube.com/watch?v=ABCD&t=42s") == "ABCD"


def test_video_id_returns_none_for_non_url():
    assert _video_id("not a url") is None
    assert _video_id("") is None
    assert _video_id(None) is None  # type: ignore[arg-type]


# ===== _build_suffix_regex / _normalize avec suffixes configurables ========
from match_youtube import _build_suffix_regex  # noqa: E402


def test_build_suffix_regex_empty_returns_none():
    assert _build_suffix_regex(()) is None


def test_build_suffix_regex_strips_listed_fragments():
    r = _build_suffix_regex(("foo bar", "baz"))
    assert r is not None
    assert r.sub(" ", "Titre (Foo Bar, S1-E2)") == "Titre  "
    assert r.sub(" ", "Titre (BAZ, ext)") == "Titre  "


def test_normalize_uses_explicit_suffix_pattern():
    """Avec un pattern custom passé explicitement, _normalize strip celui-là
    plutôt que le legacy hard-codé."""
    r = _build_suffix_regex(("flood emission",))
    # Le suffix-regex tape avant normalize_text (donc avant strip d'accents).
    # On utilise des fragments sans accent pour rester déterministe.
    out = _normalize("Hozier (Flood Emission, S3-E1)", r)
    assert "flood" not in out


def test_normalize_no_suffix_re_uses_legacy_fallback():
    """Si suffix_re est None, on retombe sur le legacy (UBM / AGT) —
    nécessaire pour conserver la rétro-compat des helpers exposés."""
    assert "un bon moment" not in _normalize("Caballero (Un Bon Moment, S5-E32)")


# ===== M5 : _select_best_video (départage des ex æquo du boost) ============
def _nv(videos):
    """Prépare la liste (video, titre normalisé) attendue par _select_best_video."""
    return [(v, _normalize(v["title"])) for v in videos]


def test_select_best_video_single_top_returns_it():
    """Cas nominal : un unique meilleur score → renvoyé tel quel."""
    videos = [
        {"id": "a", "title": "Un Bon Moment avec Waly Dia", "duration": 3600},
        {"id": "b", "title": "Documentaire sur les abeilles", "duration": 3600},
    ]
    best, score = _select_best_video("avec waly", _nv(videos))
    assert best["id"] == "a"
    assert score >= 0.9


def test_select_best_video_ambiguous_inclusion_without_duration_returns_none():
    """M5 — 2 vidéos contiennent le token RSS (boost 0.90 sur les deux) et
    aucune durée pour départager → PAS d'association confiante arbitraire."""
    videos = [
        {"id": "a", "title": "Un Bon Moment avec Waly Dia partie 1"},
        {"id": "b", "title": "Un Bon Moment avec Waly Dia partie 2"},
    ]
    best, score = _select_best_video("avec waly", _nv(videos))
    assert best is None
    assert score >= 0.9  # le score plafonne au boost, mais pas de choix arbitraire


def test_select_best_video_ambiguous_resolved_by_duration():
    """M5 — ex æquo départagés par proximité de durée (audioDuration)."""
    videos = [
        {"id": "a", "title": "Un Bon Moment avec Waly Dia partie 1", "duration": 3600},
        {"id": "b", "title": "Un Bon Moment avec Waly Dia partie 2", "duration": 7200},
    ]
    # audioDuration ≈ 3500 s → la vidéo « a » (3600) est la plus proche.
    best, score = _select_best_video("avec waly", _nv(videos), audio_duration=3500)
    assert best["id"] == "a"


def test_select_best_video_equal_distance_stays_ambiguous():
    """Distances de durée égales → toujours ambigu → None."""
    videos = [
        {"id": "a", "title": "Un Bon Moment avec Waly Dia A", "duration": 3000},
        {"id": "b", "title": "Un Bon Moment avec Waly Dia B", "duration": 4000},
    ]
    # audioDuration = 3500 → |3000-3500| == |4000-3500| == 500 → indépartageable.
    best, _ = _select_best_video("avec waly", _nv(videos), audio_duration=3500)
    assert best is None


def test_select_best_video_empty_candidates():
    best, score = _select_best_video("quoi que ce soit", [])
    assert best is None
    assert score == 0.0


# ===== L2 : _apply_video_meta ne doit pas écraser season/number ============
def test_apply_video_meta_fills_absent_season_number():
    ep = {}
    changed = _apply_video_meta(ep, {"title": "Titre (S5-E32)", "duration": 3600})
    assert changed is True
    assert ep["season"] == 5
    assert ep["number"] == 32
    assert ep["youtubeDuration"] == 3600
    assert ep["youtubeTitle"] == "Titre (S5-E32)"


def test_apply_video_meta_does_not_overwrite_existing_season_number():
    """L2 (revue 2026-07-19) — season/number déjà présents ne sont PAS écrasés
    sans --force (le RSS peut être plus fiable que le suffixe YT)."""
    ep = {"season": 4, "number": 12}
    _apply_video_meta(ep, {"title": "Titre (S5-E32)", "duration": 3600})
    assert ep["season"] == 4   # préservé
    assert ep["number"] == 12  # préservé
    # Les métadonnées purement YT restent synchronisées.
    assert ep["youtubeDuration"] == 3600
    assert ep["youtubeTitle"] == "Titre (S5-E32)"


def test_apply_video_meta_force_overwrites_season_number():
    ep = {"season": 4, "number": 12}
    changed = _apply_video_meta(ep, {"title": "Titre (S5-E32)"}, force=True)
    assert changed is True
    assert ep["season"] == 5
    assert ep["number"] == 32


def test_apply_video_meta_no_change_returns_false():
    ep = {"youtubeTitle": "T", "youtubeDuration": 3600, "season": 5, "number": 1}
    assert _apply_video_meta(ep, {"title": "T", "duration": 3600}) is False


def test_apply_video_meta_invalid_duration_ignored():
    ep = {}
    _apply_video_meta(ep, {"title": "Sans SE", "duration": "pas un entier"})
    assert "youtubeDuration" not in ep


# ===== match_youtube (intégration, yt-dlp mocké) ===========================
@pytest.fixture
def yt_dirs(tmp_path, monkeypatch):
    """Isole SOURCES_DIR / EPISODES_DIR et neutralise la config typée pour
    forcer le fallback legacy `load_source` (pas de SSOT typée en tmp)."""
    import common
    sources = tmp_path / "sources"
    episodes = tmp_path / "episodes"
    sources.mkdir()
    episodes.mkdir()
    monkeypatch.setattr(common, "SOURCES_DIR", sources)
    monkeypatch.setattr(common, "EPISODES_DIR", episodes)

    # Force le fallback legacy : get_source lève → on lit load_source.
    def _boom_get_source(_sid):
        raise RuntimeError("pas de config typée en test")

    monkeypatch.setattr(my, "get_source", _boom_get_source)
    return SimpleNamespace(sources=sources, episodes=episodes)


def _write_source(sources_dir, source_id, data):
    (sources_dir / f"{source_id}.json").write_text(
        json.dumps(data, ensure_ascii=False), encoding="utf-8")


def _write_episode(episodes_dir, source_id, name, data):
    d = episodes_dir / source_id
    d.mkdir(parents=True, exist_ok=True)
    (d / name).write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def test_match_youtube_raises_without_channel(yt_dirs):
    _write_source(yt_dirs.sources, "ubm", {"id": "ubm"})  # pas de youtubeChannel
    with pytest.raises(ValueError, match="youtubeChannel"):
        match_youtube("ubm", threshold=0.5, force=False, dry_run=False)


def test_match_youtube_no_videos_returns_zero(yt_dirs, monkeypatch):
    _write_source(yt_dirs.sources, "ubm",
                  {"id": "ubm", "youtubeChannel": "https://youtube.com/@ubm"})
    monkeypatch.setattr(my, "_fetch_channel_videos", lambda url: [])
    assert match_youtube("ubm", threshold=0.5, force=False, dry_run=False) == 0


def test_match_youtube_typed_config_success_path(monkeypatch):
    """Couvre le chemin config typée (get_source réussit sur la SSOT réelle
    « un-bon-moment » qui déclare un youtubeChannel)."""
    monkeypatch.setattr(my, "_fetch_channel_videos", lambda url: [])
    # get_source("un-bon-moment") lit la vraie config → channel non vide, mais
    # aucune vidéo → retour 0 avant même de lister les épisodes.
    assert match_youtube("un-bon-moment", 0.5, False, False) == 0


def test_match_youtube_links_new_episode(yt_dirs, monkeypatch):
    """Un épisode sans lien est associé à la vidéo au titre le plus proche,
    et youtubeUrl + métadonnées sont écrits."""
    _write_source(yt_dirs.sources, "ubm",
                  {"id": "ubm", "youtubeChannel": "https://youtube.com/@ubm"})
    _write_episode(yt_dirs.episodes, "ubm", "ep-032.json",
                   {"guid": "g-1", "title": "Caballero (Un Bon Moment, S5-E32)"})
    videos = [
        {"id": "vid1", "title": "Caballero (Un Bon Moment, S5-E32)",
         "duration": 3600},
        {"id": "vid2", "title": "Autre invité (Un Bon Moment, S5-E10)",
         "duration": 3600},
    ]
    monkeypatch.setattr(my, "_fetch_channel_videos", lambda url: videos)
    written = match_youtube("ubm", threshold=0.5, force=False, dry_run=False)
    assert written == 1
    data = json.loads((yt_dirs.episodes / "ubm" / "ep-032.json")
                      .read_text(encoding="utf-8"))
    assert data["youtubeUrl"] == "https://www.youtube.com/watch?v=vid1"
    assert data["youtubeTitle"].startswith("Caballero")


def test_match_youtube_dry_run_writes_nothing(yt_dirs, monkeypatch):
    _write_source(yt_dirs.sources, "ubm",
                  {"id": "ubm", "youtubeChannel": "https://youtube.com/@ubm"})
    _write_episode(yt_dirs.episodes, "ubm", "ep-032.json",
                   {"guid": "g-1", "title": "Caballero (Un Bon Moment, S5-E32)"})
    monkeypatch.setattr(my, "_fetch_channel_videos", lambda url: [
        {"id": "vid1", "title": "Caballero (Un Bon Moment, S5-E32)", "duration": 3600},
    ])
    written = match_youtube("ubm", threshold=0.5, force=False, dry_run=True)
    assert written == 0
    data = json.loads((yt_dirs.episodes / "ubm" / "ep-032.json")
                      .read_text(encoding="utf-8"))
    assert "youtubeUrl" not in data


def test_match_youtube_filters_short_extracts(yt_dirs, monkeypatch):
    """Les vidéos < 30 min (extraits) sont écartées du matching."""
    _write_source(yt_dirs.sources, "ubm",
                  {"id": "ubm", "youtubeChannel": "https://youtube.com/@ubm"})
    _write_episode(yt_dirs.episodes, "ubm", "ep-032.json",
                   {"guid": "g-1", "title": "Caballero (Un Bon Moment, S5-E32)"})
    videos = [
        # Extrait court au titre identique : ne doit PAS être choisi.
        {"id": "short", "title": "Caballero (Un Bon Moment, S5-E32)", "duration": 120},
        {"id": "full", "title": "Caballero (Un Bon Moment, S5-E32)", "duration": 3600},
    ]
    monkeypatch.setattr(my, "_fetch_channel_videos", lambda url: videos)
    match_youtube("ubm", threshold=0.5, force=False, dry_run=False)
    data = json.loads((yt_dirs.episodes / "ubm" / "ep-032.json")
                      .read_text(encoding="utf-8"))
    assert data["youtubeUrl"].endswith("=full")


def test_match_youtube_completes_existing_link(yt_dirs, monkeypatch):
    """Un épisode déjà lié (youtubeUrl) voit ses métadonnées complétées."""
    _write_source(yt_dirs.sources, "ubm",
                  {"id": "ubm", "youtubeChannel": "https://youtube.com/@ubm"})
    _write_episode(yt_dirs.episodes, "ubm", "ep-032.json",
                   {"guid": "g-1", "title": "Caballero",
                    "youtubeUrl": "https://www.youtube.com/watch?v=vid1"})
    monkeypatch.setattr(my, "_fetch_channel_videos", lambda url: [
        {"id": "vid1", "title": "Caballero (S5-E32)", "duration": 3600},
    ])
    written = match_youtube("ubm", threshold=0.5, force=False, dry_run=False)
    assert written == 1
    data = json.loads((yt_dirs.episodes / "ubm" / "ep-032.json")
                      .read_text(encoding="utf-8"))
    assert data["youtubeDuration"] == 3600
    assert data["season"] == 5  # complété (était absent)


def test_match_youtube_no_confident_match_below_threshold(yt_dirs, monkeypatch):
    """Aucun match au-dessus du seuil → aucun lien écrit."""
    _write_source(yt_dirs.sources, "ubm",
                  {"id": "ubm", "youtubeChannel": "https://youtube.com/@ubm"})
    _write_episode(yt_dirs.episodes, "ubm", "ep-032.json",
                   {"guid": "g-1", "title": "Titre totalement unique zzzqqq"})
    monkeypatch.setattr(my, "_fetch_channel_videos", lambda url: [
        {"id": "vid1", "title": "Rien a voir abcdef", "duration": 3600},
    ])
    written = match_youtube("ubm", threshold=0.9, force=False, dry_run=False)
    assert written == 0


def test_fetch_channel_videos_parses_entries(monkeypatch):
    """_fetch_channel_videos : ajoute /videos, mappe id/title/duration et
    ignore les entrées nulles ou sans id."""
    import sys
    import types
    from match_youtube import _fetch_channel_videos

    seen = {}

    class FakeYDL:
        def __init__(self, opts):
            seen["opts"] = opts

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def extract_info(self, url, download=False):
            seen["url"] = url
            return {"entries": [
                {"id": "v1", "title": "A", "duration": 3600},
                {"id": "v2", "title": "B", "duration": None},
                None,               # entrée nulle → ignorée
                {"title": "no id"},  # sans id → ignorée
            ]}

    fake_mod = types.ModuleType("yt_dlp")
    fake_mod.YoutubeDL = FakeYDL
    monkeypatch.setitem(sys.modules, "yt_dlp", fake_mod)

    vids = _fetch_channel_videos("https://youtube.com/@x")
    assert [v["id"] for v in vids] == ["v1", "v2"]
    assert seen["url"].endswith("/videos")


def test_fetch_channel_videos_keeps_existing_videos_suffix(monkeypatch):
    """Si l'URL se termine déjà par /videos, on ne le duplique pas."""
    import sys
    import types
    from match_youtube import _fetch_channel_videos

    seen = {}

    class FakeYDL:
        def __init__(self, opts):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def extract_info(self, url, download=False):
            seen["url"] = url
            return {"entries": []}

    fake_mod = types.ModuleType("yt_dlp")
    fake_mod.YoutubeDL = FakeYDL
    monkeypatch.setitem(sys.modules, "yt_dlp", fake_mod)

    _fetch_channel_videos("https://youtube.com/@x/videos")
    assert seen["url"].endswith("/videos")
    assert not seen["url"].endswith("/videos/videos")


def test_match_youtube_main_invokes(monkeypatch):
    """main() parse les arguments et appelle match_youtube."""
    import sys
    captured = {}

    def fake(source, threshold, force, dry_run):
        captured.update(source=source, threshold=threshold,
                        force=force, dry_run=dry_run)
        return 0

    monkeypatch.setattr(my, "match_youtube", fake)
    monkeypatch.setattr(sys, "argv", [
        "match_youtube.py", "--source", "ubm", "--threshold", "0.7",
        "--force", "--dry-run",
    ])
    my.main()
    assert captured == {"source": "ubm", "threshold": 0.7,
                        "force": True, "dry_run": True}
