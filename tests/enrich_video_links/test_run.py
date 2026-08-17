"""Tests de l'orchestration : sélection des cibles, écriture, rapport, CLI.

Le disque est réel (`tmp_path`) mais le réseau est entièrement mocké par une
fausse `resolve_video_links` injectée — les clients API sont déjà couverts par
`test_resolve.py`.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import enrich_video_links as evl

# `run` vit dans le module d'orchestration depuis la scission : c'est LUI
# qu'il faut substituer. Remplacer `enrich_video_links.resolve_video_links`
# n'aurait aucun effet — la façade ne fait que ré-exporter.
import video_links_pipeline as pipeline

IMDB = {"label": "IMDb", "url": "https://www.imdb.com/title/tt0120338/",
        "kind": "info", "ethics": "neutral"}
TMDB = {"label": "TMDB", "url": "https://www.themoviedb.org/movie/597",
        "kind": "info", "ethics": "neutral"}
JW = {"label": "JustWatch", "url": "https://www.justwatch.com/fr/film/titanic",
      "kind": "streaming", "ethics": "neutral"}

FILLED = evl.Resolution((IMDB, TMDB), evl.REASON_FILLED, "tmdb:movie/597",
                        evl.POPULATION_ID)
FILLED_SEARCH = evl.Resolution((IMDB,), evl.REASON_FILLED, "tmdb:movie/1",
                               evl.POPULATION_SEARCH)


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
                        "title": "Titanic", "types": ["film"], "status": "validated",
                        "links": [{"label": "AlloCiné", "kind": "info",
                                   "ethics": "neutral",
                                   "url": "https://www.allocine.fr/film/1.html"}],
                        "externalIds": {"tmdb": "597", "tmdbType": "movie"}})
    _write(r, "src-a", {"id": "a-0002", "sourceId": "src-a", "episodeGuid": "g1",
                        "title": "Sans id", "types": ["serie"], "status": "validated"})
    _write(r, "src-a", {"id": "a-0003", "sourceId": "src-a", "episodeGuid": "g1",
                        "title": "Écartée", "types": ["film"], "status": "discarded"})
    _write(r, "src-b", {"id": "b-0001", "sourceId": "src-b", "episodeGuid": "g2",
                        "title": "Un podcast", "types": ["podcast"],
                        "status": "validated"})
    return r


def _fake_resolver(mapping: dict[str, evl.Resolution]):
    def _resolve(reco, *, session, api_key, episode_year=None, allow_search=False,
                 sites=evl.ALL_SITES):
        return mapping.get(reco["id"],
                           evl.Resolution((), evl.REASON_SEARCH_NO_MATCH,
                                          "tmdb-search:movie", evl.POPULATION_SEARCH))
    return _resolve


@pytest.fixture()
def no_lock(monkeypatch):
    class _Lock:
        def __enter__(self): return self
        def __exit__(self, *a): return False
    monkeypatch.setattr(evl, "acquire_pipeline_lock", lambda **kw: _Lock())


# ===== Sélection ============================================================
def test_run_ignores_non_video_types(root, monkeypatch):
    monkeypatch.setattr(pipeline, "resolve_video_links", _fake_resolver({}))
    report = evl.run(root=root, session=None, api_key="k", sleep=0)
    assert report.seen == 2  # a-0001 et a-0002 ; a-0003 écartée, b-0001 podcast


def test_run_skips_discarded_recos(root, monkeypatch):
    monkeypatch.setattr(pipeline, "resolve_video_links", _fake_resolver({}))
    report = evl.run(root=root, session=None, api_key="k", sleep=0)
    assert report.skipped[evl.REASON_NOT_VALIDATED] == 1


def test_run_filters_by_source(root, monkeypatch):
    monkeypatch.setattr(pipeline, "resolve_video_links", _fake_resolver({}))
    report = evl.run(root=root, session=None, api_key="k", source="src-b", sleep=0)
    assert report.seen == 0


def test_run_reports_unreadable_json(root, monkeypatch):
    (root / "src-a" / "cassee.json").write_text("{pas du json", encoding="utf-8")
    monkeypatch.setattr(pipeline, "resolve_video_links", _fake_resolver({}))
    report = evl.run(root=root, session=None, api_key="k", sleep=0)
    assert report.skipped[evl.REASON_UNREADABLE] == 1


def test_run_excludes_listed_ids(root, monkeypatch):
    monkeypatch.setattr(pipeline, "resolve_video_links", _fake_resolver({"a-0001": FILLED}))
    report = evl.run(root=root, session=None, api_key="k", exclude_ids=["a-0001"],
                     sleep=0)
    assert report.skipped[evl.REASON_EXCLUDED] == 1
    assert report.filled == []


def test_run_limit_caps_api_calls(root, monkeypatch):
    monkeypatch.setattr(pipeline, "resolve_video_links",
                        _fake_resolver({"a-0001": FILLED, "a-0002": FILLED_SEARCH}))
    report = evl.run(root=root, session=None, api_key="k", limit=1, sleep=0)
    assert len(report.filled) == 1


def test_run_passes_episode_year_to_resolver(root, monkeypatch):
    seen = {}

    def _resolve(reco, *, session, api_key, episode_year=None, allow_search=False,
                 sites=evl.ALL_SITES):
        seen[reco["id"]] = episode_year
        return evl.Resolution((), evl.REASON_NO_NEW_LINK, "s", evl.POPULATION_ID)

    monkeypatch.setattr(pipeline, "resolve_video_links", _resolve)
    evl.run(root=root, session=None, api_key="k", episode_years={"g1": 2019}, sleep=0)
    assert seen["a-0001"] == 2019


def test_run_sleeps_between_calls(root, monkeypatch):
    calls = []
    monkeypatch.setattr(pipeline, "resolve_video_links", _fake_resolver({}))
    monkeypatch.setattr(pipeline.time, "sleep", lambda s: calls.append(s))
    evl.run(root=root, session=None, api_key="k", sleep=0.5)
    assert calls == [0.5, 0.5]


# ===== Écriture =============================================================
def test_run_dry_run_does_not_write(root, monkeypatch):
    monkeypatch.setattr(pipeline, "resolve_video_links", _fake_resolver({"a-0001": FILLED}))
    before = (root / "src-a" / "a-0001.json").read_text(encoding="utf-8")
    report = evl.run(root=root, session=None, api_key="k", sleep=0)
    assert report.written == 0
    assert len(report.filled) == 1
    assert (root / "src-a" / "a-0001.json").read_text(encoding="utf-8") == before


def test_run_apply_appends_links_after_existing_ones(root, monkeypatch):
    monkeypatch.setattr(pipeline, "resolve_video_links", _fake_resolver({"a-0001": FILLED}))
    report = evl.run(root=root, session=None, api_key="k", apply=True, sleep=0)
    assert report.written == 1
    d = json.loads((root / "src-a" / "a-0001.json").read_text(encoding="utf-8"))
    assert [link["label"] for link in d["links"]] == ["AlloCiné", "IMDb", "TMDB"]
    assert "links" in d["enrichedAt"]


def test_run_apply_leaves_other_fields_untouched(root, monkeypatch):
    monkeypatch.setattr(pipeline, "resolve_video_links", _fake_resolver({"a-0001": FILLED}))
    evl.run(root=root, session=None, api_key="k", apply=True, sleep=0)
    d = json.loads((root / "src-a" / "a-0001.json").read_text(encoding="utf-8"))
    assert d["externalIds"] == {"tmdb": "597", "tmdbType": "movie"}
    assert d["title"] == "Titanic"


def test_run_apply_skips_corrupted_audit_trail(root, monkeypatch, caplog):
    p = root / "src-a" / "a-0001.json"
    d = json.loads(p.read_text(encoding="utf-8"))
    d["enrichedAt"] = "pas-un-dict"
    p.write_text(json.dumps(d), encoding="utf-8")
    monkeypatch.setattr(pipeline, "resolve_video_links", _fake_resolver({"a-0001": FILLED}))
    report = evl.run(root=root, session=None, api_key="k", apply=True, sleep=0)
    assert report.written == 0
    assert json.loads(p.read_text(encoding="utf-8"))["enrichedAt"] == "pas-un-dict"


def test_run_apply_is_idempotent(root, monkeypatch):
    monkeypatch.setattr(pipeline, "resolve_video_links", _fake_resolver({"a-0001": FILLED}))
    evl.run(root=root, session=None, api_key="k", apply=True, sleep=0)
    second = evl.run(root=root, session=None, api_key="k", apply=True, sleep=0)
    assert second.written == 0


# ===== Rapport ==============================================================
def test_report_separates_populations(root, monkeypatch):
    monkeypatch.setattr(pipeline, "resolve_video_links",
                        _fake_resolver({"a-0001": FILLED, "a-0002": FILLED_SEARCH}))
    report = evl.run(root=root, session=None, api_key="k", sleep=0)
    assert report.by_population[evl.POPULATION_ID]["recos"] == 1
    assert report.by_population[evl.POPULATION_ID]["links"] == 2
    assert report.by_population[evl.POPULATION_SEARCH]["links"] == 1


def test_report_counts_links_by_site(root, monkeypatch):
    monkeypatch.setattr(pipeline, "resolve_video_links",
                        _fake_resolver({"a-0001": FILLED, "a-0002": FILLED_SEARCH}))
    report = evl.run(root=root, session=None, api_key="k", sleep=0)
    assert report.links_by_site[evl.POPULATION_ID]["IMDb"] == 1
    assert report.links_by_site[evl.POPULATION_ID]["TMDB"] == 1
    assert report.links_by_site[evl.POPULATION_SEARCH]["IMDb"] == 1


def test_report_flags_recos_pushed_past_the_display_cap(root, monkeypatch):
    p = root / "src-a" / "a-0001.json"
    d = json.loads(p.read_text(encoding="utf-8"))
    d["links"] = [{"label": f"L{i}", "url": f"https://x{i}.test/a",
                   "kind": "info", "ethics": "neutral"} for i in range(5)]
    p.write_text(json.dumps(d), encoding="utf-8")
    monkeypatch.setattr(pipeline, "resolve_video_links", _fake_resolver({"a-0001": FILLED}))
    report = evl.run(root=root, session=None, api_key="k", sleep=0)
    assert report.filled[0].total_after == 7
    assert len(report.truncated) == 1


def test_report_does_not_flag_when_under_the_cap(root, monkeypatch):
    monkeypatch.setattr(pipeline, "resolve_video_links", _fake_resolver({"a-0001": FILLED}))
    report = evl.run(root=root, session=None, api_key="k", sleep=0)
    assert report.truncated == []


def test_report_collects_ambiguous_cases_for_human_review(root, monkeypatch):
    doubt = evl.Resolution((), evl.REASON_SEARCH_AMBIGUOUS, "tmdb-search:movie",
                           evl.POPULATION_SEARCH, detail="2 œuvres : 1, 2")
    monkeypatch.setattr(pipeline, "resolve_video_links", _fake_resolver({"a-0002": doubt}))
    report = evl.run(root=root, session=None, api_key="k", sleep=0)
    assert [c.reco_id for c in report.review] == ["a-0002"]
    assert report.review[0].detail == "2 œuvres : 1, 2"


def test_report_ignores_plain_absences_in_review(root, monkeypatch):
    monkeypatch.setattr(pipeline, "resolve_video_links", _fake_resolver({}))
    report = evl.run(root=root, session=None, api_key="k", sleep=0)
    assert report.review == []


def test_format_report_is_readable(root, monkeypatch):
    monkeypatch.setattr(pipeline, "resolve_video_links",
                        _fake_resolver({"a-0001": FILLED, "a-0002": FILLED_SEARCH}))
    report = evl.run(root=root, session=None, api_key="k", sleep=0)
    text = evl.format_report(report)
    assert evl.POPULATION_ID in text
    assert "IMDb" in text
    assert "Recos vues : 2" in text


def test_format_report_on_empty_run():
    assert "Recos vues : 0" in evl.format_report(evl.Report())


def test_format_report_mentions_truncation_when_it_happens(root, monkeypatch):
    p = root / "src-a" / "a-0001.json"
    d = json.loads(p.read_text(encoding="utf-8"))
    d["links"] = [{"label": f"L{i}", "url": f"https://x{i}.test/a",
                   "kind": "info", "ethics": "neutral"} for i in range(5)]
    p.write_text(json.dumps(d), encoding="utf-8")
    monkeypatch.setattr(pipeline, "resolve_video_links", _fake_resolver({"a-0001": FILLED}))
    report = evl.run(root=root, session=None, api_key="k", sleep=0)
    assert "au-delà des 6" in evl.format_report(report)


def test_report_payload_is_json_serialisable(root, monkeypatch):
    monkeypatch.setattr(pipeline, "resolve_video_links",
                        _fake_resolver({"a-0001": FILLED, "a-0002": FILLED_SEARCH}))
    report = evl.run(root=root, session=None, api_key="k", sleep=0)
    payload = evl.report_payload(report)
    json.dumps(payload)  # ne doit pas lever
    assert payload["filled"][0]["population"] == evl.POPULATION_ID
    assert payload["filled"][0]["links"][0]["label"] == "IMDb"
    assert payload["byPopulation"][evl.POPULATION_ID]["links"] == 2


# ===== CLI ==================================================================
def test_main_dry_run_by_default(root, monkeypatch, no_lock):
    monkeypatch.setattr(evl, "RECOS_DIR", root)
    monkeypatch.setattr(pipeline, "resolve_video_links", _fake_resolver({"a-0001": FILLED}))
    monkeypatch.setenv("TMDB_API_KEY", "k")
    assert evl.main(["--source", "src-a"]) == 0
    d = json.loads((root / "src-a" / "a-0001.json").read_text(encoding="utf-8"))
    assert len(d["links"]) == 1


def test_main_apply_writes(root, monkeypatch, no_lock):
    monkeypatch.setattr(evl, "RECOS_DIR", root)
    monkeypatch.setattr(pipeline, "resolve_video_links", _fake_resolver({"a-0001": FILLED}))
    monkeypatch.setenv("TMDB_API_KEY", "k")
    assert evl.main(["--apply"]) == 0
    d = json.loads((root / "src-a" / "a-0001.json").read_text(encoding="utf-8"))
    assert len(d["links"]) == 3


def test_main_writes_json_report(root, tmp_path, monkeypatch, no_lock):
    monkeypatch.setattr(evl, "RECOS_DIR", root)
    monkeypatch.setattr(pipeline, "resolve_video_links", _fake_resolver({"a-0001": FILLED}))
    monkeypatch.setenv("TMDB_API_KEY", "k")
    out = tmp_path / "rapport.json"
    evl.main(["--json", str(out)])
    assert json.loads(out.read_text(encoding="utf-8"))["filled"][0]["id"] == "a-0001"


def test_main_search_flag_is_forwarded(root, monkeypatch, no_lock):
    seen = {}

    def _resolve(reco, *, session, api_key, episode_year=None, allow_search=False,
                 sites=evl.ALL_SITES):
        seen["allow_search"] = allow_search
        seen["sites"] = sites
        return evl.Resolution((), evl.REASON_NO_NEW_LINK, "s", evl.POPULATION_ID)

    monkeypatch.setattr(evl, "RECOS_DIR", root)
    monkeypatch.setattr(pipeline, "resolve_video_links", _resolve)
    monkeypatch.setenv("TMDB_API_KEY", "k")
    evl.main(["--search", "--sites", "imdb"])
    assert seen["allow_search"] is True
    assert seen["sites"] == (evl.SITE_IMDB,)


def test_main_rejects_unknown_site(root, monkeypatch, no_lock, caplog):
    monkeypatch.setattr(evl, "RECOS_DIR", root)
    monkeypatch.setenv("TMDB_API_KEY", "k")
    assert evl.main(["--sites", "allocine"]) == 2


def test_main_without_api_key_stops(root, monkeypatch, no_lock):
    monkeypatch.setattr(evl, "RECOS_DIR", root)
    monkeypatch.setattr(evl, "load_dotenv", lambda *a, **kw: None)
    monkeypatch.delenv("TMDB_API_KEY", raising=False)
    assert evl.main([]) == 1


def test_main_exclude_ids_option(root, monkeypatch, no_lock):
    monkeypatch.setattr(evl, "RECOS_DIR", root)
    monkeypatch.setattr(pipeline, "resolve_video_links", _fake_resolver({"a-0001": FILLED}))
    monkeypatch.setenv("TMDB_API_KEY", "k")
    evl.main(["--apply", "--exclude-ids", "a-0001"])
    d = json.loads((root / "src-a" / "a-0001.json").read_text(encoding="utf-8"))
    assert len(d["links"]) == 1


def test_main_returns_1_when_lock_busy(root, monkeypatch):
    def _busy(**kw):
        raise evl.ServerLockBusy("serveur de relecture actif")

    monkeypatch.setattr(evl, "RECOS_DIR", root)
    monkeypatch.setattr(evl, "acquire_pipeline_lock", _busy)
    monkeypatch.setenv("TMDB_API_KEY", "k")
    assert evl.main(["--apply"]) == 1


def test_main_dry_run_does_not_take_the_lock(root, monkeypatch):
    def _boom(**kw):
        raise AssertionError("le dry-run ne doit pas prendre le verrou")

    monkeypatch.setattr(evl, "RECOS_DIR", root)
    monkeypatch.setattr(evl, "acquire_pipeline_lock", _boom)
    monkeypatch.setattr(pipeline, "resolve_video_links", _fake_resolver({}))
    monkeypatch.setenv("TMDB_API_KEY", "k")
    assert evl.main([]) == 0


def test_main_limit_option(root, monkeypatch, no_lock):
    monkeypatch.setattr(evl, "RECOS_DIR", root)
    monkeypatch.setattr(pipeline, "resolve_video_links",
                        _fake_resolver({"a-0001": FILLED, "a-0002": FILLED_SEARCH}))
    monkeypatch.setenv("TMDB_API_KEY", "k")
    assert evl.main(["--apply", "--limit", "1"]) == 0
    d = json.loads((root / "src-a" / "a-0002.json").read_text(encoding="utf-8"))
    assert "links" not in d
