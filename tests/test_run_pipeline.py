"""Tests de l'orchestrateur run_pipeline.py.

On mocke les modules importés paresseusement (fetch_episodes, transcribe,
extract_recos) pour vérifier l'enchaînement des étapes sans toucher au réseau.
"""
from __future__ import annotations

import sys
import types
from pathlib import Path
from unittest.mock import MagicMock

import pytest

import run_pipeline as rp


# ===== _parse_steps =========================================================
def test_parse_steps_default():
    assert rp._parse_steps("fetch,transcribe,extract") == ["fetch", "transcribe", "extract"]


def test_parse_steps_reorders_canonically():
    # On les met dans le désordre : ils doivent revenir dans l'ordre canonique.
    assert rp._parse_steps("extract,fetch") == ["fetch", "extract"]


def test_parse_steps_strips_whitespace_and_case():
    assert rp._parse_steps(" FETCH ,  Extract") == ["fetch", "extract"]


def test_parse_steps_unknown_raises():
    with pytest.raises(ValueError, match="Étape\\(s\\) inconnue\\(s\\)"):
        rp._parse_steps("fetch,bidon")


def test_parse_steps_empty():
    assert rp._parse_steps("") == []


# ===== Fixtures pour run() ==================================================
@pytest.fixture
def fake_modules(monkeypatch, tmp_path):
    """Injecte des modules factices pour fetch_episodes/transcribe/extract_recos
    dans sys.modules, et patche list_episode_files dans run_pipeline."""
    # fetch_episodes
    fetch_mod = types.ModuleType("fetch_episodes")
    fetch_mod.fetch_episodes = MagicMock()
    monkeypatch.setitem(sys.modules, "fetch_episodes", fetch_mod)

    # transcribe
    transcribe_mod = types.ModuleType("transcribe")
    transcribe_mod.transcribe_episode = MagicMock()
    monkeypatch.setitem(sys.modules, "transcribe", transcribe_mod)

    # extract_recos
    extract_mod = types.ModuleType("extract_recos")
    extract_mod._make_client = MagicMock(return_value="FAKE-CLIENT")
    extract_mod.extract_all_batch = MagicMock()
    extract_mod.extract_for_episode = MagicMock()
    monkeypatch.setitem(sys.modules, "extract_recos", extract_mod)

    # Liste d'épisodes factice
    paths = [tmp_path / "a.json", tmp_path / "b.json", tmp_path / "c.json"]
    for p in paths:
        p.write_text('{"guid": "g-' + p.stem + '"}', encoding="utf-8")
    monkeypatch.setattr(rp, "list_episode_files", lambda src: paths)

    return {
        "fetch": fetch_mod,
        "transcribe": transcribe_mod,
        "extract": extract_mod,
        "paths": paths,
    }


# ===== run() ================================================================
def test_run_fetch_only(fake_modules):
    rp.run("src", ["fetch"], None, "small", "claude", False, "fr", False, False)
    fake_modules["fetch"].fetch_episodes.assert_called_once_with("src", limit=None)
    fake_modules["transcribe"].transcribe_episode.assert_not_called()
    fake_modules["extract"].extract_for_episode.assert_not_called()


def test_run_fetch_error_does_not_stop(fake_modules, caplog):
    fake_modules["fetch"].fetch_episodes.side_effect = RuntimeError("boom")
    # Ne doit PAS propager l'exception.
    rp.run("src", ["fetch"], None, "small", "claude", False, "fr", False, False)


def test_run_transcribe_iterates(fake_modules):
    rp.run("src", ["transcribe"], None, "small", "claude", False, "fr", False, False)
    assert fake_modules["transcribe"].transcribe_episode.call_count == 3
    # Premier appel : (source_id, path, model, language, force)
    first = fake_modules["transcribe"].transcribe_episode.call_args_list[0]
    assert first.args[0] == "src"
    assert first.args[2] == "small"
    assert first.args[3] == "fr"
    assert first.args[4] is False


def test_run_transcribe_continues_on_error(fake_modules):
    """Une transcription en échec ne stoppe pas le reste."""
    fake_modules["transcribe"].transcribe_episode.side_effect = [
        None, RuntimeError("crash"), None,
    ]
    rp.run("src", ["transcribe"], None, "small", "claude", False, "fr", False, False)
    assert fake_modules["transcribe"].transcribe_episode.call_count == 3


def test_run_transcribe_with_limit(fake_modules):
    rp.run("src", ["transcribe"], 2, "small", "claude", False, "fr", False, False)
    assert fake_modules["transcribe"].transcribe_episode.call_count == 2


def test_run_extract_unit_mode(fake_modules):
    rp.run("src", ["extract"], None, "small", "claude-x", False, "fr", False, False)
    fake_modules["extract"]._make_client.assert_called_once()
    assert fake_modules["extract"].extract_for_episode.call_count == 3
    fake_modules["extract"].extract_all_batch.assert_not_called()


def test_run_extract_batch_mode(fake_modules):
    rp.run("src", ["extract"], None, "small", "claude-x", True, "fr", False, False)
    fake_modules["extract"].extract_all_batch.assert_called_once()
    fake_modules["extract"].extract_for_episode.assert_not_called()


def test_run_extract_dry_run_skips_client(fake_modules):
    """En dry-run, on n'instancie pas le client Anthropic."""
    rp.run("src", ["extract"], None, "small", "claude-x", False, "fr", True, False)
    fake_modules["extract"]._make_client.assert_not_called()
    # On itère quand même les épisodes pour log/dry-run, avec client=None.
    assert fake_modules["extract"].extract_for_episode.call_count == 3
    call = fake_modules["extract"].extract_for_episode.call_args_list[0]
    assert call.args[2] is None  # client
    assert call.args[3] is True  # dry_run


def test_run_extract_batch_dry_run_ignores_batch(fake_modules):
    """batch + dry-run : on retombe sur l'itération unitaire."""
    rp.run("src", ["extract"], None, "small", "claude-x", True, "fr", True, False)
    fake_modules["extract"].extract_all_batch.assert_not_called()
    assert fake_modules["extract"].extract_for_episode.call_count == 3


def test_run_extract_client_init_failure_aborts(fake_modules):
    fake_modules["extract"]._make_client.side_effect = RuntimeError("no key")
    rp.run("src", ["extract"], None, "small", "claude-x", False, "fr", False, False)
    fake_modules["extract"].extract_for_episode.assert_not_called()
    fake_modules["extract"].extract_all_batch.assert_not_called()


def test_run_extract_per_episode_error_continues(fake_modules):
    fake_modules["extract"].extract_for_episode.side_effect = [
        None, RuntimeError("oops"), None,
    ]
    rp.run("src", ["extract"], None, "small", "claude-x", False, "fr", False, False)
    assert fake_modules["extract"].extract_for_episode.call_count == 3


def test_run_extract_batch_error_logged(fake_modules):
    fake_modules["extract"].extract_all_batch.side_effect = RuntimeError("fail")
    rp.run("src", ["extract"], None, "small", "claude-x", True, "fr", False, False)
    fake_modules["extract"].extract_all_batch.assert_called_once()


def test_run_all_steps(fake_modules):
    rp.run("src", ["fetch", "transcribe", "extract"], None, "small", "claude-x",
           False, "fr", False, False)
    fake_modules["fetch"].fetch_episodes.assert_called_once()
    assert fake_modules["transcribe"].transcribe_episode.call_count == 3
    assert fake_modules["extract"].extract_for_episode.call_count == 3


# ===== main() ===============================================================
def test_main_parses_and_runs(monkeypatch, fake_modules):
    captured = {}

    def fake_run(**kwargs):
        captured.update(kwargs)

    monkeypatch.setattr(rp, "run", fake_run)
    monkeypatch.setattr(sys, "argv", [
        "run_pipeline.py", "--source", "demo", "--limit", "5",
        "--steps", "fetch,extract", "--whisper-model", "tiny",
        "--extract-model", "claude-x", "--batch", "--language", "en",
        "--dry-run", "--force",
    ])
    rp.main()
    assert captured["source_id"] == "demo"
    assert captured["steps"] == ["fetch", "extract"]
    assert captured["limit"] == 5
    assert captured["whisper_model"] == "tiny"
    assert captured["extract_model"] == "claude-x"
    assert captured["batch"] is True
    assert captured["language"] == "en"
    assert captured["dry_run"] is True
    assert captured["force"] is True


def test_main_language_empty_becomes_none(monkeypatch, fake_modules):
    captured = {}
    monkeypatch.setattr(rp, "run", lambda **kw: captured.update(kw))
    monkeypatch.setattr(sys, "argv", [
        "run_pipeline.py", "--source", "demo", "--language", "",
    ])
    rp.main()
    assert captured["language"] is None
