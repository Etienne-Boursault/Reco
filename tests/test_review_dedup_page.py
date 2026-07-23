"""Tests pour tools/review_dedup_page.py — page /doublons (consolidation manuelle)."""
from __future__ import annotations

import review_dedup_page as ddp


def _reco(rid, title="T", quote="", status="validated", links=None):
    r = {"id": rid, "episodeGuid": "g1", "title": title, "status": status,
         "types": ["film"]}
    if quote:
        r["quote"] = quote
    if links:
        r["links"] = links
    return r


def _patch(monkeypatch, recos, episodes=None):
    source = {"title": "Src", "hosts": []}
    episodes = episodes or {"g1": {"guid": "g1", "title": "Ep"}}
    monkeypatch.setattr(ddp, "_load_groups",
                        lambda s: (source, episodes, {"g1": recos}))


def test_cluster_by_same_title(monkeypatch):
    """Même titre + même épisode → cluster ; le survivant = plus de liens."""
    _patch(monkeypatch, [
        _reco("ubm-1", "Foo"),
        _reco("ubm-2", "Foo", links=[{"url": "u"}]),
        _reco("ubm-3", "Bar"),
    ])
    _s, _e, clusters = ddp.collect_dup_clusters("src")
    assert len(clusters) == 1
    assert {r["id"] for r in clusters[0]} == {"ubm-1", "ubm-2"}
    assert clusters[0][0]["id"] == "ubm-2"  # survivant suggéré (plus de liens)


def test_cluster_by_same_quote(monkeypatch):
    """Même quote (≥15 car.) + même épisode → cluster, même si titres différents."""
    q = "je vais aller au spectacle de Valérie Lemercier"
    _patch(monkeypatch, [
        _reco("ubm-1", "Valérie Lemercier", quote=q),
        _reco("ubm-2", "Spectacle de Valérie", quote=q),
    ])
    _s, _e, clusters = ddp.collect_dup_clusters("src")
    assert len(clusters) == 1
    assert {r["id"] for r in clusters[0]} == {"ubm-1", "ubm-2"}


def test_no_cluster_when_single_active(monkeypatch):
    """Un cluster avec 1 seul membre ACTIF (l'autre discarded) n'est pas montré."""
    _patch(monkeypatch, [
        _reco("ubm-1", "Foo"),
        _reco("ubm-2", "Foo", status="discarded"),
    ])
    _s, _e, clusters = ddp.collect_dup_clusters("src")
    assert clusters == []


def test_distinct_titles_and_quotes_not_clustered(monkeypatch):
    """Titres ET quotes différents → pas de cluster (œuvres distinctes)."""
    _patch(monkeypatch, [
        _reco("ubm-1", "Blink-182", quote="j'aime le punk rock, Blink"),
        _reco("ubm-2", "Sum 41", quote="et aussi Sum 41 c'est bien"),
    ])
    _s, _e, clusters = ddp.collect_dup_clusters("src")
    assert clusters == []


def test_render_page_has_checkboxes_and_types(monkeypatch):
    """La page rend, par membre : case Garder (cochée), champ titre, radios type."""
    _patch(monkeypatch, [
        _reco("ubm-1", "Foo"),
        _reco("ubm-2", "Foo", links=[{"url": "u"}]),
    ])
    out = ddp.render_dedup_page("src")
    assert 'action="/consolidate"' in out
    assert out.count('name="keep"') == 2
    assert 'name="title_ubm-1"' in out and 'name="title_ubm-2"' in out
    assert 'name="type_ubm-1"' in out
    assert "★ suggérée" in out  # survivant marqué


def test_render_empty(monkeypatch):
    _patch(monkeypatch, [_reco("ubm-1", "Foo"), _reco("ubm-2", "Bar")])
    out = ddp.render_dedup_page("src")
    assert "Aucun doublon" in out
