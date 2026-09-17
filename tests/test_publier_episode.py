"""Tests de `tools/publier_episode.py` — recos d'un épisode vers œuvres et mentions.

Le cœur du contrat : ne JAMAIS réécrire une œuvre ou une mention existante. La
migration historique le faisait, et effacerait aujourd'hui l'enrichissement du
corpus. Tout vit dans `tmp_path`.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import publier_episode as pe

SOURCE = "demo-source"
GUID = "yt-abc"


@pytest.fixture
def corpus(tmp_path, monkeypatch):
    import common

    content = tmp_path / "content"
    monkeypatch.setattr(common, "CONTENT_DIR", content)
    monkeypatch.setattr(common, "RECOS_DIR", content / "recos")
    for sub in ("recos", "items", "mentions"):
        (content / sub / SOURCE).mkdir(parents=True)
    return content


def _reco(content: Path, reco_id: str, title: str, *, status: str = "validated",
          guid: str = GUID, types=("serie",), creator: str | None = "Auteur",
          **extra) -> None:
    reco = {"id": reco_id, "title": title, "sourceId": SOURCE, "types": list(types),
            "episodeGuid": guid, "status": status, **extra}
    if creator:
        reco["creator"] = creator
    (content / "recos" / SOURCE / f"{reco_id}.json").write_text(
        json.dumps(reco, ensure_ascii=False), encoding="utf-8")


def _existing_item(content: Path, item_id: str, title: str, *, types=("serie",),
                   creator: str | None = "Auteur", **enrichment) -> Path:
    item = {"id": item_id, "title": title, "types": list(types), "schemaVersion": 1,
            **enrichment}
    if creator:
        item["creator"] = creator
    path = content / "items" / SOURCE / f"{item_id}.json"
    path.write_text(json.dumps(item, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _snapshot(content: Path) -> dict[str, str]:
    return {str(p.relative_to(content)): p.read_text(encoding="utf-8")
            for p in sorted(content.rglob("*.json"))}


# ===== refus =================================================================
def test_a_draft_blocks_the_whole_episode(corpus):
    _reco(corpus, "ubm-1", "Mortel")
    _reco(corpus, "ubm-2", "Bref", status="draft")
    before = _snapshot(corpus)

    plan = pe.preparer(SOURCE, GUID, apply=True)

    assert plan.refused and plan.drafts == ["ubm-2"]
    assert _snapshot(corpus) == before


def test_an_unknown_episode_is_refused(corpus):
    assert pe.preparer(SOURCE, "yt-inconnu").errors == ["aucune reco pour l'épisode yt-inconnu"]


def test_without_apply_nothing_is_written(corpus):
    _reco(corpus, "ubm-1", "Mortel")
    before = _snapshot(corpus)

    plan = pe.preparer(SOURCE, GUID)

    assert len(plan.items_created) == 1 and plan.mentions_created == ["ubm-1"]
    assert _snapshot(corpus) == before


# ===== création ==============================================================
def test_new_works_get_an_item_and_a_mention(corpus):
    _reco(corpus, "ubm-1", "Mortel", creator="Frédéric Garcia")

    plan = pe.preparer(SOURCE, GUID, apply=True)

    (item_id,) = plan.items_created
    item = _json(corpus / "items" / SOURCE / f"{item_id}.json")
    mention = _json(corpus / "mentions" / SOURCE / "ubm-1.json")
    assert (item["title"], item["creator"], item["types"]) == ("Mortel", "Frédéric Garcia", ["serie"])
    assert mention["itemId"] == item_id
    assert mention["sourceRef"] == {"sourceId": SOURCE, "episodeGuid": GUID}


def test_guest_work_is_carried_over_to_the_mention(corpus):
    _reco(corpus, "ubm-1", "Bref", guestWork=True)
    _reco(corpus, "ubm-2", "Mortel")

    pe.preparer(SOURCE, GUID, apply=True)

    assert _json(corpus / "mentions" / SOURCE / "ubm-1.json")["guestWork"] is True
    assert "guestWork" not in _json(corpus / "mentions" / SOURCE / "ubm-2.json")


def test_discarded_recos_also_get_their_mention_as_in_the_corpus(corpus):
    _reco(corpus, "ubm-1", "Faux positif", status="discarded")
    pe.preparer(SOURCE, GUID, apply=True)
    assert _json(corpus / "mentions" / SOURCE / "ubm-1.json")["status"] == "discarded"


def test_two_recos_of_the_same_new_work_share_one_item(corpus):
    _reco(corpus, "ubm-1", "Mortel")
    _reco(corpus, "ubm-2", "Mortel")

    plan = pe.preparer(SOURCE, GUID, apply=True)

    assert len(plan.items_created) == 1
    ids = {_json(corpus / "mentions" / SOURCE / f"ubm-{n}.json")["itemId"] for n in (1, 2)}
    assert ids == set(plan.items_created)


def test_only_the_requested_episode_is_touched(corpus):
    _reco(corpus, "ubm-1", "Mortel")
    _reco(corpus, "ubm-9", "Autre", guid="yt-other", status="draft")

    plan = pe.preparer(SOURCE, GUID, apply=True)

    assert not plan.refused
    assert not (corpus / "mentions" / SOURCE / "ubm-9.json").exists()


# ===== ne jamais réécrire =====================================================
def test_an_existing_work_is_reused_and_never_rewritten(corpus):
    enriched = _existing_item(corpus, "11112222", "Mortel",
                              externalIds={"tmdb": 12345},
                              watchProviders=[{"name": "Netflix", "url": "https://netflix.com"}])
    before = enriched.read_text(encoding="utf-8")
    _reco(corpus, "ubm-1", "MORTEL")  # même clé canonique une fois normalisée

    plan = pe.preparer(SOURCE, GUID, apply=True)

    assert plan.items_reused == ["11112222"] and plan.items_created == []
    assert enriched.read_text(encoding="utf-8") == before
    assert _json(corpus / "mentions" / SOURCE / "ubm-1.json")["itemId"] == "11112222"


def test_same_title_but_no_common_type_is_a_different_work(corpus):
    _existing_item(corpus, "11112222", "Dune", types=("livre",))
    _reco(corpus, "ubm-1", "Dune", types=("film",))

    plan = pe.preparer(SOURCE, GUID, apply=True)

    assert plan.items_reused == [] and len(plan.items_created) == 1


def test_duplicate_canonical_keys_in_the_corpus_do_not_crash(corpus):
    """La migration plante sur deux fiches de même clé (« game of thrones »)."""
    _existing_item(corpus, "10e6e524", "Game of Thrones", types=("livre",), creator=None)
    _existing_item(corpus, "4effb9f7", "Game of Thrones", types=("serie",), creator=None)
    _reco(corpus, "ubm-1", "Game of Thrones", types=("serie",), creator=None)

    plan = pe.preparer(SOURCE, GUID, apply=True)

    assert plan.items_reused == ["4effb9f7"]


def test_an_unreadable_item_file_stops_everything(corpus):
    """Le dépôt ignore une fiche illisible : sans ce garde-fou, doublon silencieux."""
    (corpus / "items" / SOURCE / "cassee00.json").write_text("{pas du json", encoding="utf-8")
    _reco(corpus, "ubm-1", "Mortel")

    plan = pe.preparer(SOURCE, GUID, apply=True)

    assert plan.refused and "illisible" in plan.errors[0]
    assert not (corpus / "mentions" / SOURCE / "ubm-1.json").exists()


def test_an_existing_mention_is_left_untouched(corpus):
    mention_path = corpus / "mentions" / SOURCE / "ubm-1.json"
    mention_path.write_text('{"id": "ubm-1", "itemId": "relu-a-la-main"}', encoding="utf-8")
    _reco(corpus, "ubm-1", "Mortel")

    plan = pe.preparer(SOURCE, GUID, apply=True)

    assert plan.mentions_existing == ["ubm-1"] and plan.items_created == []
    assert mention_path.read_text(encoding="utf-8") == '{"id": "ubm-1", "itemId": "relu-a-la-main"}'


def test_a_second_run_changes_nothing(corpus):
    _reco(corpus, "ubm-1", "Mortel")
    pe.preparer(SOURCE, GUID, apply=True)
    before = _snapshot(corpus)

    plan = pe.preparer(SOURCE, GUID, apply=True)

    assert plan.mentions_existing == ["ubm-1"] and plan.items_created == []
    assert _snapshot(corpus) == before


def test_a_fresh_id_landing_on_an_unrelated_file_stops_everything(corpus, monkeypatch):
    unrelated = _existing_item(corpus, "deadbeef", "Tout autre chose", types=("livre",))
    before = unrelated.read_text(encoding="utf-8")
    monkeypatch.setattr(pe, "generate_item_id", lambda _canonical, _used: "deadbeef")
    _reco(corpus, "ubm-1", "Mortel")

    plan = pe.preparer(SOURCE, GUID, apply=True)

    assert plan.refused and "deadbeef" in plan.errors[0]
    assert unrelated.read_text(encoding="utf-8") == before
    assert not (corpus / "mentions" / SOURCE / "ubm-1.json").exists()


# ===== CLI ===================================================================
def test_cli_exit_codes(corpus, monkeypatch):
    import contextlib

    import review_lock

    monkeypatch.setattr(review_lock, "acquire_pipeline_lock",
                        lambda force=False: contextlib.nullcontext())
    _reco(corpus, "ubm-1", "Mortel", status="draft")
    assert pe.main(["--source", SOURCE, "--guid", GUID, "--apply"]) == 2

    _reco(corpus, "ubm-1", "Mortel")
    assert pe.main(["--source", SOURCE, "--guid", GUID]) == 0
    assert pe.main(["--source", SOURCE, "--guid", GUID, "--apply"]) == 0
    assert (corpus / "mentions" / SOURCE / "ubm-1.json").exists()
