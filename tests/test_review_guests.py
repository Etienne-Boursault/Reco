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


# ===== collect_guests : guestsParsed + guestsExcluded =======================
def test_collect_guests_includes_guests_parsed():
    """guestsParsed (snapshot du parsing) doit alimenter la liste."""
    ep = {"guests": [], "guestsParsed": ["Seb de bon matin", "de bonne humeur"]}
    out = collect_guests(ep, [], hosts=[])
    assert "Seb de bon matin" in out
    assert "de bonne humeur" in out


def test_collect_guests_excluded_wins_casefold():
    """guestsExcluded a l'autorité ultime (comparaison casefold)."""
    ep = {
        "guests": ["Seb de bon matin"],
        "guestsParsed": ["Seb de bon matin", "de bonne humeur"],
        "guestsExcluded": ["seb DE bon matin"],
    }
    recs = [{"recommendedBy": "Seb De Bon Matin"}]
    out = collect_guests(ep, recs, hosts=[])
    assert "Seb de bon matin" not in out
    assert "Seb De Bon Matin" not in out
    assert "de bonne humeur" in out  # non exclu → reste


def test_collect_guests_parsed_kwarg_fallback():
    """`parsed=` (fallback à la volée) pour les épisodes pas migrés."""
    ep = {"guests": []}  # pas de guestsParsed
    out = collect_guests(ep, [], hosts=[], parsed=["Charlie", "Diane"])
    assert out == ["Charlie", "Diane"]


# ===== apply_guest_action — exclude =========================================
def test_apply_guest_action_exclude_persists_and_cleans_recos(ep_tmp):
    """exclude : ajoute à guestsExcluded + nettoie recommendedBy + ep.guests."""
    cbs = _make_callbacks(
        ep_tmp["src_id"], ep_tmp["episodes_dir"],
        ep_tmp["recos_dir"], ep_tmp["hosts"],
    )
    ep_path = ep_tmp["episodes_dir"] / "ep-1.json"
    flash, kind = apply_guest_action(
        ep_tmp["src_id"], ep_path, "ep-1", "exclude", "Alice", "",
        load_groups=cbs[0], reco_path=cbs[1], invalidate_cache=cbs[2],
    )
    assert kind == "success"
    ep = json.loads(ep_path.read_text(encoding="utf-8"))
    assert "Alice" in ep["guestsExcluded"]
    assert "Alice" not in ep["guests"]
    r1 = json.loads((ep_tmp["recos_dir"] / "r1.json").read_text(encoding="utf-8"))
    r2 = json.loads((ep_tmp["recos_dir"] / "r2.json").read_text(encoding="utf-8"))
    assert "recommendedBy" not in r1  # r1 n'avait qu'Alice
    assert r2["recommendedBy"] == "Bob"  # Alice retirée du couple


def test_apply_guest_action_exclude_host_blocked(ep_tmp):
    """Refus d'exclure un hôte (sinon recommendedBy validés cassés)."""
    cbs = _make_callbacks(
        ep_tmp["src_id"], ep_tmp["episodes_dir"],
        ep_tmp["recos_dir"], ep_tmp["hosts"],
    )
    ep_path = ep_tmp["episodes_dir"] / "ep-1.json"
    flash, kind = apply_guest_action(
        ep_tmp["src_id"], ep_path, "ep-1", "exclude", "Kyan", "",
        load_groups=cbs[0], reco_path=cbs[1], invalidate_cache=cbs[2],
    )
    assert kind == "warning"
    ep = json.loads(ep_path.read_text(encoding="utf-8"))
    assert "Kyan" not in (ep.get("guestsExcluded") or [])


def test_apply_guest_action_delete_host_blocked(ep_tmp):
    """Même garde-fou côté `delete` (defense in depth)."""
    cbs = _make_callbacks(
        ep_tmp["src_id"], ep_tmp["episodes_dir"],
        ep_tmp["recos_dir"], ep_tmp["hosts"],
    )
    ep_path = ep_tmp["episodes_dir"] / "ep-1.json"
    flash, kind = apply_guest_action(
        ep_tmp["src_id"], ep_path, "ep-1", "delete", "Navo", "",
        load_groups=cbs[0], reco_path=cbs[1], invalidate_cache=cbs[2],
    )
    assert kind == "warning"


def test_apply_guest_action_add_rehabilitates_excluded(ep_tmp):
    """Si on ajoute un nom qui était exclu → réhabilité (retiré de l'excluded)."""
    cbs = _make_callbacks(
        ep_tmp["src_id"], ep_tmp["episodes_dir"],
        ep_tmp["recos_dir"], ep_tmp["hosts"],
    )
    ep_path = ep_tmp["episodes_dir"] / "ep-1.json"
    # Pré-condition : exclure Charlie
    ep = json.loads(ep_path.read_text(encoding="utf-8"))
    ep["guestsExcluded"] = ["Charlie"]
    ep_path.write_text(json.dumps(ep), encoding="utf-8")
    flash, kind = apply_guest_action(
        ep_tmp["src_id"], ep_path, "ep-1", "add", "", "Charlie",
        load_groups=cbs[0], reco_path=cbs[1], invalidate_cache=cbs[2],
    )
    assert kind == "success"
    ep = json.loads(ep_path.read_text(encoding="utf-8"))
    assert "Charlie" not in (ep.get("guestsExcluded") or [])
    assert "Charlie" in ep["guests"]


# ===== _parse_guests harmonisation casefold =================================
def test_parse_guests_uses_casefold_consistently():
    """Harmonisation : pas de divergence lower()/casefold() sur l'allemand ß etc."""
    from review_render_common import _parse_guests
    # Pas de host → résultat = parsing brut, juste s'assurer que ça tourne
    # sans crash + dédup case-insensitive.
    out = _parse_guests("avec Alice et alice", hosts=[])
    # dédup case-insensitive → une seule occurrence
    assert len(out) == 1


# ===== render_guests_panel : bouton exclude =================================
def test_render_guests_panel_uses_exclude_action():
    """Le ✕ doit appeler action=exclude (pas delete) pour persister le retrait."""
    out = render_guests_panel("g", {"guests": ["Alice"]}, [], hosts=[])
    assert 'value="exclude"' in out


def test_render_guests_panel_with_parsed_kwarg():
    """Le panel utilise le fallback `parsed=` (épisodes non migrés)."""
    out = render_guests_panel(
        "g", {"guests": []}, [], hosts=[], parsed=["Zaz"],
    )
    assert "Zaz" in out


# ===== apply_guest_action — rename depuis guestsParsed ======================
# Bug : renommer un invité issu de `guestsParsed` (snapshot du parsing du
# titre) et non de `ep.guests` (ajouts manuels) ne mettait pas à jour le
# panneau : `old` réapparaissait car collect_guests refait l'union
# guests+guestsParsed. Fix : masquer `old` via guestsExcluded + garantir `new`
# dans ep.guests.
def _write_ep(ep_path: Path, **fields) -> None:
    """Réécrit l'épisode ep-1 avec les champs fournis (guests, guestsParsed…)."""
    ep = json.loads(ep_path.read_text(encoding="utf-8"))
    ep.update(fields)
    ep_path.write_text(json.dumps(ep), encoding="utf-8")


def test_apply_guest_action_rename_from_guests_parsed_persists(ep_tmp):
    """old dans guestsParsed (pas dans ep.guests) : après rename le panneau
    (= collect_guests) montre `new` et non plus `old`."""
    cbs = _make_callbacks(
        ep_tmp["src_id"], ep_tmp["episodes_dir"],
        ep_tmp["recos_dir"], ep_tmp["hosts"],
    )
    ep_path = ep_tmp["episodes_dir"] / "ep-1.json"
    _write_ep(ep_path, guests=[], guestsParsed=["Seb de bon matin"])
    flash, kind = apply_guest_action(
        ep_tmp["src_id"], ep_path, "ep-1", "", "Seb de bon matin", "Sébastien",
        load_groups=cbs[0], reco_path=cbs[1], invalidate_cache=cbs[2],
    )
    assert kind == "success"
    ep = json.loads(ep_path.read_text(encoding="utf-8"))
    assert any(x.casefold() == "seb de bon matin" for x in ep["guestsExcluded"])
    assert "Sébastien" in ep["guests"]
    # Simule le reload du panneau (N4 : parsed= comme en prod) : old masqué,
    # new visible.
    out = collect_guests(ep, [], hosts=ep_tmp["hosts"],
                         parsed=ep.get("guestsParsed"))
    assert "Sébastien" in out
    assert "Seb de bon matin" not in out


def test_apply_guest_action_rename_from_guests_parsed_new_already_in_guests(ep_tmp):
    """new est déjà dans ep.guests (casse différente) → pas de doublon."""
    cbs = _make_callbacks(
        ep_tmp["src_id"], ep_tmp["episodes_dir"],
        ep_tmp["recos_dir"], ep_tmp["hosts"],
    )
    ep_path = ep_tmp["episodes_dir"] / "ep-1.json"
    _write_ep(ep_path, guests=["Bob"], guestsParsed=["Alice"])
    flash, kind = apply_guest_action(
        ep_tmp["src_id"], ep_path, "ep-1", "", "Alice", "bob",
        load_groups=cbs[0], reco_path=cbs[1], invalidate_cache=cbs[2],
    )
    assert kind == "success"
    ep = json.loads(ep_path.read_text(encoding="utf-8"))
    keys = [g.casefold() for g in ep["guests"]]
    assert keys.count("bob") == 1  # pas de doublon "Bob"/"bob"
    assert any(x.casefold() == "alice" for x in ep["guestsExcluded"])


def test_apply_guest_action_rename_from_guests_parsed_rehabilitates_new(ep_tmp):
    """new était exclu → réhabilité (retiré de guestsExcluded) ; old exclu."""
    cbs = _make_callbacks(
        ep_tmp["src_id"], ep_tmp["episodes_dir"],
        ep_tmp["recos_dir"], ep_tmp["hosts"],
    )
    ep_path = ep_tmp["episodes_dir"] / "ep-1.json"
    _write_ep(ep_path, guests=[], guestsParsed=["Alice"], guestsExcluded=["Bob"])
    flash, kind = apply_guest_action(
        ep_tmp["src_id"], ep_path, "ep-1", "", "Alice", "Bob",
        load_groups=cbs[0], reco_path=cbs[1], invalidate_cache=cbs[2],
    )
    assert kind == "success"
    ep = json.loads(ep_path.read_text(encoding="utf-8"))
    excluded = ep.get("guestsExcluded") or []
    assert not any(x.casefold() == "bob" for x in excluded)  # réhabilité
    assert any(x.casefold() == "alice" for x in excluded)    # ancien masqué
    assert "Bob" in ep["guests"]


def test_apply_guest_action_rename_from_guests_parsed_old_already_excluded(ep_tmp):
    """Défensif : old déjà dans guestsExcluded → pas de doublon d'exclusion."""
    cbs = _make_callbacks(
        ep_tmp["src_id"], ep_tmp["episodes_dir"],
        ep_tmp["recos_dir"], ep_tmp["hosts"],
    )
    ep_path = ep_tmp["episodes_dir"] / "ep-1.json"
    _write_ep(ep_path, guests=[], guestsParsed=["Alice"], guestsExcluded=["Alice"])
    flash, kind = apply_guest_action(
        ep_tmp["src_id"], ep_path, "ep-1", "", "Alice", "Alicia",
        load_groups=cbs[0], reco_path=cbs[1], invalidate_cache=cbs[2],
    )
    assert kind == "success"
    ep = json.loads(ep_path.read_text(encoding="utf-8"))
    excluded = ep.get("guestsExcluded") or []
    assert sum(1 for x in excluded if x.casefold() == "alice") == 1
    assert "Alicia" in ep["guests"]


def test_apply_guest_action_rename_guests_parsed_noop_keeps_guest(ep_tmp):
    """✓ sans édition (old == new) sur un invité guestsParsed : il reste
    visible et n'est PAS masqué."""
    cbs = _make_callbacks(
        ep_tmp["src_id"], ep_tmp["episodes_dir"],
        ep_tmp["recos_dir"], ep_tmp["hosts"],
    )
    ep_path = ep_tmp["episodes_dir"] / "ep-1.json"
    _write_ep(ep_path, guests=[], guestsParsed=["Seb de bon matin"])
    flash, kind = apply_guest_action(
        ep_tmp["src_id"], ep_path, "ep-1", "", "Seb de bon matin",
        "Seb de bon matin",
        load_groups=cbs[0], reco_path=cbs[1], invalidate_cache=cbs[2],
    )
    assert kind == "success"
    ep = json.loads(ep_path.read_text(encoding="utf-8"))
    assert not (ep.get("guestsExcluded") or [])
    out = collect_guests(ep, [], hosts=ep_tmp["hosts"],
                         parsed=ep.get("guestsParsed"))
    assert "Seb de bon matin" in out


def test_apply_guest_action_rename_from_guests_does_not_exclude_old(ep_tmp):
    """Non-régression : rename depuis ep.guests (old absent de guestsParsed)
    ne masque PAS old via guestsExcluded."""
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
    ep = json.loads(ep_path.read_text(encoding="utf-8"))
    assert "Alicia" in ep["guests"]
    assert "Alice" not in ep["guests"]
    assert not (ep.get("guestsExcluded") or [])


def test_apply_guest_action_exclude_from_guests_parsed_persists(ep_tmp):
    """exclude d'un invité SEULEMENT dans guestsParsed : masqué via
    guestsExcluded (mécanisme existant), plus réaffiché au reload."""
    cbs = _make_callbacks(
        ep_tmp["src_id"], ep_tmp["episodes_dir"],
        ep_tmp["recos_dir"], ep_tmp["hosts"],
    )
    ep_path = ep_tmp["episodes_dir"] / "ep-1.json"
    _write_ep(ep_path, guests=[], guestsParsed=["Seb de bon matin"])
    flash, kind = apply_guest_action(
        ep_tmp["src_id"], ep_path, "ep-1", "exclude", "Seb de bon matin", "",
        load_groups=cbs[0], reco_path=cbs[1], invalidate_cache=cbs[2],
    )
    assert kind == "success"
    ep = json.loads(ep_path.read_text(encoding="utf-8"))
    assert any(x.casefold() == "seb de bon matin" for x in ep["guestsExcluded"])
    # N4 : parsed= comme en prod (le panel passe le parsing du titre).
    out = collect_guests(ep, [], hosts=ep_tmp["hosts"],
                         parsed=ep.get("guestsParsed"))
    assert "Seb de bon matin" not in out


# ===== CR Story 1 — L1/L2/L3/L4/L5 + N3 ====================================
def test_apply_guest_action_rename_recos_only_updates_panel(ep_tmp):
    """L1 : nom présent UNIQUEMENT via recommendedBy des recos (ni ep.guests
    ni guestsParsed) : rename → panel (collect_guests) à jour, sans exclusion."""
    cbs = _make_callbacks(
        ep_tmp["src_id"], ep_tmp["episodes_dir"],
        ep_tmp["recos_dir"], ep_tmp["hosts"],
    )
    ep_path = ep_tmp["episodes_dir"] / "ep-1.json"
    _write_ep(ep_path, guests=[])  # Alice/Bob ne subsistent que dans les recos
    flash, kind = apply_guest_action(
        ep_tmp["src_id"], ep_path, "ep-1", "", "Alice", "Alicia",
        load_groups=cbs[0], reco_path=cbs[1], invalidate_cache=cbs[2],
    )
    assert kind == "success"
    ep = json.loads(ep_path.read_text(encoding="utf-8"))
    assert not (ep.get("guestsExcluded") or [])  # recos-only → pas d'exclusion
    _s, _e, groups = cbs[0]("demo")
    recs = groups["ep-1"]
    out = collect_guests(ep, recs, hosts=ep_tmp["hosts"],
                         parsed=ep.get("guestsParsed"))
    assert "Alicia" in out
    assert "Alice" not in out


def test_apply_guest_action_delete_from_guests_parsed_persists(ep_tmp):
    """L2 : delete (POST forgé/legacy) d'un nom SEULEMENT dans guestsParsed →
    routé vers l'exclusion (comme exclude), plus réaffiché au reload."""
    cbs = _make_callbacks(
        ep_tmp["src_id"], ep_tmp["episodes_dir"],
        ep_tmp["recos_dir"], ep_tmp["hosts"],
    )
    ep_path = ep_tmp["episodes_dir"] / "ep-1.json"
    _write_ep(ep_path, guests=[], guestsParsed=["Seb de bon matin"])
    flash, kind = apply_guest_action(
        ep_tmp["src_id"], ep_path, "ep-1", "delete", "Seb de bon matin", "",
        load_groups=cbs[0], reco_path=cbs[1], invalidate_cache=cbs[2],
    )
    assert kind == "success"
    ep = json.loads(ep_path.read_text(encoding="utf-8"))
    assert any(x.casefold() == "seb de bon matin" for x in ep["guestsExcluded"])
    out = collect_guests(ep, [], hosts=ep_tmp["hosts"],
                         parsed=ep.get("guestsParsed"))
    assert "Seb de bon matin" not in out


def test_apply_guest_action_rename_rejects_empty_new(ep_tmp):
    """L3 : renommer vers un nom vide est refusé (symétrie avec 'add')."""
    cbs = _make_callbacks(
        ep_tmp["src_id"], ep_tmp["episodes_dir"],
        ep_tmp["recos_dir"], ep_tmp["hosts"],
    )
    ep_path = ep_tmp["episodes_dir"] / "ep-1.json"
    flash, kind = apply_guest_action(
        ep_tmp["src_id"], ep_path, "ep-1", "", "Alice", "",
        load_groups=cbs[0], reco_path=cbs[1], invalidate_cache=cbs[2],
    )
    assert kind == "warning"
    ep = json.loads(ep_path.read_text(encoding="utf-8"))
    assert "Alice" in ep["guests"]  # rename annulé, rien muté


def test_apply_guest_action_rename_rejects_placeholder_new(ep_tmp):
    """L3 : renommer vers un placeholder est refusé."""
    cbs = _make_callbacks(
        ep_tmp["src_id"], ep_tmp["episodes_dir"],
        ep_tmp["recos_dir"], ep_tmp["hosts"],
    )
    ep_path = ep_tmp["episodes_dir"] / "ep-1.json"
    flash, kind = apply_guest_action(
        ep_tmp["src_id"], ep_path, "ep-1", "", "Alice", "non spécifié",
        load_groups=cbs[0], reco_path=cbs[1], invalidate_cache=cbs[2],
    )
    assert kind == "warning"
    ep = json.loads(ep_path.read_text(encoding="utf-8"))
    assert "Alice" in ep["guests"]


def test_apply_guest_action_rename_rejects_host_new(ep_tmp):
    """L3 : renommer un invité vers un hôte est refusé (sinon des
    recommendedBy validés seraient cassés)."""
    cbs = _make_callbacks(
        ep_tmp["src_id"], ep_tmp["episodes_dir"],
        ep_tmp["recos_dir"], ep_tmp["hosts"],
    )
    ep_path = ep_tmp["episodes_dir"] / "ep-1.json"
    flash, kind = apply_guest_action(
        ep_tmp["src_id"], ep_path, "ep-1", "", "Alice", "Kyan",
        load_groups=cbs[0], reco_path=cbs[1], invalidate_cache=cbs[2],
    )
    assert kind == "warning"
    assert "hôte" in flash
    ep = json.loads(ep_path.read_text(encoding="utf-8"))
    assert "Alice" in ep["guests"]  # rename annulé


def test_apply_guest_action_add_rehabilitates_name_already_in_guests(ep_tmp):
    """L4 : add d'un nom déjà dans ep.guests ET dans guestsExcluded →
    'réhabilité' (retiré de guestsExcluded), pas 'déjà dans les invités'."""
    cbs = _make_callbacks(
        ep_tmp["src_id"], ep_tmp["episodes_dir"],
        ep_tmp["recos_dir"], ep_tmp["hosts"],
    )
    ep_path = ep_tmp["episodes_dir"] / "ep-1.json"
    _write_ep(ep_path, guests=["Charlie"], guestsExcluded=["Charlie"])
    flash, kind = apply_guest_action(
        ep_tmp["src_id"], ep_path, "ep-1", "add", "", "Charlie",
        load_groups=cbs[0], reco_path=cbs[1], invalidate_cache=cbs[2],
    )
    assert kind == "success"
    assert "réhabilité" in flash
    ep = json.loads(ep_path.read_text(encoding="utf-8"))
    assert not any(x.casefold() == "charlie"
                   for x in (ep.get("guestsExcluded") or []))
    assert any(g.casefold() == "charlie" for g in ep["guests"])


def test_apply_guest_action_rename_pure_case_from_guests_parsed(ep_tmp):
    """L5 : rename pur-casse ('Seb'→'SEB') d'un nom guestsParsed → la nouvelle
    casse s'affiche SANS exclure old (l'exclure casefold masquerait new)."""
    cbs = _make_callbacks(
        ep_tmp["src_id"], ep_tmp["episodes_dir"],
        ep_tmp["recos_dir"], ep_tmp["hosts"],
    )
    ep_path = ep_tmp["episodes_dir"] / "ep-1.json"
    _write_ep(ep_path, guests=[], guestsParsed=["Seb"])
    flash, kind = apply_guest_action(
        ep_tmp["src_id"], ep_path, "ep-1", "", "Seb", "SEB",
        load_groups=cbs[0], reco_path=cbs[1], invalidate_cache=cbs[2],
    )
    assert kind == "success"
    ep = json.loads(ep_path.read_text(encoding="utf-8"))
    assert not (ep.get("guestsExcluded") or [])  # même casefold → pas d'exclusion
    assert "SEB" in ep["guests"]
    out = collect_guests(ep, [], hosts=ep_tmp["hosts"],
                         parsed=ep.get("guestsParsed"))
    assert "SEB" in out
    assert "Seb" not in out  # ancienne casse remplacée à l'affichage


def test_apply_guest_action_exclude_flash_mentions_persistence(ep_tmp):
    """N3 : le flash d'exclude signale la persistance (« ne sera plus proposé »)."""
    cbs = _make_callbacks(
        ep_tmp["src_id"], ep_tmp["episodes_dir"],
        ep_tmp["recos_dir"], ep_tmp["hosts"],
    )
    ep_path = ep_tmp["episodes_dir"] / "ep-1.json"
    flash, kind = apply_guest_action(
        ep_tmp["src_id"], ep_path, "ep-1", "exclude", "Alice", "",
        load_groups=cbs[0], reco_path=cbs[1], invalidate_cache=cbs[2],
    )
    assert kind == "success"
    assert "plus proposé" in flash
