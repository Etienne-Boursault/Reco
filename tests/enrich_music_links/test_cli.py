"""Tests de l'écriture, du rapport et du CLI.

Le disque est réel (`tmp_path`) mais le réseau est neutralisé : `resolve_reco`
est remplacé par une fausse résolution mappée par identifiant. L'orchestration
est ainsi testée indépendamment des clients API (couverts par `test_clients`
et `test_resolve`).
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import enrich_music_links as m

# Les substitutions doivent viser le module où la fonction est UTILISÉE :
# `run` vit dans le pipeline, et remplacer `enrich_music_links.resolve_reco`
# n'aurait aucun effet sur lui — la façade ne fait que ré-exporter.
import music_links_pipeline as pipeline
from enrichment.field_refresher import EnrichedAtCorruptedError

DEEZER_LINK = m.MusicLink(m.PLATFORM_DEEZER, "Deezer",
                          "https://www.deezer.com/album/1", "deezer:album/1")
APPLE_LINK = m.MusicLink(m.PLATFORM_APPLE, "Apple Music",
                         "https://music.apple.com/fr/album/x/9", "apple:album/9")


def _write(root: Path, source: str, reco: dict) -> Path:
    d = root / source
    d.mkdir(parents=True, exist_ok=True)
    p = d / f"{reco['id']}.json"
    p.write_text(json.dumps(reco, ensure_ascii=False, indent=2), encoding="utf-8")
    return p


@pytest.fixture()
def root(tmp_path: Path) -> Path:
    r = tmp_path / "recos"
    _write(r, "src-a", {"id": "a-1", "title": "Civilisation", "creator": "Orelsan",
                        "types": ["album"], "status": "validated"})
    _write(r, "src-a", {"id": "a-2", "title": "Basique", "creator": "Orelsan",
                        "types": ["musique"], "status": "validated"})
    _write(r, "src-a", {"id": "a-3", "title": "Rejetée", "types": ["album"],
                        "status": "discarded"})
    _write(r, "src-a", {"id": "a-4", "title": "Un film", "types": ["film"],
                        "status": "validated"})
    _write(r, "src-b", {"id": "b-1", "title": "Gorillaz", "types": ["artiste"],
                        "status": "validated"})
    return r


def _fake_resolver(mapping: dict[str, m.RecoOutcome]):
    def _resolve(reco, *, session, allow_artists=False):
        return mapping.get(reco["id"], m.RecoOutcome((), (), m.REASON_NO_MATCH))
    return _resolve


LINKED = m.RecoOutcome((DEEZER_LINK,), (), m.REASON_LINKED)


# ===== apply_links_to_reco ==================================================
def test_apply_links_appends_and_traces():
    reco = {"id": "x"}
    m.apply_links_to_reco(reco, [DEEZER_LINK], timestamp="2026-07-31T00:00:00Z")
    assert reco["links"] == [{"label": "Deezer",
                              "url": "https://www.deezer.com/album/1",
                              "kind": "streaming", "ethics": "neutral"}]
    assert reco["enrichedAt"] == {"links": "2026-07-31T00:00:00Z"}


def test_apply_links_preserves_existing_links():
    reco = {"id": "x", "links": [{"label": "Qobuz", "url": "https://qobuz.com/a",
                                  "kind": "streaming", "ethics": "neutral"}]}
    m.apply_links_to_reco(reco, [DEEZER_LINK])
    assert [link["label"] for link in reco["links"]] == ["Qobuz", "Deezer"]


def test_apply_links_never_duplicates_an_existing_host():
    reco = {"id": "x", "links": [{"label": "Deezer (posé à la main)",
                                  "url": "https://www.deezer.com/album/999"}]}
    m.apply_links_to_reco(reco, [DEEZER_LINK])
    assert len(reco["links"]) == 1
    assert "enrichedAt" not in reco


def test_apply_links_preserves_other_enriched_fields():
    reco = {"id": "x", "enrichedAt": {"creator": "2026-01-01T00:00:00Z"}}
    m.apply_links_to_reco(reco, [DEEZER_LINK], timestamp="2026-07-31T00:00:00Z")
    assert reco["enrichedAt"]["creator"] == "2026-01-01T00:00:00Z"
    assert reco["enrichedAt"]["links"] == "2026-07-31T00:00:00Z"


def test_apply_links_uses_now_when_no_timestamp():
    reco = {"id": "x"}
    m.apply_links_to_reco(reco, [DEEZER_LINK])
    assert reco["enrichedAt"]["links"].endswith("Z")


# ===== iter_reco_paths / parse_exclude_ids ==================================
def test_iter_reco_paths_all_sources(root):
    assert [p.stem for p in m.iter_reco_paths(root)] == [
        "a-1", "a-2", "a-3", "a-4", "b-1"]


def test_iter_reco_paths_one_source(root):
    assert [p.stem for p in m.iter_reco_paths(root, source="src-b")] == ["b-1"]


def test_iter_reco_paths_missing_root(tmp_path):
    assert m.iter_reco_paths(tmp_path / "absent") == []


def test_parse_exclude_ids_none():
    assert m.parse_exclude_ids(None) == set()


def test_parse_exclude_ids_csv():
    assert m.parse_exclude_ids("a, b ,,c") == {"a", "b", "c"}


def test_parse_exclude_ids_from_file(tmp_path):
    f = tmp_path / "ids.txt"
    f.write_text("# commentaire\na-1\n\n a-2 \n", encoding="utf-8")
    assert m.parse_exclude_ids(f"@{f}") == {"a-1", "a-2"}


# ===== run ==================================================================
def _run(root, monkeypatch, mapping, **kwargs):
    monkeypatch.setattr(pipeline, "resolve_reco", _fake_resolver(mapping))
    return m.run(root=root, session=None, sleep=0, **kwargs)


def test_run_skips_non_musical_types(root, monkeypatch):
    report = _run(root, monkeypatch, {})
    assert report.seen == 4  # a-4 (film) n'est même pas compté


def test_run_skips_non_validated(root, monkeypatch):
    report = _run(root, monkeypatch, {"a-3": LINKED})
    assert report.reasons[m.REASON_NOT_VALIDATED] == 1
    assert report.linked == []


def test_run_filters_by_type(root, monkeypatch):
    report = _run(root, monkeypatch, {}, types=("album",))
    assert report.seen == 2  # a-1 (validée) et a-3 (rejetée)


def test_run_excluded_ids(root, monkeypatch):
    report = _run(root, monkeypatch, {"a-1": LINKED}, exclude_ids=["a-1"])
    assert report.reasons[m.REASON_EXCLUDED] == 1
    assert report.linked == []


def test_run_only_missing_skips_covered_recos(root, monkeypatch):
    _write(root, "src-a", {"id": "a-1", "title": "Civilisation",
                           "creator": "Orelsan", "types": ["album"],
                           "status": "validated",
                           "links": [{"url": "https://qobuz.com/a"}]})
    report = _run(root, monkeypatch, {"a-1": LINKED}, only_missing=True)
    assert report.reasons[m.REASON_ALREADY_COMPLETE] == 1


def test_run_limit_caps_resolutions(root, monkeypatch):
    report = _run(root, monkeypatch, {"a-1": LINKED, "a-2": LINKED}, limit=1)
    assert len(report.linked) == 1


def test_run_dry_run_does_not_write(root, monkeypatch):
    report = _run(root, monkeypatch, {"a-1": LINKED})
    assert report.written == 0
    assert "links" not in json.loads(
        (root / "src-a" / "a-1.json").read_text(encoding="utf-8"))


def test_run_apply_writes_links(root, monkeypatch):
    report = _run(root, monkeypatch, {"a-1": LINKED}, apply=True)
    assert report.written == 1
    saved = json.loads((root / "src-a" / "a-1.json").read_text(encoding="utf-8"))
    assert saved["links"][0]["url"] == "https://www.deezer.com/album/1"
    assert "links" in saved["enrichedAt"]


def test_run_apply_is_idempotent(root, monkeypatch):
    _run(root, monkeypatch, {"a-1": LINKED}, apply=True)
    second = _run(root, monkeypatch, {"a-1": LINKED}, apply=True)
    assert second.written == 0


def test_run_skips_reco_with_corrupted_audit_trail(root, monkeypatch):
    _write(root, "src-a", {"id": "a-1", "title": "Civilisation",
                           "creator": "Orelsan", "types": ["album"],
                           "status": "validated", "enrichedAt": "pas-un-dict"})

    def _boom(*_a, **_kw):
        raise EnrichedAtCorruptedError("enrichedAt non-dict")
    monkeypatch.setattr(pipeline, "apply_links_to_reco", _boom)
    report = _run(root, monkeypatch, {"a-1": LINKED}, apply=True)
    assert report.written == 0


def test_run_reports_unreadable_json(root, monkeypatch):
    (root / "src-a" / "a-1.json").write_text("{cassé", encoding="utf-8")
    report = _run(root, monkeypatch, {})
    assert report.reasons[m.REASON_UNREADABLE] == 1


def test_run_sleeps_between_recos(root, monkeypatch):
    calls: list[float] = []
    monkeypatch.setattr(pipeline.time, "sleep", calls.append)
    monkeypatch.setattr(pipeline, "resolve_reco", _fake_resolver({"a-1": LINKED}))
    m.run(root=root, session=None, sleep=0.01)
    assert calls and all(c == 0.01 for c in calls)


# ===== Rapport ==============================================================
def test_report_records_links_and_platforms():
    report = m.Report()
    reco = {"id": "a-1", "title": "Civilisation", "creator": "Orelsan",
            "types": ["album"]}
    report.record(reco, m.RecoOutcome((DEEZER_LINK, APPLE_LINK), (),
                                      m.REASON_LINKED))
    assert report.by_platform == {m.PLATFORM_DEEZER: 1, m.PLATFORM_APPLE: 1}
    assert report.by_type["album"]["liens"] == 2


def test_report_collects_ambiguous_refusals_for_review():
    report = m.Report()
    reco = {"id": "a-1", "title": "Amélie", "types": ["musique"]}
    report.record(reco, m.RecoOutcome((), (
        (m.PLATFORM_DEEZER, m.REASON_ARTIST_MISMATCH, "l'API répond « X »"),
        (m.PLATFORM_APPLE, m.REASON_NO_MATCH, ""),
    ), m.REASON_ARTIST_MISMATCH))
    assert [c.reason for c in report.review] == [m.REASON_ARTIST_MISMATCH]


def test_format_report_is_readable():
    report = m.Report(seen=3)
    report.record({"id": "a", "title": "T", "types": ["album"]},
                  m.RecoOutcome((DEEZER_LINK,), (), m.REASON_LINKED))
    text = m.format_report(report)
    assert "Deezer" in text
    assert "Recos vues : 3" in text


def test_format_report_without_any_link():
    text = m.format_report(m.Report(seen=1))
    assert "Recos vues : 1" in text


def test_report_payload_is_json_serialisable():
    report = m.Report(seen=1, written=1)
    report.record({"id": "a", "title": "T", "creator": "C", "types": ["album"]},
                  m.RecoOutcome((DEEZER_LINK,),
                                ((m.PLATFORM_APPLE, m.REASON_AMBIGUOUS, "2"),),
                                m.REASON_LINKED))
    payload = report_roundtrip = json.loads(
        json.dumps(m.report_payload(report), ensure_ascii=False))
    assert payload["linked"][0]["platform"] == m.PLATFORM_DEEZER
    assert report_roundtrip["review"][0]["reason"] == m.REASON_AMBIGUOUS


# ===== _log_outcome =========================================================
def test_log_outcome_both_branches(caplog):
    reco = {"id": "a", "title": "T", "creator": "C"}
    with caplog.at_level("INFO"):
        m._log_outcome("a", reco, m.RecoOutcome((DEEZER_LINK,), (),
                                                m.REASON_LINKED))
        m._log_outcome("a", reco, m.RecoOutcome((), (), m.REASON_NO_MATCH))
    assert "deezer.com/album/1" in caplog.text
    assert m.REASON_NO_MATCH in caplog.text


# ===== CLI ==================================================================
@pytest.fixture()
def cli(monkeypatch, root):
    """Neutralise réseau, chemins et verrou : seul le CLI est sous test."""
    monkeypatch.setattr(m, "RECOS_DIR", root)
    monkeypatch.setattr(pipeline, "resolve_reco", _fake_resolver({"a-1": LINKED}))
    monkeypatch.setattr(pipeline.time, "sleep", lambda _s: None)
    return root


def test_main_dry_run_by_default(cli, caplog):
    with caplog.at_level("INFO"):
        assert m.main([]) == 0
    assert "DRY-RUN" in caplog.text
    assert "links" not in json.loads(
        (cli / "src-a" / "a-1.json").read_text(encoding="utf-8"))


def test_main_apply_takes_the_lock_and_writes(cli, monkeypatch):
    taken = []

    class _Lock:
        def __enter__(self):
            taken.append(True)
        def __exit__(self, *_a):
            return False

    monkeypatch.setattr(m, "acquire_pipeline_lock", lambda force: _Lock())
    assert m.main(["--apply"]) == 0
    assert taken == [True]
    saved = json.loads((cli / "src-a" / "a-1.json").read_text(encoding="utf-8"))
    assert saved["links"][0]["label"] == "Deezer"


def test_main_apply_aborts_when_server_lock_is_busy(cli, monkeypatch):
    def _busy(force):
        raise m.ServerLockBusy("review_server tourne")
    monkeypatch.setattr(m, "acquire_pipeline_lock", _busy)
    assert m.main(["--apply"]) == 1


def test_main_writes_json_report(cli, tmp_path):
    out = tmp_path / "rapport.json"
    assert m.main(["--json", str(out)]) == 0
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["linked"][0]["id"] == "a-1"


def test_main_accepts_filters(cli):
    assert m.main(["--source", "src-a", "--types", "album", "--limit", "1",
                   "--artists", "--only-missing", "--exclude-ids", "zzz"]) == 0


def test_build_parser_defaults():
    args = m.build_parser().parse_args([])
    assert args.apply is False
    assert args.artists is False
    assert args.only_missing is False
