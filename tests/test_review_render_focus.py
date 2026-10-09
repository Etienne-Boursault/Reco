"""Tests de la relecture « focus » : `tools/review_render_focus.py` et les
pages qui l'assemblent (épisode, accueil)."""
from __future__ import annotations

import json

import pytest

import review_render as rr
import review_render_focus as rf
from _html_helpers import parse

# Fixtures partagées avec les tests du serveur (arborescence de contenu factice).
from test_review_server import _clear_review_server_caches, fake_source  # noqa: F401


def reco(i: str, **kw) -> dict:
    r = {"id": i, "title": f"T{i}", "status": "draft", "timestamp": "00:01:05",
         "quote": "q", "recommendedBy": "Alice"}
    r.update(kw)
    return r


# ===== États et entrées de liste ============================================
@pytest.mark.parametrize("r,state", [
    ({}, "draft"),
    ({"status": "discarded", "kind": "citation"}, "discarded"),
    ({"status": "validated"}, "done"),
    ({"status": "validated", "kind": "citation"}, "citation"),
    ({"status": "validated", "guestWork": True}, "guestwork"),
    ({"status": "draft", "kind": "citation"}, "draft"),
])
def test_entry_state(r, state):
    assert rf.entry_state(r) == state


def test_reco_entry_and_cluster_entry():
    e = rf.reco_entry(reco("a", recommendedBy="Alice & Bob", quote=""),
                      {"guid": "g"}, ["Alice", "Bob"], None)
    assert e == {"id": "a", "title": "Ta", "time": "00:01:05",
                 "who": "Alice, Bob", "state": "draft", "signals": 1}
    assert rf.reco_entry({"id": "b"}, {}, [], None)["time"] == ""
    c = rf.cluster_entry("a", [reco("a"), reco("b")])
    assert c["state"] == "cluster" and c["who"] == "2 doublons probables"
    assert rf.cluster_entry("z", [])["title"] == "?"


def test_render_list_marks_signals_only_while_pending():
    entries = [
        {"id": "a", "title": "<A>", "time": "00:01:00", "who": "Alice",
         "state": "draft", "signals": 2},
        {"id": "b", "title": "B", "time": "", "who": "", "state": "done",
         "signals": 1},
    ]
    out = rf.render_list(entries)
    soup = parse(out)
    items = soup.select("[data-fx-target]")
    assert [i["data-state"] for i in items] == ["draft", "done"]
    assert items[0].select_one(".fx-sig") is not None
    assert items[1].select_one(".fx-sig") is None
    assert "&lt;A&gt;" in out
    assert "00:01:00 · Alice" in out
    assert "sur 2" in soup.select_one("[data-fx-list-toggle]").get_text()


def test_render_progress():
    entries = [{"state": "draft"}, {"state": "done"}, {"state": "cluster"},
               {"state": "discarded"}]
    out = rf.render_progress(entries)
    assert "data-fx-done>2<" in out and "width:50%" in out
    assert "width:100%" in rf.render_progress([])


def test_render_end_hidden_until_everything_is_decided():
    pending = [{"state": "draft"}, {"state": "done"}]
    assert "data-fx-end hidden" in rf.render_end(pending, {"guid": "g"}, None)
    assert "data-fx-end hidden" in rf.render_end([], {"guid": "g"}, None)
    done = [{"state": "done"}, {"state": "done"}, {"state": "citation"}]
    out = rf.render_end(done, {"guid": "yt-1"},
                        {"guid": "yt-2", "season": 6, "number": 5, "title": "Suite"})
    assert "data-fx-end hidden" not in out
    assert 'data-fx-count="done">2<' in out and "validées" in out
    assert "seulement évoquée<" in out          # 1 → singulier
    assert "0</b> <span" in out and "écartée<" in out  # 0 → singulier
    assert "la chaîne pose les liens" in out
    assert 'href="/ep?guid=yt-2"' in out and "S6·E5 Suite" in out


def test_render_end_for_a_hand_made_episode_without_next():
    out = rf.render_end([{"state": "done"}], {"guid": "acast-1"}, None)
    assert "traité à la main" in out
    assert 'href="/"' in out and "Plus rien à relire" in out


def test_next_to_review_wraps_and_skips_current():
    groups = {"a": [reco("1")], "b": [reco("2", status="validated")],
              "c": [reco("3")]}
    assert rf.next_to_review(["a", "b", "c"], "a", groups) == "c"
    assert rf.next_to_review(["a", "b", "c"], "c", groups) == "a"
    assert rf.next_to_review(["a", "b"], "a", {"a": [reco("1")]}) is None
    assert rf.next_to_review(["a", "c"], "zz", groups) == "a"
    assert rf.next_to_review([], None, groups) is None


# ===== Accueil ==============================================================
def test_render_todo_and_all_episodes():
    episodes = {
        "g1": {"guid": "g1", "title": "Un", "season": 6, "number": 1,
               "youtubeUrl": "https://www.youtube.com/watch?v=ABCDEFGHIJK"},
        "g2": {"guid": "g2", "title": "Deux", "number": 2},
        "g3": {"guid": "g3", "title": "Trois"},
    }
    groups = {
        "g1": [reco("1", recommendedBy="Inconnu"), reco("2", status="validated")],
        "g2": [reco("3", status="validated")],
    }
    todo = rf.render_todo(["g1", "g2", "g3"], episodes, groups, ["Alice"])
    assert "1 à relire sur 2" in todo and "1 à vérifier" in todo
    assert "Reprendre →" in todo and "mqdefault.jpg" in todo
    assert "Deux" not in todo
    all_eps = rf.render_all_episodes(["g1", "g2", "g3"], episodes, groups)
    soup = parse(all_eps)
    classes = [li["class"][-1] for li in soup.select("[data-ep-row]")]
    assert classes == ["empty", "done", "todo"]  # du plus récent au plus ancien
    assert "#2" in all_eps and "1 recos relues" in all_eps and "?" in all_eps
    assert soup.select_one("[data-ep-filter]") is not None


def test_render_todo_empty_and_card_without_thumbnail():
    assert "Rien à relire" in rf.render_todo(["g"], {"g": {"guid": "g"}}, {}, [])
    out = rf.render_todo(["g"], {"g": {"guid": "g", "title": "T"}},
                         {"g": [reco("1")]}, [])
    assert "Commencer →" in out and "mqdefault" not in out


def test_render_chain():
    assert rf.render_chain(None, {}, {}) == ""
    episodes = {"yt-a": {}, "yt-b": {}, "yt-c": {}, "acast": {}}
    groups = {"yt-a": [reco("1", status="validated")],
              "yt-b": [reco("2")], "acast": [reco("3", status="validated")]}
    state = {"finalized": ["yt-c"], "published": [],
             "lastErrors": {"k": "⚠️ panne <TMDB>"}}
    out = rf.render_chain(state, episodes, groups)
    assert "1 épisode(s) relu(s), en attente de finalisation" in out
    assert "1 épisode(s) finalisé(s), en attente de publication" in out
    assert "&lt;TMDB&gt;" in out
    calm = rf.render_chain({"finalized": ["yt-a"], "published": ["yt-a"]},
                           {"yt-a": {}}, {"yt-a": [reco("1", status="validated")]})
    assert "Rien en cours" in calm


# ===== Pages assemblées =====================================================
def test_episode_page_is_a_focus_page(fake_source):  # noqa: F811
    out = rr._render_episode(fake_source, "ep-001")
    soup = parse(out)
    assert soup.select_one("[data-focus]") is not None
    targets = [b["data-fx-target"] for b in soup.select("[data-fx-target]")]
    cards = [li["data-reco-id"] for li in soup.select(".ep > ul > li.row")]
    assert targets == cards == ["ubm-001", "ubm-002", "ubm-003"]
    assert "1 sur 3" not in out  # 2 traitées (validée + écartée) sur 3
    assert "data-fx-done>2<" in out
    assert soup.select_one(".add-reco-form") is not None
    end = soup.select_one("[data-fx-end]")
    assert end.has_attr("hidden")


def test_episode_page_lists_clusters_as_one_entry(fake_source, monkeypatch):  # noqa: F811
    from types import SimpleNamespace

    import reco_dedup
    members = [{"id": "ubm-001", "title": "Mortel"}, {"id": "ubm-002", "title": "Mortel"}]
    fake = SimpleNamespace(members=members, canonical_id="ubm-001",
                           similarity=0.9, avg_timecode_delta=3)
    monkeypatch.setattr(reco_dedup, "cluster_recos", lambda recs: [fake])
    soup = parse(rr._render_episode(fake_source, "ep-001"))
    states = [b["data-state"] for b in soup.select("[data-fx-target]")]
    assert states == ["cluster", "discarded"]
    assert soup.select_one('li.row.cluster[data-cluster-id="ubm-001"]') is not None


def test_episode_page_in_edit_mode_lists_every_reco(fake_source):  # noqa: F811
    soup = parse(rr._render_episode(fake_source, "ep-001", "ubm-001"))
    assert len(soup.select("[data-fx-target]")) == 3
    assert soup.select_one('li.row.editing[data-reco-id="ubm-001"]') is not None


def test_home_shows_chain_state_when_the_pipeline_ran(fake_source, tmp_path,  # noqa: F811
                                                      monkeypatch):
    import common
    monkeypatch.setattr(common, "OUTPUT_DIR", tmp_path / "out")
    assert "La chaîne" not in rr._render_index(fake_source)
    state = tmp_path / "out" / "pipeline" / f"{fake_source}.json"
    state.parent.mkdir(parents=True)
    state.write_text(json.dumps({"finalized": [], "published": []}), encoding="utf-8")
    assert "La chaîne" in rr._render_index(fake_source)
    state.write_text("{pas du json", encoding="utf-8")
    assert "La chaîne" not in rr._render_index(fake_source)


def test_card_shows_signals_and_decision_bar(fake_source):  # noqa: F811
    r = reco("x", recommendedBy="Charlie", quote="")
    ep = {"guid": "ep-001", "title": "Un épisode avec Charlie Tartempion"}
    soup = parse(rr._reco_card(r, ep, ["Alice", "Bob"], fake_source))
    li = soup.select_one("li.row")
    assert li["data-signals"] == "2"  # prénom de l'invité + pas de citation
    fix = soup.select_one(".verif-fix")
    assert fix["data-fix-to"] == "Charlie Tartempion"
    decide = [b["value"] for b in soup.select(".decide button")]
    assert decide == ["validate", "citation", "discard", "guest-work"]
    assert soup.select_one(".more [data-merge-select]") is not None


@pytest.mark.parametrize("r,label", [
    ({"status": "draft"}, "à relire"),
    ({"status": "discarded"}, "écartée"),
    ({"status": "validated"}, "validée"),
    ({"status": "validated", "kind": "citation"}, "évoquée"),
    ({"status": "validated", "guestWork": True}, "leur œuvre"),
])
def test_status_label(r, label):
    assert rr._status_label(r) == label
