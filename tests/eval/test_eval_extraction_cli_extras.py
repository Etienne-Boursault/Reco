"""Tests CLI étendus : exit codes, strict-guid, compare, save-manifest, verbose."""
from __future__ import annotations

import csv
import io
import json
from pathlib import Path

import pytest

from tools import eval_extraction
from tools.eval.types import RunManifest

FIXTURES = Path(__file__).parent / "golden_set"


@pytest.fixture
def extracted_full(tmp_path: Path) -> Path:
    data = {
        "ep001": [{"title": "Drive"}, {"title": "Inception"}],
        "ep002": [{"title": "Le Mépris"}],
        "ep003": [{"title": "Citizen Kane"}],
    }
    p = tmp_path / "ex.json"
    p.write_text(json.dumps(data), encoding="utf-8")
    return p


@pytest.fixture
def extracted_missing_guid(tmp_path: Path) -> Path:
    """Dict sans ep002 → strict-guid doit échouer."""
    p = tmp_path / "ex.json"
    p.write_text(json.dumps({"ep001": [{"title": "Drive"}]}), encoding="utf-8")
    return p


class TestExitCodes:
    def test_missing_required_returns_1(self) -> None:
        assert eval_extraction.main([]) == eval_extraction.EXIT_USAGE

    def test_extracted_not_found_returns_1(self, tmp_path: Path) -> None:
        rc = eval_extraction.main([
            "--golden-set", str(FIXTURES),
            "--extracted", str(tmp_path / "ghost.json"),
        ])
        assert rc == eval_extraction.EXIT_USAGE

    def test_invalid_golden_set_returns_2(
        self, tmp_path: Path, extracted_full: Path,
    ) -> None:
        bad = tmp_path / "bad"
        bad.mkdir()
        (bad / "broken.json").write_text("not json", encoding="utf-8")
        rc = eval_extraction.main([
            "--golden-set", str(bad),
            "--extracted", str(extracted_full),
        ])
        assert rc == eval_extraction.EXIT_HARNESS

    def test_unknown_episode_returns_2(
        self, extracted_full: Path,
    ) -> None:
        rc = eval_extraction.main([
            "--golden-set", str(FIXTURES),
            "--extracted", str(extracted_full),
            "--episode-guid", "ghost",
        ])
        assert rc == eval_extraction.EXIT_HARNESS


class TestStrictGuid:
    def test_strict_guid_fails_on_missing(
        self, extracted_missing_guid: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        rc = eval_extraction.main([
            "--golden-set", str(FIXTURES),
            "--extracted", str(extracted_missing_guid),
            "--strict-guid",
        ])
        assert rc == eval_extraction.EXIT_HARNESS
        err = capsys.readouterr().err
        assert "ep002" in err or "ep003" in err

    def test_strict_guid_passes_when_all_present(
        self, extracted_full: Path,
    ) -> None:
        rc = eval_extraction.main([
            "--golden-set", str(FIXTURES),
            "--extracted", str(extracted_full),
            "--strict-guid",
            "--format", "csv",
        ])
        assert rc == eval_extraction.EXIT_OK


class TestSourceFilter:
    def test_source_filter_matches(
        self, extracted_full: Path,
    ) -> None:
        rc = eval_extraction.main([
            "--golden-set", str(FIXTURES),
            "--extracted", str(extracted_full),
            "--source", "un-bon-moment",
        ])
        assert rc == eval_extraction.EXIT_OK

    def test_source_filter_no_match(
        self, extracted_full: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        rc = eval_extraction.main([
            "--golden-set", str(FIXTURES),
            "--extracted", str(extracted_full),
            "--source", "ghost-source",
        ])
        assert rc == eval_extraction.EXIT_HARNESS


class TestVerbose:
    def test_verbose_dumps_details(
        self, extracted_full: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        rc = eval_extraction.main([
            "--golden-set", str(FIXTURES),
            "--extracted", str(extracted_full),
            "--episode-guid", "ep001",
            "--verbose",
        ])
        assert rc == eval_extraction.EXIT_OK
        out = capsys.readouterr().out
        assert "# Détails par verdict" in out


class TestFormatFlag:
    def test_format_alias_csv(
        self, extracted_full: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        rc = eval_extraction.main([
            "--golden-set", str(FIXTURES),
            "--extracted", str(extracted_full),
            "--episode-guid", "ep001",
            "--format", "csv",
        ])
        assert rc == eval_extraction.EXIT_OK
        # CSV est parsable.
        out = capsys.readouterr().out
        rows = list(csv.reader(io.StringIO(out)))
        assert any("precision" in r for r in rows if r)

    def test_format_markdown(
        self, extracted_full: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        rc = eval_extraction.main([
            "--golden-set", str(FIXTURES),
            "--extracted", str(extracted_full),
            "--episode-guid", "ep001",
            "--format", "markdown",
        ])
        assert rc == eval_extraction.EXIT_OK
        out = capsys.readouterr().out
        assert "# Eval report" in out


class TestSaveManifest:
    def test_save_creates_json(
        self, extracted_full: Path, tmp_path: Path, monkeypatch,
    ) -> None:
        runs_dir = tmp_path / "runs"
        monkeypatch.setattr(eval_extraction, "_RUNS_DIR", runs_dir)
        rc = eval_extraction.main([
            "--golden-set", str(FIXTURES),
            "--extracted", str(extracted_full),
            "--episode-guid", "ep001",
            "--save-manifest",
            "--run-id", "test-run",
            "--timestamp", "2026-06-10T12:00:00+00:00",
            "--output", str(tmp_path / "out.csv"),
        ])
        assert rc == eval_extraction.EXIT_OK
        manifest_file = runs_dir / "test-run.json"
        assert manifest_file.exists()
        data = json.loads(manifest_file.read_text("utf-8"))
        assert data["run_id"] == "test-run"
        assert data["timestamp"] == "2026-06-10T12:00:00+00:00"
        assert "f1" in data["scores"]

    def test_default_run_id_derived(
        self, extracted_full: Path, tmp_path: Path, monkeypatch,
    ) -> None:
        runs_dir = tmp_path / "runs"
        monkeypatch.setattr(eval_extraction, "_RUNS_DIR", runs_dir)
        rc = eval_extraction.main([
            "--golden-set", str(FIXTURES),
            "--extracted", str(extracted_full),
            "--episode-guid", "ep001",
            "--save-manifest",
            "--timestamp", "2026-06-10T12:00:00+00:00",
            "--output", str(tmp_path / "out.csv"),
        ])
        assert rc == eval_extraction.EXIT_OK
        # run_id dérivé du timestamp.
        files = list(runs_dir.glob("*.json"))
        assert len(files) == 1


class TestCompareSubcommand:
    def _make_manifest(self, tmp_path: Path, run_id: str, f1: float) -> Path:
        m = RunManifest(
            run_id=run_id, timestamp="2026-06-10T00:00:00+00:00",
            git_sha="", config_hash="", golden_set_hash="",
            scores={"precision": f1, "recall": f1, "f1": f1},
        )
        p = tmp_path / f"{run_id}.json"
        p.write_text(m.to_json(), encoding="utf-8")
        return p

    def test_compare_two_manifests(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str],
    ) -> None:
        base = self._make_manifest(tmp_path, "base", 0.5)
        target = self._make_manifest(tmp_path, "target", 0.8)
        rc = eval_extraction.main([
            "compare", "--base", str(base), "--target", str(target),
        ])
        assert rc == eval_extraction.EXIT_OK
        out = capsys.readouterr().out
        assert "Comparaison" in out
        assert "+30.00 pts" in out

    def test_compare_missing_file(
        self, tmp_path: Path,
    ) -> None:
        rc = eval_extraction.main([
            "compare", "--base", "ghost", "--target", "ghost2",
        ])
        assert rc == eval_extraction.EXIT_USAGE


class TestReportersRegistry:
    def test_registry_contains_csv_markdown(self) -> None:
        from tools.eval.reporters import REPORTERS
        assert "csv" in REPORTERS
        assert "markdown" in REPORTERS

    def test_csv_reporter_implements_protocol(self) -> None:
        from tools.eval.reporters import REPORTERS
        from tools.eval.types import EvalReporter
        inst = REPORTERS["csv"]()
        assert isinstance(inst, EvalReporter)
