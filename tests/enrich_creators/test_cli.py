"""Tests de l'orchestration : sélection des cibles, écriture, CLI, rapport.

Le disque est réel (tmp_path) mais le réseau est entièrement mocké via une
fausse fonction `resolve_creator` injectée — l'orchestration est testée
indépendamment des clients API (déjà couverts par `test_resolve.py`).
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import enrich_creators as ec


# ===== Fixtures =============================================================
def _write(root: Path, source: str, reco: dict) -> Path:
    d = root / source
    d.mkdir(parents=True, exist_ok=True)
    p = d / f"{reco['id']}.json"
    p.write_text(json.dumps(reco, ensure_ascii=False, indent=2), encoding="utf-8")
    return p


@pytest.fixture()
def root(tmp_path: Path) -> Path:
    r = tmp_path / "recos"
    _write(r, "src-a", {"id": "a-0001", "sourceId": "src-a", "episodeGuid": "g1",
                        "title": "Titanic", "types": ["film"],
                        "externalIds": {"tmdb": "597", "tmdbType": "movie"}})
    _write(r, "src-a", {"id": "a-0002", "sourceId": "src-a", "episodeGuid": "g1",
                        "title": "Breaking Bad", "types": ["serie"],
                        "externalIds": {"tmdb": "1396", "tmdbType": "tv"}})
    _write(r, "src-a", {"id": "a-0003", "sourceId": "src-a", "episodeGuid": "g1",
                        "title": "Déjà rempli", "types": ["film"], "creator": "X",
                        "externalIds": {"tmdb": "1", "tmdbType": "movie"}})
    _write(r, "src-b", {"id": "b-0001", "sourceId": "src-b", "episodeGuid": "g2",
                        "title": "Un podcast", "types": ["podcast"]})
    return r


def _fake_resolver(mapping: dict[str, ec.Resolution]):
    """Remplace `resolve_creator` : renvoie la résolution mappée par id."""
    def _resolve(reco, *, session, api_key, episode_year=None,
                 allow_search=False):
        return mapping.get(reco["id"],
                           ec.Resolution(None, ec.REASON_TYPE_UNSUPPORTED, None))
    return _resolve


FILLED = ec.Resolution("James Cameron", ec.REASON_FILLED, "tmdb:movie/597")


# ===== Sélection des fichiers ==============================================
def test_iter_reco_paths_all_sources(root):
    paths = ec.iter_reco_paths(root)
    assert [p.stem for p in paths] == ["a-0001", "a-0002", "a-0003", "b-0001"]


def test_iter_reco_paths_filtered_by_source(root):
    assert [p.stem for p in ec.iter_reco_paths(root, source="src-b")] == ["b-0001"]


def test_iter_reco_paths_unknown_source_is_empty(root):
    assert ec.iter_reco_paths(root, source="nope") == []


def test_iter_reco_paths_missing_root(tmp_path):
    assert ec.iter_reco_paths(tmp_path / "absent") == []


# ===== apply_creator ========================================================
def test_apply_creator_sets_field_and_audit_trail():
    reco = {"id": "x", "title": "T"}
    ec.apply_creator(reco, "James Cameron", timestamp="2026-07-29T00:00:00Z")
    assert reco["creator"] == "James Cameron"
    assert reco["enrichedAt"] == {"creator": "2026-07-29T00:00:00Z"}


def test_apply_creator_preserves_other_enriched_fields():
    reco = {"id": "x", "enrichedAt": {"watchProviders": "2026-01-01T00:00:00Z"}}
    ec.apply_creator(reco, "A", timestamp="2026-07-29T00:00:00Z")
    assert reco["enrichedAt"]["watchProviders"] == "2026-01-01T00:00:00Z"
    assert reco["enrichedAt"]["creator"] == "2026-07-29T00:00:00Z"


def test_apply_creator_uses_now_when_no_timestamp():
    reco = {"id": "x"}
    ec.apply_creator(reco, "A")
    assert reco["enrichedAt"]["creator"].endswith("Z")


def test_apply_creator_refuses_corrupted_enriched_at():
    reco = {"id": "x", "enrichedAt": "pas-un-dict"}
    with pytest.raises(ec.EnrichedAtCorruptedError):
        ec.apply_creator(reco, "A")


# ===== run() — dry-run vs apply ============================================
def test_run_dry_run_does_not_write(root, monkeypatch):
    monkeypatch.setattr(ec, "resolve_creator", _fake_resolver({"a-0001": FILLED}))
    before = (root / "src-a" / "a-0001.json").read_text(encoding="utf-8")
    report = ec.run(root=root, session=None, api_key="k", sleep=0)
    assert report.written == 0
    assert len(report.filled) == 1
    assert (root / "src-a" / "a-0001.json").read_text(encoding="utf-8") == before


def test_run_apply_writes_creator(root, monkeypatch):
    monkeypatch.setattr(ec, "resolve_creator", _fake_resolver({"a-0001": FILLED}))
    report = ec.run(root=root, session=None, api_key="k", apply=True, sleep=0)
    assert report.written == 1
    d = json.loads((root / "src-a" / "a-0001.json").read_text(encoding="utf-8"))
    assert d["creator"] == "James Cameron"
    assert "creator" in d["enrichedAt"]


def test_run_apply_touches_only_creator_and_audit(root, monkeypatch):
    monkeypatch.setattr(ec, "resolve_creator", _fake_resolver({"a-0001": FILLED}))
    path = root / "src-a" / "a-0001.json"
    before = json.loads(path.read_text(encoding="utf-8"))
    ec.run(root=root, session=None, api_key="k", apply=True, sleep=0)
    after = json.loads(path.read_text(encoding="utf-8"))
    assert set(after) - set(before) == {"creator", "enrichedAt"}
    for k, v in before.items():
        assert after[k] == v


def test_run_is_idempotent(root, monkeypatch):
    monkeypatch.setattr(ec, "resolve_creator", _fake_resolver({"a-0001": FILLED}))
    ec.run(root=root, session=None, api_key="k", apply=True, sleep=0)
    # Second passage : le vrai resolver rendrait ALREADY_SET ; ici le fake
    # renverrait encore FILLED — c'est `run` qui doit court-circuiter.
    report = ec.run(root=root, session=None, api_key="k", apply=True, sleep=0)
    assert report.written == 0
    assert report.skipped[ec.REASON_ALREADY_SET] >= 1


def test_run_never_overwrites_existing_creator(root, monkeypatch):
    monkeypatch.setattr(ec, "resolve_creator", _fake_resolver({"a-0003": FILLED}))
    ec.run(root=root, session=None, api_key="k", apply=True, sleep=0)
    d = json.loads((root / "src-a" / "a-0003.json").read_text(encoding="utf-8"))
    assert d["creator"] == "X"


# ===== run() — filtres ======================================================
def test_run_does_not_count_unchanged_writes(root, monkeypatch):
    """`write_json_if_changed` renvoie False si le contenu est identique."""
    monkeypatch.setattr(ec, "resolve_creator", _fake_resolver({"a-0001": FILLED}))
    monkeypatch.setattr(ec, "write_json_if_changed", lambda p, d: False)
    report = ec.run(root=root, session=None, api_key="k", apply=True, sleep=0)
    assert len(report.filled) == 1 and report.written == 0


def test_run_sleeps_between_calls(root, monkeypatch):
    calls: list[float] = []
    monkeypatch.setattr(ec.time, "sleep", calls.append)
    monkeypatch.setattr(ec, "resolve_creator", _fake_resolver({"a-0001": FILLED}))
    ec.run(root=root, session=None, api_key="k", sleep=0.01)
    assert calls and all(c == 0.01 for c in calls)


def test_load_episode_years(tmp_path):
    eps = tmp_path / "episodes" / "src-a"
    eps.mkdir(parents=True)
    (eps / "ep-001.json").write_text(
        json.dumps({"guid": "g1", "date": "2021-03-07T10:00:00Z"}), encoding="utf-8")
    (eps / "ep-002.json").write_text(
        json.dumps({"guid": "g2"}), encoding="utf-8")           # sans date
    (eps / "ep-003.json").write_text("{cassé", encoding="utf-8")
    years = ec.load_episode_years(tmp_path / "episodes")
    assert years == {"g1": 2021}
    assert ec.load_episode_years(tmp_path / "episodes", source="src-a") == {"g1": 2021}
    assert ec.load_episode_years(tmp_path / "absent") == {}


def test_run_passes_episode_year_to_resolver(root, monkeypatch):
    seen: dict[str, int | None] = {}

    def _resolve(reco, *, session, api_key, episode_year=None,
                 allow_search=False):
        seen[reco["id"]] = episode_year
        return ec.Resolution(None, ec.REASON_NO_DIRECTOR, None)

    monkeypatch.setattr(ec, "resolve_creator", _resolve)
    ec.run(root=root, session=None, api_key="k", sleep=0,
           episode_years={"g1": 2021})
    assert seen["a-0001"] == 2021
    assert seen["b-0001"] is None      # guid g2 absent de l'index


def test_run_filter_source(root, monkeypatch):
    monkeypatch.setattr(ec, "resolve_creator", _fake_resolver({}))
    report = ec.run(root=root, source="src-b", session=None, api_key="k", sleep=0)
    assert report.seen == 1


def test_run_filter_types(root, monkeypatch):
    monkeypatch.setattr(ec, "resolve_creator", _fake_resolver({}))
    report = ec.run(root=root, types=("serie",), session=None, api_key="k", sleep=0)
    assert report.seen == 1


def test_run_filter_limit_counts_candidates_only(root, monkeypatch):
    """`--limit` borne les recos RÉSOLUES, pas les fichiers lus."""
    monkeypatch.setattr(ec, "resolve_creator",
                        _fake_resolver({"a-0001": FILLED, "a-0002": FILLED}))
    report = ec.run(root=root, limit=1, session=None, api_key="k", sleep=0)
    assert len(report.filled) == 1


def test_run_exclude_ids(root, monkeypatch):
    monkeypatch.setattr(ec, "resolve_creator", _fake_resolver({"a-0001": FILLED}))
    report = ec.run(root=root, exclude_ids={"a-0001"}, session=None,
                    api_key="k", apply=True, sleep=0)
    assert report.written == 0
    assert report.skipped[ec.REASON_EXCLUDED] == 1


def test_run_skips_unreadable_json(root, monkeypatch):
    (root / "src-a" / "broken.json").write_text("{invalid", encoding="utf-8")
    monkeypatch.setattr(ec, "resolve_creator", _fake_resolver({}))
    report = ec.run(root=root, session=None, api_key="k", sleep=0)
    assert report.skipped[ec.REASON_UNREADABLE] == 1


# ===== Rapport ==============================================================
def test_report_tracks_reasons_by_type(root, monkeypatch):
    monkeypatch.setattr(ec, "resolve_creator", _fake_resolver({
        "a-0001": FILLED,
        "a-0002": ec.Resolution(None, ec.REASON_NO_CREATED_BY, None),
    }))
    report = ec.run(root=root, session=None, api_key="k", sleep=0)
    assert report.by_type["film"]["filled"] == 1
    assert report.by_type["serie"]["empty"] == 1
    assert report.reasons_by_type["serie"][ec.REASON_NO_CREATED_BY] == 1


def test_report_lists_ambiguous_cases(root, monkeypatch):
    monkeypatch.setattr(ec, "resolve_creator", _fake_resolver({
        "a-0001": ec.Resolution(None, ec.REASON_TITLE_MISMATCH, None,
                                detail="TMDB dit « Autre »"),
    }))
    report = ec.run(root=root, session=None, api_key="k", sleep=0)
    assert [r.reco_id for r in report.review] == ["a-0001"]
    assert "Autre" in report.review[0].detail


def test_report_not_ambiguous_when_source_simply_has_no_data(root, monkeypatch):
    monkeypatch.setattr(ec, "resolve_creator", _fake_resolver({
        "a-0002": ec.Resolution(None, ec.REASON_NO_CREATED_BY, None)}))
    report = ec.run(root=root, session=None, api_key="k", sleep=0)
    assert report.review == []


def test_report_completion_rate_on_empty_run(tmp_path):
    report = ec.run(root=tmp_path / "vide", session=None, api_key="k", sleep=0)
    assert report.seen == 0
    assert "0.0 %" in ec.format_report(report)


def test_run_skips_reco_with_corrupted_enriched_at(root, monkeypatch):
    """Audit trail corrompu : on refuse d'écrire plutôt que de l'écraser."""
    _write(root, "src-a", {"id": "a-0004", "title": "Titanic", "types": ["film"],
                           "enrichedAt": "pas-un-dict",
                           "externalIds": {"tmdb": "597", "tmdbType": "movie"}})
    monkeypatch.setattr(ec, "resolve_creator", _fake_resolver({"a-0004": FILLED}))
    report = ec.run(root=root, session=None, api_key="k", apply=True, sleep=0)
    assert report.written == 0
    d = json.loads((root / "src-a" / "a-0004.json").read_text(encoding="utf-8"))
    assert "creator" not in d


def test_format_report_is_readable(root, monkeypatch):
    monkeypatch.setattr(ec, "resolve_creator", _fake_resolver({"a-0001": FILLED}))
    text = ec.format_report(ec.run(root=root, session=None, api_key="k", sleep=0))
    assert "film" in text and "James Cameron" not in text  # agrégat, pas détail
    assert "%" in text


def test_report_json_payload_round_trips(root, monkeypatch):
    monkeypatch.setattr(ec, "resolve_creator", _fake_resolver({"a-0001": FILLED}))
    report = ec.run(root=root, session=None, api_key="k", sleep=0)
    payload = ec.report_payload(report)
    assert json.loads(json.dumps(payload, ensure_ascii=False))["filled"][0]["creator"] \
        == "James Cameron"


# ===== main() ===============================================================
@pytest.fixture()
def no_lock(monkeypatch):
    """Neutralise le verrou pipeline (pas de review_server dans les tests)."""
    import contextlib
    monkeypatch.setattr(ec, "acquire_pipeline_lock",
                        lambda force=False: contextlib.nullcontext())


def test_main_dry_run_by_default(root, monkeypatch, no_lock, capsys):
    monkeypatch.setattr(ec, "RECOS_DIR", root)
    monkeypatch.setattr(ec, "resolve_creator", _fake_resolver({"a-0001": FILLED}))
    monkeypatch.setenv("TMDB_API_KEY", "k")
    rc = ec.main(["--source", "src-a"])
    assert rc == 0
    d = json.loads((root / "src-a" / "a-0001.json").read_text(encoding="utf-8"))
    assert "creator" not in d


def test_main_apply_writes(root, monkeypatch, no_lock):
    monkeypatch.setattr(ec, "RECOS_DIR", root)
    monkeypatch.setattr(ec, "resolve_creator", _fake_resolver({"a-0001": FILLED}))
    monkeypatch.setenv("TMDB_API_KEY", "k")
    assert ec.main(["--apply"]) == 0
    d = json.loads((root / "src-a" / "a-0001.json").read_text(encoding="utf-8"))
    assert d["creator"] == "James Cameron"


def test_main_writes_json_report(root, tmp_path, monkeypatch, no_lock):
    monkeypatch.setattr(ec, "RECOS_DIR", root)
    monkeypatch.setattr(ec, "resolve_creator", _fake_resolver({"a-0001": FILLED}))
    monkeypatch.setenv("TMDB_API_KEY", "k")
    out = tmp_path / "rep.json"
    ec.main(["--json", str(out)])
    assert json.loads(out.read_text(encoding="utf-8"))["filled"][0]["id"] == "a-0001"


def test_main_without_tmdb_key_still_runs(root, monkeypatch, no_lock, caplog):
    """Pas de clé TMDB : on continue (Deezer/OpenLibrary sont sans clé)."""
    monkeypatch.setattr(ec, "RECOS_DIR", root)
    monkeypatch.setattr(ec, "resolve_creator", _fake_resolver({}))
    monkeypatch.delenv("TMDB_API_KEY", raising=False)
    monkeypatch.setattr(ec, "load_dotenv", lambda *a, **kw: None)
    assert ec.main([]) == 0


def test_main_exclude_ids_option(root, monkeypatch, no_lock):
    monkeypatch.setattr(ec, "RECOS_DIR", root)
    monkeypatch.setattr(ec, "resolve_creator", _fake_resolver({"a-0001": FILLED}))
    monkeypatch.setenv("TMDB_API_KEY", "k")
    ec.main(["--apply", "--exclude-ids", "a-0001,a-0002"])
    d = json.loads((root / "src-a" / "a-0001.json").read_text(encoding="utf-8"))
    assert "creator" not in d


def test_main_exclude_ids_from_file(root, tmp_path, monkeypatch, no_lock):
    f = tmp_path / "skip.txt"
    f.write_text("# commentaire\na-0001\n\n", encoding="utf-8")
    monkeypatch.setattr(ec, "RECOS_DIR", root)
    monkeypatch.setattr(ec, "resolve_creator", _fake_resolver({"a-0001": FILLED}))
    monkeypatch.setenv("TMDB_API_KEY", "k")
    ec.main(["--apply", "--exclude-ids", f"@{f}"])
    d = json.loads((root / "src-a" / "a-0001.json").read_text(encoding="utf-8"))
    assert "creator" not in d


def test_main_returns_1_when_lock_busy(root, monkeypatch):
    monkeypatch.setattr(ec, "RECOS_DIR", root)

    def _busy(force=False):
        raise ec.ServerLockBusy("review_server tourne")
    monkeypatch.setattr(ec, "acquire_pipeline_lock", _busy)
    monkeypatch.setenv("TMDB_API_KEY", "k")
    assert ec.main(["--apply"]) == 1


def test_main_dry_run_does_not_need_the_lock(root, monkeypatch):
    """Lecture seule → pas de verrou (on peut auditer serveur allumé)."""
    monkeypatch.setattr(ec, "RECOS_DIR", root)

    def _boom(force=False):
        raise AssertionError("le dry-run ne doit pas prendre le verrou")
    monkeypatch.setattr(ec, "acquire_pipeline_lock", _boom)
    monkeypatch.setattr(ec, "resolve_creator", _fake_resolver({}))
    monkeypatch.setenv("TMDB_API_KEY", "k")
    assert ec.main([]) == 0
