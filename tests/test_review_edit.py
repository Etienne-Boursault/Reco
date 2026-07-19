"""Tests pour tools/review_edit.py — cible 100%."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from review_edit import (
    EXT_FIELDS, RECO_TYPES, _kind_for,
    _render_creators_datalist, _render_custom_links_section,
    _render_ext_inputs, _render_overrides_section,
    _render_recommenders_datalist, _render_type_boxes, _render_wp_inputs,
    apply_edit, is_reenrichable,
    render_edit_form, render_type_badges,
)


# ===== render_type_badges ===================================================
def test_render_type_badges_includes_emoji_and_title():
    out = render_type_badges(["film", "musique"])
    assert "🎬" in out
    assert "🎵" in out
    assert 'title="Film"' in out
    assert 'title="Musique"' in out
    assert 'aria-label="Film"' in out


def test_render_type_badges_unknown_type_falls_back():
    out = render_type_badges(["zzz"])
    assert "✨" in out
    assert 'title="zzz"' in out


def test_render_type_badges_empty():
    assert render_type_badges([]) == ""


# ===== is_reenrichable ======================================================
@pytest.mark.parametrize("t", ["film", "serie", "musique", "album", "artiste"])
def test_is_reenrichable_true_for_supported_types(t):
    assert is_reenrichable({"types": [t]}) is True


@pytest.mark.parametrize("t", ["livre", "podcast", "jeu", "bd"])
def test_is_reenrichable_false_for_unsupported_types(t):
    assert is_reenrichable({"types": [t]}) is False


def test_is_reenrichable_multi_type_keeps_true_if_one_supported():
    assert is_reenrichable({"types": ["livre", "film"]}) is True


def test_is_reenrichable_empty_types():
    assert is_reenrichable({}) is False


# ===== apply_edit ===========================================================
@pytest.fixture
def reco_path(tmp_path):
    """Crée une reco minimale sur disque + renvoie le chemin."""
    p = tmp_path / "r1.json"
    p.write_text(json.dumps({
        "id": "r1", "episodeGuid": "ep-1", "title": "Old",
        "creator": "Old creator", "types": ["film"], "status": "draft",
    }), encoding="utf-8")
    return p


def test_apply_edit_minimal_required_fields(reco_path):
    ok, guid = apply_edit(reco_path, {
        "title": ["New"], "types": ["film"],
    })
    assert ok is True
    assert guid == "ep-1"
    reco = json.loads(reco_path.read_text(encoding="utf-8"))
    assert reco["title"] == "New"
    assert reco["types"] == ["film"]


def test_apply_edit_rejects_empty_title(reco_path):
    ok, guid = apply_edit(reco_path, {"title": [""], "types": ["film"]})
    assert ok is False
    assert guid == ""


def test_apply_edit_rejects_empty_types(reco_path):
    ok, _ = apply_edit(reco_path, {"title": ["X"], "types": []})
    assert ok is False


def test_apply_edit_unknown_types_filtered_out(reco_path):
    """Un type inconnu est filtré → si AUCUN type connu, rejet."""
    ok, _ = apply_edit(reco_path, {"title": ["X"], "types": ["unknown_type"]})
    assert ok is False


def test_apply_edit_unknown_types_partially_filtered(reco_path):
    """Type inconnu mélangé à un type connu : on garde le connu."""
    ok, _ = apply_edit(reco_path, {
        "title": ["X"], "types": ["film", "blablabla"],
    })
    assert ok is True
    reco = json.loads(reco_path.read_text(encoding="utf-8"))
    assert reco["types"] == ["film"]


def test_apply_edit_dedups_types(reco_path):
    apply_edit(reco_path, {"title": ["X"], "types": ["film", "film", "serie"]})
    reco = json.loads(reco_path.read_text(encoding="utf-8"))
    assert reco["types"] == ["film", "serie"]


def test_apply_edit_recommendedBy_persisted(reco_path):
    apply_edit(reco_path, {
        "title": ["X"], "types": ["film"], "recommendedBy": ["Kyan"],
    })
    reco = json.loads(reco_path.read_text(encoding="utf-8"))
    assert reco["recommendedBy"] == "Kyan"


def test_apply_edit_empty_recommendedBy_removes_key(reco_path):
    # Pre-set
    apply_edit(reco_path, {
        "title": ["X"], "types": ["film"], "recommendedBy": ["Kyan"],
    })
    apply_edit(reco_path, {
        "title": ["X"], "types": ["film"], "recommendedBy": [""],
    })
    reco = json.loads(reco_path.read_text(encoding="utf-8"))
    assert "recommendedBy" not in reco


# ----- customLinks ----------------------------------------------------------
def test_apply_edit_writes_custom_links(reco_path):
    ok, _ = apply_edit(reco_path, {
        "title": ["X"], "types": ["film"],
        "cl_label_0": ["FNAC"], "cl_url_0": ["https://fnac.com/x"],
        "cl_logo_0": [""],
    })
    assert ok
    reco = json.loads(reco_path.read_text(encoding="utf-8"))
    assert reco["customLinks"] == [{"label": "FNAC", "url": "https://fnac.com/x"}]


def test_apply_edit_custom_links_with_logo_url(reco_path):
    apply_edit(reco_path, {
        "title": ["X"], "types": ["film"],
        "cl_label_0": ["FNAC"], "cl_url_0": ["https://fnac.com/x"],
        "cl_logo_0": ["https://fnac.com/logo.png"],
    })
    reco = json.loads(reco_path.read_text(encoding="utf-8"))
    assert reco["customLinks"][0]["logoUrl"] == "https://fnac.com/logo.png"


def test_apply_edit_custom_link_logo_rejects_non_https(reco_path):
    """m2 (rev-render) — un cl_logo non-https (rendu en <img src> sur le site
    public) n'est pas stocké ; le lien lui-même reste valide."""
    apply_edit(reco_path, {
        "title": ["X"], "types": ["film"],
        "cl_label_0": ["FNAC"], "cl_url_0": ["https://fnac.com/x"],
        "cl_logo_0": ["http://tracker.example/pixel.gif"],
    })
    reco = json.loads(reco_path.read_text(encoding="utf-8"))
    assert reco["customLinks"][0]["url"] == "https://fnac.com/x"
    assert "logoUrl" not in reco["customLinks"][0]


def test_apply_edit_custom_links_empty_label_dropped(reco_path):
    apply_edit(reco_path, {
        "title": ["X"], "types": ["film"],
        "cl_label_0": [""], "cl_url_0": ["https://x.com"],
    })
    reco = json.loads(reco_path.read_text(encoding="utf-8"))
    assert "customLinks" not in reco


def test_apply_edit_custom_links_empty_url_dropped(reco_path):
    apply_edit(reco_path, {
        "title": ["X"], "types": ["film"],
        "cl_label_0": ["FNAC"], "cl_url_0": [""],
    })
    reco = json.loads(reco_path.read_text(encoding="utf-8"))
    assert "customLinks" not in reco


def test_apply_edit_custom_links_removes_existing_when_all_empty(reco_path):
    """Une reco avec customLinks préexistants, soumis vides → suppression."""
    reco = json.loads(reco_path.read_text(encoding="utf-8"))
    reco["customLinks"] = [{"label": "Old", "url": "https://old"}]
    reco_path.write_text(json.dumps(reco), encoding="utf-8")
    apply_edit(reco_path, {
        "title": ["X"], "types": ["film"],
        "cl_label_0": [""], "cl_url_0": [""],
    })
    reco = json.loads(reco_path.read_text(encoding="utf-8"))
    assert "customLinks" not in reco


def test_apply_edit_custom_links_rejects_non_https(reco_path):
    """m1 (revue 2026-07-19) — un customLink à scheme non-https (javascript:)
    est refusé ; un lien https:// valide de la même soumission est conservé
    (garde XSS au write, parité watchProviders)."""
    apply_edit(reco_path, {
        "title": ["X"], "types": ["film"],
        "cl_label_0": ["Evil"], "cl_url_0": ["javascript:alert(1)"],
        "cl_label_1": ["FNAC"], "cl_url_1": ["https://fnac.com/x"],
    })
    reco = json.loads(reco_path.read_text(encoding="utf-8"))
    urls = [link["url"] for link in reco.get("customLinks", [])]
    assert "javascript:alert(1)" not in urls
    assert urls == ["https://fnac.com/x"]


# ----- linkOverrides --------------------------------------------------------
def test_apply_edit_link_overrides_rejects_non_https(reco_path):
    """m1 — un override à scheme non-https est refusé."""
    apply_edit(reco_path, {
        "title": ["X"], "types": ["film"],
        "lo_JustWatch": ["javascript:alert(1)"],
    })
    reco = json.loads(reco_path.read_text(encoding="utf-8"))
    assert "linkOverrides" not in reco


def test_apply_edit_writes_link_overrides(reco_path):
    apply_edit(reco_path, {
        "title": ["X"], "types": ["film"],
        "lo_JustWatch": ["https://justwatch.com/exact"],
    })
    reco = json.loads(reco_path.read_text(encoding="utf-8"))
    assert reco["linkOverrides"] == {"JustWatch": "https://justwatch.com/exact"}


def test_apply_edit_link_overrides_empty_url_deletes_entry(reco_path):
    # On pose un override existant.
    apply_edit(reco_path, {
        "title": ["X"], "types": ["film"],
        "lo_JustWatch": ["https://justwatch.com/x"],
    })
    # Puis on l'efface (URL vide).
    apply_edit(reco_path, {
        "title": ["X"], "types": ["film"],
        "lo_JustWatch": [""],
    })
    reco = json.loads(reco_path.read_text(encoding="utf-8"))
    assert "linkOverrides" not in reco


def test_apply_edit_link_overrides_rejects_unknown_label(reco_path):
    """H3 : un label hors miroir merchants.ts est ignoré silencieusement."""
    apply_edit(reco_path, {
        "title": ["X"], "types": ["film"],
        "lo_EvilCorp": ["https://evil.com"],
        "lo_JustWatch": ["https://jw.com/x"],
    })
    reco = json.loads(reco_path.read_text(encoding="utf-8"))
    assert reco["linkOverrides"] == {"JustWatch": "https://jw.com/x"}
    assert "EvilCorp" not in reco["linkOverrides"]


# ----- externalIds / watchProviders / creator -------------------------------
def test_apply_edit_creator_empty_drops_key(reco_path):
    apply_edit(reco_path, {
        "title": ["X"], "types": ["film"], "creator": [""],
    })
    reco = json.loads(reco_path.read_text(encoding="utf-8"))
    assert "creator" not in reco


def test_apply_edit_ext_field_value_kept(reco_path):
    # Pre-set ext
    reco = json.loads(reco_path.read_text(encoding="utf-8"))
    reco["externalIds"] = {"tmdb": "old"}
    reco_path.write_text(json.dumps(reco), encoding="utf-8")
    apply_edit(reco_path, {
        "title": ["X"], "types": ["film"], "ext_tmdb": ["new42"],
    })
    reco = json.loads(reco_path.read_text(encoding="utf-8"))
    assert reco["externalIds"]["tmdb"] == "new42"


def test_apply_edit_watchProviders_kept_when_label_and_url(reco_path):
    apply_edit(reco_path, {
        "title": ["X"], "types": ["film"],
        "wp_label_0": ["Netflix"], "wp_url_0": ["https://netflix.com/x"],
    })
    reco = json.loads(reco_path.read_text(encoding="utf-8"))
    assert reco["watchProviders"] == [
        {"label": "Netflix", "url": "https://netflix.com/x"},
    ]


def test_apply_edit_watchProviders_rejects_non_https(reco_path):
    """L10 : une URL non-https (http, javascript:, /chemin) est rejetée."""
    apply_edit(reco_path, {
        "title": ["X"], "types": ["film"],
        "wp_label_0": ["A"], "wp_url_0": ["http://insecure.com/x"],
        "wp_label_1": ["B"], "wp_url_1": ["javascript:alert(1)"],
        "wp_label_2": ["C"], "wp_url_2": ["https://ok.com/y"],
    })
    reco = json.loads(reco_path.read_text(encoding="utf-8"))
    assert reco["watchProviders"] == [{"label": "C", "url": "https://ok.com/y"}]


# ===== render_edit_form =====================================================
def _ep():
    return {"guid": "ep-1", "title": "Ep titre"}


def test_render_edit_form_includes_creators_datalist():
    r = {"id": "r1", "title": "T", "types": ["film"]}
    siblings = [
        {"id": "r2", "creator": "X. Auteur"},
        {"id": "r3", "creator": "Y. Auteur"},
    ]
    out = render_edit_form(r, _ep(), siblings=siblings, hosts=[])
    assert 'list="creators-r1"' in out
    assert "X. Auteur" in out
    assert "Y. Auteur" in out


def test_render_edit_form_includes_recommenders_datalist_with_hosts_first():
    """M8 : la datalist doit lister hosts en premier puis autres invités."""
    r = {"id": "r1", "title": "T", "types": ["film"]}
    siblings = [{"id": "r2", "recommendedBy": "Zaz"}]
    hosts = ["Kyan", "Navo"]
    out = render_edit_form(r, _ep(), siblings=siblings, hosts=hosts)
    # Kyan apparaît AVANT Navo, qui apparaît AVANT Zaz.
    i_kyan = out.find("Kyan")
    i_navo = out.find("Navo")
    i_zaz = out.find("Zaz")
    assert 0 < i_kyan < i_navo < i_zaz


def test_render_edit_form_includes_clickable_platform_labels():
    """Pour les types film, JustWatch apparaît avec un lien `<a>`."""
    r = {"id": "r1", "title": "T", "types": ["film"]}
    out = render_edit_form(r, _ep(), siblings=[], hosts=[])
    assert "JustWatch" in out
    assert "<a class=\"ov-label\"" in out


def test_render_edit_form_includes_existing_overrides_even_if_type_unsupported():
    """M9 : un override sur un label qui n'est plus dans les types affichés
    reste éditable (cas d'un type changé après coup)."""
    r = {
        "id": "r1", "title": "T", "types": [],
        "linkOverrides": {"JustWatch": "https://jw.com/x"},
    }
    out = render_edit_form(r, _ep(), siblings=[], hosts=[])
    assert "JustWatch" in out
    assert "https://jw.com/x" in out


def test_render_edit_form_renders_custom_links_block_when_present():
    r = {"id": "r1", "title": "T", "types": ["film"],
         "customLinks": [{"label": "FNAC", "url": "https://fnac.com/x"}]}
    out = render_edit_form(r, _ep(), siblings=[], hosts=[])
    assert "FNAC" in out
    assert "https://fnac.com/x" in out


def test_render_edit_form_renders_ext_and_wp_inputs():
    r = {"id": "r1", "title": "T", "types": ["film"],
         "externalIds": {"tmdb": "42"},
         "watchProviders": [{"label": "Netflix", "url": "https://nf"}]}
    out = render_edit_form(r, _ep(), siblings=[], hosts=[])
    assert 'name="ext_tmdb"' in out
    assert 'name="wp_label_0"' in out
    assert 'name="wp_url_0"' in out


def test_render_edit_form_escapes_dangerous_input():
    r = {"id": "r1", "title": "<script>alert(1)</script>", "types": ["film"]}
    out = render_edit_form(r, _ep(), siblings=[], hosts=[])
    assert "<script>alert(1)</script>" not in out
    assert "&lt;script&gt;" in out


# ===== _kind_for ============================================================
def test_kind_for_priority():
    assert _kind_for(["error", "ok"]) == "error"
    assert _kind_for(["not_found", "ok"]) == "warning"
    assert _kind_for(["ok"]) == "success"
    assert _kind_for([]) == "info"


# ===== apply_reenrich (mocké) ===============================================
# ===== Helpers de render_edit_form ==========================================
def test_render_creators_datalist_empty_returns_empty_html():
    creators, dl_id, dl_html = _render_creators_datalist([], "r1")
    assert creators == []
    assert dl_html == ""


def test_render_creators_datalist_excludes_self():
    """La reco elle-même n'apparaît PAS dans sa propre datalist de créateurs."""
    siblings = [
        {"id": "r1", "creator": "Self"},  # self → exclu
        {"id": "r2", "creator": "Other"},
    ]
    creators, _, dl_html = _render_creators_datalist(siblings, "r1")
    assert "Self" not in creators
    assert "Other" in creators


def test_render_recommenders_datalist_hosts_first_then_alpha():
    siblings = [{"id": "r2", "recommendedBy": "Zaz"}, {"id": "r3", "recommendedBy": "Albert"}]
    hosts = ["Kyan", "Navo"]
    rec, _, dl_html = _render_recommenders_datalist(siblings, hosts, "r1")
    assert rec[:2] == ["Kyan", "Navo"]
    # Et Albert avant Zaz (alphabétique)
    assert rec.index("Albert") < rec.index("Zaz")


def test_render_recommenders_datalist_dedups_hosts():
    """Si `hosts` contient des doublons casse → dédup en gardant l'ordre."""
    rec, _, _ = _render_recommenders_datalist([], ["Kyan", "kyan"], "r1")
    assert rec == ["Kyan"]


def test_render_type_boxes_marks_checked_only_for_current():
    out = _render_type_boxes({"film"})
    assert 'value="film" checked' in out
    assert 'value="serie" checked' not in out


def test_render_ext_inputs_one_per_present_field():
    out = _render_ext_inputs({"tmdb": "42", "imdb": "tt999"})
    assert len(out) == 2
    assert any('name="ext_tmdb"' in s for s in out)


def test_render_ext_inputs_empty():
    assert _render_ext_inputs({}) == []


def test_render_wp_inputs_one_per_provider():
    out = _render_wp_inputs([
        {"label": "Netflix", "url": "https://nf"},
        {"label": "Canal", "url": "https://canal"},
    ])
    assert len(out) == 2
    assert 'name="wp_label_0"' in out[0]
    assert 'name="wp_url_1"' in out[1]


def test_render_custom_links_section_renders_empty_row_at_end():
    out = _render_custom_links_section([])
    # Une ligne vide pour ajouter
    assert 'name="cl_label_0"' in out


def test_render_custom_links_section_with_existing_link():
    out = _render_custom_links_section([{"label": "FNAC", "url": "https://fnac.com"}])
    assert "FNAC" in out
    assert 'name="cl_label_0" value="FNAC"' in out
    # La ligne d'ajout vide à l'index suivant
    assert 'name="cl_label_1"' in out


def test_render_overrides_section_empty_when_no_types_no_overrides():
    out = _render_overrides_section({"types": []})
    assert out == ""


def test_render_overrides_section_rejects_javascript_href():
    """C1 (revue 2026-07-19) — un externalIds hostile (javascript:) ne devient
    JAMAIS un href cliquable dans le formulaire d'override : html.escape
    n'échappe pas le schéma, donc _safe_url le neutralise (rendu en <span>)."""
    out = _render_overrides_section({
        "types": ["artiste"],
        "externalIds": {"website": "javascript:alert(document.domain)"},
    })
    assert "javascript:" not in out
    out2 = _render_overrides_section({
        "types": ["album"],
        "externalIds": {"deezer": "javascript:alert(1)"},
    })
    assert "javascript:" not in out2


def test_render_recap_string_duration_no_crash():
    """M1 (revue 2026-07-19) — youtubeDuration en chaîne ne fait pas planter le
    recap (offset via _safe_int, parité _reco_card)."""
    from review_edit_form import render_edit_form
    r = {"id": "ubm-1", "title": "X", "types": ["film"],
         "timestamp": "00:01:00", "transcriptSource": "acast"}
    ep = {"guid": "g1", "youtubeUrl": "https://youtu.be/abc",
          "youtubeDuration": "3700", "audioDuration": 3600}
    out = render_edit_form(r, ep, [], [])  # ne doit pas lever
    assert 'class="tc"' in out  # timecode cliquable rendu (offset appliqué)


def test_render_overrides_section_for_film_includes_justwatch():
    out = _render_overrides_section({"types": ["film"], "title": "X"})
    assert "JustWatch" in out
    assert 'name="lo_JustWatch"' in out


# ===== F2 — Dropdown invités pour recommendedBy =============================
def test_edit_form_shows_recommendedby_select_with_hosts_and_guests():
    r = {"id": "r1", "title": "T", "types": ["film"]}
    ep = {"guid": "g", "title": "Ep", "guests": ["Charlie"]}
    out = render_edit_form(r, ep, siblings=[], hosts=["Kyan", "Navo"])
    assert '<select name="recommendedBy">' in out
    # Hosts puis invité ; chaque candidat est un <option>.
    assert '<option value="Kyan"' in out
    assert '<option value="Navo"' in out
    assert '<option value="Charlie"' in out
    # Option neutre vide en tête.
    assert '<option value="">' in out
    # Hosts AVANT invités dans l'ordre du HTML.
    assert out.find('value="Kyan"') < out.find('value="Charlie"')


def test_edit_form_recby_select_includes_guests_parsed():
    """#3 — les invités du snapshot `guestsParsed` (épisode migré, sans
    `guests` manuel) doivent apparaître dans le dropdown « Reco de »."""
    r = {"id": "r1", "title": "T", "types": ["film"]}
    ep = {"guid": "g", "title": "Ep", "guestsParsed": ["Djamila"]}
    out = render_edit_form(r, ep, siblings=[], hosts=["Kyan"])
    assert '<option value="Djamila"' in out


def test_edit_form_recby_select_falls_back_to_title_parse():
    """#3 — épisode legacy (ni `guests` ni `guestsParsed`) : on parse le
    titre à la volée pour proposer l'invité, comme les checkboxes de carte."""
    r = {"id": "r1", "title": "T", "types": ["film"]}
    ep = {"guid": "g", "title": "Un bon moment avec Fary"}
    out = render_edit_form(r, ep, siblings=[], hosts=["Kyan", "Navo"])
    assert '<option value="Fary"' in out


def test_edit_form_recby_select_excludes_guests_excluded():
    """#3 — un invité présent dans `guestsExcluded` ne doit PAS être proposé
    (cohérence avec collect_guests, autorité ultime)."""
    r = {"id": "r1", "title": "T", "types": ["film"]}
    ep = {
        "guid": "g", "title": "Ep",
        "guestsParsed": ["Djamila", "Fary"],
        "guestsExcluded": ["Fary"],
    }
    out = render_edit_form(r, ep, siblings=[], hosts=["Kyan"])
    assert '<option value="Djamila"' in out
    assert '<option value="Fary"' not in out


def test_edit_form_shows_freeform_other_input():
    r = {"id": "r1", "title": "T", "types": ["film"]}
    out = render_edit_form(r, {"guid": "g"}, siblings=[], hosts=["Kyan"])
    assert 'name="recommendedByOther"' in out
    # Le champ libre est un input texte vide (placeholder, pas value).
    assert 'name="recommendedByOther" value=""' in out


def test_edit_form_select_preselects_existing_recommendedBy():
    """Si la reco a déjà un recommendedBy, l'option correspondante est selected."""
    r = {"id": "r1", "title": "T", "types": ["film"], "recommendedBy": "Kyan"}
    out = render_edit_form(r, {"guid": "g"}, siblings=[], hosts=["Kyan", "Navo"])
    assert 'value="Kyan" selected' in out


def test_edit_form_select_keeps_unknown_recommendedBy_as_option():
    """Si recommendedBy n'est pas dans les candidats, l'ajouter en option
    sélectionnée pour ne pas perdre silencieusement la valeur."""
    r = {"id": "r1", "title": "T", "types": ["film"], "recommendedBy": "Inconnu"}
    out = render_edit_form(r, {"guid": "g"}, siblings=[], hosts=["Kyan"])
    assert 'value="Inconnu" selected' in out


def test_apply_edit_uses_freeform_other_when_provided(reco_path):
    """`recommendedByOther` non vide → l'emporte sur `recommendedBy`."""
    ok, _ = apply_edit(reco_path, {
        "title": ["X"], "types": ["film"],
        "recommendedBy": ["Kyan"],
        "recommendedByOther": ["Nouvelle Invitée"],
    })
    assert ok
    reco = json.loads(reco_path.read_text(encoding="utf-8"))
    assert reco["recommendedBy"] == "Nouvelle Invitée"


def test_apply_edit_uses_select_when_other_empty(reco_path):
    """`recommendedByOther` vide → on garde la valeur du select."""
    ok, _ = apply_edit(reco_path, {
        "title": ["X"], "types": ["film"],
        "recommendedBy": ["Kyan"],
        "recommendedByOther": [""],
    })
    assert ok
    reco = json.loads(reco_path.read_text(encoding="utf-8"))
    assert reco["recommendedBy"] == "Kyan"


def test_apply_edit_both_empty_removes_recommendedBy(reco_path):
    """Les deux vides → la clé disparait (comportement précédent préservé)."""
    # Pré-set
    apply_edit(reco_path, {
        "title": ["X"], "types": ["film"],
        "recommendedByOther": ["First"],
    })
    apply_edit(reco_path, {
        "title": ["X"], "types": ["film"],
        "recommendedBy": [""],
        "recommendedByOther": [""],
    })
    reco = json.loads(reco_path.read_text(encoding="utf-8"))
    assert "recommendedBy" not in reco


# ===== F3 — Récap timecode + quote dans edit form ===========================
def test_edit_form_recap_has_clickable_timecode():
    """Le récap contient le ▶ HH:MM:SS cliquable comme dans _reco_card."""
    r = {
        "id": "r1", "title": "T", "types": ["film"],
        "timestamp": "00:10:30", "transcriptSource": "youtube",
    }
    ep = {
        "guid": "g",
        "youtubeUrl": "https://www.youtube.com/watch?v=ABCDEFGHIJK",
    }
    out = render_edit_form(r, ep, siblings=[], hosts=[])
    # Le bloc récap doit précéder le formulaire.
    assert "edit-recap" in out
    assert "▶ 00:10:30" in out
    assert "embed/ABCDEFGHIJK" in out
    assert "start=630" in out  # 10*60 + 30
    # Recap AVANT le formulaire.
    assert out.find("edit-recap") < out.find('<form class="edit-form"')


def test_edit_form_recap_shows_quote():
    r = {
        "id": "r1", "title": "T", "types": ["film"],
        "quote": "Citation magnifique",
    }
    out = render_edit_form(r, {"guid": "g"}, siblings=[], hosts=[])
    assert "recap-quote" in out
    assert "Citation magnifique" in out
    assert "« Citation magnifique »" in out


def test_edit_form_recap_applies_yt_offset_for_acast_source():
    """transcriptSource=acast → tv = secs + (youtubeDuration - audioDuration)."""
    r = {
        "id": "r1", "title": "T", "types": ["film"],
        "timestamp": "00:01:00", "transcriptSource": "acast",
    }
    ep = {
        "guid": "g",
        "youtubeUrl": "https://www.youtube.com/watch?v=XYZ",
        "audioDuration": 3600,
        "youtubeDuration": 3700,  # offset = 100
    }
    out = render_edit_form(r, ep, siblings=[], hosts=[])
    # 60 (timestamp) + 100 (offset) = 160
    assert "start=160" in out


def test_edit_form_recap_no_offset_for_youtube_source():
    r = {
        "id": "r1", "title": "T", "types": ["film"],
        "timestamp": "00:01:00", "transcriptSource": "youtube",
    }
    ep = {
        "guid": "g",
        "youtubeUrl": "https://www.youtube.com/watch?v=XYZ",
        "audioDuration": 3600,
        "youtubeDuration": 3700,
    }
    out = render_edit_form(r, ep, siblings=[], hosts=[])
    assert "start=60" in out


def test_edit_form_recap_shows_recommendedBy():
    r = {
        "id": "r1", "title": "T", "types": ["film"],
        "recommendedBy": "Kyan",
    }
    out = render_edit_form(r, {"guid": "g"}, siblings=[], hosts=[])
    assert "recap-recby" in out
    assert "Kyan" in out


def test_edit_form_recap_omitted_when_nothing_to_show():
    """Pas de timestamp/quote/recommendedBy → pas de bloc récap inutile."""
    r = {"id": "r1", "title": "T", "types": ["film"]}
    out = render_edit_form(r, {"guid": "g"}, siblings=[], hosts=[])
    assert "edit-recap" not in out


def test_edit_form_recap_escapes_quote():
    """XSS : la quote est échappée."""
    r = {
        "id": "r1", "title": "T", "types": ["film"],
        "quote": "<script>x</script>",
    }
    out = render_edit_form(r, {"guid": "g"}, siblings=[], hosts=[])
    assert "<script>x</script>" not in out
    assert "&lt;script&gt;" in out


def test_apply_reenrich_no_targetable_types_returns_info(tmp_path, monkeypatch):
    p = tmp_path / "r.json"
    p.write_text(json.dumps({
        "id": "r", "episodeGuid": "ep-x", "title": "Livre", "types": ["livre"],
    }), encoding="utf-8")
    # Mock pour s'assurer que les enrichers ne sont pas appelés.
    import enrich_tmdb, enrich_music  # noqa: E401
    called = []
    monkeypatch.setattr(enrich_tmdb, "enrich_one",
                        lambda *a, **k: called.append("tmdb"))
    monkeypatch.setattr(enrich_music, "enrich_one",
                        lambda *a, **k: called.append("music"))
    monkeypatch.setattr(enrich_tmdb, "is_targetable", lambda r: False)
    monkeypatch.setattr(enrich_music, "is_targetable", lambda r: False)
    from review_edit import apply_reenrich
    guid, msg, kind = apply_reenrich(p, "r")
    assert guid == "ep-x"
    assert kind == "info"
    assert called == []


# ===== m8/m9 : gardes d'URL convergentes (revue 2026-07-19) =================
from review_edit import _ext_value_ok, _is_https_url  # noqa: E402


@pytest.mark.parametrize("url,expected", [
    ("https://x.com", True),
    ("HTTPS://x.com", True),          # schéma en capitales = https légitime
    ("HttpS://x.com", True),          # casse mixte
    ("http://x.com", False),          # http rejeté (https-only préservé)
    ("javascript:alert(1)", False),
    ("JAVASCRIPT:alert(1)", False),
    ("data:text/html,x", False),
    ("/chemin/relatif", False),
    ("", False),
])
def test_is_https_url(url, expected):
    """m8/m9 — garde https-only mais insensible à la casse du schéma."""
    assert _is_https_url(url) is expected


@pytest.mark.parametrize("val,expected", [
    ("42", True),                     # ID opaque (tmdb) — pas de schéma
    ("tt1375666", True),              # ID opaque (imdb)
    ("978-2-07-040850-4", True),      # ISBN
    ("https://site.com", True),       # URL https OK
    ("HTTPS://site.com", True),       # URL https casse-insensible OK
    ("http://site.com", False),       # URL http rejetée
    ("javascript:alert(1)", False),   # schéma dangereux rejeté
    ("data:text/html,x", False),
])
def test_ext_value_ok(val, expected):
    """m8/m9 — un externalId sans schéma (ID opaque) passe ; AVEC schéma, il
    doit être https:// (défense en profondeur contre un href/src hostile)."""
    assert _ext_value_ok(val) is expected


def test_apply_edit_custom_link_accepts_uppercase_https(reco_path):
    """m8/m9 — un customLink `HTTPS://…` (schéma en capitales) est désormais
    accepté (avant : `.startswith("https://")` strict le rejetait à tort)."""
    apply_edit(reco_path, {
        "title": ["X"], "types": ["film"],
        "cl_label_0": ["FNAC"], "cl_url_0": ["HTTPS://fnac.com/x"],
    })
    reco = json.loads(reco_path.read_text(encoding="utf-8"))
    assert reco["customLinks"] == [{"label": "FNAC", "url": "HTTPS://fnac.com/x"}]


def test_apply_edit_custom_link_logo_accepts_uppercase_https(reco_path):
    """m8/m9 — parité : le logo `HTTPS://…` est accepté."""
    apply_edit(reco_path, {
        "title": ["X"], "types": ["film"],
        "cl_label_0": ["FNAC"], "cl_url_0": ["https://fnac.com/x"],
        "cl_logo_0": ["HTTPS://fnac.com/logo.png"],
    })
    reco = json.loads(reco_path.read_text(encoding="utf-8"))
    assert reco["customLinks"][0]["logoUrl"] == "HTTPS://fnac.com/logo.png"


def test_apply_edit_watchProvider_accepts_uppercase_https(reco_path):
    """m8/m9 — parité watchProviders : `HTTPS://…` accepté."""
    apply_edit(reco_path, {
        "title": ["X"], "types": ["film"],
        "wp_label_0": ["Netflix"], "wp_url_0": ["HTTPS://netflix.com/x"],
    })
    reco = json.loads(reco_path.read_text(encoding="utf-8"))
    assert reco["watchProviders"] == [
        {"label": "Netflix", "url": "HTTPS://netflix.com/x"},
    ]


def test_apply_edit_link_override_accepts_uppercase_https(reco_path):
    """m8/m9 — parité linkOverrides : `HTTPS://…` accepté."""
    apply_edit(reco_path, {
        "title": ["X"], "types": ["film"],
        "lo_JustWatch": ["HTTPS://justwatch.com/exact"],
    })
    reco = json.loads(reco_path.read_text(encoding="utf-8"))
    assert reco["linkOverrides"] == {"JustWatch": "HTTPS://justwatch.com/exact"}


def test_apply_edit_external_id_rejects_dangerous_url(reco_path):
    """m8/m9 — un externalId à schéma dangereux (javascript:) n'est PAS persisté
    (défense en profondeur : website/deezer… finissent en href sur le site)."""
    reco = json.loads(reco_path.read_text(encoding="utf-8"))
    reco["externalIds"] = {"website": "https://safe.example"}
    reco_path.write_text(json.dumps(reco), encoding="utf-8")
    apply_edit(reco_path, {
        "title": ["X"], "types": ["film"],
        "ext_website": ["javascript:alert(document.domain)"],
    })
    reco = json.loads(reco_path.read_text(encoding="utf-8"))
    # La valeur hostile est rejetée → l'ancienne valeur sûre est conservée.
    assert reco["externalIds"]["website"] == "https://safe.example"


def test_apply_edit_external_id_accepts_https_url(reco_path):
    """m8/m9 — un externalId URL https:// passe."""
    apply_edit(reco_path, {
        "title": ["X"], "types": ["film"],
        "ext_website": ["https://officiel.example"],
    })
    reco = json.loads(reco_path.read_text(encoding="utf-8"))
    assert reco["externalIds"]["website"] == "https://officiel.example"


def test_apply_edit_external_id_accepts_opaque_id(reco_path):
    """m8/m9 — un ID opaque (tmdb=42, sans schéma) reste accepté (pas de
    régression sur les identifiants non-URL)."""
    apply_edit(reco_path, {
        "title": ["X"], "types": ["film"],
        "ext_tmdb": ["42"], "ext_imdb": ["tt1375666"],
    })
    reco = json.loads(reco_path.read_text(encoding="utf-8"))
    assert reco["externalIds"]["tmdb"] == "42"
    assert reco["externalIds"]["imdb"] == "tt1375666"


def test_render_recap_safe_url_blocks_dangerous_youtube_url():
    """m8/m9 (rendu) — parité avec `_yt_timecode_link_parts` : un youtubeUrl
    hostile passe par `_safe_url` → aucun lien embed cliquable rendu, mais le
    timecode statique reste affiché."""
    from review_edit_form import _render_recap
    r = {"id": "x", "timestamp": "00:05:00", "transcriptSource": "youtube"}
    ep = {"guid": "g", "youtubeUrl": "javascript:alert(1)"}
    out = _render_recap(r, ep)
    assert "javascript" not in out
    assert 'class="tc"' not in out          # pas de lien embed cliquable
    assert "00:05:00" in out                # timecode statique conservé


def test_render_recap_valid_youtube_url_makes_embed():
    """m8/m9 (rendu) — cas nominal : un youtubeUrl https valide produit bien un
    lien d'embed positionné au timecode."""
    from review_edit_form import _render_recap
    r = {"id": "x", "timestamp": "00:05:00", "transcriptSource": "youtube"}
    ep = {"guid": "g", "youtubeUrl": "https://www.youtube.com/watch?v=ABCDEFGHIJK"}
    out = _render_recap(r, ep)
    assert "youtube-nocookie.com/embed/" in out
    assert "start=300" in out
