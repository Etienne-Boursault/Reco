"""Tests : tools.match_audit.flag_writer."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.match_audit.flag_writer import (
    CommonEpisodeRepo,
    clear_match_suspect_flag,
    set_match_suspect_flag,
)


def _write(p: Path, data: dict) -> None:
    """Écrit un JSON SANS sort_keys pour pouvoir tester l'ordre des clés."""
    p.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def test_flag_set_true_writes(tmp_path):
    p = tmp_path / "ep.json"
    _write(p, {"guid": "g", "title": "t"})
    changed = set_match_suspect_flag(p, True)
    assert changed is True
    assert json.loads(p.read_text(encoding="utf-8"))["matchSuspect"] is True


def test_flag_set_true_idempotent(tmp_path):
    p = tmp_path / "ep.json"
    _write(p, {"guid": "g", "matchSuspect": True})
    changed = set_match_suspect_flag(p, True)
    assert changed is False


def test_flag_set_false_removes_field(tmp_path):
    p = tmp_path / "ep.json"
    _write(p, {"guid": "g", "matchSuspect": True})
    changed = set_match_suspect_flag(p, False)
    assert changed is True
    data = json.loads(p.read_text(encoding="utf-8"))
    assert "matchSuspect" not in data


def test_flag_set_false_when_absent_is_noop(tmp_path):
    p = tmp_path / "ep.json"
    _write(p, {"guid": "g"})
    changed = set_match_suspect_flag(p, False)
    assert changed is False


def test_clear_helper_equivalent_to_set_false(tmp_path):
    p = tmp_path / "ep.json"
    _write(p, {"guid": "g", "matchSuspect": True})
    assert clear_match_suspect_flag(p) is True
    assert "matchSuspect" not in json.loads(p.read_text(encoding="utf-8"))


def test_idempotence_preserves_key_order(tmp_path):
    """CR senior C5 — pas de sort_keys, l'ordre est préservé. Un fichier
    avec un ordre 'inhabituel' (zzz avant aaa) NE doit PAS être réécrit
    par un set_match_suspect_flag(False) idempotent sur un fichier sans
    matchSuspect.
    """
    p = tmp_path / "ep.json"
    # Ordre volontairement inversé.
    raw = '{\n  "zzz": 1,\n  "aaa": 2\n}'
    p.write_text(raw, encoding="utf-8")
    mtime_before = p.stat().st_mtime_ns
    changed = set_match_suspect_flag(p, False)  # noop
    assert changed is False
    assert p.read_text(encoding="utf-8") == raw
    assert p.stat().st_mtime_ns == mtime_before


def test_set_true_idempotent_does_not_rewrite(tmp_path):
    """Set true sur un fichier qui contient déjà matchSuspect=true et un
    ordre de clés non-trié NE doit PAS réécrire (idempotence).
    """
    p = tmp_path / "ep.json"
    raw = (
        '{\n'
        '  "zzz": 1,\n'
        '  "matchSuspect": true,\n'
        '  "aaa": 2\n'
        '}'
    )
    p.write_text(raw, encoding="utf-8")
    mtime_before = p.stat().st_mtime_ns
    assert set_match_suspect_flag(p, True) is False
    assert p.stat().st_mtime_ns == mtime_before


def test_custom_repo_dip(tmp_path):
    """CR senior H2 — on peut injecter un EpisodeRepo custom."""
    calls = {"load": 0, "save": 0}

    class FakeRepo:
        def __init__(self):
            self.store: dict = {"guid": "g"}

        def load(self, path: Path):
            calls["load"] += 1
            return dict(self.store)

        def save_if_changed(self, path: Path, data):
            calls["save"] += 1
            self.store = dict(data)
            return True

    repo = FakeRepo()
    set_match_suspect_flag(tmp_path / "fake.json", True, repo=repo)  # type: ignore[arg-type]
    assert calls["load"] == 1
    assert calls["save"] == 1
    assert repo.store["matchSuspect"] is True


def test_unreadable_file_propagates(tmp_path):
    """Un fichier inexistant lève une exception explicite côté repo
    (on ne masque pas l'erreur — CR senior H9)."""
    with pytest.raises(FileNotFoundError):
        set_match_suspect_flag(tmp_path / "missing.json", True)


def test_common_episode_repo_basic_round_trip(tmp_path):
    """Couvre directement CommonEpisodeRepo (DIP)."""
    p = tmp_path / "ep.json"
    _write(p, {"guid": "g"})
    repo = CommonEpisodeRepo()
    data = repo.load(p)
    data["x"] = 1
    assert repo.save_if_changed(p, data) is True
    assert repo.save_if_changed(p, data) is False
