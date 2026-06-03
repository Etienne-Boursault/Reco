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


# ----- linkOverrides --------------------------------------------------------
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


def test_render_overrides_section_for_film_includes_justwatch():
    out = _render_overrides_section({"types": ["film"], "title": "X"})
    assert "JustWatch" in out
    assert 'name="lo_JustWatch"' in out


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
