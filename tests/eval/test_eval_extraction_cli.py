"""Tests du CLI ``tools/eval_extraction.py``."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools import eval_extraction


FIXTURES = Path(__file__).parent / "golden_set"


@pytest.fixture
def extracted_dict_file(tmp_path: Path) -> Path:
    """Format dict : { episode_guid: [recos] }."""
    data = {
        "ep001": [
            {"title": "Drive", "creator": "Nicolas Winding Refn", "timestamp": "00:12:00"},
            {"title": "Inception", "creator": "Christopher Nolan", "timestamp": "00:25:30"},
            {"title": "Le Bureau des Légendes", "creator": "Éric Rochant", "timestamp": "00:42:10"},
            {"title": "1984", "creator": "George Orwell"},
            {"title": "Discovery", "creator": "Daft Punk"},
        ],
    }
    p = tmp_path / "extracted.json"
    p.write_text(json.dumps(data), encoding="utf-8")
    return p


@pytest.fixture
def extracted_list_file(tmp_path: Path) -> Path:
    """Format plat : liste de recos."""
    data = [{"title": "Drive", "creator": "Refn"}]
    p = tmp_path / "extracted_flat.json"
    p.write_text(json.dumps(data), encoding="utf-8")
    return p


class TestBuildParser:
    def test_missing_args_exits_with_usage(self) -> None:
        """Sans --golden-set ni --extracted, main() retourne EXIT_USAGE (1)."""
        rc = eval_extraction.main([])
        assert rc == eval_extraction.EXIT_USAGE

    def test_defaults(self) -> None:
        parser = eval_extraction.build_parser()
        args = parser.parse_args([
            "--golden-set", "gs", "--extracted", "ex",
        ])
        # `--format` est le canonique, `--report` est alias deprecated.
        assert args.fmt is None  # défaut résolu à csv dans main()
        assert args.fuzzy_threshold == 0.85
        assert args.output is None
        assert args.episode_guid is None
        assert args.source is None
        assert args.strict_guid is False
        assert args.verbose is False
        assert args.save_manifest is False


class TestLoadExtracted:
    def test_load_list(self, extracted_list_file: Path) -> None:
        recos = eval_extraction._load_extracted(extracted_list_file, None)
        assert recos == [{"title": "Drive", "creator": "Refn"}]

    def test_load_dict_with_guid(self, extracted_dict_file: Path) -> None:
        recos = eval_extraction._load_extracted(extracted_dict_file, "ep001")
        assert len(recos) == 5

    def test_load_dict_missing_guid_returns_empty(
        self, extracted_dict_file: Path,
    ) -> None:
        assert eval_extraction._load_extracted(extracted_dict_file, "ghost") == []

    def test_load_dict_no_guid_flattens(self, extracted_dict_file: Path) -> None:
        recos = eval_extraction._load_extracted(extracted_dict_file, None)
        assert len(recos) == 5

    def test_load_dict_skips_non_list_values(self, tmp_path: Path) -> None:
        p = tmp_path / "x.json"
        p.write_text(json.dumps({"a": [{"title": "X"}], "b": "ignored"}), encoding="utf-8")
        recos = eval_extraction._load_extracted(p, None)
        assert recos == [{"title": "X"}]

    def test_load_invalid_format(self, tmp_path: Path) -> None:
        p = tmp_path / "x.json"
        p.write_text(json.dumps("a string"), encoding="utf-8")
        with pytest.raises(ValueError):
            eval_extraction._load_extracted(p, None)


class TestMain:
    def test_main_csv_to_stdout(
        self, extracted_dict_file: Path, capsys: pytest.CaptureFixture[str],
    ) -> None:
        rc = eval_extraction.main([
            "--golden-set", str(FIXTURES),
            "--extracted", str(extracted_dict_file),
            "--episode-guid", "ep001",
            "--report", "csv",
        ])
        assert rc == 0
        captured = capsys.readouterr().out
        assert "precision" in captured
        assert "Drive" in captured

    def test_main_csv_to_file(
        self, extracted_dict_file: Path, tmp_path: Path,
    ) -> None:
        out = tmp_path / "report.csv"
        rc = eval_extraction.main([
            "--golden-set", str(FIXTURES),
            "--extracted", str(extracted_dict_file),
            "--episode-guid", "ep001",
            "--report", "csv",
            "--output", str(out),
        ])
        assert rc == 0
        assert out.exists()
        assert "Drive" in out.read_text(encoding="utf-8")

    def test_main_markdown_to_stdout(
        self, extracted_dict_file: Path, capsys: pytest.CaptureFixture[str],
    ) -> None:
        rc = eval_extraction.main([
            "--golden-set", str(FIXTURES),
            "--extracted", str(extracted_dict_file),
            "--episode-guid", "ep001",
            "--report", "markdown",
        ])
        assert rc == 0
        out = capsys.readouterr().out
        assert "# Eval report" in out

    def test_main_markdown_to_file(
        self, extracted_dict_file: Path, tmp_path: Path,
    ) -> None:
        out = tmp_path / "report.md"
        rc = eval_extraction.main([
            "--golden-set", str(FIXTURES),
            "--extracted", str(extracted_dict_file),
            "--episode-guid", "ep001",
            "--report", "markdown",
            "--output", str(out),
        ])
        assert rc == 0
        assert "Precision" in out.read_text(encoding="utf-8")

    def test_main_perfect_score(
        self, extracted_dict_file: Path, capsys: pytest.CaptureFixture[str],
    ) -> None:
        rc = eval_extraction.main([
            "--golden-set", str(FIXTURES),
            "--extracted", str(extracted_dict_file),
            "--episode-guid", "ep001",
            "--report", "csv",
        ])
        assert rc == 0
        out = capsys.readouterr().out
        # 5 attendus, 5 extraits, tous matchés → precision=recall=f1=1.0
        assert "1.0" in out


class TestPublicApi:
    def test_imports(self) -> None:
        from tools import eval as eval_pkg
        assert eval_pkg.EvalHarness is not None
        assert eval_pkg.EvalResult is not None
        assert eval_pkg.MatchVerdict is not None
        assert eval_pkg.fuzzy_match_score is not None
        assert eval_pkg.normalize_text is not None
        assert eval_pkg.load_golden_set is not None
