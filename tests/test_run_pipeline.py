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
    extract_mod.extract_all_batch = MagicMock()
    extract_mod.extract_for_episode = MagicMock()
    # M4 : run_pipeline importe `new_run_index` pour construire l'index de run
    # partagé une seule fois. Le fake le renvoie None (extract_for_episode est
    # de toute façon mocké, l'index n'est pas consommé).
    extract_mod.new_run_index = MagicMock(return_value=None)
    monkeypatch.setitem(sys.modules, "extract_recos", extract_mod)

    # `make_anthropic_client` est importé paresseusement dans `rp.run()` —
    # patcher `common.make_anthropic_client` suffit donc à intercepter l'appel.
    import common as common_mod
    fake_client_factory = MagicMock(return_value="FAKE-CLIENT")
    monkeypatch.setattr(common_mod, "make_anthropic_client", fake_client_factory)
    # Pour les assertions des tests, on expose le mock via une clé du dict.
    extract_mod._make_client = fake_client_factory  # accès des tests, non-utilisé par rp

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
def test_run_extract_acquires_pipeline_lock(fake_modules, monkeypatch):
    """rev-pipeline M1 (revue 2026-07-19) — l'étape extract s'exécute SOUS le
    verrou pipeline (sinon un re-extract concurrent au review_server peut
    écraser une validation humaine)."""
    import contextlib

    import review_lock
    entered = {"n": 0}

    @contextlib.contextmanager
    def _spy(force=False):
        entered["n"] += 1
        yield

    monkeypatch.setattr(review_lock, "acquire_pipeline_lock", _spy)
    rp.run("src", ["extract"], None, "small", "claude", False, "fr", False, False)
    assert entered["n"] == 1
    fake_modules["extract"].extract_for_episode.assert_called()


def test_run_extract_server_lock_busy_logged(fake_modules, monkeypatch):
    """rev-pipeline M1 — si le review_server tient le verrou, l'étape extract
    est abandonnée proprement (log), sans propager ni écrire."""
    import contextlib

    import review_lock

    @contextlib.contextmanager
    def _busy(force=False):
        raise review_lock.ServerLockBusy("serveur tient le verrou")
        yield  # pragma: no cover — jamais atteint

    monkeypatch.setattr(review_lock, "acquire_pipeline_lock", _busy)
    # Ne doit PAS lever.
    rp.run("src", ["extract"], None, "small", "claude", False, "fr", False, False)
    fake_modules["extract"].extract_for_episode.assert_not_called()


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


def test_main_extract_model_default_aligns_with_extract_recos(monkeypatch, fake_modules):
    """L4 (revue 2026-07-19) — le défaut --extract-model est la SSOT
    extract_recos.MODEL (claude-haiku-4-5), pas une chaîne Sonnet dupliquée."""
    captured = {}
    monkeypatch.setattr(rp, "run", lambda **kw: captured.update(kw))
    monkeypatch.setattr(sys, "argv", ["run_pipeline.py", "--source", "demo"])
    rp.main()
    assert captured["extract_model"] == rp.DEFAULT_EXTRACT_MODEL == "claude-haiku-4-5"
