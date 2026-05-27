"""Tests pour `tools/rebalance_watcher.py` (helpers + main argparse)."""
from __future__ import annotations

import json
import sys
import urllib.error
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

import rebalance_watcher as rw


# ===== transcripts_dir_for ================================================
def test_transcripts_dir_for_returns_path_under_tools_output():
    p = rw.transcripts_dir_for("src1")
    assert p.name == "src1"
    assert p.parent.name == "transcripts"


# ===== laptop_transcripts =================================================
def test_laptop_transcripts_parses_html(monkeypatch):
    html = '<a href="g1.txt">x</a><a href="g2.txt">y</a><a href="g3.json">z</a>'

    class Resp:
        def read(self):
            return html.encode("utf-8")
        def __enter__(self): return self
        def __exit__(self, *a): pass

    monkeypatch.setattr(rw.urllib.request, "urlopen", lambda *a, **kw: Resp())
    out = rw.laptop_transcripts()
    assert out == {"g1.txt", "g2.txt"}


def test_laptop_transcripts_returns_none_on_url_error(monkeypatch):
    def boom(*a, **kw):
        raise urllib.error.URLError("offline")

    monkeypatch.setattr(rw.urllib.request, "urlopen", boom)
    assert rw.laptop_transcripts() is None


# ===== pull_missing =======================================================
def test_pull_missing_skips_existing_downloads_new(monkeypatch, tmp_path):
    (tmp_path / "g1.txt").write_text("present", encoding="utf-8")

    class Resp:
        def __init__(self, body): self.body = body
        def read(self): return self.body
        def __enter__(self): return self
        def __exit__(self, *a): pass

    def fake_urlopen(url, timeout=30):
        return Resp(b"content-of-" + url.encode()[-10:])

    monkeypatch.setattr(rw.urllib.request, "urlopen", fake_urlopen)
    new = rw.pull_missing({"g1.txt", "g2.txt", "g3.txt"}, tmp_path)
    assert new == 2  # g2 et g3 nouveaux, g1 existait


def test_pull_missing_logs_warning_on_url_error(monkeypatch, tmp_path, caplog):
    def boom(*a, **kw):
        raise urllib.error.URLError("offline")
    monkeypatch.setattr(rw.urllib.request, "urlopen", boom)
    import logging
    with caplog.at_level(logging.WARNING, logger="reco"):
        new = rw.pull_missing({"g1.txt"}, tmp_path)
    assert new == 0


# ===== main_remaining_guids ===============================================
def test_main_remaining_guids_filters_done(tmp_path, monkeypatch):
    """Ne retourne que les guids non encore transcrits localement."""
    dispatch = tmp_path / "dispatch"
    dispatch.mkdir()
    (dispatch / "main_guids.txt").write_text("g1\ng2\n  \n", encoding="utf-8")
    monkeypatch.setattr(rw, "DISPATCH", dispatch)

    def fake_path(src, guid):
        p = tmp_path / f"{guid}.txt"
        return p

    monkeypatch.setattr(rw, "transcript_path_for", fake_path)
    # g1 a un transcript, g2 non.
    (tmp_path / "g1.txt").write_text("ok", encoding="utf-8")
    assert rw.main_remaining_guids("src") == ["g2"]


# ===== rebalance ==========================================================
def test_rebalance_writes_handover_and_attempts_relaunch(tmp_path, monkeypatch):
    dispatch = tmp_path / "dispatch"
    dispatch.mkdir()
    monkeypatch.setattr(rw, "DISPATCH", dispatch)
    monkeypatch.setattr(rw, "main_remaining_guids",
                        lambda s: ["a", "b", "c", "d"])
    monkeypatch.setattr(rw, "laptop_worker_running", lambda: False)
    relaunch = MagicMock(return_value=True)
    monkeypatch.setattr(rw, "relaunch_worker_on_laptop", relaunch)

    n = rw.rebalance("src")
    # 4 * 0.75 = 3 → handover des 3 derniers.
    assert n == 3
    written = (dispatch / "laptop_guids.txt").read_text(encoding="utf-8")
    assert "b\nc\nd\n" in written
    relaunch.assert_called_once()


def test_rebalance_with_no_pending_returns_zero(monkeypatch):
    monkeypatch.setattr(rw, "main_remaining_guids", lambda s: [])
    assert rw.rebalance("src") == 0


def test_rebalance_waits_if_worker_still_running(tmp_path, monkeypatch):
    dispatch = tmp_path / "dispatch"
    dispatch.mkdir()
    monkeypatch.setattr(rw, "DISPATCH", dispatch)
    monkeypatch.setattr(rw, "main_remaining_guids", lambda s: ["a", "b"])
    monkeypatch.setattr(rw, "laptop_worker_running", lambda: True)
    relaunch = MagicMock()
    monkeypatch.setattr(rw, "relaunch_worker_on_laptop", relaunch)
    n = rw.rebalance("src")
    assert n >= 1
    relaunch.assert_not_called()


# ===== laptop_worker_running / relaunch =================================
def test_laptop_worker_running_parses_yes(monkeypatch):
    monkeypatch.setattr(rw, "_ssh",
                        lambda cmd, timeout=30: SimpleNamespace(stdout="YES\n"))
    assert rw.laptop_worker_running() is True


def test_laptop_worker_running_parses_no(monkeypatch):
    monkeypatch.setattr(rw, "_ssh",
                        lambda cmd, timeout=30: SimpleNamespace(stdout="NO\n"))
    assert rw.laptop_worker_running() is False


def test_relaunch_worker_success(monkeypatch):
    monkeypatch.setattr(rw, "_ssh", lambda cmd, timeout=30: SimpleNamespace(
        stdout="OK\n", stderr="", returncode=0))
    assert rw.relaunch_worker_on_laptop() is True


def test_relaunch_worker_failure(monkeypatch):
    monkeypatch.setattr(rw, "_ssh", lambda cmd, timeout=30: SimpleNamespace(
        stdout="", stderr="ssh down", returncode=255))
    assert rw.relaunch_worker_on_laptop() is False


# ===== global_missing ====================================================
def test_global_missing_counts_yt_episodes_without_transcript(tmp_path, monkeypatch):
    ep_dir = tmp_path / "ep"
    ep_dir.mkdir()
    (ep_dir / "a.json").write_text(json.dumps(
        {"guid": "g1", "youtubeUrl": "https://yt/x"}), encoding="utf-8")
    (ep_dir / "b.json").write_text(json.dumps(
        {"guid": "g2", "youtubeUrl": "https://yt/y"}), encoding="utf-8")
    (ep_dir / "c.json").write_text(json.dumps(
        {"guid": "g3"}), encoding="utf-8")  # pas de yt → exclu

    monkeypatch.setattr(rw, "list_episode_files",
                        lambda s: sorted(ep_dir.glob("*.json")))
    # g1 transcrit, g2 non.
    transcripts = {"g1": tmp_path / "g1.txt"}
    (tmp_path / "g1.txt").write_text("ok", encoding="utf-8")

    monkeypatch.setattr(rw, "transcript_path_for",
                        lambda src, guid: transcripts.get(guid, tmp_path / "missing.txt"))
    assert rw.global_missing("src") == 1


# ===== main() ============================================================
def test_main_requires_source(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["rebalance_watcher.py"])
    with pytest.raises(SystemExit):
        rw.main()


def test_main_passes_source_to_watch_loop(monkeypatch):
    captured = {}
    monkeypatch.setattr(rw, "watch_loop",
                        lambda src: captured.setdefault("src", src))
    monkeypatch.setattr(sys, "argv",
                        ["rebalance_watcher.py", "--source", "ubm"])
    rw.main()
    assert captured["src"] == "ubm"


# ===== watch_loop (1 itération) ==========================================
def test_watch_loop_exits_when_no_missing(monkeypatch, tmp_path):
    """Si plus rien à transcrire, watch_loop renvoie sans boucler."""
    monkeypatch.setattr(rw, "transcripts_dir_for", lambda s: tmp_path)
    monkeypatch.setattr(rw, "laptop_transcripts", lambda: set())
    monkeypatch.setattr(rw, "pull_missing", lambda r, d: 0)
    monkeypatch.setattr(rw, "global_missing", lambda s: 0)
    # Ne doit pas appeler time.sleep car on sort sur missing=0.
    sleep_mock = MagicMock()
    monkeypatch.setattr(rw.time, "sleep", sleep_mock)
    rw.watch_loop("src")
    sleep_mock.assert_not_called()


def test_watch_loop_logs_new_pulls(monkeypatch, tmp_path, caplog):
    """Quand pull_missing renvoie >0, on logge le nombre de fichiers récupérés."""
    monkeypatch.setattr(rw, "transcripts_dir_for", lambda s: tmp_path)
    monkeypatch.setattr(rw, "laptop_transcripts", lambda: {"g1.txt"})
    monkeypatch.setattr(rw, "pull_missing", lambda r, d: 3)
    monkeypatch.setattr(rw, "global_missing", lambda s: 0)
    monkeypatch.setattr(rw.time, "sleep", lambda *_: None)
    import logging
    with caplog.at_level(logging.INFO, logger="reco"):
        rw.watch_loop("src")
    assert any("3 nouveau" in r.message for r in caplog.records)


def test_watch_loop_triggers_rebalance_when_threshold_reached(monkeypatch, tmp_path):
    """Si len(remote) >= PORTABLE_INITIAL → rebalance + check worker."""
    monkeypatch.setattr(rw, "transcripts_dir_for", lambda s: tmp_path)
    # Renvoie une fois le seuil dépassé puis on sort sur missing=0.
    monkeypatch.setattr(rw, "laptop_transcripts",
                        lambda: {f"g{i}.txt" for i in range(rw.PORTABLE_INITIAL)})
    monkeypatch.setattr(rw, "pull_missing", lambda r, d: 0)
    monkeypatch.setattr(rw, "global_missing", lambda s: 0)
    monkeypatch.setattr(rw.time, "sleep", lambda *_: None)
    rebalance_mock = MagicMock()
    monkeypatch.setattr(rw, "rebalance", rebalance_mock)
    monkeypatch.setattr(rw, "laptop_worker_running", lambda: True)
    rw.watch_loop("src")
    rebalance_mock.assert_called_once_with("src")


def test_watch_loop_hang_detection_relaunches_worker(monkeypatch, tmp_path):
    """Si pas de progrès depuis HANG_THRESHOLD ET missing > 0 → kill + relaunch.

    Stratégie de test : fixer un seuil HANG_THRESHOLD négatif via monkeypatch
    pour que la condition `time.time() - last_change > HANG_THRESHOLD` soit
    immédiatement vraie, indépendamment des fluctuations d'horloge induites
    par le logging.
    """
    monkeypatch.setattr(rw, "transcripts_dir_for", lambda s: tmp_path)
    monkeypatch.setattr(rw, "laptop_transcripts", lambda: {"a.txt"})
    monkeypatch.setattr(rw, "pull_missing", lambda r, d: 0)
    # iter 1 → missing=5 (continue). iter 2 → hang condition test (>0) +
    # affichage final puis sortie sur 0.
    missing_seq = iter([5, 5, 0])
    monkeypatch.setattr(rw, "global_missing", lambda s: next(missing_seq))
    monkeypatch.setattr(rw.time, "sleep", lambda *_: None)
    monkeypatch.setattr(rw, "HANG_THRESHOLD", -1)
    ssh_mock = MagicMock(return_value=SimpleNamespace(
        stdout="", stderr="", returncode=0))
    monkeypatch.setattr(rw, "_ssh", ssh_mock)
    relaunch_mock = MagicMock(return_value=True)
    monkeypatch.setattr(rw, "relaunch_worker_on_laptop", relaunch_mock)
    rw.watch_loop("src")
    relaunch_mock.assert_called()


def test_watch_loop_retries_when_laptop_unreachable(monkeypatch, tmp_path):
    """Si laptop_transcripts() = None une fois puis OK + missing=0, on sort."""
    monkeypatch.setattr(rw, "transcripts_dir_for", lambda s: tmp_path)
    calls = {"n": 0}

    def fake_laptop():
        calls["n"] += 1
        return None if calls["n"] == 1 else set()

    monkeypatch.setattr(rw, "laptop_transcripts", fake_laptop)
    monkeypatch.setattr(rw, "pull_missing", lambda r, d: 0)
    monkeypatch.setattr(rw, "global_missing", lambda s: 0)
    monkeypatch.setattr(rw.time, "sleep", lambda *_: None)
    rw.watch_loop("src")
    assert calls["n"] == 2
