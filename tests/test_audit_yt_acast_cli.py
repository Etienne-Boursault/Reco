"""Tests CLI : tools/audit_yt_acast.py (couche thin argparse)."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

import audit_yt_acast
import common


def _make_ep(d: Path, guid: str, audio: int, yt: int, title: str = "x",
             ytt: str = "y") -> Path:
    p = d / f"{guid}.json"
    p.write_text(json.dumps({
        "guid": guid,
        "sourceId": "demo-source",
        "title": title,
        "youtubeTitle": ytt,
        "audioDuration": audio,
        "youtubeDuration": yt,
    }, ensure_ascii=False), encoding="utf-8")
    return p


@pytest.fixture
def _epdir(tmp_path, monkeypatch):
    base = tmp_path / "src" / "content" / "episodes"
    base.mkdir(parents=True)
    monkeypatch.setattr(common, "EPISODES_DIR", base)
    monkeypatch.setattr(
        audit_yt_acast,
        "_settings_from_args",
        lambda args: audit_yt_acast._settings_from_args(args),
    )
    # Isole le sidecar dir
    monkeypatch.setattr(
        common, "OUTPUT_DIR", tmp_path / "tools_output",
    )
    (tmp_path / "tools_output").mkdir(exist_ok=True)
    # Réimporte le module sidecar pour qu'il prenne en compte OUTPUT_DIR
    from importlib import reload
    from tools.match_audit import sidecar as sc_mod
    reload(sc_mod)
    yield base / "demo-source"
    reload(sc_mod)  # restaure pour les autres tests


def test_cli_default_is_check_mode(tmp_path, monkeypatch, capsys):
    base = tmp_path / "src" / "content" / "episodes"
    epdir = base / "demo-source"
    epdir.mkdir(parents=True)
    p = _make_ep(epdir, "g1", 3600, 5400)
    monkeypatch.setattr(common, "EPISODES_DIR", base)
    rc = audit_yt_acast.main(["--source", "demo-source"])
    assert rc == 0
    assert "matchSuspect" not in json.loads(p.read_text(encoding="utf-8"))


def test_cli_apply_writes_flag(tmp_path, monkeypatch):
    base = tmp_path / "src" / "content" / "episodes"
    epdir = base / "demo-source"
    epdir.mkdir(parents=True)
    p = _make_ep(epdir, "g1", 3600, 5400)
    _make_ep(epdir, "g2", 3600, 3700, "abc", "abc x")
    monkeypatch.setattr(common, "EPISODES_DIR", base)
    monkeypatch.setattr(common, "OUTPUT_DIR", tmp_path / "out")
    rc = audit_yt_acast.main(["--source", "demo-source", "--apply"])
    assert rc == 0
    assert json.loads(p.read_text(encoding="utf-8"))["matchSuspect"] is True


def test_cli_format_json(tmp_path, monkeypatch, capsys):
    base = tmp_path / "src" / "content" / "episodes"
    epdir = base / "demo-source"
    epdir.mkdir(parents=True)
    _make_ep(epdir, "g1", 3600, 5400)
    monkeypatch.setattr(common, "EPISODES_DIR", base)
    rc = audit_yt_acast.main(["--source", "demo-source", "--format", "json"])
    assert rc == 0
    report = json.loads(capsys.readouterr().out)
    assert report["source_id"] == "demo-source"
    assert report["suspect_count"] == 1


def test_cli_format_markdown(tmp_path, monkeypatch, capsys):
    base = tmp_path / "src" / "content" / "episodes"
    epdir = base / "demo-source"
    epdir.mkdir(parents=True)
    _make_ep(epdir, "g1", 3600, 5400)
    monkeypatch.setattr(common, "EPISODES_DIR", base)
    rc = audit_yt_acast.main(["--source", "demo-source", "--format", "markdown"])
    assert rc == 0
    out = capsys.readouterr().out
    assert out.startswith("# Audit match")
    assert "g1" in out


def test_cli_format_human(tmp_path, monkeypatch, capsys):
    base = tmp_path / "src" / "content" / "episodes"
    epdir = base / "demo-source"
    epdir.mkdir(parents=True)
    _make_ep(epdir, "g1", 3600, 5400)
    monkeypatch.setattr(common, "EPISODES_DIR", base)
    rc = audit_yt_acast.main(["--source", "demo-source", "--format", "human"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "suspects=" in out


def test_cli_fail_on_suspect_exit_1(tmp_path, monkeypatch):
    base = tmp_path / "src" / "content" / "episodes"
    epdir = base / "demo-source"
    epdir.mkdir(parents=True)
    _make_ep(epdir, "g1", 3600, 5400)
    monkeypatch.setattr(common, "EPISODES_DIR", base)
    rc = audit_yt_acast.main([
        "--source", "demo-source", "--fail-on-suspect", "--format", "human",
    ])
    assert rc == 1


def test_cli_duration_tolerance_loose_no_suspect(tmp_path, monkeypatch):
    """CR senior H1 — seuil injectable."""
    base = tmp_path / "src" / "content" / "episodes"
    epdir = base / "demo-source"
    epdir.mkdir(parents=True)
    _make_ep(epdir, "g1", 3600, 5400)  # 50% — flag par défaut
    monkeypatch.setattr(common, "EPISODES_DIR", base)
    rc = audit_yt_acast.main([
        "--source", "demo-source", "--duration-tolerance", "0.9",
        "--fail-on-suspect",
    ])
    assert rc == 0  # le seuil 0.9 désactive le flag


def test_cli_apply_clears_flag_when_no_longer_suspect(tmp_path, monkeypatch):
    base = tmp_path / "src" / "content" / "episodes"
    epdir = base / "demo-source"
    epdir.mkdir(parents=True)
    p = _make_ep(epdir, "g1", 3600, 3700, "abc def", "abc def yt")
    data = json.loads(p.read_text(encoding="utf-8"))
    data["matchSuspect"] = True
    p.write_text(json.dumps(data), encoding="utf-8")
    monkeypatch.setattr(common, "EPISODES_DIR", base)
    monkeypatch.setattr(common, "OUTPUT_DIR", tmp_path / "out")
    rc = audit_yt_acast.main(["--source", "demo-source", "--apply"])
    assert rc == 0
    assert "matchSuspect" not in json.loads(p.read_text(encoding="utf-8"))


def test_cli_undo_last_after_apply(tmp_path, monkeypatch):
    """CR archi #6 — undo-last annule la dernière session apply."""
    base = tmp_path / "src" / "content" / "episodes"
    epdir = base / "demo-source"
    epdir.mkdir(parents=True)
    p = _make_ep(epdir, "g1", 3600, 5400)
    monkeypatch.setattr(common, "EPISODES_DIR", base)
    monkeypatch.setattr(common, "OUTPUT_DIR", tmp_path / "out")
    # Reload sidecar pour prendre OUTPUT_DIR
    from importlib import reload
    from tools.match_audit import sidecar as sc_mod
    reload(sc_mod)
    from tools.match_audit import cli_runner as cli_mod
    reload(cli_mod)
    import audit_yt_acast as cli_main_mod
    reload(cli_main_mod)

    assert cli_main_mod.main(["--source", "demo-source", "--apply"]) == 0
    assert json.loads(p.read_text(encoding="utf-8"))["matchSuspect"] is True
    assert cli_main_mod.main(["--source", "demo-source", "--undo-last"]) == 0
    assert "matchSuspect" not in json.loads(p.read_text(encoding="utf-8"))

    # Restaure pour les tests suivants
    reload(sc_mod)
    reload(cli_mod)
    reload(cli_main_mod)


def test_cli_missing_source_dir_handled(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(common, "EPISODES_DIR", tmp_path / "missing")
    rc = audit_yt_acast.main(["--source", "nope", "--format", "json"])
    assert rc == 0
    report = json.loads(capsys.readouterr().out)
    assert report["total"] == 0


def test_cli_corrupt_json_skipped(tmp_path, monkeypatch):
    base = tmp_path / "src" / "content" / "episodes"
    epdir = base / "demo-source"
    epdir.mkdir(parents=True)
    (epdir / "bad.json").write_text("not json", encoding="utf-8")
    _make_ep(epdir, "g1", 3600, 3700, "x", "x")
    monkeypatch.setattr(common, "EPISODES_DIR", base)
    rc = audit_yt_acast.main(["--source", "demo-source"])
    assert rc == 0


def test_cli_acquires_pipeline_lock(tmp_path, monkeypatch):
    base = tmp_path / "src" / "content" / "episodes"
    epdir = base / "demo-source"
    epdir.mkdir(parents=True)
    _make_ep(epdir, "g1", 3600, 3700, "x", "x")
    monkeypatch.setattr(common, "EPISODES_DIR", base)
    with patch.object(audit_yt_acast, "acquire_pipeline_lock") as lock:
        rc = audit_yt_acast.main(["--source", "demo-source"])
        assert rc == 0
        lock.assert_called_once()


def test_cli_log_format_json_emits_events(tmp_path, monkeypatch, capsys):
    """CR senior H6 — --log-format json émet du JSONL sur stderr."""
    base = tmp_path / "src" / "content" / "episodes"
    epdir = base / "demo-source"
    epdir.mkdir(parents=True)
    _make_ep(epdir, "g1", 3600, 5400)
    monkeypatch.setattr(common, "EPISODES_DIR", base)
    rc = audit_yt_acast.main([
        "--source", "demo-source", "--log-format", "json",
    ])
    assert rc == 0
    err_lines = [
        ln for ln in capsys.readouterr().err.splitlines()
        if ln.strip().startswith("{")
    ]
    parsed = [json.loads(ln) for ln in err_lines]
    assert any(e.get("event") == "match_audit.finding" for e in parsed)


def test_settings_from_args_reads_source_config_extra(tmp_path, monkeypatch):
    """Vérifie que _settings_from_args lit bien SourceConfig.extra."""
    from tools.config.registry import _default_registry
    from tools.config.schema import SourceConfig
    cfg = SourceConfig(
        id="demo-source", title="Demo", reco_prefix="ds", hosts=("h",),
        extra={"match_audit": {"duration_tolerance": 0.42}},
    )
    monkeypatch.setattr(_default_registry, "_cache", {"demo-source": cfg})
    args = audit_yt_acast._build_parser().parse_args(["--source", "demo-source"])
    s = audit_yt_acast._settings_from_args(args)
    assert s.duration_tolerance == 0.42


def test_settings_from_args_overrides_win(tmp_path, monkeypatch):
    """CLI overrides priment sur la config."""
    args = audit_yt_acast._build_parser().parse_args([
        "--source", "demo-source",
        "--duration-tolerance", "0.99",
        "--intro-threshold", "0.5",
        "--intro-chars", "200",
        "--title-threshold", "0.1",
    ])
    s = audit_yt_acast._settings_from_args(args)
    assert s.duration_tolerance == 0.99
    assert s.intro_threshold == 0.5
    assert s.intro_chars == 200
    assert s.title_threshold == 0.1


def test_settings_from_args_config_unreadable_fallback_to_defaults(monkeypatch):
    """Si get_source lève, on retombe sur les défauts (sans crasher)."""
    def boom(*a, **kw):
        raise RuntimeError("nope")
    monkeypatch.setattr("tools.config.registry.get_source", boom)
    args = audit_yt_acast._build_parser().parse_args(["--source", "x"])
    s = audit_yt_acast._settings_from_args(args)
    assert s.duration_tolerance == 0.05


def test_cli_mutually_exclusive_apply_undo(tmp_path, monkeypatch):
    base = tmp_path / "src" / "content" / "episodes"
    epdir = base / "demo-source"
    epdir.mkdir(parents=True)
    monkeypatch.setattr(common, "EPISODES_DIR", base)
    with pytest.raises(SystemExit):
        audit_yt_acast.main(["--source", "demo-source", "--apply", "--undo-last"])
