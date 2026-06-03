"""Tests pour tools/review_guests.py — cible 100%."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import review_guests as rg
from review_guests import (
    apply_guest_action, collect_guests, handle_rename_guest,
    is_placeholder, render_guests_panel, split_names,
)


# ===== Fixtures =============================================================
@pytest.fixture
def ep_tmp(tmp_path):
    """Crée un mini-setup (épisode + 2 recos) sur disque + des callbacks
    minimalistes (load_groups / reco_path / invalidate_cache)."""
    src_id = "demo"
    episodes_dir = tmp_path / "episodes" / src_id
    recos_dir = tmp_path / "recos" / src_id
    sources_dir = tmp_path / "sources"
    for d in (episodes_dir, recos_dir, sources_dir):
        d.mkdir(parents=True, exist_ok=True)

    import common
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(common, "EPISODES_DIR", tmp_path / "episodes")
    monkeypatch.setattr(common, "RECOS_DIR", tmp_path / "recos")
    monkeypatch.setattr(common, "SOURCES_DIR", sources_dir)
    yield_data = {
        "src_id": src_id,
        "episodes_dir": episodes_dir,
        "recos_dir": recos_dir,
        "tmp_path": tmp_path,
        "hosts": ["Kyan", "Navo"],
    }
    # Source minimale (load_groups en a besoin pour récupérer hosts).
    (sources_dir / f"{src_id}.json").write_text(
        json.dumps({"title": "Demo", "hosts": yield_data["hosts"]}),
        encoding="utf-8",
    )
    # Épisode
    ep = {"guid": "ep-1", "title": "Ep", "guests": ["Alice", "Bob"]}
    (episodes_dir / "ep-1.json").write_text(json.dumps(ep), encoding="utf-8")
    # Deux recos
    r1 = {"id": "r1", "episodeGuid": "ep-1", "title": "T1",
          "recommendedBy": "Alice", "types": ["film"], "status": "draft"}
    r2 = {"id": "r2", "episodeGuid": "ep-1", "title": "T2",
          "recommendedBy": "Bob & Alice", "types": ["film"], "status": "draft"}
    (recos_dir / "r1.json").write_text(json.dumps(r1), encoding="utf-8")
    (recos_dir / "r2.json").write_text(json.dumps(r2), encoding="utf-8")
    yield yield_data
    monkeypatch.undo()


def _make_callbacks(src_id: str, episodes_dir: Path, recos_dir: Path,
                    hosts: list[str]):
    """Construit les 3 callbacks attendus par apply_guest_action."""
    from common import read_json

    def load_groups(s):
        source = {"hosts": hosts, "title": "Demo"}
        episodes = {}
        for p in episodes_dir.glob("*.json"):
            ep = read_json(p)
            episodes[ep["guid"]] = ep
        groups = {}
        for p in recos_dir.glob("*.json"):
            r = read_json(p)
            groups.setdefault(r.get("episodeGuid", ""), []).append(r)
        return source, episodes, groups

    def reco_path(s, rid):
        p = recos_dir / f"{rid}.json"
        return p if p.exists() else None

    def invalidate_cache(s):
        pass

    return load_groups, reco_path, invalidate_cache


# ===== is_placeholder + split_names =========================================
@pytest.mark.parametrize("name", [
    "intervenant non spécifié", "invité non spécifié",
    "intervenants non spécifiés", "invités non spécifiés", "non spécifié",
])
def test_is_placeholder_recognizes_known_placeholders(name):
    assert is_placeholder(name)


def test_is_placeholder_case_insensitive():
    assert is_placeholder("Intervenant Non Spécifié")
    assert is_placeholder("  NON SPÉCIFIÉ  ")


def test_is_placeholder_rejects_real_name():
    assert not is_placeholder("Alice")


def test_split_names_basic():
    assert split_names("Alice & Bob") == ["Alice", "Bob"]
    assert split_names("Alice, Bob") == ["Alice", "Bob"]
    assert split_names("Alice et Bob") == ["Alice", "Bob"]


def test_split_names_strips_whitespace():
    assert split_names("  Alice  &  Bob  ") == ["Alice", "Bob"]


def test_split_names_empty_string_returns_empty_list():
    assert split_names("") == []
    assert split_names(None) == []


def test_split_names_mixed_separators():
    assert split_names("A, B & C et D") == ["A", "B", "C", "D"]


# ===== collect_guests =======================================================
def test_collect_guests_filters_hosts():
    ep = {"guests": ["Alice", "Kyan"]}
    recs = [{"recommendedBy": "Navo & Alice"}]
    out = collect_guests(ep, recs, hosts=["Kyan", "Navo"])
    assert "Kyan" not in out
    assert "Navo" not in out
    assert "Alice" in out


def test_collect_guests_filters_placeholders():
    ep = {"guests": ["Alice", "intervenant non spécifié"]}
    out = collect_guests(ep, [], hosts=[])
    assert out == ["Alice"]


def test_collect_guests_union_of_ep_guests_and_recs():
    ep = {"guests": ["Alice"]}
    recs = [{"recommendedBy": "Bob"}, {"recommendedBy": "Charlie & Bob"}]
    out = collect_guests(ep, recs, hosts=[])
    assert sorted(out) == ["Alice", "Bob", "Charlie"]


def test_collect_guests_preserves_first_occurrence_order():
    """L'ordre des premières occurrences est préservé (UX prévisible)."""
    ep = {"guests": ["Zaz", "Alice"]}
    recs = [{"recommendedBy": "Bob"}]
    out = collect_guests(ep, recs, hosts=[])
    assert out == ["Zaz", "Alice", "Bob"]


def test_collect_guests_case_insensitive_dedup():
    ep = {"guests": ["Alice"]}
    recs = [{"recommendedBy": "alice"}]
    out = collect_guests(ep, recs, hosts=[])
    assert out == ["Alice"]


# ===== apply_guest_action — add =============================================
def test_apply_guest_action_add_inserts_into_ep_guests(ep_tmp):
    cbs = _make_callbacks(
        ep_tmp["src_id"], ep_tmp["episodes_dir"],
        ep_tmp["recos_dir"], ep_tmp["hosts"],
    )
    ep_path = ep_tmp["episodes_dir"] / "ep-1.json"
    flash, kind = apply_guest_action(
        ep_tmp["src_id"], ep_path, "ep-1", "add", "", "Charlie",
        load_groups=cbs[0], reco_path=cbs[1], invalidate_cache=cbs[2],
    )
    assert kind == "success"
    assert "Charlie" in flash
    ep = json.loads(ep_path.read_text(encoding="utf-8"))
    assert "Charlie" in ep["guests"]


def test_apply_guest_action_add_rejects_placeholder(ep_tmp):
    cbs = _make_callbacks(
        ep_tmp["src_id"], ep_tmp["episodes_dir"],
        ep_tmp["recos_dir"], ep_tmp["hosts"],
    )
    ep_path = ep_tmp["episodes_dir"] / "ep-1.json"
    flash, kind = apply_guest_action(
        ep_tmp["src_id"], ep_path, "ep-1", "add", "", "non spécifié",
        load_groups=cbs[0], reco_path=cbs[1], invalidate_cache=cbs[2],
    )
    assert kind == "warning"


def test_apply_guest_action_add_rejects_empty(ep_tmp):
    cbs = _make_callbacks(
        ep_tmp["src_id"], ep_tmp["episodes_dir"],
        ep_tmp["recos_dir"], ep_tmp["hosts"],
    )
    ep_path = ep_tmp["episodes_dir"] / "ep-1.json"
    flash, kind = apply_guest_action(
        ep_tmp["src_id"], ep_path, "ep-1", "add", "", "",
        load_groups=cbs[0], reco_path=cbs[1], invalidate_cache=cbs[2],
    )
    assert kind == "warning"


def test_apply_guest_action_add_rejects_host(ep_tmp):
    """H1 : ajouter un hôte du podcast comme invité doit être refusé."""
    cbs = _make_callbacks(
        ep_tmp["src_id"], ep_tmp["episodes_dir"],
        ep_tmp["recos_dir"], ep_tmp["hosts"],
    )
    ep_path = ep_tmp["episodes_dir"] / "ep-1.json"
    flash, kind = apply_guest_action(
        ep_tmp["src_id"], ep_path, "ep-1", "add", "", "Kyan",
        load_groups=cbs[0], reco_path=cbs[1], invalidate_cache=cbs[2],
    )
    assert kind == "warning"
    assert "hôte" in flash


def test_apply_guest_action_add_rejects_duplicate_case_insensitive(ep_tmp):
    cbs = _make_callbacks(
        ep_tmp["src_id"], ep_tmp["episodes_dir"],
        ep_tmp["recos_dir"], ep_tmp["hosts"],
    )
    ep_path = ep_tmp["episodes_dir"] / "ep-1.json"
    flash, kind = apply_guest_action(
        ep_tmp["src_id"], ep_path, "ep-1", "add", "", "alice",
        load_groups=cbs[0], reco_path=cbs[1], invalidate_cache=cbs[2],
    )
    assert kind == "info"
    assert "déjà" in flash


# ===== apply_guest_action — rename / delete =================================
def test_apply_guest_action_rename_propagates_to_all_recos(ep_tmp):
    cbs = _make_callbacks(
        ep_tmp["src_id"], ep_tmp["episodes_dir"],
        ep_tmp["recos_dir"], ep_tmp["hosts"],
    )
    ep_path = ep_tmp["episodes_dir"] / "ep-1.json"
    flash, kind = apply_guest_action(
        ep_tmp["src_id"], ep_path, "ep-1", "", "Alice", "Alicia",
        load_groups=cbs[0], reco_path=cbs[1], invalidate_cache=cbs[2],
    )
    assert kind == "success"
    r1 = json.loads((ep_tmp["recos_dir"] / "r1.json").read_text(encoding="utf-8"))
    r2 = json.loads((ep_tmp["recos_dir"] / "r2.json").read_text(encoding="utf-8"))
    assert r1["recommendedBy"] == "Alicia"
    assert "Alicia" in r2["recommendedBy"]
    ep = json.loads(ep_path.read_text(encoding="utf-8"))
    assert "Alicia" in ep["guests"]
    assert "Alice" not in ep["guests"]


def test_apply_guest_action_delete_removes_from_ep_guests_and_recos(ep_tmp):
    cbs = _make_callbacks(
        ep_tmp["src_id"], ep_tmp["episodes_dir"],
        ep_tmp["recos_dir"], ep_tmp["hosts"],
    )
    ep_path = ep_tmp["episodes_dir"] / "ep-1.json"
    flash, kind = apply_guest_action(
        ep_tmp["src_id"], ep_path, "ep-1", "delete", "Alice", "",
        load_groups=cbs[0], reco_path=cbs[1], invalidate_cache=cbs[2],
    )
    assert kind == "success"
    r1 = json.loads((ep_tmp["recos_dir"] / "r1.json").read_text(encoding="utf-8"))
    r2 = json.loads((ep_tmp["recos_dir"] / "r2.json").read_text(encoding="utf-8"))
    assert "recommendedBy" not in r1
    assert r2["recommendedBy"] == "Bob"
    ep = json.loads(ep_path.read_text(encoding="utf-8"))
    assert "Alice" not in ep["guests"]


def test_apply_guest_action_rename_no_old_returns_error(ep_tmp):
    cbs = _make_callbacks(
        ep_tmp["src_id"], ep_tmp["episodes_dir"],
        ep_tmp["recos_dir"], ep_tmp["hosts"],
    )
    ep_path = ep_tmp["episodes_dir"] / "ep-1.json"
    flash, kind = apply_guest_action(
        ep_tmp["src_id"], ep_path, "ep-1", "", "", "Bob",
        load_groups=cbs[0], reco_path=cbs[1], invalidate_cache=cbs[2],
    )
    assert kind == "error"


def test_apply_guest_action_rename_no_match_in_recos_still_succeeds(ep_tmp):
    """Rename d'un invité présent dans ep.guests mais absent des recos."""
    cbs = _make_callbacks(
        ep_tmp["src_id"], ep_tmp["episodes_dir"],
        ep_tmp["recos_dir"], ep_tmp["hosts"],
    )
    ep_path = ep_tmp["episodes_dir"] / "ep-1.json"
    # Ajoute un invité absent des recos
    ep = json.loads(ep_path.read_text(encoding="utf-8"))
    ep["guests"].append("Zaz")
    ep_path.write_text(json.dumps(ep), encoding="utf-8")
    flash, kind = apply_guest_action(
        ep_tmp["src_id"], ep_path, "ep-1", "", "Zaz", "Zazie",
        load_groups=cbs[0], reco_path=cbs[1], invalidate_cache=cbs[2],
    )
    assert kind == "success"
    assert "épisode" in flash  # message « invité renommé de l'épisode »


def test_apply_guest_action_rename_to_existing_dedup(ep_tmp):
    """Renommer A → B, B existait déjà → pas de doublon dans recommendedBy."""
    cbs = _make_callbacks(
        ep_tmp["src_id"], ep_tmp["episodes_dir"],
        ep_tmp["recos_dir"], ep_tmp["hosts"],
    )
    ep_path = ep_tmp["episodes_dir"] / "ep-1.json"
    flash, kind = apply_guest_action(
        ep_tmp["src_id"], ep_path, "ep-1", "", "Alice", "Bob",
        load_groups=cbs[0], reco_path=cbs[1], invalidate_cache=cbs[2],
    )
    assert kind == "success"
    r2 = json.loads((ep_tmp["recos_dir"] / "r2.json").read_text(encoding="utf-8"))
    # r2 avait "Bob & Alice", après rename Alice→Bob → "Bob" seul
    assert r2["recommendedBy"] == "Bob"


# ===== render_guests_panel ==================================================
def test_render_guests_panel_renders_add_form_even_if_empty():
    out = render_guests_panel("g", {"guests": []}, [], hosts=[])
    assert "ajouter un invité" in out
    assert 'action="/rename-guest"' in out


def test_render_guests_panel_lists_distinct_guests():
    ep = {"guests": ["Alice", "Bob"]}
    recs = [{"recommendedBy": "Charlie & Alice"}]
    out = render_guests_panel("g1", ep, recs, hosts=[])
    assert "Alice" in out
    assert "Bob" in out
    assert "Charlie" in out
    assert "(3)" in out  # 3 invités distincts


def test_render_guests_panel_escapes_guid():
    out = render_guests_panel("<x>", {"guests": ["A"]}, [], hosts=[])
    assert "&lt;x&gt;" in out
    assert "<x>" not in out


# ===== handle_rename_guest ==================================================
def test_handle_rename_guest_missing_guid_returns_root(ep_tmp):
    cbs = _make_callbacks(
        ep_tmp["src_id"], ep_tmp["episodes_dir"],
        ep_tmp["recos_dir"], ep_tmp["hosts"],
    )
    loc = handle_rename_guest(
        ep_tmp["src_id"], {"new": ["Bob"]},
        load_groups=cbs[0], reco_path=cbs[1], invalidate_cache=cbs[2],
    )
    assert loc == "/"


def test_handle_rename_guest_invalid_guid_returns_root(ep_tmp):
    """M6 : un guid invalide (caractères interdits) → redirige /."""
    cbs = _make_callbacks(
        ep_tmp["src_id"], ep_tmp["episodes_dir"],
        ep_tmp["recos_dir"], ep_tmp["hosts"],
    )
    loc = handle_rename_guest(
        ep_tmp["src_id"], {"guid": ["../etc"], "action": ["add"], "new": ["X"]},
        load_groups=cbs[0], reco_path=cbs[1], invalidate_cache=cbs[2],
    )
    assert loc == "/"


def test_handle_rename_guest_unknown_guid_returns_root(ep_tmp):
    cbs = _make_callbacks(
        ep_tmp["src_id"], ep_tmp["episodes_dir"],
        ep_tmp["recos_dir"], ep_tmp["hosts"],
    )
    loc = handle_rename_guest(
        ep_tmp["src_id"], {"guid": ["ep-999"], "action": ["add"], "new": ["X"]},
        load_groups=cbs[0], reco_path=cbs[1], invalidate_cache=cbs[2],
    )
    assert loc == "/"


def test_handle_rename_guest_add_returns_ep_url_with_flash(ep_tmp):
    cbs = _make_callbacks(
        ep_tmp["src_id"], ep_tmp["episodes_dir"],
        ep_tmp["recos_dir"], ep_tmp["hosts"],
    )
    loc = handle_rename_guest(
        ep_tmp["src_id"],
        {"guid": ["ep-1"], "action": ["add"], "new": ["Charlie"]},
        load_groups=cbs[0], reco_path=cbs[1], invalidate_cache=cbs[2],
    )
    assert loc.startswith("/ep?guid=ep-1")
    assert "flash=" in loc
    assert "kind=success" in loc
