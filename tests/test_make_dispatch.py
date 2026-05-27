"""Tests du dispatcher main/portable (tools/make_dispatch.py).

On teste `main()` en bout-en-bout avec un EPISODES_DIR temporaire et un
TRANSCRIPTS_DIR temporaire. C'est un script « pur fichiers » sans réseau.
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import pytest


@pytest.fixture
def isolated_dirs(monkeypatch, tmp_path: Path):
    """Redirige tous les chemins du pipeline vers tmp_path/."""
    import common, make_dispatch
    eps_dir = tmp_path / "src" / "content" / "episodes"
    trans_dir = tmp_path / "tools" / "output" / "transcripts"
    dispatch_dir = tmp_path / "tools" / "dispatch"
    monkeypatch.setattr(common, "EPISODES_DIR", eps_dir)
    monkeypatch.setattr(common, "TRANSCRIPTS_DIR", trans_dir)
    monkeypatch.setattr(make_dispatch, "DISPATCH_DIR", dispatch_dir)
    return tmp_path, eps_dir, trans_dir, dispatch_dir


def _make_episode(eps_dir: Path, source: str, guid: str, **extra):
    src_dir = eps_dir / source
    src_dir.mkdir(parents=True, exist_ok=True)
    d = {"guid": guid, "title": f"Episode {guid}", **extra}
    (src_dir / f"{guid}.json").write_text(json.dumps(d), encoding="utf-8")


def test_dispatch_splits_pending_by_share(isolated_dirs):
    _, eps_dir, _, dispatch_dir = isolated_dirs
    import make_dispatch
    # 10 épisodes avec youtubeUrl, aucun déjà transcrit.
    for i in range(10):
        _make_episode(
            eps_dir, "un-bon-moment", f"g{i:02d}",
            youtubeUrl=f"https://www.youtube.com/watch?v=v{i}",
            date=f"2024-01-{i+1:02d}",
        )
    make_dispatch.make_dispatch("un-bon-moment")

    main_guids = (dispatch_dir / "main_guids.txt").read_text(encoding="utf-8").splitlines()
    laptop_guids = (dispatch_dir / "laptop_guids.txt").read_text(encoding="utf-8").splitlines()
    # LAPTOP_SHARE = 0.64 → portable: 6, main: 4.
    main_guids = [g for g in main_guids if g]
    laptop_guids = [g for g in laptop_guids if g]
    assert len(main_guids) == 4
    assert len(laptop_guids) == 6
    # Pas de doublons entre les deux.
    assert set(main_guids).isdisjoint(set(laptop_guids))


def test_dispatch_excludes_already_transcribed(isolated_dirs):
    """Un épisode dont le transcript existe déjà est ignoré du dispatch."""
    _, eps_dir, trans_dir, dispatch_dir = isolated_dirs
    import make_dispatch
    _make_episode(eps_dir, "un-bon-moment", "g01",
                  youtubeUrl="https://www.youtube.com/watch?v=v1")
    _make_episode(eps_dir, "un-bon-moment", "g02",
                  youtubeUrl="https://www.youtube.com/watch?v=v2")
    # Le 1er est déjà transcrit.
    src_trans = trans_dir / "un-bon-moment"
    src_trans.mkdir(parents=True, exist_ok=True)
    (src_trans / "g01.txt").write_text("hello", encoding="utf-8")

    make_dispatch.make_dispatch("un-bon-moment")

    eps_map = json.loads((dispatch_dir / "episodes.json").read_text(encoding="utf-8"))
    assert "g01" not in eps_map
    assert "g02" in eps_map


def test_dispatch_excludes_episodes_without_youtube(isolated_dirs):
    """Un épisode sans youtubeUrl est ignoré (le portable ne sait pas le transcrire)."""
    _, eps_dir, _, dispatch_dir = isolated_dirs
    import make_dispatch
    _make_episode(eps_dir, "un-bon-moment", "g01", audioUrl="https://acast")  # pas de yt
    _make_episode(eps_dir, "un-bon-moment", "g02",
                  youtubeUrl="https://www.youtube.com/watch?v=v2")
    make_dispatch.make_dispatch("un-bon-moment")
    eps_map = json.loads((dispatch_dir / "episodes.json").read_text(encoding="utf-8"))
    assert "g01" not in eps_map
    assert "g02" in eps_map


def test_main_requires_source(monkeypatch):
    """main() exige --source : sans, SystemExit (argparse)."""
    import make_dispatch
    monkeypatch.setattr(sys, "argv", ["make_dispatch.py"])
    with pytest.raises(SystemExit):
        make_dispatch.main()


def test_main_dispatches_for_argparse_source(isolated_dirs, monkeypatch):
    """main() avec --source bidule appelle make_dispatch sur cette source."""
    _, eps_dir, _, dispatch_dir = isolated_dirs
    import make_dispatch
    _make_episode(eps_dir, "podcast-x", "g1",
                  youtubeUrl="https://www.youtube.com/watch?v=v1")
    monkeypatch.setattr(sys, "argv", ["make_dispatch.py", "--source", "podcast-x"])
    make_dispatch.main()
    eps_map = json.loads((dispatch_dir / "episodes.json").read_text(encoding="utf-8"))
    assert "g1" in eps_map


def test_laptop_share_derived_from_speeds():
    """LAPTOP_SHARE est calculée depuis les constantes, pas codée en dur."""
    import make_dispatch
    inv_main = 1.0 / make_dispatch.MAIN_SPEED_MIN_PER_EP
    inv_laptop = 1.0 / make_dispatch.LAPTOP_SPEED_MIN_PER_EP
    expected = inv_laptop / (inv_main + inv_laptop)
    assert math.isclose(make_dispatch.LAPTOP_SHARE, expected)


def test_dispatch_files_use_lf_endings(isolated_dirs):
    """Les fichiers .txt doivent utiliser des sauts LF (sinon CR parasite côté
    portable Linux quand bash lit la liste — bug historique du projet)."""
    _, eps_dir, _, dispatch_dir = isolated_dirs
    import make_dispatch
    for i in range(3):
        _make_episode(eps_dir, "un-bon-moment", f"g{i:02d}",
                      youtubeUrl=f"https://www.youtube.com/watch?v=v{i}")
    make_dispatch.make_dispatch("un-bon-moment")
    raw = (dispatch_dir / "main_guids.txt").read_bytes()
    assert b"\r\n" not in raw, "le fichier dispatch doit être en LF pour le bash portable"
