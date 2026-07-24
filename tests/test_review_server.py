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

import review_render as rr
import review_server as rs
from _html_helpers import (
    find_form,
    find_input,
    find_link,
    find_radio,
    find_rows,
    has_class,
    is_checked,
    parse,
    text_of,
)


# ===== Fixtures =============================================================
@pytest.fixture(autouse=True)
def _clear_review_server_caches():
    """Les caches module-level (`_RECO_PATH_CACHE`, `_GROUPS_CACHE`, et le
    LRU `_load_transcript`) persistent entre tests : on les vide avant
    chaque test pour éviter de récupérer des Paths/résultats obsolètes
    pointant vers un tmp_path précédent."""
    rs._RECO_PATH_CACHE.clear()
    rr._clear_groups_cache()
    rs._load_transcript.cache_clear()
    yield
    rs._RECO_PATH_CACHE.clear()
    rr._clear_groups_cache()
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


def test_embed_url_uses_nocookie_and_safe_params():
    """L'embed YouTube doit passer par nocookie.com + rel=0 + playsinline=1
    pour éviter l'erreur 153 et limiter les recommendations / autoplay mobile."""
    out = rs._embed_url("https://www.youtube.com/watch?v=XYZ", 0)
    assert "youtube-nocookie.com" in out
    assert "rel=0" in out
    assert "playsinline=1" in out


def test_embed_url_no_video_id():
    assert rs._embed_url("https://example.com", 10) == ""


def test_referrer_policy_allows_youtube_embed_validation():
    """Referrer-Policy doit envoyer l'origine (sinon YT erreur 153)."""
    assert (rs._SECURITY_HEADERS["Referrer-Policy"]
            == "strict-origin-when-cross-origin")


def test_ep_nav_link_with_guid_renders_anchor():
    """Flèche cliquable : un <a> vers /ep?guid=<guid> avec aria-label."""
    out = rr._ep_nav_link("prev", "abc-123")
    soup = parse(out)
    a = soup.find("a")
    assert a is not None
    assert has_class(a, "eph-arrow", "eph-arrow-prev")
    assert "/ep?guid=abc-123" in a.get("href", "")
    assert a.get("aria-label") == "Épisode précédent"
    assert "←" in text_of(a)


def test_ep_nav_link_without_guid_renders_disabled_span():
    """Sans guid : span désactivé pour garder l'alignement visuel."""
    out = rr._ep_nav_link("next", None)
    soup = parse(out)
    span = soup.find("span")
    assert span is not None
    assert has_class(span, "eph-arrow", "eph-arrow-next", "disabled")
    assert span.has_attr("aria-hidden")
    assert "→" in text_of(span)
    assert soup.find("a") is None


def test_ep_nav_link_escapes_guid_in_href():
    """Garde-fou XSS : un guid pathologique est %-encodé."""
    out = rr._ep_nav_link("prev", 'a"b<c')
    assert 'a"b<c' not in out  # le brut ne fuit pas
    assert "a%22b%3Cc" in out


def test_render_episode_has_navigation_arrows(fake_source):
    """Avec 2 épisodes : la nav doit présenter des flèches eph-arrow."""
    out = rr._render_episode(fake_source, "ep-002")
    assert "/ep?guid=ep-001" in out or "/ep?guid=ep-002" in out
    assert "eph-arrow" in out


def test_render_episode_at_boundary_has_disabled_arrow(fake_source):
    """Aux extrémités, une flèche est disabled (span sans <a>)."""
    out = rr._render_episode(fake_source, "ep-001")
    assert "eph-arrow" in out
    assert "disabled" in out


def test_allocate_new_reco_writes_stub_and_returns_unique_id(fake_source):
    """_allocate_new_reco crée un fichier JSON avec id incrémenté."""
    new_id, new_path = rs._allocate_new_reco(fake_source, "ep-001")
    assert new_path.exists()
    # demo-source → segments ["demo","source"] → initials "ds"
    assert new_id.startswith("ds-")
    data = json.loads(new_path.read_text(encoding="utf-8"))
    assert data["id"] == new_id
    assert data["sourceId"] == fake_source
    assert data["episodeGuid"] == "ep-001"
    assert data["title"] == "Nouvelle reco"
    assert data["types"] == ["autre"]
    assert data["status"] == "draft"
    assert data["extractors"] == ["manual"]


def test_allocate_new_reco_increments_max_id(fake_source):
    """Un second appel renvoie un id strictement supérieur."""
    id1, _ = rs._allocate_new_reco(fake_source, "ep-001")
    id2, _ = rs._allocate_new_reco(fake_source, "ep-001")
    n1 = int(id1.rsplit("-", 1)[1])
    n2 = int(id2.rsplit("-", 1)[1])
    assert n2 == n1 + 1


def test_render_episode_includes_add_reco_button(fake_source):
    """La page épisode propose un bouton « + Ajouter une reco ». """
    out = rr._render_episode(fake_source, "ep-001")
    soup = parse(out)
    form = find_form(soup, "/add-reco")
    assert form is not None
    assert "Ajouter une reco" in text_of(form)
    guid_input = find_input(form, "guid", "ep-001")
    assert guid_input is not None


def test_reco_card_includes_delete_button(fake_source):
    """Chaque carte expose un bouton 🗑 avec confirmation JS."""
    out = rr._render_episode(fake_source, "ep-001")
    assert 'action="/delete-reco"' in out
    assert "btn-delete" in out
    assert "confirm(" in out  # window.confirm garde-fou avant suppression


def test_render_episode_includes_player_close_button(fake_source):
    """Le wrap player contient un bouton ✕ data-player-close."""
    out = rr._render_episode(fake_source, "ep-001")
    soup = parse(out)
    assert soup.find(attrs={"data-player-wrap": True}) is not None
    close_btn = soup.find(attrs={"data-player-close": True})
    assert close_btn is not None
    assert has_class(close_btn, "player-close") or soup.find(class_="player-close") is not None


def test_player_wrap_hidden_until_timecode_click(fake_source):
    """Le lecteur est MASQUÉ à l'arrivée sur la page (pas d'iframe vide
    flottante) — le JS retire `hidden` au premier clic sur un timecode."""
    out = rr._render_episode(fake_source, "ep-001")
    soup = parse(out)
    wrap = soup.find(attrs={"data-player-wrap": True})
    assert has_class(wrap, "hidden")


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
    soup = parse(out)
    alice_cb = soup.find("input", {"value": "Alice", "type": "checkbox"})
    if alice_cb is None:
        # cas radio (selon le rendu actuel)
        alice_cb = soup.find("input", {"value": "Alice"})
    assert is_checked(alice_cb)
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


# ===== M1 — _reco_checkboxes : appartenance EXACTE (pas sous-chaîne) =========
def test_reco_checkboxes_substring_not_checked():
    """M1 — « Navo » ne doit PAS être coché si recommendedBy contient « Navon »
    (sous-chaîne). L'attribution serait sinon silencieusement fausse."""
    out = rr._reco_checkboxes(["Navo", "Navon"], "Navon")
    soup = parse(out)
    assert not is_checked(soup.find("input", {"value": "Navo"}))
    assert is_checked(soup.find("input", {"value": "Navon"}))


def test_reco_checkboxes_exact_name_checked():
    """M1 — un nom exact présent dans recommendedBy est coché."""
    out = rr._reco_checkboxes(["Navo", "Kyan"], "Navo")
    soup = parse(out)
    assert is_checked(soup.find("input", {"value": "Navo"}))
    assert not is_checked(soup.find("input", {"value": "Kyan"}))


def test_reco_checkboxes_multi_names_both_checked():
    """M1 — recommendedBy multi-noms « A & B » coche A ET B, pas C."""
    out = rr._reco_checkboxes(["A", "B", "C"], "A & B")
    soup = parse(out)
    assert is_checked(soup.find("input", {"value": "A"}))
    assert is_checked(soup.find("input", {"value": "B"}))
    assert not is_checked(soup.find("input", {"value": "C"}))


def test_render_episode_parses_guests_once(fake_source, monkeypatch):
    """L3 — le fallback de parsing du titre (invités) est calculé UNE fois par
    _render_episode et propagé aux cartes, pas recalculé par carte.

    ep-001 a 3 recos sans guestsParsed : sans propagation, `_parse_guests`
    serait appelé une fois par carte (≥ 3). Avec propagation : 1 seule fois."""
    calls = []
    real = rr._parse_guests

    def counting(title, hosts):
        calls.append(title)
        return real(title, hosts)

    monkeypatch.setattr(rr, "_parse_guests", counting)
    rr._render_episode(fake_source, "ep-001")
    assert len(calls) == 1


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


# ===== Story 3 — titre RSS prioritaire sur youtubeTitle ======================
def test_ep_header_prefers_rss_title_over_youtube_title():
    """La chaîne YT publie parfois sous des titres de format anglais
    (« A Good Time with… ») : le header doit afficher le titre RSS français.

    N4 CR — youtubeUrl présent pour que l'assertion négative porte sur le
    contenu du lien (sinon elle passait trivialement, faute de <a>)."""
    ep = {"title": "Jérémy Ferrari en grande forme (S4-E40)",
          "youtubeTitle": "A Good Time with JEREMY FERRARI",
          "youtubeUrl": "https://www.youtube.com/watch?v=X"}
    out = rs._ep_header(ep, [])
    assert "Jérémy Ferrari en grande forme" in out
    assert ">A Good Time with JEREMY FERRARI<" not in out


def test_ep_header_youtube_title_shown_as_tooltip_when_different():
    ep = {"title": "Titre RSS", "youtubeTitle": "English Format Title",
          "youtubeUrl": "https://www.youtube.com/watch?v=X"}
    out = rs._ep_header(ep, [])
    assert 'title="YouTube : English Format Title"' in out


def test_ep_header_no_tooltip_when_titles_match():
    ep = {"title": "Même titre", "youtubeTitle": "Même titre",
          "youtubeUrl": "https://www.youtube.com/watch?v=X"}
    out = rs._ep_header(ep, [])
    assert "YouTube :" not in out


def test_ep_header_falls_back_to_youtube_title_without_rss():
    ep = {"youtubeTitle": "Seul titre connu"}
    out = rs._ep_header(ep, [])
    assert "Seul titre connu" in out


def test_ep_header_tooltip_escapes_html():
    """N2 CR — l'attribut title= doit échapper quotes ET tags."""
    ep = {"title": "RSS", "youtubeTitle": 'Bad "quote" <script>',
          "youtubeUrl": "https://www.youtube.com/watch?v=X"}
    out = rs._ep_header(ep, [])
    assert "<script>" not in out
    # Pas de quote brute dans la valeur du tooltip (breakout d'attribut).
    assert 'title="YouTube : Bad &quot;quote&quot; &lt;script&gt;"' in out


def test_ep_header_tooltip_kept_without_youtube_url():
    """L1 CR — sans youtubeUrl, le tooltip youtubeTitle doit survivre
    (rendu via <span title=…> au lieu du lien)."""
    ep = {"title": "Titre RSS", "youtubeTitle": "English Format Title"}
    out = rs._ep_header(ep, [])
    assert 'title="YouTube : English Format Title"' in out


def test_ep_header_question_mark_when_no_titles():
    """N3 CR — ni title ni youtubeTitle → « ? »."""
    ep = {}
    out = rs._ep_header(ep, [])
    assert ">?" in out or "?<" in out


# ===== Story 2 — distinction visuelle reco (vert) / citation (bleu) =========
def test_css_validated_citation_has_blue_rule():
    """Les citations validées doivent avoir leur propre règle (bleu),
    distincte du vert des recos validées (.row.done)."""
    import review_render_common as rrc
    css = rrc._CSS_PATH.read_text(encoding="utf-8")
    assert ".row.done.citation" in css
    # La règle doit surcharger le fond vert ET la couleur du statut (N1 CR).
    rule = css.split(".row.done.citation", 1)[1]
    assert "background" in rule.split("}")[0]
    assert ".row.done.citation .st" in css


def test_css_discarded_citation_keeps_rejected_signal():
    """M1 CR — une citation DISCARDÉE garde le signal « rejeté » (rouge,
    atténué), pas le bleu-gris d'une citation en attente."""
    import review_render_common as rrc
    css = rrc._CSS_PATH.read_text(encoding="utf-8")
    assert ".row.discarded.citation" in css
    rule = css.split(".row.discarded.citation", 1)[1].split("}")[0]
    assert "#6b3a3a" in rule


def test_css_discarded_guestwork_keeps_rejected_signal():
    """M1-bis — même exigence pour une œuvre d'invité discardée (le liseré
    ambre de .row.guestwork gagnerait sinon sur .row.discarded)."""
    import review_render_common as rrc
    css = rrc._CSS_PATH.read_text(encoding="utf-8")
    assert ".row.discarded.guestwork" in css
    rule = css.split(".row.discarded.guestwork", 1)[1].split("}")[0]
    assert "#6b3a3a" in rule


def test_reco_card_validated_citation_carries_both_classes():
    """Pré-requis CSS : la carte citation validée porte 'done citation'."""
    r = {"id": "x", "title": "T", "types": ["film"],
         "status": "validated", "kind": "citation"}
    out = rs._reco_card(r, {"guid": "g", "title": "Ep"}, [], "src")
    assert 'class="row done citation"' in out


# ===== Story 4 — marqueur « œuvre d'invité » (guestWork) ====================
def test_css_validated_guestwork_has_amber_rule():
    """Les œuvres d'invité validées ont leur propre règle (ambre), distincte
    du vert des recos (.row.done) ET du bleu des citations (.row.done.citation)."""
    import review_render_common as rrc
    css = rrc._CSS_PATH.read_text(encoding="utf-8")
    assert ".row.done.guestwork" in css
    # La règle doit surcharger le fond ET la couleur du statut (comme citation).
    rule = css.split(".row.done.guestwork", 1)[1]
    assert "background" in rule.split("}")[0]
    # Ne casse pas la règle citation existante (Story 2).
    assert ".row.done.citation" in css


def test_reco_card_validated_guestwork_carries_both_classes():
    """Pré-requis CSS : la carte œuvre d'invité validée porte 'done guestwork'."""
    r = {"id": "x", "title": "T", "types": ["spectacle"],
         "status": "validated", "guestWork": True}
    out = rs._reco_card(r, {"guid": "g", "title": "Ep"}, [], "src")
    assert 'class="row done guestwork"' in out


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
    (qui voudrait lire depuis le socket).

    #C/#D — Par défaut on simule un client local + le header X-Reco-CSRF=1
    (l'équivalent de ce qu'enverrait un client curl/test). Les tests
    spécifiques au CSRF peuvent override `headers` et `client_address`
    pour valider les rejets.
    """

    def __init__(self, source_id: str, path: str, body: bytes = b"",
                 accept: str = ""):
        # On NE PAS appeler super().__init__ pour éviter le parsing HTTP.
        self.source_id = source_id
        self.path = path
        self.rfile = io.BytesIO(body)
        self.wfile = io.BytesIO()
        self.headers = {
            "Content-Length": str(len(body)),
            "Accept": accept,
            "X-Reco-CSRF": "1",  # #D — opt-in implicite pour les tests
        }
        # #C — client local par défaut (sinon DNS-rebinding guard rejette).
        self.client_address = ("127.0.0.1", 0)
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


def test_handler_add_reco_missing_config_graceful(fake_source, monkeypatch):
    """m2 (revue 2026-07-19) — si la config source est absente (reco_prefix →
    FileNotFoundError), /add-reco flashe une erreur actionnable au lieu de
    crasher en 500 + stacktrace."""
    import review_routes_reco

    def _boom(*_a, **_k):
        raise FileNotFoundError("Pas de config pour la source « x ».")

    monkeypatch.setattr(review_routes_reco, "_allocate_new_reco", _boom)
    h = _FakeHandler(fake_source, "/add-reco", b"guid=ep-001")
    h.do_POST()  # ne doit PAS lever
    assert h._status == 303  # redirect PRG, pas de 500
    loc = h._sent_headers.get("Location", "")
    assert "flash=" in loc and "kind=error" in loc


def test_handler_post_unknown_route_404_no_mutation(fake_source):
    """rev-server M1 (revue 2026-07-19) — une route POST inconnue renvoie 404
    et NE mute PAS la reco (avant : else → _save_status → validate silencieux)."""
    from common import read_json, recos_dir_for
    before = read_json(recos_dir_for(fake_source) / "ubm-001.json")["status"]
    h = _FakeHandler(fake_source, "/bogus", b"id=ubm-001")
    h.do_POST()
    assert h._status == 404
    after = read_json(recos_dir_for(fake_source) / "ubm-001.json")["status"]
    assert after == before


def test_handler_post_non_utf8_body_no_exception(fake_source):
    """rev-server M2 (revue 2026-07-19) — un body POST non-UTF-8 ne lève pas
    (decode errors='replace') : sinon UnicodeDecodeError s'échappait de do_POST
    sans réponse HTTP propre."""
    h = _FakeHandler(fake_source, "/save", b"\xff\xfe")
    h.do_POST()  # ne doit pas lever
    assert h._status is not None


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


def test_post_save_from_doutes_redirects_to_doutes(fake_source):
    """M3 — POST /save initié depuis /doutes (Referer path /doutes) → 303 vers
    /doutes avec flash, pas vers /ep : traitement de la file en un seul passage."""
    body = b"id=ubm-001&action=validate&who=Alice"
    h = _FakeHandler(fake_source, "/save", body)
    h.headers["Referer"] = "http://127.0.0.1:8000/doutes"
    h.do_POST()
    assert h._status == 303
    loc = h._sent_headers["Location"]
    assert loc.startswith("/doutes")
    assert "flash=" in loc
    assert "kind=success" in loc
    # La reco a bien été validée.
    from common import read_json, recos_dir_for
    reco = read_json(recos_dir_for(fake_source) / "ubm-001.json")
    assert reco["status"] == "validated"


def test_post_save_without_referer_redirects_to_episode(fake_source):
    """M3 — sans Referer /doutes, /save redirige vers /ep (comportement
    historique préservé)."""
    body = b"id=ubm-001&action=validate&who=Alice"
    h = _FakeHandler(fake_source, "/save", body)
    h.do_POST()
    assert h._status == 303
    assert h._sent_headers["Location"].startswith("/ep?guid=ep-001")


def test_post_save_from_episode_referer_redirects_to_episode(fake_source):
    """M3 — un Referer /ep (page épisode) garde la redirection /ep."""
    body = b"id=ubm-001&action=validate&who=Alice"
    h = _FakeHandler(fake_source, "/save", body)
    h.headers["Referer"] = "http://127.0.0.1:8000/ep?guid=ep-001"
    h.do_POST()
    assert h._status == 303
    assert h._sent_headers["Location"].startswith("/ep?guid=ep-001")


def test_handler_post_payload_too_large(fake_source):
    """Content-Length > 1 MiB -> 413 Payload too large."""
    h = _FakeHandler(fake_source, "/save", b"id=ubm-001")
    # Surcharge Content-Length pour simuler un payload énorme sans charger 1 MiB.
    # On préserve les autres headers (X-Reco-CSRF) — sinon CSRF guard rejette
    # avant qu'on n'arrive au check de taille.
    h.headers["Content-Length"] = str((1 << 20) + 1)
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
    sans entrer dans la boucle réelle.

    rev-server m7 (revue 2026-07-19) : on mocke `acquire_server_lock` ET
    `_cleanup_orphan_tmp_files` — sinon le test prenait le VRAI verrou serveur
    (filelock sur tools/output/) et grattait le disque réel de la source
    « demo », ce qui pouvait échouer/polluer selon l'environnement."""
    import contextlib

    captured = {}

    class _FakeServer:
        def __init__(self, addr, handler):
            captured["addr"] = addr
            captured["handler"] = handler

        def serve_forever(self):
            raise KeyboardInterrupt  # on simule un Ctrl+C immédiat

    cleanup_calls: list[str] = []
    monkeypatch.setattr(rs, "HTTPServer", _FakeServer)
    monkeypatch.setattr(rs, "acquire_server_lock",
                        lambda: contextlib.nullcontext())
    monkeypatch.setattr(rs, "_cleanup_orphan_tmp_files",
                        lambda src: cleanup_calls.append(src) or 0)
    monkeypatch.setattr("sys.argv", ["review_server.py", "--source", "demo", "--port", "9999"])
    rs.main()
    assert captured["addr"] == ("127.0.0.1", 9999)
    # Le cleanup est bien invoqué (mocké) avec la source demandée.
    assert cleanup_calls == ["demo"]


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
    soup = parse(body)
    assert find_input(soup, "title") is not None
    assert find_input(soup, "creator") is not None
    assert find_input(soup, "types", "film") is not None
    assert soup.find("details") is not None
    assert find_input(soup, "ext_tmdb") is not None
    # Les autres cartes restent en mode normal
    assert "Solo" in body


def test_edit_invalid_id_no_edit_mode(fake_source):
    """GET /ep?guid=X&edit=<invalide> : aucun crash, pas de mode édition."""
    h = _FakeHandler(fake_source, "/ep?guid=ep-001&edit=../etc/passwd")
    h.do_GET()
    assert h._status == 200
    body = h.wfile.getvalue().decode("utf-8")
    # Pas de formulaire d'édition
    assert find_input(parse(body), "title") is None


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


def test_post_edit_from_doutes_marks_reviewed(fake_source):
    """« Corriger » sur /doutes est TERMINAL : après l'édition, la reco est
    marquée reviewedByHuman → elle quitte la file des doutes (refonte 07-21).
    Une édition depuis /ep ne la marque PAS."""
    from common import read_json, recos_dir_for
    # Depuis /doutes → marquée reviewedByHuman.
    h = _FakeHandler(fake_source, "/edit", b"id=ubm-001&title=Mortel&types=film")
    h.headers["Referer"] = "http://127.0.0.1:8000/doutes"
    h.do_POST()
    reco = read_json(recos_dir_for(fake_source) / "ubm-001.json")
    assert reco["agentReview"]["reviewedByHuman"] is True

    # Depuis /ep → NON marquée (édition ordinaire, pas une résolution de doute).
    p = recos_dir_for(fake_source) / "ubm-005.json"
    p.write_text(json.dumps({
        "id": "ubm-005", "episodeGuid": "ep-001", "types": ["film"],
        "title": "Y", "status": "draft",
    }), encoding="utf-8")
    rs._invalidate_reco_path_cache(fake_source)
    h2 = _FakeHandler(fake_source, "/edit", b"id=ubm-005&title=Y&types=film")
    h2.headers["Referer"] = "http://127.0.0.1:8000/ep?guid=ep-001"
    h2.do_POST()
    assert "reviewedByHuman" not in read_json(p).get("agentReview", {})


def test_post_edit_from_doutes_applies_type_action(fake_source):
    """« Corriger » depuis /doutes porte des radios de TYPE (name=action) :
    « Sauvegarder » applique le kind choisi EN PLUS de la correction du titre
    (retour utilisateur 07-24). Ici : reclassement en citation."""
    from common import read_json, recos_dir_for
    h = _FakeHandler(
        fake_source, "/edit",
        b"id=ubm-001&title=Une%20phrase&types=film&action=citation")
    h.headers["Referer"] = "http://127.0.0.1:8000/doutes"
    h.do_POST()
    reco = read_json(recos_dir_for(fake_source) / "ubm-001.json")
    assert reco["title"] == "Une phrase"
    assert reco["kind"] == "citation"
    assert reco["status"] == "validated"
    assert reco["agentReview"]["reviewedByHuman"] is True


def test_post_edit_from_doutes_action_discard_sets_status(fake_source):
    """Radio « Pas une reco » (action=discard) depuis /doutes → status discarded,
    tout en gardant la correction de titre appliquée."""
    from common import read_json, recos_dir_for
    h = _FakeHandler(
        fake_source, "/edit",
        b"id=ubm-001&title=Corrige&types=film&action=discard")
    h.headers["Referer"] = "http://127.0.0.1:8000/doutes"
    h.do_POST()
    reco = read_json(recos_dir_for(fake_source) / "ubm-001.json")
    assert reco["title"] == "Corrige"
    assert reco["status"] == "discarded"
    assert reco["agentReview"]["reviewedByHuman"] is True


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
    soup = parse(body)
    assert len(find_rows(soup)) >= 1
    # Fragment seul : pas le shell complet (pas de <body>, pas de <h1>).
    assert soup.find("body") is None
    assert soup.find("h1") is None


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


# #10 review — test_kind_for_empty_returns_info déplacé dans test_review_edit
# (test_kind_for_priority couvre déjà le cas [] → "info").


def test_get_ep_renders_flash_banner(fake_source):
    h = _FakeHandler(
        fake_source,
        "/ep?guid=ep-001&flash=Bravo&kind=success",
        b"",
    )
    h.do_GET()
    assert h._status == 200
    body = h.wfile.getvalue().decode("utf-8")
    soup = parse(body)
    flash = soup.find(class_="flash-success")
    assert flash is not None
    assert has_class(flash, "flash", "flash-success")
    assert "Bravo" in text_of(flash)


def test_get_ep_flash_kind_invalid_falls_back_to_info(fake_source):
    h = _FakeHandler(
        fake_source, "/ep?guid=ep-001&flash=hi&kind=<script>", b"",
    )
    h.do_GET()
    body = h.wfile.getvalue().decode("utf-8")
    soup = parse(body)
    assert soup.find(class_="flash-info") is not None
    # Le kind injecté `<script>` ne doit JAMAIS être interpolé tel quel dans
    # un attribut/balise (le shell contient un <script> légitime pour le JS
    # client, c'est attendu — mais pas avec le payload).
    assert "flash-<script>" not in body
    # Aucun élément flash n'a une classe contenant '<'.
    for el in soup.find_all(class_="flash"):
        for c in el.get("class", []):
            assert "<" not in c


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
    soup = parse(body)
    assert soup.find(class_="guests") is not None
    assert find_form(soup, "/rename-guest") is not None
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
    """Renomme un invité (non-host) → recommendedBy mis à jour partout."""
    # Pré-condition : on remplace Alice (host) par Charlie (guest) sur ubm-002
    # pour pouvoir tester le rename — renommer un host est désormais refusé
    # (garde-fou contre la corruption silencieuse des recos validées).
    from common import read_json, recos_dir_for, write_json_if_changed
    rp = recos_dir_for(fake_source) / "ubm-002.json"
    r = read_json(rp)
    r["recommendedBy"] = "Charlie"
    write_json_if_changed(rp, r)
    body = b"guid=ep-001&old=Charlie&new=Charline"
    h = _FakeHandler(fake_source, "/rename-guest", body)
    h.do_POST()
    r2 = read_json(rp)
    assert r2["recommendedBy"] == "Charline"


def test_post_rename_guest_delete_removes_everywhere(fake_source):
    from common import read_json, recos_dir_for, write_json_if_changed
    rp = recos_dir_for(fake_source) / "ubm-002.json"
    r = read_json(rp)
    r["recommendedBy"] = "Charlie"
    write_json_if_changed(rp, r)
    body = b"guid=ep-001&old=Charlie&action=delete"
    h = _FakeHandler(fake_source, "/rename-guest", body)
    h.do_POST()
    r2 = read_json(rp)
    assert "recommendedBy" not in r2


def test_post_rename_guest_rename_host_refused(fake_source):
    """Garde-fou : renommer un hôte (Alice est dans source.hosts) → refusé."""
    body = b"guid=ep-001&old=Alice&new=Alicia"
    h = _FakeHandler(fake_source, "/rename-guest", body)
    h.do_POST()
    from common import read_json, recos_dir_for
    r2 = read_json(recos_dir_for(fake_source) / "ubm-002.json")
    # recommendedBy intact
    assert r2["recommendedBy"] == "Alice"


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
    soup = parse(out)
    assert soup.find("input", {"value": "non spécifié"}) is None


def test_reco_card_dedups_guests_already_in_candidates(fake_source):
    """Un nom déjà candidate (via hosts/parse) n'est pas ré-ajouté depuis ep.guests."""
    r = {"id": "x", "title": "T", "types": ["film"], "status": "draft"}
    ep = {"guid": "g", "title": "avec Charlie", "guests": ["Charlie"]}
    out = rs._reco_card(r, ep, ["Kyan"], fake_source)
    soup = parse(out)
    # Charlie doit apparaître une seule fois comme input
    charlie_inputs = soup.find_all("input", {"value": "Charlie"})
    assert len(charlie_inputs) == 1


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


def test_rebuild_cache_clears_existing_entries(fake_source, tmp_path):
    """#6 review — renforcé : on injecte une entrée OBSOLETE dans le cache
    (path qui n'existe pas) et on vérifie que rebuild la supprime au lieu
    de juste co-exister avec les vraies entrées."""
    # Warm-up : remplit le cache.
    assert rs._reco_path(fake_source, "ubm-001") is not None
    # Injection d'une entrée obsolete (path vers un fichier qui n'existe pas).
    rs._RECO_PATH_CACHE.setdefault(fake_source, {})["ubm-obsolete"] = (
        tmp_path / "does-not-exist.json"
    )
    assert "ubm-obsolete" in rs._RECO_PATH_CACHE[fake_source]
    rs._rebuild_reco_path_cache(fake_source)
    # Après rebuild, l'entrée obsolete doit avoir été supprimée.
    assert "ubm-obsolete" not in rs._RECO_PATH_CACHE[fake_source]
    # Les vraies entrées sont préservées.
    assert "ubm-001" in rs._RECO_PATH_CACHE[fake_source]


def test_style_oserror_returns_empty_string(monkeypatch, tmp_path):
    """Couvre `except OSError → return ""` dans _style.

    #H — `_style` vit dans `review_render_common` (source unique de vérité).
    Le patch doit cibler ce module ; `review_render._CSS_PATH` est seulement
    un ré-export.
    """
    import review_render_common
    review_render_common._style.cache_clear()
    monkeypatch.setattr(
        review_render_common, "_CSS_PATH",
        tmp_path / "does-not-exist.css",
    )
    assert review_render_common._style() == ""
    review_render_common._style.cache_clear()


def test_reco_card_collects_sibling_recommenders(fake_source):
    """Une reco dont un sibling a un recommendedBy : la liste de candidates
    inclut ce nom (ligne 289)."""
    r = {"id": "x", "title": "T", "types": ["film"], "status": "draft"}
    ep = {"guid": "g", "title": "Ep"}
    siblings = [{"id": "y", "recommendedBy": "Camille"}]
    out = rs._reco_card(r, ep, [], fake_source, siblings=siblings)
    assert parse(out).find("input", {"value": "Camille"}) is not None


def test_post_edit_invalid_payload_with_unreadable_reco(fake_source, monkeypatch):
    """Couvre `except (OSError, ValueError)` autour de read_json sur reject."""
    from common import recos_dir_for
    # On rejette via title vide ET on fait planter read_json après coup.
    import review_routes
    real_read = review_routes.read_json
    def picky_read(p):
        if "ubm-001" in str(p):
            raise OSError("simu disk fail")
        return real_read(p)
    monkeypatch.setattr(review_routes, "read_json", picky_read)
    body = b"id=ubm-001&title=&types=film"
    h = _FakeHandler(fake_source, "/edit", body)
    h.do_POST()
    # On accepte un 303 même en l'absence de guid lisible.
    assert h._status == 303
    # guid manquant → redirige /
    assert h._sent_headers["Location"] == "/"


def test_send_json_post_rebuild_exception_swallowed(fake_source, monkeypatch):
    """#12 sécu — les erreurs "métier" (OSError/ValueError/KeyError) du rebuild
    de la carte sont avalées : on renvoie un JSON sans card_html. Une vraie
    erreur imprévue (RuntimeError) remonte au caller (catch externe → 500).
    """
    import review_routes
    real_card = review_routes._reco_card
    calls = []
    def boom(*a, **kw):
        calls.append(1)
        if calls == [1]:
            # #12 — on simule une erreur "métier" attendue (KeyError) plutôt
            # qu'un RuntimeError : c'est ce qu'on veut effectivement avaler.
            raise KeyError("rebuild fail (expected)")
        return real_card(*a, **kw)
    monkeypatch.setattr(review_routes, "_reco_card", boom)
    body = b"id=ubm-001&title=NewTitle&types=film"
    h = _FakeHandler(fake_source, "/edit", body, accept="application/json")
    h.do_POST()
    payload = json.loads(h.wfile.getvalue().decode("utf-8"))
    assert payload["kind"] == "success"
    assert payload["card_html"] == ""


def test_post_save_citation_sets_kind_and_status(fake_source):
    """POST /save action=citation → status=validated, kind=citation."""
    body = b"id=ubm-001&action=citation"
    h = _FakeHandler(fake_source, "/save", body)
    h.do_POST()
    assert h._status == 303
    from common import read_json, recos_dir_for
    reco = read_json(recos_dir_for(fake_source) / "ubm-001.json")
    assert reco["status"] == "validated"
    assert reco["kind"] == "citation"


def test_post_save_validate_sets_kind_reco_default(fake_source):
    """POST /save action=validate sans kind → kind=reco explicite."""
    body = b"id=ubm-001&action=validate"
    h = _FakeHandler(fake_source, "/save", body)
    h.do_POST()
    from common import read_json, recos_dir_for
    reco = read_json(recos_dir_for(fake_source) / "ubm-001.json")
    assert reco["status"] == "validated"
    assert reco["kind"] == "reco"


def test_post_save_discard_preserves_existing_kind(fake_source):
    """Si une reco est déjà kind=citation, /discard ne touche pas kind."""
    from common import read_json, recos_dir_for
    p = recos_dir_for(fake_source) / "ubm-001.json"
    d = json.loads(p.read_text(encoding="utf-8"))
    d["kind"] = "citation"
    d["status"] = "validated"
    p.write_text(json.dumps(d), encoding="utf-8")
    rs._invalidate_reco_path_cache(fake_source)

    body = b"id=ubm-001&action=discard"
    h = _FakeHandler(fake_source, "/save", body)
    h.do_POST()
    reco = read_json(p)
    assert reco["status"] == "discarded"
    assert reco["kind"] == "citation"


def test_reco_card_renders_citation_button(fake_source):
    """La carte propose un bouton « Citation » à côté de Valider/Pas une reco."""
    r = {"id": "x", "title": "T", "types": ["film"], "status": "draft"}
    ep = {"guid": "g", "title": "Ep"}
    out = rs._reco_card(r, ep, [], fake_source)
    soup = parse(out)
    assert soup.find(attrs={"value": "citation"}) is not None
    assert "Citation" in text_of(soup)


def test_reco_card_shows_citation_class_when_kind_citation(fake_source):
    """Une reco kind=citation porte la classe CSS `citation` sur la <li>."""
    r = {"id": "x", "title": "T", "types": ["film"], "status": "validated",
         "kind": "citation"}
    ep = {"guid": "g", "title": "Ep"}
    out = rs._reco_card(r, ep, [], fake_source)
    # <li class="row done citation"> ou un ordre similaire
    soup = parse(out)
    li = soup.find("li")
    assert has_class(li, "citation")


# ===== Story 4 — action guest-work (POST /save) + bouton 🎤 =================
def test_post_save_guest_work_sets_flag_kind_status(fake_source):
    """POST /save action=guest-work → validated, kind=reco, guestWork=True.
    Le recommendedBy se gère comme une validation classique."""
    body = b"id=ubm-001&who=Alice&action=guest-work"
    h = _FakeHandler(fake_source, "/save", body)
    h.do_POST()
    assert h._status == 303
    assert h._sent_headers["Location"].startswith("/ep?guid=ep-001")
    from common import read_json, recos_dir_for
    reco = read_json(recos_dir_for(fake_source) / "ubm-001.json")
    assert reco["status"] == "validated"
    assert reco["kind"] == "reco"
    assert reco["guestWork"] is True
    assert reco["recommendedBy"] == "Alice"


def test_post_save_guest_work_no_names_removes_recommendedby(fake_source):
    """guest-work sans cocher personne retire un recommendedBy existant
    (même logique que validate ; ubm-002 a recommendedBy=Alice)."""
    body = b"id=ubm-002&action=guest-work"
    h = _FakeHandler(fake_source, "/save", body)
    h.do_POST()
    from common import read_json, recos_dir_for
    reco = read_json(recos_dir_for(fake_source) / "ubm-002.json")
    assert reco["status"] == "validated"
    assert reco["kind"] == "reco"
    assert reco["guestWork"] is True
    assert "recommendedBy" not in reco


def test_post_save_validate_removes_guestwork_flag(fake_source):
    """Re-qualifier en validate RETIRE un guestWork existant (re-qualification)."""
    from common import read_json, recos_dir_for
    p = recos_dir_for(fake_source) / "ubm-001.json"
    d = json.loads(p.read_text(encoding="utf-8"))
    d["guestWork"] = True
    d["status"] = "validated"
    p.write_text(json.dumps(d), encoding="utf-8")
    rs._invalidate_reco_path_cache(fake_source)

    body = b"id=ubm-001&action=validate"
    h = _FakeHandler(fake_source, "/save", body)
    h.do_POST()
    reco = read_json(p)
    assert reco["status"] == "validated"
    assert reco["kind"] == "reco"
    assert "guestWork" not in reco


def test_post_save_citation_removes_guestwork_flag(fake_source):
    """Re-qualifier en citation RETIRE un guestWork existant (re-qualification)."""
    from common import read_json, recos_dir_for
    p = recos_dir_for(fake_source) / "ubm-001.json"
    d = json.loads(p.read_text(encoding="utf-8"))
    d["guestWork"] = True
    p.write_text(json.dumps(d), encoding="utf-8")
    rs._invalidate_reco_path_cache(fake_source)

    body = b"id=ubm-001&action=citation"
    h = _FakeHandler(fake_source, "/save", body)
    h.do_POST()
    reco = read_json(p)
    assert reco["kind"] == "citation"
    assert "guestWork" not in reco


def test_post_save_discard_preserves_guestwork_flag(fake_source):
    """/discard ne touche pas guestWork (même logique que kind : décision
    orthogonale à la pertinence globale)."""
    from common import read_json, recos_dir_for
    p = recos_dir_for(fake_source) / "ubm-001.json"
    d = json.loads(p.read_text(encoding="utf-8"))
    d["guestWork"] = True
    d["status"] = "validated"
    p.write_text(json.dumps(d), encoding="utf-8")
    rs._invalidate_reco_path_cache(fake_source)

    body = b"id=ubm-001&action=discard"
    h = _FakeHandler(fake_source, "/save", body)
    h.do_POST()
    reco = read_json(p)
    assert reco["status"] == "discarded"
    assert reco["guestWork"] is True


def test_reco_card_renders_guest_work_button(fake_source):
    """La carte propose un bouton « Leur œuvre » (action=guest-work)
    à côté de Citation. Libellé 2026-07-07 : couvre invité·es ET hosts."""
    r = {"id": "x", "title": "T", "types": ["spectacle"], "status": "draft"}
    ep = {"guid": "g", "title": "Ep"}
    out = rs._reco_card(r, ep, [], fake_source)
    soup = parse(out)
    assert soup.find(attrs={"value": "guest-work"}) is not None
    assert "Leur œuvre" in text_of(soup)
    # Le bouton Citation existant reste présent (Story 2 non cassée).
    assert soup.find(attrs={"value": "citation"}) is not None


def test_reco_card_guest_work_button_uses_star_emoji(fake_source):
    """Additional M3 — le bouton « Œuvre d'invité·e » utilise ⭐ (aligné avec le
    front) et non plus 🎤 (le micro entrait en collision avec l'emoji du type
    « artiste »)."""
    r = {"id": "x", "title": "T", "types": ["spectacle"], "status": "draft"}
    ep = {"guid": "g", "title": "Ep"}
    out = rs._reco_card(r, ep, [], fake_source)
    soup = parse(out)
    btn = soup.find(attrs={"value": "guest-work"})
    assert btn is not None
    assert "⭐" in text_of(btn)
    assert "🎤" not in text_of(btn)


def test_reco_card_shows_guestwork_class_when_flag_set(fake_source):
    """Une reco guestWork porte la classe CSS `guestwork` sur la <li>."""
    r = {"id": "x", "title": "T", "types": ["spectacle"], "status": "validated",
         "guestWork": True}
    ep = {"guid": "g", "title": "Ep"}
    out = rs._reco_card(r, ep, [], fake_source)
    soup = parse(out)
    li = soup.find("li")
    assert has_class(li, "guestwork")


# ===== F4.3 — Dédup recos : UI clusters + endpoints =========================
def _add_dup_recos(fake_source, source_dir):
    """Ajoute 2 recos quasi-identiques (Hannes/Annes) à ep-001 pour le cluster."""
    from common import recos_dir_for
    d = recos_dir_for(fake_source)
    for rid, title in [("ubm-dup-1", "Hannes"), ("ubm-dup-2", "Annes")]:
        (d / f"{rid}.json").write_text(json.dumps({
            "id": rid, "episodeGuid": "ep-001", "types": ["artiste"],
            "title": title, "timestamp": "00:05:00",
            "status": "draft", "extractors": ["claude"],
        }), encoding="utf-8")
    rs._invalidate_reco_path_cache(fake_source)


def test_render_episode_groups_cluster_in_single_card(fake_source):
    """Deux recos similaires → 1 seule carte cluster (pas 2 _reco_card)."""
    _add_dup_recos(fake_source, None)
    rs._load_transcript.cache_clear()
    out = rr._render_episode(fake_source, "ep-001")
    soup = parse(out)
    # La carte cluster est visible.
    clusters = find_rows(soup, cls="cluster")
    assert len(clusters) == 1
    assert "doublons probables" in text_of(soup)
    # Les radios des deux membres sont présents.
    assert find_radio(soup, "keep_id", "ubm-dup-1") is not None
    assert find_radio(soup, "keep_id", "ubm-dup-2") is not None
    # Le formulaire pointe sur /merge-recos.
    assert find_form(soup, "/merge-recos") is not None


def test_render_episode_clusters_disabled_in_edit_mode(fake_source):
    """En mode édition d'une carte, on désactive le regroupement."""
    _add_dup_recos(fake_source, None)
    out = rr._render_episode(fake_source, "ep-001", edit_id="ubm-001")
    # Pas de carte cluster ; les recos restent indépendantes.
    assert find_rows(parse(out), cls="cluster") == []


def test_post_merge_recos_preview_shows_diff(fake_source):
    _add_dup_recos(fake_source, None)
    body = (b"guid=ep-001&cluster_ids=ubm-dup-1,ubm-dup-2"
            b"&keep_id=ubm-dup-1&action=preview")
    h = _FakeHandler(fake_source, "/merge-recos", body)
    h.do_POST()
    assert h._status == 200
    out = h.wfile.getvalue().decode("utf-8")
    assert "Aperçu de la fusion" in out
    assert "ubm-dup-1" in out
    assert "ubm-dup-2" in out
    assert "Confirmer la fusion" in out


def test_post_merge_recos_action_merge_persists(fake_source):
    _add_dup_recos(fake_source, None)
    body = (b"guid=ep-001&cluster_ids=ubm-dup-1,ubm-dup-2"
            b"&keep_id=ubm-dup-1&action=merge")
    h = _FakeHandler(fake_source, "/merge-recos", body)
    h.do_POST()
    assert h._status == 303
    from common import recos_dir_for
    # ubm-dup-2 supprimé, ubm-dup-1 enrichi avec aliases.
    assert not (recos_dir_for(fake_source) / "ubm-dup-2.json").exists()
    reco = json.loads(
        (recos_dir_for(fake_source) / "ubm-dup-1.json").read_text(encoding="utf-8")
    )
    assert "Annes" in (reco.get("aliases") or [])


def test_post_merge_recos_invalid_keep_id_404(fake_source):
    """keep_id absent du cluster → 404."""
    _add_dup_recos(fake_source, None)
    body = (b"guid=ep-001&cluster_ids=ubm-dup-1,ubm-dup-2"
            b"&keep_id=ubm-zzz&action=merge")
    h = _FakeHandler(fake_source, "/merge-recos", body)
    h.do_POST()
    assert h._status == 404


def test_post_merge_recos_cancel_redirects_with_flash(fake_source):
    _add_dup_recos(fake_source, None)
    body = b"guid=ep-001&cluster_ids=ubm-dup-1,ubm-dup-2&action=cancel"
    h = _FakeHandler(fake_source, "/merge-recos", body)
    h.do_POST()
    assert h._status == 303
    assert h._sent_headers["Location"].startswith("/ep?guid=ep-001")
    assert "kind=info" in h._sent_headers["Location"]


def test_post_merge_recos_invalid_cluster_ids_format(fake_source):
    """cluster_ids avec caractères interdits → redirige vers /."""
    body = b"guid=ep-001&cluster_ids=../bad,ubm-1&action=preview"
    h = _FakeHandler(fake_source, "/merge-recos", body)
    h.do_POST()
    assert h._status == 303
    assert h._sent_headers["Location"] == "/"


def test_post_merge_recos_missing_cluster_ids(fake_source):
    """cluster_ids absent → / """
    body = b"guid=ep-001&action=preview"
    h = _FakeHandler(fake_source, "/merge-recos", body)
    h.do_POST()
    assert h._status == 303
    assert h._sent_headers["Location"] == "/"


def test_post_merge_recos_merge_without_keep_id_warns(fake_source):
    """action=merge sans keep_id sélectionné → flash error."""
    _add_dup_recos(fake_source, None)
    body = (b"guid=ep-001&cluster_ids=ubm-dup-1,ubm-dup-2&action=merge")
    h = _FakeHandler(fake_source, "/merge-recos", body)
    h.do_POST()
    assert h._status == 303
    loc = h._sent_headers["Location"]
    assert "kind=error" in loc


def test_post_merge_recos_unknown_members_404(fake_source):
    """cluster_ids pointant vers recos inexistantes → 404."""
    body = (b"guid=ep-001&cluster_ids=ubm-zzz-1,ubm-zzz-2"
            b"&keep_id=ubm-zzz-1&action=preview")
    h = _FakeHandler(fake_source, "/merge-recos", body)
    h.do_POST()
    assert h._status == 404


def test_post_undo_merge_restores_files(fake_source, tmp_path, monkeypatch):
    """Après un merge, /undo-merge restaure les fichiers supprimés."""
    _add_dup_recos(fake_source, None)
    from common import recos_dir_for
    # Reroute BACKUP_DIR vers tmp_path pour ne pas polluer.
    # #G — la constante vit maintenant dans reco_dedup_merge, on patche les
    # deux modules (reco_dedup la ré-exporte mais le code utilise reco_dedup_merge).
    import reco_dedup
    import reco_dedup_merge
    monkeypatch.setattr(reco_dedup, "BACKUP_DIR", tmp_path / "dedup-backup")
    monkeypatch.setattr(reco_dedup_merge, "BACKUP_DIR", tmp_path / "dedup-backup")
    # Exécute la fusion.
    body = (b"guid=ep-001&cluster_ids=ubm-dup-1,ubm-dup-2"
            b"&keep_id=ubm-dup-1&action=merge")
    h = _FakeHandler(fake_source, "/merge-recos", body)
    h.do_POST()
    assert not (recos_dir_for(fake_source) / "ubm-dup-2.json").exists()
    # Undo.
    h2 = _FakeHandler(fake_source, "/undo-merge", b"guid=ep-001")
    h2.do_POST()
    assert h2._status == 303
    # Le fichier est restauré.
    assert (recos_dir_for(fake_source) / "ubm-dup-2.json").exists()


def test_post_undo_merge_no_backup_warning(fake_source, tmp_path, monkeypatch):
    """Aucun backup existant → flash warning, pas d'erreur."""
    import reco_dedup
    import reco_dedup_merge
    monkeypatch.setattr(reco_dedup, "BACKUP_DIR", tmp_path / "empty-backup")
    monkeypatch.setattr(reco_dedup_merge, "BACKUP_DIR", tmp_path / "empty-backup")
    h = _FakeHandler(fake_source, "/undo-merge", b"guid=ep-001")
    h.do_POST()
    assert h._status == 303
    assert "kind=warning" in h._sent_headers["Location"]


def test_dedup_cluster_card_marks_canonical(fake_source):
    from reco_dedup import Cluster
    from review_render import _dedup_cluster_card
    members = [
        {"id": "ubm-1", "title": "Hannes", "timestamp": "00:05:00",
         "status": "draft", "extractors": ["claude"]},
        {"id": "ubm-2", "title": "Annes", "timestamp": "00:05:05",
         "status": "validated", "extractors": ["claude"]},
    ]
    cluster = Cluster(canonical_id="ubm-2", members=members, similarity=0.85,
                      avg_timecode_delta=5)
    out = _dedup_cluster_card(cluster, {"guid": "ep-1"}, fake_source)
    soup = parse(out)
    radio = find_radio(soup, "keep_id", "ubm-2")
    assert is_checked(radio)
    text = text_of(soup)
    assert "par défaut" in text
    assert "similarité ≥ 85%" in text


# ===== F4.3.b — Ajout manuel d'une reco à un cluster ========================
def test_other_episode_recos_excludes_cluster_members():
    from review_render_cluster import _other_episode_recos_for_cluster
    ep_recos = [
        {"id": "a", "status": "draft", "kind": "reco"},
        {"id": "b", "status": "draft", "kind": "reco"},
        {"id": "c", "status": "draft", "kind": "reco"},
    ]
    out = _other_episode_recos_for_cluster(ep_recos, {"a", "b"})
    assert [r["id"] for r in out] == ["c"]


def test_other_episode_recos_excludes_discarded():
    from review_render_cluster import _other_episode_recos_for_cluster
    ep_recos = [
        {"id": "a", "status": "draft"},
        {"id": "b", "status": "discarded"},
        {"id": "c", "status": "validated"},
    ]
    out = _other_episode_recos_for_cluster(ep_recos, set())
    assert [r["id"] for r in out] == ["a", "c"]


def test_other_episode_recos_includes_citations():
    from review_render_cluster import _other_episode_recos_for_cluster
    ep_recos = [
        {"id": "a", "status": "draft", "kind": "reco"},
        {"id": "b", "status": "validated", "kind": "citation"},
    ]
    out = _other_episode_recos_for_cluster(ep_recos, set())
    assert {r["id"] for r in out} == {"a", "b"}


def test_other_episode_recos_sorted_by_timestamp():
    from review_render_cluster import _other_episode_recos_for_cluster
    ep_recos = [
        {"id": "a", "status": "draft", "timestamp": "00:10:00"},
        {"id": "b", "status": "draft", "timestamp": "00:02:00"},
        {"id": "c", "status": "draft", "timestamp": None},
        {"id": "d", "status": "draft", "timestamp": "00:05:00"},
    ]
    out = _other_episode_recos_for_cluster(ep_recos, set())
    # Tri ascendant par timestamp ; None en fin de liste.
    assert [r["id"] for r in out] == ["b", "d", "a", "c"]


def test_cluster_card_renders_add_select_when_other_recos(fake_source):
    from reco_dedup import Cluster
    from review_render import _dedup_cluster_card
    members = [
        {"id": "ubm-1", "title": "Hannes", "timestamp": "00:05:00",
         "status": "draft", "extractors": ["claude"]},
        {"id": "ubm-2", "title": "Annes", "timestamp": "00:05:05",
         "status": "draft", "extractors": ["claude"]},
    ]
    cluster = Cluster(canonical_id="ubm-1", members=members, similarity=0.85,
                      avg_timecode_delta=5)
    other = [{"id": "ubm-9", "title": "Hanness", "recommendedBy": "Alice",
              "timestamp": "00:05:30"}]
    out = _dedup_cluster_card(cluster, {"guid": "ep-1"}, fake_source,
                              other_recos=other)
    soup = parse(out)
    assert soup.find(class_="cluster-add-select") is not None
    assert soup.find(attrs={"value": "ubm-9"}) is not None
    assert "Ajouter une autre reco" in text_of(soup)


def test_cluster_card_omits_add_select_when_no_other_recos(fake_source):
    from reco_dedup import Cluster
    from review_render import _dedup_cluster_card
    members = [
        {"id": "ubm-1", "title": "Hannes", "timestamp": "00:05:00",
         "status": "draft", "extractors": ["claude"]},
        {"id": "ubm-2", "title": "Annes", "timestamp": "00:05:05",
         "status": "draft", "extractors": ["claude"]},
    ]
    cluster = Cluster(canonical_id="ubm-1", members=members, similarity=0.85,
                      avg_timecode_delta=5)
    out = _dedup_cluster_card(cluster, {"guid": "ep-1"}, fake_source,
                              other_recos=[])
    assert "cluster-add-select" not in out


def test_cluster_card_add_option_shows_title_creator_timestamp(fake_source):
    from reco_dedup import Cluster
    from review_render import _dedup_cluster_card
    members = [
        {"id": "ubm-1", "title": "Hannes", "timestamp": "00:05:00",
         "status": "draft", "extractors": ["claude"]},
        {"id": "ubm-2", "title": "Annes", "timestamp": "00:05:05",
         "status": "draft", "extractors": ["claude"]},
    ]
    cluster = Cluster(canonical_id="ubm-1", members=members, similarity=0.85,
                      avg_timecode_delta=5)
    other = [{"id": "ubm-9", "title": "Hanness Wagner",
              "recommendedBy": "Alice", "timestamp": "00:05:30"}]
    out = _dedup_cluster_card(cluster, {"guid": "ep-1"}, fake_source,
                              other_recos=other)
    assert "Hanness Wagner" in out
    assert "Alice" in out
    assert "00:05:30" in out or "5:30" in out


def test_render_episode_passes_other_recos_to_cluster_card(fake_source):
    """Intégration : une 3ᵉ reco du même épisode apparaît dans le <select>."""
    _add_dup_recos(fake_source, None)
    # Ajoute une reco non-clusterable (titre très différent) au même épisode.
    from common import recos_dir_for
    extra = {
        "id": "ubm-extra", "episodeGuid": "ep-001", "types": ["livre"],
        "title": "Un livre totalement différent",
        "recommendedBy": "Alice", "timestamp": "00:10:00",
        "status": "draft", "extractors": ["claude"],
    }
    (recos_dir_for(fake_source) / "ubm-extra.json").write_text(
        json.dumps(extra), encoding="utf-8",
    )
    rs._invalidate_reco_path_cache(fake_source)
    out = rr._render_episode(fake_source, "ep-001")
    soup = parse(out)
    assert soup.find(class_="cluster-add-select") is not None
    assert soup.find(attrs={"value": "ubm-extra"}) is not None


def test_get_ep_unknown_guid_returns_back_link(fake_source):
    """GET /ep?guid=inconnu renvoie un message + lien de retour."""
    h = _FakeHandler(fake_source, "/ep?guid=inconnu")
    h.do_GET()
    body = h.wfile.getvalue().decode("utf-8")
    assert "introuvable" in body


# ===== F4.4 — _yt_timecode_link helper ======================================
def test_yt_timecode_link_with_yt_and_timestamp():
    """YT + timestamp → lien <a class="tc"> cliquable vers embed."""
    r = {"timestamp": "00:05:00"}
    ep = {"youtubeUrl": "https://www.youtube.com/watch?v=ABCDEFGHIJK",
          "audioDuration": 3600, "youtubeDuration": 3600}
    out = rr._yt_timecode_link(r, ep)
    soup = parse(out)
    a = soup.find("a")
    assert a is not None
    assert has_class(a, "tc")
    assert a.get("target") == "ytplayer"
    assert "embed/ABCDEFGHIJK" in a.get("href", "")
    assert "00:05:00" in text_of(a)


def test_yt_timecode_link_no_yt_returns_static_span():
    """Pas de youtubeUrl mais timestamp présent → <span class="tc off">."""
    r = {"timestamp": "00:05:00"}
    ep = {"youtubeUrl": None}
    out = rr._yt_timecode_link(r, ep)
    soup = parse(out)
    span = soup.find("span")
    assert span is not None
    assert has_class(span, "tc", "off")
    assert "00:05:00" in text_of(span)
    assert soup.find("a") is None


def test_yt_timecode_link_no_timestamp_returns_empty():
    """Pas de timestamp → chaîne vide."""
    assert rr._yt_timecode_link({}, {"youtubeUrl": "x"}) == ""
    assert rr._yt_timecode_link({"timestamp": ""}, {"youtubeUrl": "x"}) == ""


def test_yt_timecode_link_applies_acast_offset():
    """transcriptSource=acast → offset YT appliqué (audio vs video diff)."""
    r = {"timestamp": "00:05:00", "transcriptSource": "acast"}
    ep = {"youtubeUrl": "https://www.youtube.com/watch?v=ABCDEFGHIJK",
          "audioDuration": 3000, "youtubeDuration": 3060}  # offset 60s
    out = rr._yt_timecode_link(r, ep)
    # 5*60 + 60 = 360
    assert "start=360" in out


def test_yt_timecode_link_no_offset_for_youtube_source():
    """transcriptSource=youtube → pas d'offset (les timestamps sont déjà YT)."""
    r = {"timestamp": "00:05:00", "transcriptSource": "youtube"}
    ep = {"youtubeUrl": "https://www.youtube.com/watch?v=ABCDEFGHIJK",
          "audioDuration": 3000, "youtubeDuration": 3060}
    out = rr._yt_timecode_link(r, ep)
    assert "start=300" in out  # juste 5*60


# ===== F4.5 — _load_cluster_members validation ==============================
def test_load_cluster_members_rejects_different_episode(fake_source):
    """Si une reco du cluster a un episodeGuid différent → rejetée."""
    from common import recos_dir_for
    d = recos_dir_for(fake_source)
    (d / "ubm-ok.json").write_text(json.dumps({
        "id": "ubm-ok", "episodeGuid": "ep-001", "title": "OK",
        "status": "draft", "kind": "reco",
    }), encoding="utf-8")
    (d / "ubm-bad.json").write_text(json.dumps({
        "id": "ubm-bad", "episodeGuid": "ep-999", "title": "BAD",
        "status": "draft", "kind": "reco",
    }), encoding="utf-8")
    rs._invalidate_reco_path_cache(fake_source)
    h = _FakeHandler(fake_source, "/")
    members, missing, by_id = h._load_cluster_members(
        ["ubm-ok", "ubm-bad"], expected_guid="ep-001",
    )
    assert [m["id"] for m in members] == ["ubm-ok"]
    assert "ubm-bad" in missing
    assert set(by_id.keys()) == {"ubm-ok"}


def test_load_cluster_members_rejects_discarded(fake_source):
    """Une reco status=discarded est rejetée du cluster."""
    from common import recos_dir_for
    d = recos_dir_for(fake_source)
    (d / "ubm-ok.json").write_text(json.dumps({
        "id": "ubm-ok", "episodeGuid": "ep-001", "title": "OK",
        "status": "draft", "kind": "reco",
    }), encoding="utf-8")
    (d / "ubm-disc.json").write_text(json.dumps({
        "id": "ubm-disc", "episodeGuid": "ep-001", "title": "X",
        "status": "discarded", "kind": "reco",
    }), encoding="utf-8")
    rs._invalidate_reco_path_cache(fake_source)
    h = _FakeHandler(fake_source, "/")
    members, missing, by_id = h._load_cluster_members(
        ["ubm-ok", "ubm-disc"], expected_guid="ep-001",
    )
    assert [m["id"] for m in members] == ["ubm-ok"]
    assert "ubm-disc" in missing
    assert set(by_id.keys()) == {"ubm-ok"}


def test_load_cluster_members_rejects_mixed_kinds(fake_source):
    """Cluster mélangeant kind=reco et kind=citation → la minorité rejetée."""
    from common import recos_dir_for
    d = recos_dir_for(fake_source)
    (d / "ubm-r1.json").write_text(json.dumps({
        "id": "ubm-r1", "episodeGuid": "ep-001", "title": "A",
        "status": "draft", "kind": "reco",
    }), encoding="utf-8")
    (d / "ubm-r2.json").write_text(json.dumps({
        "id": "ubm-r2", "episodeGuid": "ep-001", "title": "B",
        "status": "draft", "kind": "reco",
    }), encoding="utf-8")
    (d / "ubm-cite.json").write_text(json.dumps({
        "id": "ubm-cite", "episodeGuid": "ep-001", "title": "C",
        "status": "draft", "kind": "citation",
    }), encoding="utf-8")
    rs._invalidate_reco_path_cache(fake_source)
    h = _FakeHandler(fake_source, "/")
    members, missing, by_id = h._load_cluster_members(
        ["ubm-r1", "ubm-r2", "ubm-cite"], expected_guid="ep-001",
    )
    ids = {m["id"] for m in members}
    assert ids == {"ubm-r1", "ubm-r2"}
    assert "ubm-cite" in missing
    assert set(by_id.keys()) == {"ubm-r1", "ubm-r2"}


# ===== F4.6 — cluster card : timecode cliquable + quote + extractors =========
def test_dedup_cluster_card_has_clickable_timecode_per_member(fake_source):
    from reco_dedup import Cluster
    from review_render import _dedup_cluster_card
    members = [
        {"id": "ubm-1", "title": "Hannes", "timestamp": "00:05:00",
         "status": "draft", "extractors": ["claude"]},
        {"id": "ubm-2", "title": "Annes", "timestamp": "00:05:05",
         "status": "draft", "extractors": ["claude"]},
    ]
    cluster = Cluster(canonical_id="ubm-1", members=members, similarity=0.9,
                      avg_timecode_delta=5)
    ep = {"guid": "ep-1",
          "youtubeUrl": "https://www.youtube.com/watch?v=ABCDEFGHIJK",
          "audioDuration": 3600, "youtubeDuration": 3600}
    out = _dedup_cluster_card(cluster, ep, fake_source)
    # Au moins un lien cliquable <a class="tc"> par membre.
    assert out.count('<a class="tc"') >= 2
    assert "embed/ABCDEFGHIJK" in out


def test_dedup_cluster_card_shows_quote_per_member_when_present(fake_source):
    from reco_dedup import Cluster
    from review_render import _dedup_cluster_card
    members = [
        {"id": "ubm-1", "title": "Hannes", "timestamp": "00:05:00",
         "status": "draft", "extractors": ["claude"],
         "quote": "Une œuvre incroyable"},
        {"id": "ubm-2", "title": "Annes", "timestamp": "00:05:05",
         "status": "draft", "extractors": ["claude"]},
    ]
    cluster = Cluster(canonical_id="ubm-1", members=members, similarity=0.9,
                      avg_timecode_delta=5)
    out = _dedup_cluster_card(cluster, {"guid": "ep-1"}, fake_source)
    soup = parse(out)
    quote = soup.find(class_="cluster-quote")
    assert quote is not None
    assert "Une œuvre incroyable" in text_of(soup)


def test_dedup_cluster_card_omits_quote_when_absent(fake_source):
    from reco_dedup import Cluster
    from review_render import _dedup_cluster_card
    members = [
        {"id": "ubm-1", "title": "Hannes", "timestamp": "00:05:00",
         "status": "draft", "extractors": ["claude"]},
        {"id": "ubm-2", "title": "Annes", "timestamp": "00:05:05",
         "status": "draft", "extractors": ["claude"]},
    ]
    cluster = Cluster(canonical_id="ubm-1", members=members, similarity=0.9,
                      avg_timecode_delta=5)
    out = _dedup_cluster_card(cluster, {"guid": "ep-1"}, fake_source)
    assert parse(out).find(class_="cluster-quote") is None


def test_dedup_cluster_card_keeps_existing_assertions(fake_source):
    """Régression : tous les marqueurs des 9 tests existants sont conservés."""
    from reco_dedup import Cluster
    from review_render import _dedup_cluster_card
    members = [
        {"id": "ubm-1", "title": "Hannes", "timestamp": "00:05:00",
         "status": "draft", "extractors": ["claude"]},
        {"id": "ubm-2", "title": "Annes", "timestamp": "00:05:05",
         "status": "validated", "extractors": ["claude"]},
    ]
    cluster = Cluster(canonical_id="ubm-2", members=members, similarity=0.85,
                      avg_timecode_delta=5)
    out = _dedup_cluster_card(cluster, {"guid": "ep-1"}, fake_source)
    soup = parse(out)
    assert find_rows(soup, cls="cluster")
    assert soup.find("input", {"name": "keep_id"}) is not None
    assert is_checked(find_radio(soup, "keep_id", "ubm-2"))
    assert find_form(soup, "/merge-recos") is not None
    text = text_of(soup)
    assert "doublons probables" in text
    assert "par défaut" in text


# =============================================================================
# ===== Nouveaux tests TDD — session backend CR exhaustive ====================
# =============================================================================

# --- #5 XSS : youtubeUrl=javascript:... doit être neutralisé -----------------
def test_xss_youtube_url_javascript_scheme_neutralized():
    """#5 — `youtubeUrl=javascript:alert(1)` ne doit JAMAIS produire de href actif."""
    ep = {
        "guid": "ep-xss",
        "title": "Test XSS",
        "youtubeUrl": "javascript:alert(1)",
    }
    out = rr._ep_header(ep, [])
    # Le href ne doit PAS contenir le payload javascript:
    assert "javascript:alert" not in out
    # title brut affiché (sans <a>) puisque l'URL est rejetée
    assert "<a href=" not in out or 'href="javascript' not in out


def test_xss_youtube_url_data_scheme_neutralized():
    """#5 — `youtubeUrl=data:text/html,...` neutralisé."""
    ep = {"guid": "ep", "title": "t", "youtubeUrl": "data:text/html,<script>x</script>"}
    out = rr._ep_header(ep, [])
    assert "data:text/html" not in out


def test_xss_yt_timecode_link_rejects_javascript_url():
    """#5 — `_yt_timecode_link` doit ignorer une URL non-http(s) pour le href."""
    r = {"timestamp": "00:01:00"}
    ep = {"youtubeUrl": "javascript:alert(1)"}
    out = rr._yt_timecode_link(r, ep)
    # Pas de <a href="javascript:...">, mais on tombe sur le span statique.
    assert "javascript:alert" not in out


def test_safe_url_accepts_https_and_http():
    """#5 — `_safe_url` retourne l'URL telle quelle pour http(s), None sinon."""
    from review_render_common import _safe_url
    assert _safe_url("https://example.com") == "https://example.com"
    assert _safe_url("http://example.com") == "http://example.com"
    assert _safe_url("javascript:alert(1)") is None
    assert _safe_url("data:text/html,x") is None
    assert _safe_url("") is None
    assert _safe_url(None) is None
    assert _safe_url("  https://x.com  ") == "  https://x.com  "  # trim non auto


# --- #6 CSRF : Origin/Referer cross-site rejetés -----------------------------
def test_csrf_post_with_evil_origin_rejected(fake_source):
    """#6 — POST `/delete-reco` avec Origin: evil.com → 403."""
    body = b"id=ubm-001"
    h = _FakeHandler(fake_source, "/delete-reco", body)
    h.headers["Origin"] = "http://evil.com"
    h.do_POST()
    assert h._status == 403


def test_csrf_post_with_evil_referer_rejected(fake_source):
    """#6 — POST avec Referer cross-site → 403."""
    body = b"id=ubm-001"
    h = _FakeHandler(fake_source, "/delete-reco", body)
    h.headers["Referer"] = "https://attacker.example/foo"
    h.do_POST()
    assert h._status == 403


def test_csrf_post_without_origin_accepted(fake_source):
    """#6/#D — POST sans Origin/Referer mais avec X-Reco-CSRF=1 (curl/tests)
    → accepté. _FakeHandler envoie ce header par défaut."""
    body = b"id=ubm-001&action=validate&who=Alice"
    h = _FakeHandler(fake_source, "/save", body)
    h.do_POST()
    assert h._status != 403


def test_csrf_post_without_origin_without_csrf_header_rejected(fake_source):
    """#D — Sans Origin/Referer ET sans X-Reco-CSRF=1 → 403 (refus par défaut)."""
    body = b"id=ubm-001&action=validate"
    h = _FakeHandler(fake_source, "/save", body)
    del h.headers["X-Reco-CSRF"]  # retire l'opt-in du fake
    h.do_POST()
    assert h._status == 403


def test_csrf_post_from_non_local_client_rejected(fake_source):
    """#C — Client IP non-locale → 403 (DNS rebinding guard)."""
    body = b"id=ubm-001&action=validate"
    h = _FakeHandler(fake_source, "/save", body)
    h.client_address = ("192.168.1.50", 12345)  # client externe
    h.do_POST()
    assert h._status == 403


def test_csrf_post_with_localhost_origin_accepted(fake_source):
    """#6 — Origin: http://localhost:8000 → accepté."""
    body = b"id=ubm-001&action=validate"
    h = _FakeHandler(fake_source, "/save", body)
    h.headers["Origin"] = "http://localhost:8000"
    h.do_POST()
    assert h._status != 403


def test_lan_mode_accepts_private_client_matching_origin(fake_source, monkeypatch):
    """Mode LAN (2026-07-23) — client du réseau privé + Origin == Host → accepté
    (déport du serveur sur le portable, accès direct par IP LAN)."""
    import review_handler_base
    monkeypatch.setattr(review_handler_base, "ALLOW_LAN", True)
    h = _FakeHandler(fake_source, "/save", b"id=ubm-001&action=validate")
    h.client_address = ("192.168.1.50", 12345)
    h.headers["Host"] = "192.168.1.234:8000"
    h.headers["Origin"] = "http://192.168.1.234:8000"
    h.do_POST()
    assert h._status != 403


def test_lan_mode_still_rejects_cross_origin(fake_source, monkeypatch):
    """Mode LAN — l'anti-CSRF reste actif : Origin != Host de la requête → 403."""
    import review_handler_base
    monkeypatch.setattr(review_handler_base, "ALLOW_LAN", True)
    h = _FakeHandler(fake_source, "/delete-reco", b"id=ubm-001")
    h.client_address = ("192.168.1.50", 12345)
    h.headers["Host"] = "192.168.1.234:8000"
    h.headers["Origin"] = "http://evil.com"
    h.do_POST()
    assert h._status == 403


def test_lan_mode_off_still_rejects_private_client(fake_source, monkeypatch):
    """Sécurité par défaut : sans mode LAN, un client privé reste refusé."""
    import review_handler_base
    monkeypatch.setattr(review_handler_base, "ALLOW_LAN", False)
    h = _FakeHandler(fake_source, "/save", b"id=ubm-001&action=validate")
    h.client_address = ("192.168.1.50", 12345)
    h.headers["Origin"] = "http://192.168.1.234:8000"
    h.do_POST()
    assert h._status == 403


def test_consolidate_keeps_and_discards(fake_source):
    """POST /consolidate (page /doublons, 2026-07-23) — les recos COCHÉES (keep)
    sont validées avec leur type + titre corrigé, les autres du cluster écartées ;
    reviewedByHuman posé partout."""
    from common import read_json, recos_dir_for
    d = recos_dir_for(fake_source)
    for i in ("1", "2"):
        (d / f"ubm-cons{i}.json").write_text(json.dumps({
            "id": f"ubm-cons{i}", "episodeGuid": "ep-001", "types": ["film"],
            "title": f"T{i}", "status": "draft"}), encoding="utf-8")
    rs._invalidate_reco_path_cache(fake_source)
    body = (b"member=ubm-cons1&member=ubm-cons2&keep=ubm-cons1"
            b"&type_ubm-cons1=citation&title_ubm-cons1=Titre+corrige")
    h = _FakeHandler(fake_source, "/consolidate", body)
    h.do_POST()
    assert h._status == 303
    a = read_json(d / "ubm-cons1.json")
    b = read_json(d / "ubm-cons2.json")
    assert a["status"] == "validated" and a["kind"] == "citation"
    assert a["title"] == "Titre corrige"
    assert a["agentReview"]["reviewedByHuman"] is True
    assert b["status"] == "discarded"
    assert b["agentReview"]["reviewedByHuman"] is True


def test_csrf_post_with_127_origin_accepted(fake_source):
    """#6 — Origin: http://127.0.0.1:8000 → accepté."""
    body = b"id=ubm-001&action=validate"
    h = _FakeHandler(fake_source, "/save", body)
    h.headers["Origin"] = "http://127.0.0.1:8000"
    h.do_POST()
    assert h._status != 403


# --- #11 cluster minimal safety ---------------------------------------------
def test_dedup_cluster_card_minimal_members_safe():
    """#13 — Cluster minimal valide (2 membres) : pas de crash."""
    from reco_dedup import Cluster
    from review_render import _dedup_cluster_card
    members = [
        {"id": "x", "title": "t", "extractors": ["c"]},
        {"id": "y", "title": "t", "extractors": ["c"]},
    ]
    cluster = Cluster(canonical_id="x", members=members, similarity=1.0,
                      avg_timecode_delta=0)
    out = _dedup_cluster_card(cluster, {"guid": "ep"}, "src")
    assert find_rows(parse(out), cls="cluster")


# --- #22/#8 kind mixte : ajout citation à cluster reco rejeté ----------------
def test_merge_recos_rejects_citation_mixed_with_reco(fake_source):
    """#22 + #8 — cluster [reco A, reco B] + cluster_ids C(citation) →
    C rejeté avec log explicite, A+B fusionnés sur le kind du keep_id."""
    from common import recos_dir_for
    d = recos_dir_for(fake_source)
    # 3 recos : 2 reco, 1 citation, même épisode.
    for i, kind in [(11, "reco"), (12, "reco"), (13, "citation")]:
        path = d / f"ubm-{i:03d}.json"
        path.write_text(json.dumps({
            "id": f"ubm-{i:03d}",
            "episodeGuid": "ep-001",
            "title": f"Reco {i}",
            "types": ["livre"],
            "status": "validated",
            "kind": kind,
            "extractors": ["claude"],
        }), encoding="utf-8")
    rs._invalidate_reco_path_cache(fake_source)

    # POST merge avec keep_id=ubm-011 (reco) + cluster_ids contenant la citation
    body = (b"guid=ep-001&action=preview&keep_id=ubm-011"
            b"&cluster_ids=ubm-011,ubm-012,ubm-013")
    h = _FakeHandler(fake_source, "/merge-recos", body)
    h.do_POST()
    # preview doit aboutir (200) sur les 2 reco seulement (la citation est out)
    assert h._status == 200
    body_out = h.wfile.getvalue().decode("utf-8")
    # ubm-013 (citation) doit avoir été filtré : son id ne doit pas apparaître
    # dans la preview comme membre absorbé.
    assert "ubm-013" not in body_out


# --- #27 guid vide rejeté ----------------------------------------------------
def test_merge_recos_rejects_empty_guid(fake_source):
    """#27 — POST /merge-recos avec guid vide → 400, pas de mutation."""
    body = b"guid=&action=preview&keep_id=ubm-001&cluster_ids=ubm-001,ubm-002"
    h = _FakeHandler(fake_source, "/merge-recos", body)
    h.do_POST()
    assert h._status == 400


# --- #23 youtubeDuration en string -------------------------------------------
def test_yt_timecode_link_youtubeDuration_string():
    """#23 — `youtubeDuration` arrive en string : pas de TypeError, offset=0
    si non castable."""
    r = {"timestamp": "00:01:00", "transcriptSource": "acast"}
    ep = {"youtubeUrl": "https://www.youtube.com/watch?v=ABCDEFGHIJK",
          "audioDuration": "3000", "youtubeDuration": "3060"}
    # Ne doit pas lever.
    out = rr._yt_timecode_link(r, ep)
    assert "start=" in out  # offset bien appliqué (60s)
    assert "start=120" in out  # 60 + 60


def test_ep_header_youtubeDuration_invalid_no_crash():
    """#23/#6 review — durées invalides → pas de crash dans _ep_header.

    Renforcé : on vérifie explicitement (a) que le rendu produit la
    classe attendue `<h2 class="eph">`, (b) qu'aucune valeur littérale
    suspecte des inputs cassés ne fuit dans le HTML (pas de "not-a-number"
    affiché, pas de TypeError encodé).
    """
    ep = {"guid": "ep", "title": "t",
          "audioDuration": "not-a-number", "youtubeDuration": None}
    out = rr._ep_header(ep, [])
    # Assertion structurelle (et pas un `or` qui masquerait l'autre).
    assert '<h2 class="eph">' in out
    # L'input invalide ne doit PAS apparaître brut.
    assert "not-a-number" not in out


# --- #26 aliases propagés du loser -------------------------------------------
def test_merge_cluster_propagates_loser_aliases(tmp_path, fake_source):
    """#26 — Lors d'un merge, les `aliases` existants du loser doivent
    rejoindre la liste finale (pas juste son `title`)."""
    from common import recos_dir_for
    from reco_dedup import Cluster, merge_cluster
    d = recos_dir_for(fake_source)
    keep = {
        "id": "ubm-301", "episodeGuid": "ep-001", "title": "Titre A",
        "types": ["livre"], "extractors": ["claude"],
    }
    loser = {
        "id": "ubm-302", "episodeGuid": "ep-001", "title": "Titre B",
        "aliases": ["Titre C", "Titre D"],
        "types": ["livre"], "extractors": ["openai"],
    }
    (d / "ubm-301.json").write_text(json.dumps(keep), encoding="utf-8")
    (d / "ubm-302.json").write_text(json.dumps(loser), encoding="utf-8")
    cluster = Cluster(canonical_id="ubm-301", members=[keep, loser])
    backup_dir = tmp_path / "backup"
    result = merge_cluster(cluster, keep_id="ubm-301",
                           source_id=fake_source,
                           backup_root=backup_dir)
    aliases = result.get("aliases", [])
    # Le titre du loser doit être présent + ses aliases existants.
    assert "Titre B" in aliases
    assert "Titre C" in aliases
    assert "Titre D" in aliases


# --- #7 atomicité merge_cluster : kept écrit avant losers supprimés ---------
def test_merge_cluster_writes_kept_before_unlinking_losers(monkeypatch, fake_source, tmp_path):
    """#7 — Ordre garanti : write kept (atomique) AVANT unlink des losers.

    Vérifié via un mock sur os.replace qui lève → kept doit avoir été tenté
    avant unlink, et les losers doivent encore exister sur disque."""
    from common import recos_dir_for
    from reco_dedup import Cluster, merge_cluster
    d = recos_dir_for(fake_source)
    keep = {"id": "ubm-401", "episodeGuid": "ep-001", "title": "K",
            "types": ["livre"], "extractors": ["c"]}
    loser = {"id": "ubm-402", "episodeGuid": "ep-001", "title": "L",
             "types": ["livre"], "extractors": ["o"]}
    (d / "ubm-401.json").write_text(json.dumps(keep), encoding="utf-8")
    (d / "ubm-402.json").write_text(json.dumps(loser), encoding="utf-8")

    # Mock os.replace pour lever — simule crash entre tmp.write et rename.
    # #G — `_atomic_write_json` vit dans reco_dedup_merge (extrait).
    import reco_dedup_merge
    call_state = {"raised": False}

    def fake_replace(*a, **kw):
        call_state["raised"] = True
        raise OSError("simulated disk failure")

    monkeypatch.setattr(reco_dedup_merge.os, "replace", fake_replace)

    cluster = Cluster(canonical_id="ubm-401", members=[keep, loser])
    with pytest.raises(OSError):
        merge_cluster(cluster, keep_id="ubm-401",
                      source_id=fake_source, backup_root=tmp_path / "bk")
    # Les losers doivent encore exister puisque l'écriture du kept a échoué.
    assert (d / "ubm-402.json").exists()
    assert call_state["raised"]


# --- #9/Option-A : locks supprimés (single-thread) --------------------------
# Le test du lock (test_get_source_lock_returns_same_instance) a été retiré :
# l'outil tourne sur HTTPServer (mono-thread), pas de concurrence à protéger.
# Voir docs/yagni.md.


# --- #14 is_cluster_compatible centralisé -----------------------------------
def test_is_cluster_compatible_rejects_different_guid():
    """#14 — guid différent → False."""
    from reco_dedup import is_cluster_compatible
    r = {"episodeGuid": "ep-X", "kind": "reco", "status": "validated"}
    assert not is_cluster_compatible(r, expected_guid="ep-Y", expected_kind="reco")


def test_is_cluster_compatible_rejects_discarded():
    """#14 — status=discarded rejeté par défaut."""
    from reco_dedup import is_cluster_compatible
    r = {"episodeGuid": "ep", "kind": "reco", "status": "discarded"}
    assert not is_cluster_compatible(r, expected_guid="ep", expected_kind="reco")


def test_is_cluster_compatible_kind_mismatch():
    """#14 — kind différent → False."""
    from reco_dedup import is_cluster_compatible
    r = {"episodeGuid": "ep", "kind": "citation", "status": "validated"}
    assert not is_cluster_compatible(r, expected_guid="ep", expected_kind="reco")


def test_is_cluster_compatible_happy_path():
    """#14 — guid+kind+status OK → True."""
    from reco_dedup import is_cluster_compatible
    r = {"episodeGuid": "ep", "kind": "reco", "status": "validated"}
    assert is_cluster_compatible(r, expected_guid="ep", expected_kind="reco")


# --- #12 strip french quotes -------------------------------------------------
def test_strip_french_quotes_basic():
    """#12 — « text » → text (pas de double quote à l'affichage)."""
    from review_render_common import _strip_french_quotes
    assert _strip_french_quotes("« bonjour »") == "bonjour"
    assert _strip_french_quotes("« bonjour ") == "bonjour"
    assert _strip_french_quotes('"hello"') == "hello"
    assert _strip_french_quotes("«   spaced   »") == "spaced"
    assert _strip_french_quotes("") == ""


# --- Helpers privés _reco_* (#16 — décomposition _reco_card) ----------------
def test_reco_quote_block_empty():
    import review_render as rr
    assert rr._reco_quote_block({}) == ""
    assert rr._reco_quote_block({"quote": ""}) == ""


def test_reco_quote_block_strips_french_quotes():
    import review_render as rr
    out = rr._reco_quote_block({"quote": "« déjà entre guillemets »"})
    # Une seule paire de guillemets autour, pas deux.
    assert out.count("«") == 1
    assert out.count("»") == 1
    assert "déjà entre guillemets" in out


def test_reco_quote_block_escapes_html():
    import review_render as rr
    out = rr._reco_quote_block({"quote": "<script>alert(1)</script>"})
    assert "<script>" not in out
    assert "&lt;script&gt;" in out


def test_reco_row_class_validated():
    import review_render as rr
    assert rr._reco_row_class({"status": "validated"}) == "done"


def test_reco_row_class_discarded():
    import review_render as rr
    assert rr._reco_row_class({"status": "discarded"}) == "discarded"


def test_reco_row_class_draft_empty():
    import review_render as rr
    assert rr._reco_row_class({"status": "draft"}) == ""
    assert rr._reco_row_class({}) == ""


def test_reco_row_class_citation_appends():
    import review_render as rr
    assert rr._reco_row_class({"status": "validated", "kind": "citation"}) == "done citation"
    assert rr._reco_row_class({"kind": "citation"}) == "citation"


def test_reco_row_class_guestwork_appends():
    import review_render as rr
    assert rr._reco_row_class(
        {"status": "validated", "guestWork": True}) == "done guestwork"
    assert rr._reco_row_class({"guestWork": True}) == "guestwork"


def test_reco_row_class_citation_and_guestwork_combo():
    """Combo legacy kind=citation + guestWork : les DEUX classes, `guestwork`
    en dernier pour gagner la cascade CSS (NIT-9)."""
    import review_render as rr
    assert rr._reco_row_class(
        {"status": "validated", "kind": "citation", "guestWork": True},
    ) == "done citation guestwork"


def test_css_guestwork_rule_declared_after_citation_for_cascade():
    """La règle `.row.done.guestwork` doit venir APRÈS `.row.done.citation`
    dans le CSS pour gagner la cascade sur le combo citation+guestWork (NIT-9)."""
    import review_render_common as rrc
    css = rrc._CSS_PATH.read_text(encoding="utf-8")
    assert css.index(".row.done.citation") < css.index(".row.done.guestwork")


def test_reco_context_block_empty_when_no_secs():
    import review_render as rr
    assert rr._reco_context_block({}, {"guid": "g"}, "src", None) == ""


def test_reco_context_block_empty_when_transcript_missing(tmp_path, monkeypatch):
    """Pas de transcript → bloc vide."""
    import review_render as rr
    rr._load_transcript.cache_clear()
    # transcript_path_for renvoie un chemin qui n'existe pas → tuple vide.
    assert rr._reco_context_block({}, {"guid": "no-such-guid"}, "no-src", 100) == ""


def test_reco_header_includes_basics():
    import review_render as rr
    r = {
        "id": "x", "title": "Titre", "types": ["film"], "status": "draft",
        "extractors": ["claude"], "episodeGuid": "g",
    }
    ep = {"guid": "g"}
    out = rr._reco_header(r, ep, "")
    soup = parse(out)
    text = text_of(soup)
    assert "Titre" in text
    assert soup.find(class_="merge-select") is not None  # checkbox merge
    assert soup.find(attrs={"value": "x"}) is not None
    assert "draft" in text  # status badge


def test_reco_header_propagates_episode_guid_when_missing():
    """Si reco sans episodeGuid, le helper le renseigne via ep.guid pour edit."""
    import review_render as rr
    r = {"id": "x", "title": "T", "status": "draft"}
    ep = {"guid": "ep-1"}
    out = rr._reco_header(r, ep, "")
    # Le formulaire edit doit pointer vers guid=ep-1.
    assert "guid=ep-1" in out


# --- Helpers privés _handle_merge_recos (#19 — validation extraite) ---------
def test_validate_merge_input_rejects_empty_cluster_ids(fake_source):
    """cluster_ids vide → 303 vers /, _validate_merge_input renvoie None."""
    handler = _FakeHandler(fake_source, "/merge-recos")
    sent: list[tuple[int, dict]] = []
    handler._send = lambda code, body="", headers=None: sent.append(
        (code, headers or {}),
    )
    result = handler._validate_merge_input({"cluster_ids": [""]})
    assert result is None
    assert sent[0][0] == 303
    assert sent[0][1].get("Location") == "/"


def test_validate_merge_input_rejects_invalid_cluster_id_format(fake_source):
    handler = _FakeHandler(fake_source, "/merge-recos")
    sent: list[tuple[int, dict]] = []
    handler._send = lambda code, body="", headers=None: sent.append(
        (code, headers or {}),
    )
    # "BAD ID" ne matche pas le regex.
    result = handler._validate_merge_input({"cluster_ids": ["BAD ID,ubm-2"]})
    assert result is None
    assert sent[0][0] == 303


def test_validate_merge_input_rejects_invalid_keep_id(fake_source):
    handler = _FakeHandler(fake_source, "/merge-recos")
    sent: list[tuple[int, dict]] = []
    handler._send = lambda code, body="", headers=None: sent.append(
        (code, headers or {}),
    )
    result = handler._validate_merge_input({
        "cluster_ids": ["ubm-1,ubm-2"],
        "keep_id": ["INVALID ID"],
    })
    assert result is None


def test_validate_merge_input_ok(fake_source):
    handler = _FakeHandler(fake_source, "/merge-recos")
    handler._send = lambda *a, **k: None
    result = handler._validate_merge_input({
        "cluster_ids": ["ubm-1,ubm-2"],
        "keep_id": ["ubm-1"],
        "guid": ["g"],
        "action": ["preview"],
    })
    assert result == ("g", "preview", "ubm-1", ["ubm-1", "ubm-2"])


def test_resolve_expected_kind_missing_keep_id_returns_none(fake_source):
    handler = _FakeHandler(fake_source, "/merge-recos")
    assert handler._resolve_expected_kind("") is None


def test_resolve_expected_kind_unknown_reco_returns_none(fake_source):
    handler = _FakeHandler(fake_source, "/merge-recos")
    assert handler._resolve_expected_kind("ubm-zzzzz") is None


# --- API publique alias (#15) -----------------------------------------------
def test_public_api_aliases_exist():
    """#15 — `render_episode`, `render_index`, `render_card_fragment` exposés."""
    import review_render
    assert hasattr(review_render, "render_episode")
    assert hasattr(review_render, "render_index")
    assert hasattr(review_render, "render_card_fragment")
    assert review_render.render_episode is review_render._render_episode
    assert review_render.render_index is review_render._render_index
    assert review_render.render_card_fragment is review_render._reco_card


# ===== rev-server m2 : validation du guid GET /ep ===========================
def test_get_ep_invalid_guid_format_404(fake_source):
    """m2 (revue 2026-07-19) — guid non vide au format invalide (espace,
    caractères d'injection) → 404 avant tout rendu."""
    h = _FakeHandler(fake_source, "/ep?guid=" + urllib.parse.quote("bad guid;rm"))
    h.do_GET()
    assert h._status == 404


def test_get_ep_valid_format_unknown_guid_still_renders(fake_source):
    """m2 — un guid de bon format mais inconnu suit son cours (page introuvable),
    ce n'est PAS un rejet de format."""
    h = _FakeHandler(fake_source, "/ep?guid=ep-999")
    h.do_GET()
    assert h._status == 200
    assert "introuvable" in h.wfile.getvalue().decode("utf-8")


def test_get_ep_empty_guid_not_rejected(fake_source):
    """m2 — guid vide (aucun param) ne déclenche pas le rejet de format
    (comportement historique préservé : 200)."""
    h = _FakeHandler(fake_source, "/ep")
    h.do_GET()
    assert h._status == 200


# ===== rev-server m3 : toast/flash sur /save ================================
def test_save_json_returns_success_toast(fake_source):
    """m3 (revue 2026-07-19) — POST /save en JSON (fetch) renvoie un message
    de succès non vide (avant : message vide → aucun toast côté client)."""
    body = b"id=ubm-001&action=validate&who=Alice"
    h = _FakeHandler(fake_source, "/save", body, accept="application/json")
    h.do_POST()
    assert h._status == 200
    payload = json.loads(h.wfile.getvalue().decode("utf-8"))
    assert payload["kind"] == "success"
    assert payload["message"]  # message non vide (toast)


def test_save_non_json_redirect_carries_flash(fake_source):
    """m3 — la redirection non-JS de /save embarque désormais un flash de
    confirmation (kind=success)."""
    body = b"id=ubm-001&action=discard"
    h = _FakeHandler(fake_source, "/save", body)
    h.do_POST()
    assert h._status == 303
    loc = h._sent_headers["Location"]
    assert loc.startswith("/ep?guid=ep-001")
    assert "flash=" in loc and "kind=success" in loc


# ===== rev-server m4 : whitelist des actions /save ==========================
def test_save_unknown_action_rejected_no_mutation(fake_source):
    """m4 (revue 2026-07-19) — action /save inconnue → PAS de mutation (avant :
    retombait en `validate` silencieux) + flash d'erreur."""
    from common import read_json, recos_dir_for
    before = read_json(recos_dir_for(fake_source) / "ubm-001.json")["status"]
    body = b"id=ubm-001&action=bogus"
    h = _FakeHandler(fake_source, "/save", body)
    h.do_POST()
    assert h._status == 303
    assert "kind=error" in h._sent_headers["Location"]
    after = read_json(recos_dir_for(fake_source) / "ubm-001.json")["status"]
    assert after == before  # statut inchangé


def test_save_unknown_action_json_error_kind(fake_source):
    """m4 — action inconnue en JSON → kind=error dans le payload."""
    body = b"id=ubm-001&action=bogus"
    h = _FakeHandler(fake_source, "/save", body, accept="application/json")
    h.do_POST()
    payload = json.loads(h.wfile.getvalue().decode("utf-8"))
    assert payload["kind"] == "error"


@pytest.mark.parametrize("action", ["validate", "discard", "citation", "guest-work"])
def test_save_all_whitelisted_actions_accepted(fake_source, action):
    """m4 — chaque action de la whitelist produit bien un flash succès."""
    body = f"id=ubm-001&action={action}".encode()
    h = _FakeHandler(fake_source, "/save", body, accept="application/json")
    h.do_POST()
    payload = json.loads(h.wfile.getvalue().decode("utf-8"))
    assert payload["kind"] == "success"


# ===== rev-render m4 : edit_origin de la carte JSON =========================
def test_save_json_from_doutes_card_has_doutes_edit_origin(fake_source):
    """rev-render m4 (revue 2026-07-19) — carte JSON renvoyée pour un fetch
    initié depuis /doutes : son bouton Éditer pointe vers /doutes (inline),
    pas vers /ep. Refonte 2026-07-21 : l'URL porte désormais `ep=<guid>` pour
    rester dans la vue épisode."""
    body = b"id=ubm-002&action=validate&who=Alice"
    h = _FakeHandler(fake_source, "/save", body, accept="application/json")
    h.headers["Referer"] = "http://127.0.0.1:8000/doutes"
    h.do_POST()
    payload = json.loads(h.wfile.getvalue().decode("utf-8"))
    assert 'href="/doutes?ep=' in payload["card_html"]
    assert "&edit=ubm-002" in payload["card_html"]


def test_save_json_from_episode_card_has_ep_edit_origin(fake_source):
    """rev-render m4 — sans Referer /doutes, la carte garde l'edit_origin /ep."""
    body = b"id=ubm-002&action=validate&who=Alice"
    h = _FakeHandler(fake_source, "/save", body, accept="application/json")
    h.do_POST()
    payload = json.loads(h.wfile.getvalue().decode("utf-8"))
    assert "/ep?guid=ep-001&edit=ubm-002" in payload["card_html"]


# ===== rev-server m5 : _action_merge 500-safe ===============================
def test_merge_recos_invalid_guid_format_redirects_root(fake_source):
    """_validate_merge_input — guid au format invalide → redirige / (59-61)."""
    _add_dup_recos(fake_source, None)
    body = (b"guid=bad+guid&action=preview&keep_id=ubm-dup-1"
            b"&cluster_ids=ubm-dup-1,ubm-dup-2")
    h = _FakeHandler(fake_source, "/merge-recos", body)
    h.do_POST()
    assert h._status == 303
    assert h._sent_headers["Location"] == "/"


def test_merge_recos_unknown_action_400(fake_source):
    """_handle_merge_recos — une action valide mais inconnue (≠ pick/preview/
    merge/cancel) avec un cluster valide → 400 « Action inconnue »."""
    _add_dup_recos(fake_source, None)
    body = (b"guid=ep-001&action=frobnicate&keep_id=ubm-dup-1"
            b"&cluster_ids=ubm-dup-1,ubm-dup-2")
    h = _FakeHandler(fake_source, "/merge-recos", body)
    h.do_POST()
    assert h._status == 400


def test_load_cluster_members_read_error_marks_missing(fake_source, monkeypatch):
    """_load_cluster_members — un membre dont read_json échoue va dans `missing`
    (except OSError/ValueError, pas de crash de la fusion)."""
    _add_dup_recos(fake_source, None)
    import review_routes_merge
    real_read = review_routes_merge.read_json

    def picky(path):
        if "ubm-dup-2" in str(path):
            raise ValueError("json cassé")
        return real_read(path)

    monkeypatch.setattr(review_routes_merge, "read_json", picky)
    h = _FakeHandler(fake_source, "/merge-recos")
    members, missing, _by_id = h._load_cluster_members(
        ["ubm-dup-1", "ubm-dup-2"], expected_guid="ep-001")
    assert "ubm-dup-2" in missing
    assert [m["id"] for m in members] == ["ubm-dup-1"]


def test_load_cluster_members_no_expected_guid_returns_all(fake_source):
    """_load_cluster_members sans expected_guid → aucun filtrage épisode/kind
    (retour anticipé), tous les membres lisibles sont conservés."""
    _add_dup_recos(fake_source, None)
    h = _FakeHandler(fake_source, "/merge-recos")
    members, missing, by_id = h._load_cluster_members(["ubm-dup-1", "ubm-dup-2"])
    assert {m["id"] for m in members} == {"ubm-dup-1", "ubm-dup-2"}
    assert missing == []
    assert set(by_id) == {"ubm-dup-1", "ubm-dup-2"}


def test_resolve_expected_kind_read_error_returns_none(fake_source, monkeypatch):
    """_resolve_expected_kind — read_json en échec sur le keep_id → None
    (except OSError/ValueError, 81-82)."""
    _add_dup_recos(fake_source, None)
    import review_routes_merge
    real_read = review_routes_merge.read_json

    def picky(path):
        if "ubm-dup-1" in str(path):
            raise ValueError("json cassé")
        return real_read(path)

    monkeypatch.setattr(review_routes_merge, "read_json", picky)
    h = _FakeHandler(fake_source, "/merge-recos")
    assert h._resolve_expected_kind("ubm-dup-1") is None


def test_action_merge_unexpected_error_is_500_safe(fake_source, monkeypatch):
    """m5 (revue 2026-07-19) — merge_cluster lève une erreur INATTENDUE
    (RuntimeError, pas seulement ValueError/OSError) → flash error + 303,
    pas d'exception qui s'échappe (500)."""
    _add_dup_recos(fake_source, None)
    import review_routes_merge

    def _boom(*_a, **_k):
        raise RuntimeError("boom inattendu")

    monkeypatch.setattr(review_routes_merge, "merge_cluster", _boom)
    body = (b"guid=ep-001&cluster_ids=ubm-dup-1,ubm-dup-2"
            b"&keep_id=ubm-dup-1&action=merge")
    h = _FakeHandler(fake_source, "/merge-recos", body)
    h.do_POST()  # ne doit PAS lever
    assert h._status == 303
    assert "kind=error" in h._sent_headers["Location"]


# ===== rev-server M3 : contrôle de port anti-CSRF ===========================
class _FakeServerAddr:
    """Faux serveur exposant server_address pour tester le contrôle de port."""

    def __init__(self, port: int):
        self.server_address = ("127.0.0.1", port)


def test_csrf_origin_port_matches_server_accepted(fake_source):
    """rev-server M3 — Origin sur le MÊME port que le serveur → accepté."""
    body = b"id=ubm-001&action=validate"
    h = _FakeHandler(fake_source, "/save", body)
    h.server = _FakeServerAddr(8000)
    h.headers["Origin"] = "http://127.0.0.1:8000"
    h.do_POST()
    assert h._status != 403


def test_csrf_origin_port_mismatch_rejected(fake_source):
    """rev-server M3 — un service local sur un AUTRE port (3000) ne doit pas
    pouvoir CSRF nos POST → 403."""
    body = b"id=ubm-001&action=validate"
    h = _FakeHandler(fake_source, "/save", body)
    h.server = _FakeServerAddr(8000)
    h.headers["Origin"] = "http://127.0.0.1:3000"
    h.do_POST()
    assert h._status == 403


def test_csrf_origin_default_port_accepted(fake_source):
    """rev-server M3 — Origin sans port explicite (port=None) est accepté
    (compat curl/tests : on ne peut rien déduire)."""
    body = b"id=ubm-001&action=validate"
    h = _FakeHandler(fake_source, "/save", body)
    h.server = _FakeServerAddr(8000)
    h.headers["Origin"] = "http://127.0.0.1"
    h.do_POST()
    assert h._status != 403


def test_csrf_origin_non_http_scheme_rejected(fake_source):
    """_is_same_origin — un Origin à schéma non-http(s) (ftp:) est rejeté."""
    body = b"id=ubm-001&action=validate"
    h = _FakeHandler(fake_source, "/save", body)
    h.headers["Origin"] = "ftp://127.0.0.1"
    h.do_POST()
    assert h._status == 403


# ===== Couverture _handle_add_reco (chemin nominal + rejets) ================
def test_add_reco_nominal_creates_and_redirects_to_edit(fake_source):
    """Chemin NOMINAL de /add-reco : crée un stub et redirige vers l'édition."""
    from common import recos_dir_for
    before = {p.name for p in recos_dir_for(fake_source).glob("*.json")}
    h = _FakeHandler(fake_source, "/add-reco", b"guid=ep-001")
    h.do_POST()
    assert h._status == 303
    loc = h._sent_headers["Location"]
    assert loc.startswith("/ep?guid=ep-001")
    assert "edit=" in loc and "kind=info" in loc
    after = {p.name for p in recos_dir_for(fake_source).glob("*.json")}
    assert len(after) == len(before) + 1


def test_add_reco_missing_guid_redirects_root(fake_source):
    h = _FakeHandler(fake_source, "/add-reco", b"guid=")
    h.do_POST()
    assert h._status == 303
    assert h._sent_headers["Location"] == "/"


def test_add_reco_invalid_guid_format_redirects_root(fake_source):
    """guid au format invalide (espace) → redirige / sans rien créer."""
    from common import recos_dir_for
    before = {p.name for p in recos_dir_for(fake_source).glob("*.json")}
    h = _FakeHandler(fake_source, "/add-reco", b"guid=bad+guid")
    h.do_POST()
    assert h._status == 303
    assert h._sent_headers["Location"] == "/"
    after = {p.name for p in recos_dir_for(fake_source).glob("*.json")}
    assert after == before  # rien créé


def test_add_reco_unknown_guid_redirects_root(fake_source):
    """guid de bon format mais absent des épisodes → redirige /."""
    h = _FakeHandler(fake_source, "/add-reco", b"guid=ep-999")
    h.do_POST()
    assert h._status == 303
    assert h._sent_headers["Location"] == "/"


def test_add_reco_path_outside_root_aborts_and_unlinks(fake_source, monkeypatch):
    """#7 sécu — si le nouveau fichier résout HORS recos_root, on le supprime
    et on abort vers / (defense in depth)."""
    import review_routes_reco
    created: list = []
    real_alloc = review_routes_reco._allocate_new_reco

    def _alloc_spy(src, guid):
        new_id, new_path = real_alloc(src, guid)
        created.append(new_path)
        return new_id, new_path

    monkeypatch.setattr(review_routes_reco, "_allocate_new_reco", _alloc_spy)
    monkeypatch.setattr(
        review_routes_reco, "_assert_under_recos", lambda _p, _s: False)
    h = _FakeHandler(fake_source, "/add-reco", b"guid=ep-001")
    h.do_POST()
    assert h._status == 303
    assert h._sent_headers["Location"] == "/"
    # Le stub créé a bien été supprimé (abort).
    assert created and not created[0].exists()


def test_allocate_new_reco_skips_corrupt_and_non_int_id(fake_source):
    """_allocate_new_reco tolère un JSON corrompu (except OSError/ValueError) et
    un id à suffixe non-numérique (except ValueError) sans planter."""
    from common import recos_dir_for
    d = recos_dir_for(fake_source)
    (d / "corrupt.json").write_text("{pas du json", encoding="utf-8")
    (d / "weird.json").write_text(
        json.dumps({"id": "ds-pasunnombre"}), encoding="utf-8")
    new_id, new_path = rs._allocate_new_reco(fake_source, "ep-001")
    assert new_id.startswith("ds-")
    assert new_path.exists()


def test_delete_reco_no_guid_redirects_root(fake_source, monkeypatch, tmp_path):
    """Une reco sans episodeGuid supprimée → redirige / (branche guid falsy)."""
    import review_routes_reco
    monkeypatch.setattr(review_routes_reco, "BACKUP_DIR", tmp_path / "nobackup")
    from common import recos_dir_for
    p = recos_dir_for(fake_source) / "ubm-noguid.json"
    p.write_text(json.dumps({"id": "ubm-noguid", "title": "X"}), encoding="utf-8")
    rs._invalidate_reco_path_cache(fake_source)
    h = _FakeHandler(fake_source, "/delete-reco", b"id=ubm-noguid")
    h.do_POST()
    assert h._status == 303
    assert h._sent_headers["Location"] == "/"
    assert not p.exists()


def test_delete_reco_read_json_error_still_deletes(fake_source, monkeypatch, tmp_path):
    """Si read_json échoue au moment de récupérer le guid (except OSError/
    ValueError), la suppression se poursuit avec guid vide → redirige /."""
    import review_routes_reco
    monkeypatch.setattr(review_routes_reco, "BACKUP_DIR", tmp_path / "nobackup")
    from common import recos_dir_for
    p = recos_dir_for(fake_source) / "ubm-002.json"
    assert p.exists()
    real_read = review_routes_reco.read_json

    def picky(path):
        if "ubm-002" in str(path):
            raise OSError("lecture impossible")
        return real_read(path)

    monkeypatch.setattr(review_routes_reco, "read_json", picky)
    h = _FakeHandler(fake_source, "/delete-reco", b"id=ubm-002")
    h.do_POST()
    assert h._status == 303
    assert h._sent_headers["Location"] == "/"
    assert not p.exists()


# ===== Couverture _handle_delete_reco =======================================
def test_delete_reco_nominal_removes_and_redirects(fake_source, monkeypatch, tmp_path):
    """Chemin nominal : suppression du fichier + redirect /ep avec kind=success."""
    import review_routes_reco
    monkeypatch.setattr(review_routes_reco, "BACKUP_DIR", tmp_path / "nobackup")
    from common import recos_dir_for
    p = recos_dir_for(fake_source) / "ubm-002.json"
    assert p.exists()
    h = _FakeHandler(fake_source, "/delete-reco", b"id=ubm-002")
    h.do_POST()
    assert h._status == 303
    assert not p.exists()
    loc = h._sent_headers["Location"]
    assert loc.startswith("/ep?guid=ep-001")
    assert "kind=success" in loc


def test_delete_reco_invalid_id_redirects_root(fake_source):
    h = _FakeHandler(fake_source, "/delete-reco", b"id=../etc/passwd")
    h.do_POST()
    assert h._status == 303
    assert h._sent_headers["Location"] == "/"


def test_delete_reco_unknown_id_redirects_root(fake_source):
    h = _FakeHandler(fake_source, "/delete-reco", b"id=ubm-zzz")
    h.do_POST()
    assert h._status == 303
    assert h._sent_headers["Location"] == "/"


def test_delete_reco_path_outside_root_403(fake_source, monkeypatch, tmp_path):
    """#19 sécu — un path résolu HORS recos_root → 403, fichier non supprimé."""
    import review_routes_reco
    intruder = tmp_path / "intruder.json"
    intruder.write_text(
        json.dumps({"id": "ubm-x", "episodeGuid": "ep-001"}), encoding="utf-8")
    monkeypatch.setattr(
        review_routes_reco, "_reco_path", lambda _src, _rid: intruder)
    h = _FakeHandler(fake_source, "/delete-reco", b"id=ubm-x")
    h.do_POST()
    assert h._status == 403
    assert intruder.exists()  # défense : pas supprimé


def test_delete_reco_unlink_oserror_redirects_root(fake_source, monkeypatch, tmp_path):
    """OSError sur unlink (fichier verrouillé) → redirige / sans crash."""
    import review_routes_reco
    monkeypatch.setattr(review_routes_reco, "BACKUP_DIR", tmp_path / "nobackup")
    from pathlib import Path
    real_unlink = Path.unlink

    def boom_unlink(self, *a, **k):
        if self.name == "ubm-002.json":
            raise OSError("verrouillé")
        return real_unlink(self, *a, **k)

    monkeypatch.setattr(Path, "unlink", boom_unlink)
    h = _FakeHandler(fake_source, "/delete-reco", b"id=ubm-002")
    h.do_POST()
    assert h._status == 303
    assert h._sent_headers["Location"] == "/"


# ===== Couverture _reco_id_in_recent_backup =================================
def _write_backup_manifest(backup_dir, name, manifest):
    d = backup_dir / name
    d.mkdir(parents=True, exist_ok=True)
    (d / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return d


def test_recent_backup_no_dir_returns_false(fake_source, monkeypatch, tmp_path):
    import review_routes_reco
    monkeypatch.setattr(review_routes_reco, "BACKUP_DIR", tmp_path / "absent")
    h = _FakeHandler(fake_source, "/")
    assert h._reco_id_in_recent_backup("ubm-001") is False


def test_recent_backup_matches_keep_id(fake_source, monkeypatch, tmp_path):
    import review_routes_reco
    backup = tmp_path / "backup"
    _write_backup_manifest(backup, "20260101_000000_a", {
        "source_id": fake_source, "keep_id": "ubm-001", "loser_ids": [],
    })
    monkeypatch.setattr(review_routes_reco, "BACKUP_DIR", backup)
    h = _FakeHandler(fake_source, "/")
    assert h._reco_id_in_recent_backup("ubm-001") is True


def test_recent_backup_matches_loser_id(fake_source, monkeypatch, tmp_path):
    import review_routes_reco
    backup = tmp_path / "backup"
    _write_backup_manifest(backup, "20260101_000000_b", {
        "source_id": fake_source, "keep_id": "ubm-001", "loser_ids": ["ubm-009"],
    })
    monkeypatch.setattr(review_routes_reco, "BACKUP_DIR", backup)
    h = _FakeHandler(fake_source, "/")
    assert h._reco_id_in_recent_backup("ubm-009") is True


def test_recent_backup_other_source_ignored(fake_source, monkeypatch, tmp_path):
    import review_routes_reco
    backup = tmp_path / "backup"
    _write_backup_manifest(backup, "20260101_000000_c", {
        "source_id": "autre-source", "keep_id": "ubm-001", "loser_ids": [],
    })
    monkeypatch.setattr(review_routes_reco, "BACKUP_DIR", backup)
    h = _FakeHandler(fake_source, "/")
    assert h._reco_id_in_recent_backup("ubm-001") is False


def test_recent_backup_unreadable_manifest_skipped(fake_source, monkeypatch, tmp_path):
    import review_routes_reco
    backup = tmp_path / "backup"
    d = backup / "20260101_000000_d"
    d.mkdir(parents=True)
    (d / "manifest.json").write_text("{pas du json", encoding="utf-8")
    monkeypatch.setattr(review_routes_reco, "BACKUP_DIR", backup)
    h = _FakeHandler(fake_source, "/")
    assert h._reco_id_in_recent_backup("ubm-001") is False


def test_recent_backup_dir_without_manifest_skipped(fake_source, monkeypatch, tmp_path):
    import review_routes_reco
    backup = tmp_path / "backup"
    (backup / "20260101_000000_e").mkdir(parents=True)  # pas de manifest.json
    monkeypatch.setattr(review_routes_reco, "BACKUP_DIR", backup)
    h = _FakeHandler(fake_source, "/")
    assert h._reco_id_in_recent_backup("ubm-001") is False


def test_delete_reco_with_recent_backup_warns(fake_source, monkeypatch, tmp_path):
    """#13 sécu — si un backup récent référence l'id supprimé, flash=warning."""
    import review_routes_reco
    backup = tmp_path / "backup"
    _write_backup_manifest(backup, "20260101_000000_f", {
        "source_id": fake_source, "keep_id": "ubm-002", "loser_ids": [],
    })
    monkeypatch.setattr(review_routes_reco, "BACKUP_DIR", backup)
    h = _FakeHandler(fake_source, "/delete-reco", b"id=ubm-002")
    h.do_POST()
    assert h._status == 303
    assert "kind=warning" in h._sent_headers["Location"]


# ===== Couverture _cleanup_orphan_tmp_files =================================
def test_cleanup_orphan_tmp_removes_and_counts(fake_source, monkeypatch, tmp_path):
    """Supprime les *.tmp du dossier recos ET du backup, retourne le compte."""
    import review_routes
    from common import recos_dir_for
    recos = recos_dir_for(fake_source)
    (recos / "orphan1.tmp").write_text("x", encoding="utf-8")
    backup = tmp_path / "backup"
    backup.mkdir()
    (backup / "orphan2.tmp").write_text("x", encoding="utf-8")
    monkeypatch.setattr(review_routes, "BACKUP_DIR", backup)
    n = review_routes._cleanup_orphan_tmp_files(fake_source)
    assert n == 2
    assert not (recos / "orphan1.tmp").exists()
    assert not (backup / "orphan2.tmp").exists()


def test_cleanup_orphan_tmp_none_returns_zero(fake_source, monkeypatch, tmp_path):
    import review_routes
    monkeypatch.setattr(review_routes, "BACKUP_DIR", tmp_path / "empty-backup")
    assert review_routes._cleanup_orphan_tmp_files(fake_source) == 0


# ===== rev-render m7 : render_merge_preview keep_id absent ==================
def test_render_merge_preview_keep_id_absent_no_stopiteration():
    """rev-render m7 (revue 2026-07-19) — appelée directement avec un keep_id
    hors des membres, la fonction ne lève plus StopIteration : elle rend une
    page d'erreur lisible (garde `next(..., None)`)."""
    from review_render_cluster import render_merge_preview
    members = [
        {"id": "ubm-1", "title": "A"},
        {"id": "ubm-2", "title": "B"},
    ]
    out = render_merge_preview(members, keep_id="ubm-absent", guid="ep-001")
    assert "introuvable" in out.lower()


def test_render_merge_preview_keep_id_present_ok():
    """rev-render m7 — cas nominal préservé : keep_id ∈ members rend le diff."""
    from review_render_cluster import render_merge_preview
    members = [
        {"id": "ubm-1", "title": "Garder"},
        {"id": "ubm-2", "title": "Absorber"},
    ]
    out = render_merge_preview(members, keep_id="ubm-1", guid="ep-001")
    assert "Aperçu de la fusion" in out
    assert "ubm-2" in out


# ===== rev-render m3 : route GET /doutes propage flash/kind =================
def test_get_doutes_route_renders_flash_banner(fake_source):
    """rev-render m3 — la route GET /doutes?flash=…&kind=… lit les params et
    rend la bannière (retour d'un POST /save initié depuis /doutes, sans JS)."""
    # ubm-001 (draft) porte un agentReview unsure → une entrée /doutes existe.
    from common import recos_dir_for
    p = recos_dir_for(fake_source) / "ubm-001.json"
    reco = json.loads(p.read_text(encoding="utf-8"))
    reco["agentReview"] = {"verdict": "unsure", "confidence": 0.4, "reason": "?"}
    p.write_text(json.dumps(reco), encoding="utf-8")
    rs._invalidate_reco_path_cache(fake_source)

    loc = "/doutes?flash=" + urllib.parse.quote("Traité — reco suivante.") + "&kind=success"
    h = _FakeHandler(fake_source, loc)
    h.do_GET()
    assert h._status == 200
    body = h.wfile.getvalue().decode("utf-8")
    assert "flash-success" in body
    assert "Traité" in body


def test_get_doutes_route_invalid_kind_falls_back_info(fake_source):
    """rev-render m3 — un kind hors liste blanche dans l'URL retombe sur info."""
    loc = "/doutes?flash=" + urllib.parse.quote("msg") + "&kind=zzz"
    h = _FakeHandler(fake_source, loc)
    h.do_GET()
    assert h._status == 200
    body = h.wfile.getvalue().decode("utf-8")
    if "class=\"flash" in body:  # bannière présente (au moins l'état vide)
        assert "flash-info" in body
        assert "flash-zzz" not in body


# ===== Couverture render_pick_canonical / _action_pick ======================
def test_post_merge_recos_pick_renders_canonical_page(fake_source):
    """Chemin pick nominal : ≥ 2 membres → page « choisis la version à garder »
    (couvre _action_pick + render_pick_canonical)."""
    _add_dup_recos(fake_source, None)
    body = b"guid=ep-001&action=pick&cluster_ids=ubm-dup-1,ubm-dup-2"
    h = _FakeHandler(fake_source, "/merge-recos", body)
    h.do_POST()
    assert h._status == 200
    out = h.wfile.getvalue().decode("utf-8")
    assert "choisis la version à garder" in out
    assert find_radio(parse(out), "keep_id", "ubm-dup-1") is not None


def test_post_merge_recos_pick_one_member_rejected_warns(fake_source):
    """_action_pick : 1 membre valide + 1 rejeté (inexistant) → flash warning
    mentionnant le rejet (branche n_rejected > 0)."""
    from common import recos_dir_for
    (recos_dir_for(fake_source) / "ubm-solo.json").write_text(json.dumps({
        "id": "ubm-solo", "episodeGuid": "ep-001", "types": ["film"],
        "title": "Solo", "status": "draft", "extractors": ["claude"],
    }), encoding="utf-8")
    rs._invalidate_reco_path_cache(fake_source)
    body = b"guid=ep-001&action=pick&cluster_ids=ubm-solo,ubm-ghost"
    h = _FakeHandler(fake_source, "/merge-recos", body)
    h.do_POST()
    assert h._status == 303
    loc = h._sent_headers["Location"]
    assert "kind=warning" in loc
    assert "rejet" in urllib.parse.unquote(loc).lower()


def test_post_merge_recos_pick_single_no_rejected_warns(fake_source):
    """_action_pick : un seul membre, aucun rejet → message « au moins 2 »
    (branche else)."""
    from common import recos_dir_for
    (recos_dir_for(fake_source) / "ubm-solo.json").write_text(json.dumps({
        "id": "ubm-solo", "episodeGuid": "ep-001", "types": ["film"],
        "title": "Solo", "status": "draft", "extractors": ["claude"],
    }), encoding="utf-8")
    rs._invalidate_reco_path_cache(fake_source)
    body = b"guid=ep-001&action=pick&cluster_ids=ubm-solo"
    h = _FakeHandler(fake_source, "/merge-recos", body)
    h.do_POST()
    assert h._status == 303
    loc = urllib.parse.unquote(h._sent_headers["Location"])
    assert "kind=warning" in h._sent_headers["Location"]
    assert "au moins 2" in loc


# ===== Couverture do_POST : bornes Content-Length ===========================
def test_post_content_length_non_numeric_400(fake_source):
    """Content-Length non numérique → 400 (avant lecture du body)."""
    h = _FakeHandler(fake_source, "/save", b"id=ubm-001")
    h.headers["Content-Length"] = "abc"
    h.do_POST()
    assert h._status == 400


def test_post_content_length_negative_400(fake_source):
    """Content-Length négatif → 400."""
    h = _FakeHandler(fake_source, "/save", b"id=ubm-001")
    h.headers["Content-Length"] = "-5"
    h.do_POST()
    assert h._status == 400


def test_cleanup_orphan_tmp_oserror_logged(fake_source, monkeypatch, tmp_path, caplog):
    """Un unlink qui échoue est loggé en warning sans faire crasher le cleanup."""
    import review_routes
    from common import recos_dir_for
    from pathlib import Path
    (recos_dir_for(fake_source) / "stuck.tmp").write_text("x", encoding="utf-8")
    monkeypatch.setattr(review_routes, "BACKUP_DIR", tmp_path / "empty-backup")
    real_unlink = Path.unlink

    def boom(self, *a, **k):
        if self.suffix == ".tmp":
            raise OSError("verrouillé")
        return real_unlink(self, *a, **k)

    monkeypatch.setattr(Path, "unlink", boom)
    with caplog.at_level("WARNING"):
        n = review_routes._cleanup_orphan_tmp_files(fake_source)
    assert n == 0
    assert any("Cleanup tmp" in r.message for r in caplog.records)


# ===== Couverture _apply_save_action : recommendedBy citation ===============
def test_save_citation_with_recommender_sets_recby(fake_source):
    """action=citation + who → recommendedBy renseigné (branche recommended)."""
    from common import read_json, recos_dir_for
    body = b"id=ubm-001&action=citation&who=Alice"
    h = _FakeHandler(fake_source, "/save", body)
    h.do_POST()
    reco = read_json(recos_dir_for(fake_source) / "ubm-001.json")
    assert reco["recommendedBy"] == "Alice"
    assert reco["kind"] == "citation"


def test_save_citation_without_names_drops_existing_recby(fake_source):
    """action=citation sans nom sur une reco qui AVAIT un recommendedBy → il est
    retiré (branche elif del)."""
    from common import read_json, recos_dir_for
    p = recos_dir_for(fake_source) / "ubm-002.json"  # a recommendedBy=Alice
    assert json.loads(p.read_text(encoding="utf-8")).get("recommendedBy") == "Alice"
    body = b"id=ubm-002&action=citation"
    h = _FakeHandler(fake_source, "/save", body)
    h.do_POST()
    reco = read_json(p)
    assert "recommendedBy" not in reco
    assert reco["kind"] == "citation"


# ===== Couverture undo-merge : guid invalide + restauration partielle =======
def test_undo_merge_invalid_guid_format_redirects_root(fake_source):
    """/undo-merge avec guid au format invalide → redirige / (garde _RE_GUID)."""
    h = _FakeHandler(fake_source, "/undo-merge", b"guid=bad+guid")
    h.do_POST()
    assert h._status == 303
    assert h._sent_headers["Location"] == "/"


def test_undo_merge_partial_restore_warns(fake_source, monkeypatch):
    """/undo-merge avec restauration PARTIELLE (n_failed > 0) → flash warning
    distinct (branche #10 sécu)."""
    import review_routes_merge
    monkeypatch.setattr(
        review_routes_merge, "restore_last_backup",
        lambda _src: {"n_restored": 3, "n_failed": 1})
    h = _FakeHandler(fake_source, "/undo-merge", b"guid=ep-001")
    h.do_POST()
    assert h._status == 303
    loc = urllib.parse.unquote(h._sent_headers["Location"])
    assert "kind=warning" in h._sent_headers["Location"]
    assert "échec" in loc


def test_undo_merge_without_guid_redirects_root(fake_source, monkeypatch):
    """/undo-merge sans guid → redirige / (loc par défaut)."""
    import review_routes_merge
    monkeypatch.setattr(
        review_routes_merge, "restore_last_backup",
        lambda _src: {"n_restored": 2, "n_failed": 0})
    h = _FakeHandler(fake_source, "/undo-merge", b"guid=")
    h.do_POST()
    assert h._status == 303
    assert h._sent_headers["Location"] == "/"
