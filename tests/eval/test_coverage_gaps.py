"""Tests qui ciblent spécifiquement les branches non couvertes."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.eval.adapters.legacy_reco_adapter import LegacyRecoExtractionSource
from tools.eval.golden_set import GoldenEpisode, GoldenSet, load_golden_set
from tools.eval.harness import (
    DictExtractionSource,
    EvalHarness,
    _to_extracted,
)
from tools.eval.metrics import f1_inclusive_ts
from tools.eval.reporters import REPORTERS
from tools.eval.reporters.base import get_registry, register_reporter
from tools.eval.reporters.csv_reporter import CsvReporter, render_csv
from tools.eval.reporters.markdown_reporter import (
    MarkdownReporter,
    render_markdown,
)
from tools.eval.types import EvalDetail, EvalMetrics, ExtractedReco


def test_to_extracted_raises_on_unknown_type() -> None:
    with pytest.raises(TypeError):
        _to_extracted(42)


def test_to_extracted_passthrough_extracted_reco() -> None:
    r = ExtractedReco(title="X")
    assert _to_extracted(r) is r


def test_dict_extraction_source_flat_no_default_guid() -> None:
    src = DictExtractionSource.from_legacy_dict([{"title": "A"}])
    # Pas de guid → bucket spécial.
    assert "__flat__" in src.by_guid


def test_evaluate_full_handles_empty_golden_set() -> None:
    h = EvalHarness(GoldenSet())
    src = DictExtractionSource(by_guid={})
    metrics = h.evaluate_full(src)
    assert metrics.n_expected == 0


def test_evaluate_with_extraction_source_no_episode_guid() -> None:
    """Branche : harness.evaluate appelé avec un ExtractionSource."""
    ep = GoldenEpisode("ep1", "src", (
        # avec creator pour atteindre la branche fuzzy match config
    ))
    gs = GoldenSet(episodes=(ep,))
    h = EvalHarness(gs)
    src = DictExtractionSource(by_guid={"ep1": ()})
    r = h.evaluate(src)
    assert r.n_expected == 0
    assert r.n_extracted == 0


def test_load_golden_set_non_dict_root(tmp_path: Path) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps([1, 2, 3]), encoding="utf-8")
    with pytest.raises(Exception, match="objet JSON"):
        load_golden_set(bad)


def test_get_registry_returns_copy() -> None:
    reg = get_registry()
    reg["whatever"] = type
    assert "whatever" not in REPORTERS


def test_csv_reporter_class_methods() -> None:
    from tools.eval.metrics import EvalResult, MatchVerdict
    r = EvalResult(
        n_expected=1, n_extracted=1, n_exact_match=1, n_fuzzy_match=0,
        n_missed=0, n_spurious=0, n_wrong_timestamp=0,
        precision=1.0, recall=1.0, f1=1.0,
        details=({"verdict": MatchVerdict.EXACT_MATCH.value,
                  "expected_title": "X", "matched_title": "X",
                  "score": 1.0},),
    )
    reporter = CsvReporter()
    s = reporter.render(r, title="ignored")
    assert "X" in s


def test_csv_reporter_with_eval_detail_objects() -> None:
    m = EvalMetrics(
        n_expected=1, n_extracted=1, n_exact_match=1, n_fuzzy_match=0,
        n_missed=0, n_spurious=0, n_wrong_timestamp=0,
        precision=1.0, recall=1.0, f1=1.0,
        details=(EvalDetail(verdict="exact", expected_title="X",
                            matched_title="X", score=1.0),),
    )
    s = render_csv(m)
    assert "exact" in s


def test_csv_reporter_write_with_title(tmp_path: Path) -> None:
    from tools.eval.metrics import EvalResult
    r = EvalResult(
        n_expected=0, n_extracted=0, n_exact_match=0, n_fuzzy_match=0,
        n_missed=0, n_spurious=0, n_wrong_timestamp=0,
        precision=0.0, recall=0.0, f1=0.0,
    )
    p = tmp_path / "x.csv"
    CsvReporter().write(r, p, title="ignored")
    assert p.exists()


def test_markdown_reporter_with_per_episode() -> None:
    ep_metric = EvalMetrics(
        n_expected=1, n_extracted=1, n_exact_match=1, n_fuzzy_match=0,
        n_missed=0, n_spurious=0, n_wrong_timestamp=0,
        precision=1.0, recall=1.0, f1=1.0,
    )
    m = EvalMetrics(
        n_expected=1, n_extracted=1, n_exact_match=1, n_fuzzy_match=0,
        n_missed=0, n_spurious=0, n_wrong_timestamp=0,
        precision=1.0, recall=1.0, f1=1.0,
        per_episode={"ep1": ep_metric},
    )
    out = render_markdown(m)
    assert "Top 5 épisodes" in out
    assert "Bottom 5 épisodes" in out
    assert "ep1" in out


def test_markdown_reporter_class() -> None:
    from tools.eval.metrics import EvalResult
    r = EvalResult(
        n_expected=0, n_extracted=0, n_exact_match=0, n_fuzzy_match=0,
        n_missed=0, n_spurious=0, n_wrong_timestamp=0,
        precision=0.0, recall=0.0, f1=0.0,
    )
    out = MarkdownReporter().render(r, title="T")
    assert "# T" in out


def test_markdown_reporter_write(tmp_path: Path) -> None:
    from tools.eval.metrics import EvalResult
    r = EvalResult(
        n_expected=0, n_extracted=0, n_exact_match=0, n_fuzzy_match=0,
        n_missed=0, n_spurious=0, n_wrong_timestamp=0,
        precision=0.0, recall=0.0, f1=0.0,
    )
    p = tmp_path / "x.md"
    MarkdownReporter().write(r, p, title="T")
    assert "# T" in p.read_text("utf-8")


def test_markdown_no_per_episode_skips_section() -> None:
    from tools.eval.metrics import EvalResult
    r = EvalResult(
        n_expected=1, n_extracted=1, n_exact_match=1, n_fuzzy_match=0,
        n_missed=0, n_spurious=0, n_wrong_timestamp=0,
        precision=1.0, recall=1.0, f1=1.0,
    )
    out = render_markdown(r)
    assert "Top 5" not in out


def test_legacy_adapter_protocol_check() -> None:
    """Vérifie que ``LegacyRecoExtractionSource`` est utilisable."""
    src = LegacyRecoExtractionSource(by_guid={"x": ()})
    assert tuple(src.for_episode("x")) == ()


def test_f1_inclusive_ts_basic() -> None:
    # n_exact=2, n_fuzzy=0, n_wrong_ts=2, n_missed=0, n_spurious=0
    # tp_weighted = 3 ; extracted = 4 ; expected = 4
    # p = r = 0.75 → f1 = 0.75
    assert f1_inclusive_ts(2, 0, 2, 0, 0) == pytest.approx(0.75)


def test_f1_inclusive_ts_empty() -> None:
    assert f1_inclusive_ts(0, 0, 0, 0, 0) == 0.0


def test_markdown_eval_metrics_no_per_episode() -> None:
    """Branche : EvalMetrics avec ``per_episode`` vide."""
    m = EvalMetrics(
        n_expected=1, n_extracted=1, n_exact_match=1, n_fuzzy_match=0,
        n_missed=0, n_spurious=0, n_wrong_timestamp=0,
        precision=1.0, recall=1.0, f1=1.0,
        details=(EvalDetail(verdict="exact", expected_title="X",
                            matched_title="X", score=1.0),),
    )
    out = render_markdown(m)
    assert "Top 5" not in out
    # Et la ligne avec EvalDetail.to_dict est passée.
    assert "X" in out


def test_legacy_adapter_skips_blank_title() -> None:
    from dataclasses import dataclass

    @dataclass
    class _R:
        title: str
        episode_guid: str | None = None

    src = LegacyRecoExtractionSource.from_legacy([_R(title="", episode_guid="x")])
    assert list(src.episode_guids()) == []


def test_markdown_details_iter_with_plain_dict() -> None:
    """Branche : ``_details_iter`` reçoit un dict (pas un ``EvalDetail``)."""
    from tools.eval.metrics import EvalResult
    r = EvalResult(
        n_expected=0, n_extracted=0, n_exact_match=0, n_fuzzy_match=0,
        n_missed=0, n_spurious=0, n_wrong_timestamp=0,
        precision=0.0, recall=0.0, f1=0.0,
        details=({"verdict": "X", "expected_title": "T", "score": ""},),
    )
    out = render_markdown(r)
    assert "T" in out


def test_filter_sources_empty_list_no_filter() -> None:
    from tools.eval_extraction import _filter_sources
    gs = GoldenSet(episodes=(GoldenEpisode("g", "src", ()),))
    assert _filter_sources(gs, None) is gs
    assert _filter_sources(gs, []) is gs


def test_check_strict_guid_non_dict() -> None:
    from tools.eval_extraction import _check_strict_guid
    gs = GoldenSet(episodes=(GoldenEpisode("g", "src", ()),))
    assert _check_strict_guid(gs, [1, 2]) == []


def test_resolve_manifest_path_uses_runs_dir(tmp_path: Path) -> None:
    from tools.eval_extraction import _resolve_manifest_path
    runs = tmp_path / "runs"
    runs.mkdir()
    (runs / "r1.json").write_text("{}", encoding="utf-8")
    resolved = _resolve_manifest_path("r1", runs_dir=runs)
    assert resolved.name == "r1.json"


def test_register_reporter_decorator() -> None:
    @register_reporter("test-dummy")
    class Dummy:
        pass

    assert REPORTERS["test-dummy"] is Dummy
    REPORTERS.pop("test-dummy", None)
