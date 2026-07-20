"""Tests TDD pour la CLI `lint_dataset.py` (P0 #3, M2, L7, L8, H10, H7, P2 #15)."""
from __future__ import annotations

import datetime as _dt
import json
from pathlib import Path

import pytest

import lint_dataset
from lint import Severity


# ---------------------------------------------------------------------------
# build_context (backward-compat helper)
# ---------------------------------------------------------------------------


def _seed(tmp_path: Path, source_id: str) -> tuple[Path, Path, Path, Path]:
    recos_dir = tmp_path / "recos" / source_id
    eps_dir = tmp_path / "episodes" / source_id
    items_dir = tmp_path / "items" / source_id
    mentions_dir = tmp_path / "mentions" / source_id
    for d in (recos_dir, eps_dir, items_dir, mentions_dir):
        d.mkdir(parents=True, exist_ok=True)
    return recos_dir, eps_dir, items_dir, mentions_dir


def test_build_context_loads_recos(tmp_path):
    recos_dir, eps_dir, items_dir, mentions_dir = _seed(tmp_path, "ubm")
    (recos_dir / "0001.json").write_text(
        json.dumps({"id": "ubm-1", "title": "T", "episodeGuid": "g", "sourceId": "ubm"}),
        encoding="utf-8",
    )
    ctx = lint_dataset.build_context(
        "ubm",
        recos_base=tmp_path / "recos",
        episodes_base=tmp_path / "episodes",
        items_base=tmp_path / "items",
        mentions_base=tmp_path / "mentions",
    )
    assert len(ctx.recos) == 1
    assert ctx.recos[0]["id"] == "ubm-1"


def test_build_context_skips_corrupt_json(tmp_path):
    recos_dir, _, _, _ = _seed(tmp_path, "ubm")
    (recos_dir / "0001.json").write_text("not json", encoding="utf-8")
    (recos_dir / "0002.json").write_text(
        json.dumps({"id": "ubm-2", "title": "T"}), encoding="utf-8",
    )
    ctx = lint_dataset.build_context(
        "ubm",
        recos_base=tmp_path / "recos",
        episodes_base=tmp_path / "episodes",
        items_base=tmp_path / "items",
        mentions_base=tmp_path / "mentions",
    )
    assert len(ctx.recos) == 1


def test_build_context_handles_missing_dirs(tmp_path):
    ctx = lint_dataset.build_context(
        "ubm",
        recos_base=tmp_path / "missing",
        episodes_base=tmp_path / "missing",
        items_base=tmp_path / "missing",
        mentions_base=tmp_path / "missing",
    )
    assert ctx.recos == ()


def test_build_context_skips_non_dict_json(tmp_path):
    recos_dir, _, _, _ = _seed(tmp_path, "ubm")
    (recos_dir / "0001.json").write_text(json.dumps([1, 2]), encoding="utf-8")
    ctx = lint_dataset.build_context(
        "ubm",
        recos_base=tmp_path / "recos",
        episodes_base=tmp_path / "episodes",
        items_base=tmp_path / "items",
        mentions_base=tmp_path / "mentions",
    )
    assert ctx.recos == ()


# ---------------------------------------------------------------------------
# CLI main
# ---------------------------------------------------------------------------


@pytest.fixture
def fake_dataset(tmp_path, monkeypatch):
    """Pointe les paths globaux du CLI vers un tmp seed + isole le CWD."""
    _seed(tmp_path, "ubm")
    monkeypatch.setattr(lint_dataset, "RECOS_BASE_DIR", tmp_path / "recos")
    monkeypatch.setattr(lint_dataset, "EPISODES_BASE_DIR", tmp_path / "episodes")
    monkeypatch.setattr(lint_dataset, "ITEMS_BASE_DIR", tmp_path / "items")
    monkeypatch.setattr(lint_dataset, "MENTIONS_BASE_DIR", tmp_path / "mentions")
    # M2 : la validation path-traversal compare au CWD courant. On le
    # déplace dans tmp_path pour que les sorties tmp_path soient « safe ».
    monkeypatch.chdir(tmp_path)
    return tmp_path


def test_cli_rejects_invalid_source_id(capsys):
    rc = lint_dataset.main(["--source", "../etc/passwd"])
    assert rc == 2
    err = capsys.readouterr().err
    assert "source invalide" in err


def test_cli_writes_report_to_default_output(fake_dataset, monkeypatch, capsys):
    out_dir = fake_dataset / "audit"
    monkeypatch.setattr(lint_dataset, "DEFAULT_OUTPUT_DIR", out_dir)
    # M9 : monkeypatcher la `date` injectée plutôt que `date.today()`.
    fixed = _dt.date(2026, 6, 10)

    class _D:
        @staticmethod
        def today():
            return fixed

    monkeypatch.setattr(lint_dataset, "date", _D)
    rc = lint_dataset.main(["--source", "ubm"])
    assert rc == 0
    files = list(out_dir.glob("*.md"))
    assert len(files) == 1
    # P0 #3 : nommage `<date>__<scope>__<source>.md`.
    assert "2026-06-10__lint__ubm" in files[0].name
    assert "Dataset Lint Report" in files[0].read_text(encoding="utf-8")
    msg = capsys.readouterr().out
    assert "Lint report écrit" in msg


def test_cli_writes_report_with_custom_output(fake_dataset, tmp_path):
    out = fake_dataset / "custom.md"
    rc = lint_dataset.main(["--source", "ubm", "--output", str(out)])
    assert rc == 0
    assert out.exists()


def test_cli_exit_code_1_when_errors(fake_dataset):
    (fake_dataset / "recos" / "ubm" / "broken.json").write_text(
        json.dumps({"id": "ubm-x"}), encoding="utf-8",
    )
    out = fake_dataset / "out.md"
    rc = lint_dataset.main(["--source", "ubm", "--output", str(out)])
    assert rc == 1


def test_cli_exit_code_2_when_warnings_only(fake_dataset):
    (fake_dataset / "recos" / "ubm" / "warn.json").write_text(
        json.dumps({
            "id": "ubm-w", "episodeGuid": "g", "title": "AB", "sourceId": "ubm",
        }), encoding="utf-8",
    )
    out = fake_dataset / "out.md"
    rc = lint_dataset.main(["--source", "ubm", "--output", str(out)])
    assert rc == 2


def test_cli_severity_filter_does_not_change_exit_code(fake_dataset):
    """H9 : filter cosmétique — exit code reflète l'état réel."""
    (fake_dataset / "recos" / "ubm" / "err.json").write_text(
        json.dumps({"id": "ubm-e"}), encoding="utf-8",
    )
    (fake_dataset / "recos" / "ubm" / "warn.json").write_text(
        json.dumps({
            "id": "ubm-w", "episodeGuid": "g", "title": "AB", "sourceId": "ubm",
        }), encoding="utf-8",
    )
    out = fake_dataset / "out.md"
    rc = lint_dataset.main([
        "--source", "ubm", "--output", str(out), "--severity", "warning",
    ])
    # Le rapport contient une vraie ERROR → exit 1 même filtré sur warning.
    assert rc == 1
    md = out.read_text(encoding="utf-8")
    assert "ubm-w" in md
    assert "ubm-e" not in md


def test_cli_rule_filter(fake_dataset):
    (fake_dataset / "recos" / "ubm" / "warn.json").write_text(
        json.dumps({
            "id": "ubm-w", "episodeGuid": "g", "title": "AB", "sourceId": "ubm",
        }), encoding="utf-8",
    )
    out = fake_dataset / "out.md"
    rc = lint_dataset.main([
        "--source", "ubm", "--output", str(out),
        "--rule", "required_fields",
    ])
    # Pas d'errors → 0 ou 2 selon residual warnings unfiltered (présents).
    assert rc == 2


def test_cli_format_json_writes_jsonl(fake_dataset):
    (fake_dataset / "recos" / "ubm" / "warn.json").write_text(
        json.dumps({
            "id": "ubm-w", "episodeGuid": "g", "title": "AB", "sourceId": "ubm",
        }), encoding="utf-8",
    )
    out = fake_dataset / "out.json"
    rc = lint_dataset.main([
        "--source", "ubm", "--output", str(out), "--format", "json",
    ])
    assert rc == 2
    payloads = [
        json.loads(ln) for ln in out.read_text(encoding="utf-8").splitlines()
        if ln.strip()
    ]
    assert payloads[0]["kind"] == "meta"


def test_cli_no_overwrite_creates_suffixed_file(fake_dataset):
    out = fake_dataset / "out.md"
    out.write_text("existing", encoding="utf-8")
    rc = lint_dataset.main([
        "--source", "ubm", "--output", str(out), "--no-overwrite",
    ])
    assert rc == 0
    # Le fichier d'origine ne doit pas avoir bougé.
    assert out.read_text(encoding="utf-8") == "existing"
    # Un fichier suffixé doit apparaître à côté.
    siblings = [p for p in fake_dataset.glob("out__*.md")]
    assert siblings, "L7 : nouveau fichier horodaté attendu"


def test_cli_resolve_output_uses_today_and_scope_by_default(monkeypatch):
    fixed = _dt.date(2026, 6, 10)

    class _D:
        @staticmethod
        def today():
            return fixed

    monkeypatch.setattr(lint_dataset, "date", _D)
    path = lint_dataset._resolve_output_path(None, source_id="ubm")
    assert path.name == "2026-06-10__lint__ubm.md"


def test_cli_resolve_output_uses_arg_when_provided(tmp_path):
    custom = tmp_path / "x.md"
    assert lint_dataset._resolve_output_path(custom, source_id="ubm") is custom


def test_cli_resolve_output_json_format(monkeypatch):
    fixed = _dt.date(2026, 6, 10)

    class _D:
        @staticmethod
        def today():
            return fixed

    monkeypatch.setattr(lint_dataset, "date", _D)
    path = lint_dataset._resolve_output_path(None, source_id="ubm", fmt="json")
    assert path.suffix == ".json"
    assert "2026-06-10__lint__ubm" in path.name


def test_cli_compute_exit_code_no_issues():
    from lint.service import LintReport
    assert lint_dataset._compute_exit_code(LintReport.from_issues([])) == 0


def test_cli_validate_output_safe_rejects_traversal(tmp_path, monkeypatch):
    """M2 : path hors du CWD refusé."""
    monkeypatch.chdir(tmp_path)
    # Un fichier dans CWD est OK.
    assert lint_dataset._validate_output_safe(tmp_path / "ok.md") is True
    # Un fichier parent (hors CWD) refusé.
    assert lint_dataset._validate_output_safe(tmp_path.parent / "out.md") is False


def test_cli_path_traversal_returns_exit_2(fake_dataset, tmp_path):
    """M2 : output hors CWD → refus."""
    bad = tmp_path.parent / "evil.md"
    rc = lint_dataset.main(["--source", "ubm", "--output", str(bad)])
    assert rc == 2


def test_cli_pipeline_lock_busy_returns_4(fake_dataset, monkeypatch):
    import review_lock

    class _Busy:
        def __enter__(self):
            raise review_lock.PipelineLockBusy("busy")

        def __exit__(self, *_a):
            return False

    monkeypatch.setattr(
        review_lock, "acquire_pipeline_lock",
        lambda **kw: _Busy(),
    )
    rc = lint_dataset.main(["--source", "ubm"])
    assert rc == 4


def test_cli_loads_real_source_config_when_available(fake_dataset):
    out = fake_dataset / "out.md"
    rc = lint_dataset.main(["--source", "ubm", "--output", str(out)])
    assert out.exists()
    assert rc in (0, 1, 2)


def test_build_context_handles_get_source_failure(fake_dataset, monkeypatch):
    def _boom(source_id):
        raise RuntimeError("registry busted")

    monkeypatch.setattr(lint_dataset, "_get_source", _boom)
    ctx = lint_dataset.build_context("ubm")
    assert ctx.source_config is None


def test_cli_severity_all_values():
    parser = lint_dataset._build_parser()
    sev_action = next(a for a in parser._actions if a.dest == "severity")
    assert set(sev_action.choices) == {s.value for s in Severity}


def test_cli_format_choices_match_registry():
    from lint.reporters import REPORTERS
    parser = lint_dataset._build_parser()
    fmt_action = next(a for a in parser._actions if a.dest == "format")
    assert set(fmt_action.choices) == set(REPORTERS.keys())


# ---------------------------------------------------------------------------
# P2 #15 — --source all
# ---------------------------------------------------------------------------


def test_iter_target_sources_with_explicit_id(monkeypatch):
    """Un slug normal renvoie un tuple à 1 élément, pas d'appel registry."""
    monkeypatch.setattr(lint_dataset, "_list_sources",
                        lambda: pytest.fail("ne devrait pas être appelé"))
    assert lint_dataset._iter_target_sources("ubm") == ("ubm",)


def test_iter_target_sources_all_calls_registry(monkeypatch):
    class _S:
        def __init__(self, id):
            self.id = id

    monkeypatch.setattr(
        lint_dataset, "_list_sources",
        lambda: [_S("a"), _S("b")],
    )
    assert lint_dataset._iter_target_sources("all") == ("a", "b")


# ---------------------------------------------------------------------------
# H7 — IO issues remontés via le loader (couvre le helper sync)
# ---------------------------------------------------------------------------


def test_load_jsons_returns_only_valid_payloads(tmp_path):
    """Wrapper sync `_load_jsons` reste backward-compat (drops les IO issues)."""
    d = tmp_path / "x"
    d.mkdir()
    (d / "ok.json").write_text(json.dumps({"a": 1}), encoding="utf-8")
    (d / "bad.json").write_text("not json", encoding="utf-8")
    payloads = lint_dataset._load_jsons(d)
    assert len(payloads) == 1


def test_avoid_overwrite_returns_same_path_if_missing(tmp_path):
    """L7 : pas de collision → pas de modification du chemin."""
    p = tmp_path / "fresh.md"
    assert lint_dataset._avoid_overwrite(p) is p


def test_compute_exit_code_warnings_only():
    from lint.service import LintReport
    from lint.rules.base import LintIssue, Severity

    issues = (LintIssue(
        rule="r", severity=Severity.WARNING, entity_type="reco",
        entity_id="x", field=None, message="m",
    ),)
    assert lint_dataset._compute_exit_code(LintReport.from_issues(issues)) == 2


def test_compute_exit_code_errors_present():
    """192 : path explicite errors > 0 → exit 1."""
    from lint.service import LintReport
    from lint.rules.base import LintIssue, Severity

    issues = (LintIssue(
        rule="r", severity=Severity.ERROR, entity_type="reco",
        entity_id="x", field=None, message="m",
    ),)
    assert lint_dataset._compute_exit_code(LintReport.from_issues(issues)) == 1


def test_settings_for_source_handles_registry_exception(monkeypatch):
    """214-215 : registry KO → settings par défaut."""
    def _boom(_id):
        raise RuntimeError("nope")

    monkeypatch.setattr(lint_dataset, "_get_source", _boom)
    s = lint_dataset._settings_for_source("ghost-source")
    from lint.settings import LintSettings
    assert isinstance(s, LintSettings)


def test_main_with_empty_all_returns_zero(monkeypatch):
    """Cas limite 249 : `--source all` sans aucune source enregistrée."""
    monkeypatch.setattr(lint_dataset, "_list_sources", lambda: [])

    class _Pass:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    import review_lock
    monkeypatch.setattr(
        review_lock, "acquire_pipeline_lock", lambda **kw: _Pass(),
    )
    rc = lint_dataset.main(["--source", "all"])
    assert rc == 0


def test_main_resolves_output_default_dir_for_json(fake_dataset, monkeypatch):
    """131 : avec --format json sans --output, écrit sous DEFAULT_OUTPUT_LINT_JSON_DIR."""
    out_dir = fake_dataset / "json_out"
    monkeypatch.setattr(lint_dataset, "DEFAULT_OUTPUT_LINT_JSON_DIR", out_dir)
    fixed = _dt.date(2026, 6, 10)

    class _D:
        @staticmethod
        def today():
            return fixed

    monkeypatch.setattr(lint_dataset, "date", _D)
    rc = lint_dataset.main(["--source", "ubm", "--format", "json"])
    assert rc == 0
    # Le fichier devrait être sous out_dir/ubm/.
    expected = out_dir / "ubm" / "2026-06-10__lint__ubm.json"
    assert expected.exists()
