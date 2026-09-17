"""Tests de `tools/apply_verdicts.py` — application des verdicts d'agents.

Le corpus est monté dans `tmp_path` et `common.RECOS_DIR` y est redirigé : un
test ne doit jamais écrire dans `src/content/recos`.
"""
from __future__ import annotations

import contextlib
import json
from pathlib import Path

import pytest

import apply_verdicts as av
import review_actions
import review_routes as rt

SOURCE = "demo-source"
GUID = "ep-1"


def _write(recos_dir: Path, reco: dict) -> None:
    (recos_dir / f"{reco['id']}.json").write_text(
        json.dumps(reco, ensure_ascii=False), encoding="utf-8")


def _read(recos_dir: Path, reco_id: str) -> dict:
    return json.loads((recos_dir / f"{reco_id}.json").read_text(encoding="utf-8"))


@pytest.fixture
def corpus(tmp_path, monkeypatch):
    import common

    monkeypatch.setattr(common, "RECOS_DIR", tmp_path / "recos")
    recos_dir = tmp_path / "recos" / SOURCE
    recos_dir.mkdir(parents=True)
    for n in range(1, 6):
        _write(recos_dir, {"id": f"ubm-000{n}", "episodeGuid": GUID,
                           "title": f"Œuvre {n}", "status": "draft",
                           "recommendedBy": "Extracteur"})
    _write(recos_dir, {"id": "ubm-0009", "episodeGuid": GUID, "title": "Déjà vue",
                       "status": "validated", "kind": "reco"})
    _write(recos_dir, {"id": "ubm-0010", "episodeGuid": "ep-2", "title": "Ailleurs",
                       "status": "draft"})
    return recos_dir


def _entry(verdict: str, **extra) -> dict:
    return {"verdict": verdict, "confidence": 0.8, "reason": "Raison.",
            "recommendedBy": "", **extra}


def _full_file() -> dict:
    return {
        "ubm-0001": _entry("validate", recommendedBy="Navo", flags=["title_suspect"],
                           note="Titre à vérifier."),
        "ubm-0002": _entry("citation", recommendedBy="Kyan Khojandi"),
        "ubm-0003": _entry("guest-work", recommendedBy="Navo"),
        "ubm-0004": _entry("discard"),
        "ubm-0005": _entry("unsure"),
    }


def _run(tmp_path: Path, verdicts: dict, *extra: str) -> int:
    path = tmp_path / "verdicts.json"
    path.write_text(json.dumps(verdicts, ensure_ascii=False), encoding="utf-8")
    argv = ["--source", SOURCE, "--guid", GUID, "--verdicts", str(path),
            "--model", "claude-test", *extra]
    return av.main(argv, today="2026-09-20", use_lock=False)


def _snapshot(recos_dir: Path) -> dict[str, str]:
    return {p.name: p.read_text(encoding="utf-8") for p in sorted(recos_dir.iterdir())}


# ===== application ==========================================================
def test_each_verdict_sets_what_the_review_server_would(tmp_path, corpus):
    assert _run(tmp_path, _full_file()) == 0

    validated = _read(corpus, "ubm-0001")
    assert (validated["status"], validated["kind"], validated["recommendedBy"]) == (
        "validated", "reco", "Navo")
    citation = _read(corpus, "ubm-0002")
    assert (citation["status"], citation["kind"]) == ("validated", "citation")
    guest = _read(corpus, "ubm-0003")
    assert (guest["status"], guest["kind"], guest["guestWork"]) == (
        "validated", "reco", True)
    assert _read(corpus, "ubm-0004")["status"] == "discarded"


def test_empty_recommended_by_removes_the_extracted_attribution(tmp_path, corpus):
    """Chaîne vide = attribution douteuse : on retire celle de l'extracteur."""
    verdicts = {**_full_file(), "ubm-0001": _entry("validate", recommendedBy="")}
    assert _run(tmp_path, verdicts) == 0
    assert "recommendedBy" not in _read(corpus, "ubm-0001")


def test_discard_keeps_the_attribution_like_the_review_server(tmp_path, corpus):
    """Écarter ne requalifie rien : même règle que la décision humaine."""
    assert _run(tmp_path, _full_file()) == 0
    assert _read(corpus, "ubm-0004")["recommendedBy"] == "Extracteur"


def test_unsure_stays_draft_and_is_marked_not_applied(tmp_path, corpus):
    assert _run(tmp_path, _full_file()) == 0

    unsure = _read(corpus, "ubm-0005")
    assert unsure["status"] == "draft"
    assert unsure["recommendedBy"] == "Extracteur"
    assert unsure["agentReview"]["applied"] is False


def test_agent_review_block_is_traced_without_the_human_marker(tmp_path, corpus):
    assert _run(tmp_path, _full_file()) == 0

    review = _read(corpus, "ubm-0001")["agentReview"]
    assert review == {"verdict": "validate", "confidence": 0.8, "reason": "Raison.",
                      "model": "claude-test", "date": "2026-09-20", "applied": True,
                      "flags": ["title_suspect"], "note": "Titre à vérifier."}


def test_rerun_keeps_human_keys_and_drops_stale_flags(tmp_path, corpus):
    reco = _read(corpus, "ubm-0001")
    reco["agentReview"] = {"verdict": "unsure", "flags": ["ancien"], "note": "vieux",
                           "reviewedByHuman": True, "flagsResolved": ["ancien"]}
    _write(corpus, reco)

    assert _run(tmp_path, {"ubm-0001": _entry("validate")}, "--allow-partial") == 0

    review = _read(corpus, "ubm-0001")["agentReview"]
    assert review["reviewedByHuman"] is True
    assert review["flagsResolved"] == ["ancien"]
    assert "flags" not in review and "note" not in review


def test_other_recos_are_left_untouched(tmp_path, corpus):
    before = {rid: _read(corpus, rid) for rid in ("ubm-0009", "ubm-0010")}
    assert _run(tmp_path, _full_file()) == 0
    assert {rid: _read(corpus, rid) for rid in before} == before


# ===== garde-fous : refus en bloc ============================================
@pytest.mark.parametrize("patch, fragment", [
    ({"ubm-9999": _entry("validate")}, "aucune reco"),
    ({"ubm-0009": _entry("validate")}, "seules les recos draft"),
    ({"ubm-0010": _entry("validate")}, "aucune reco"),
    ({"ubm-0001": _entry("approve")}, "inconnu"),
    ({"ubm-0001": {**_entry("validate"), "confidence": 1.5}}, "confidence"),
    ({"ubm-0001": {**_entry("validate"), "confidence": True}}, "confidence"),
    ({"ubm-0001": {**_entry("validate"), "reason": "  "}}, "reason vide"),
    ({"ubm-0001": {k: v for k, v in _entry("validate").items()
                   if k != "recommendedBy"}}, "recommendedBy manquant"),
    ({"ubm-0001": {**_entry("validate"), "flags": "title_suspect"}}, "flags"),
])
def test_a_single_bad_entry_refuses_the_whole_file(tmp_path, corpus, caplog,
                                                   patch, fragment):
    before = _snapshot(corpus)

    assert _run(tmp_path, {**_full_file(), **patch}) == 2

    assert _snapshot(corpus) == before
    assert fragment in caplog.text


def test_drafts_without_verdict_are_refused_unless_partial_is_allowed(tmp_path,
                                                                      corpus):
    partial = {"ubm-0001": _entry("validate")}
    before = _snapshot(corpus)

    assert _run(tmp_path, partial) == 2
    assert _snapshot(corpus) == before

    assert _run(tmp_path, partial, "--allow-partial") == 0
    assert _read(corpus, "ubm-0001")["status"] == "validated"
    assert _read(corpus, "ubm-0002")["status"] == "draft"


def test_unreadable_or_empty_file_is_refused(tmp_path, corpus):
    bad = tmp_path / "verdicts.json"
    bad.write_text("{pas du json", encoding="utf-8")
    argv = ["--source", SOURCE, "--guid", GUID, "--verdicts", str(bad),
            "--model", "m"]
    assert av.main(argv, use_lock=False) == 2
    assert _run(tmp_path, {}) == 2


def test_unknown_episode_is_refused(tmp_path, corpus):
    path = tmp_path / "verdicts.json"
    path.write_text(json.dumps(_full_file()), encoding="utf-8")
    argv = ["--source", SOURCE, "--guid", "ep-inconnu", "--verdicts", str(path),
            "--model", "m"]
    assert av.main(argv, use_lock=False) == 2


def test_dry_run_writes_nothing(tmp_path, corpus):
    before = _snapshot(corpus)
    assert _run(tmp_path, _full_file(), "--dry-run") == 0
    assert _snapshot(corpus) == before


# ===== verrou et intégrité ===================================================
def test_busy_review_server_refuses_without_writing(tmp_path, corpus, monkeypatch):
    import review_lock

    @contextlib.contextmanager
    def _busy(*, force=False):
        raise review_lock.ServerLockBusy("le review_server tourne")
        yield  # pragma: no cover

    monkeypatch.setattr(review_lock, "acquire_pipeline_lock", _busy)
    path = tmp_path / "verdicts.json"
    path.write_text(json.dumps(_full_file()), encoding="utf-8")
    before = _snapshot(corpus)

    argv = ["--source", SOURCE, "--guid", GUID, "--verdicts", str(path), "--model", "m"]
    assert av.main(argv) == 2
    assert _snapshot(corpus) == before


def test_integrity_check_reports_a_status_that_does_not_match(tmp_path, corpus):
    verdicts = _full_file()
    assert _run(tmp_path, verdicts) == 0
    reco = _read(corpus, "ubm-0004")
    reco["status"] = "validated"
    _write(corpus, reco)

    problems = av.check_integrity(SOURCE, GUID, verdicts)

    assert problems == ["ubm-0004 : statut « validated », attendu « discarded »"]


# ===== source unique partagée avec le review_server ==========================
def test_review_server_and_agents_share_the_same_actions():
    assert rt._SAVE_ACTIONS is review_actions.SAVE_ACTIONS
    assert av.VERDICTS == review_actions.SAVE_ACTIONS | {"unsure"}


def test_human_save_still_marks_the_reco_as_reviewed_by_human():
    reco = {"status": "draft"}
    rt.Handler._apply_save_action(reco, "citation", "Navo", "ubm-0001")
    assert reco["agentReview"]["reviewedByHuman"] is True
    assert (reco["status"], reco["kind"]) == ("validated", "citation")
