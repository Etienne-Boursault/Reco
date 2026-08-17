"""Tests de `tools/review_table.py` — COLLECTE des lignes du tableau.

Ce fichier couvre `build_rows` : filtrage des recos écartées, clés de tri,
fusion du sidecar de curation et des propositions de types, et sûreté des liens
retenus. Le RENDU est testé dans `test_review_table_render.py`, et
l'échappement dans `test_review_table_escaping.py` — la version d'origine
réunissait les trois et dépassait 500 lignes.
"""
from __future__ import annotations

import review_table as rtab
from fixtures_review_table import _patch, _reco


# ===== build_rows ==========================================================
def test_build_rows_keeps_only_active_recos(monkeypatch):
    _patch(monkeypatch, [_reco("ubm-1"), _reco("ubm-2", status="discarded")])
    _source, rows = rtab.build_rows("src")
    assert [r["id"] for r in rows] == ["ubm-1"]


def test_build_rows_exposes_display_fields(monkeypatch):
    _patch(monkeypatch, [_reco("ubm-1", title="Mortel", creator="F. Garcia",
                               recommendedBy="Hakim", types=["serie"])])
    _source, rows = rtab.build_rows("src")
    row = rows[0]
    assert row["title"] == "Mortel"
    assert row["artist"] == "F. Garcia"
    assert row["by"] == "Hakim"
    assert row["types"] == ["serie"]
    assert row["ep_label"] == "S1·E3 — Ép. 1"


def test_build_rows_tolerates_missing_fields(monkeypatch):
    """Une reco sans creator/recommendedBy/timestamp ne casse pas la collecte."""
    _patch(monkeypatch, [{"id": "ubm-1", "episodeGuid": "g1", "title": "T",
                          "status": "validated"}])
    _source, rows = rtab.build_rows("src")
    assert rows[0]["artist"] == "" and rows[0]["by"] == ""
    assert rows[0]["types"] == []


def test_build_rows_handles_unknown_episode(monkeypatch):
    """Reco rattachée à un guid inconnu → libellé de repli, pas de KeyError."""
    _patch(monkeypatch, [_reco("ubm-1", episodeGuid="fantome")])
    _source, rows = rtab.build_rows("src")
    assert rows[0]["ep_label"] == "fantome"
    assert rows[0]["ep_guid"] == "fantome"


def test_build_rows_episode_label_without_season(monkeypatch):
    _patch(monkeypatch, [_reco("ubm-1")],
           episodes={"g1": {"guid": "g1", "title": "Ép. seule", "number": 7}})
    _source, rows = rtab.build_rows("src")
    assert rows[0]["ep_label"] == "#7 — Ép. seule"


def test_build_rows_episode_label_without_number(monkeypatch):
    _patch(monkeypatch, [_reco("ubm-1")],
           episodes={"g1": {"guid": "g1", "title": "Hors-série"}})
    _source, rows = rtab.build_rows("src")
    assert rows[0]["ep_label"] == "Hors-série"


def test_build_rows_episode_label_falls_back_to_guid(monkeypatch):
    _patch(monkeypatch, [_reco("ubm-1")], episodes={"g1": {"guid": "g1"}})
    _source, rows = rtab.build_rows("src")
    assert rows[0]["ep_label"] == "g1"


def test_build_rows_chrono_key_orders_by_date_then_timestamp(monkeypatch):
    """Le tri « chronologique » suit la date d'épisode puis le timecode."""
    episodes = {
        "g1": {"guid": "g1", "title": "A", "date": "2021-02-14", "number": 3},
        "g2": {"guid": "g2", "title": "B", "date": "2020-01-01", "number": 1},
    }
    _patch(monkeypatch, [
        _reco("ubm-1", timestamp="01:00:00"),
        _reco("ubm-2", timestamp="00:05:00"),
        _reco("ubm-3", episodeGuid="g2"),
    ], episodes=episodes)
    _source, rows = rtab.build_rows("src")
    order = sorted(rows, key=lambda r: r["chrono"])
    assert [r["id"] for r in order] == ["ubm-3", "ubm-2", "ubm-1"]


def test_build_rows_chrono_key_tolerates_missing_metadata(monkeypatch):
    """Épisode sans date/numéro et reco sans timestamp → clé quand même formée."""
    _patch(monkeypatch, [{"id": "ubm-1", "episodeGuid": "g1", "title": "T",
                          "status": "validated"}],
           episodes={"g1": {"guid": "g1", "title": "X"}})
    _source, rows = rtab.build_rows("src")
    assert isinstance(rows[0]["chrono"], str) and rows[0]["chrono"]


def test_build_rows_merges_curation_sidecar(monkeypatch):
    _patch(monkeypatch, [_reco("ubm-1"), _reco("ubm-2")],
           curation={"ubm-1": {"comment": "à revoir", "checked": True,
                               "updatedAt": "2026-07-31T10:00:00+00:00"}})
    _source, rows = rtab.build_rows("src")
    by_id = {r["id"]: r for r in rows}
    assert by_id["ubm-1"]["comment"] == "à revoir"
    assert by_id["ubm-1"]["checked"] is True
    assert by_id["ubm-2"]["comment"] == "" and by_id["ubm-2"]["checked"] is False


def test_build_rows_attaches_type_proposal(monkeypatch):
    _patch(monkeypatch, [_reco("ubm-1", types=["autre"])],
           proposals={"ubm-1": {"types": ["film"], "reason": "long métrage"}})
    _source, rows = rtab.build_rows("src")
    assert rows[0]["proposal"]["types"] == ["film"]
    assert rows[0]["proposal"]["reason"] == "long métrage"


def test_build_rows_proposal_lists_dropped_types(monkeypatch):
    """La proposition REMPLACE `types` : ce qu'elle retire doit être explicite."""
    _patch(monkeypatch, [_reco("ubm-1", types=["autre", "lieu"])],
           proposals={"ubm-1": {"types": ["lieu"]}})
    assert rtab.build_rows("src")[1][0]["proposal"]["dropped"] == ["autre"]


def test_build_rows_proposal_without_dropped_types(monkeypatch):
    _patch(monkeypatch, [_reco("ubm-1", types=["autre"])],
           proposals={"ubm-1": {"types": ["autre", "film"]}})
    assert rtab.build_rows("src")[1][0]["proposal"]["dropped"] == []


def test_build_rows_ignores_proposal_with_unknown_type(monkeypatch):
    """Un type hors vocabulaire ne doit pas devenir acceptable d'une coche."""
    _patch(monkeypatch, [_reco("ubm-1")],
           proposals={"ubm-1": {"types": ["nawak"], "reason": ""}})
    assert rtab.build_rows("src")[1][0]["proposal"] is None


def test_build_rows_ignores_proposal_identical_to_current_types(monkeypatch):
    _patch(monkeypatch, [_reco("ubm-1", types=["film"])],
           proposals={"ubm-1": {"types": ["film"], "reason": ""}})
    assert rtab.build_rows("src")[1][0]["proposal"] is None


def test_build_rows_without_proposal_file(monkeypatch):
    _patch(monkeypatch, [_reco("ubm-1")], proposals={})
    assert rtab.build_rows("src")[1][0]["proposal"] is None


def test_build_rows_filters_unsafe_links(monkeypatch):
    _patch(monkeypatch, [_reco("ubm-1", links=[
        {"url": "https://ok.example/a", "label": "Bon", "ethics": "indie"},
        {"url": "javascript:alert(1)", "label": "XSS"},
        {"url": "file:///C:/secret.txt", "label": "Local"},
        {"label": "Sans URL"},
        "pas un objet",
    ])])
    _source, rows = rtab.build_rows("src")
    assert [link["url"] for link in rows[0]["links"]] == ["https://ok.example/a"]


def test_build_rows_link_label_falls_back_to_host(monkeypatch):
    _patch(monkeypatch, [_reco("ubm-1", links=[{"url": "https://deezer.com/x"}])])
    _source, rows = rtab.build_rows("src")
    assert rows[0]["links"][0]["label"] == "deezer.com"


def test_build_rows_link_label_falls_back_to_url_when_host_unparsable(monkeypatch):
    _patch(monkeypatch, [_reco("ubm-1", links=[{"url": "https:///chemin"}])])
    _source, rows = rtab.build_rows("src")
    assert rows[0]["links"][0]["label"] == "https:///chemin"


def test_build_rows_links_not_a_list(monkeypatch):
    _patch(monkeypatch, [_reco("ubm-1", links="oups")])
    assert rtab.build_rows("src")[1][0]["links"] == []



# ===== Recherches pré-remplies =============================================
def test_build_rows_attaches_missing_search_links(monkeypatch):
    """118 films n'ont aucune fiche : la recherche pré-remplie est le seul
    chemin restant (TMDB ne renvoie plus de lien JustWatch, AlloCiné n'a pas
    d'API)."""
    _patch(monkeypatch, [_reco("ubm-1", title="Mortel", types=["film"])])
    labels = [s["label"] for s in rtab.build_rows("src")[1][0]["search"]]
    assert "JustWatch" in labels and "AlloCiné" in labels


def test_build_rows_search_skips_platforms_already_linked(monkeypatch):
    """On ne propose pas de CHERCHER ce qui est déjà TROUVÉ."""
    _patch(monkeypatch, [_reco("ubm-1", types=["film"], links=[
        {"url": "https://www.allocine.fr/film/fichefilm_gen_cfilm=1.html"}])])
    labels = [s["label"] for s in rtab.build_rows("src")[1][0]["search"]]
    assert "AlloCiné" not in labels and "JustWatch" in labels


def test_build_rows_search_ignores_links_rejected_as_unsafe(monkeypatch):
    """Un `javascript:allocine.fr` ne « couvre » pas AlloCiné : la détection
    travaille sur les liens NORMALISÉS, pas sur la donnée brute."""
    _patch(monkeypatch, [_reco("ubm-1", types=["film"], links=[
        {"url": "javascript:allocine.fr"}])])
    labels = [s["label"] for s in rtab.build_rows("src")[1][0]["search"]]
    assert "AlloCiné" in labels


