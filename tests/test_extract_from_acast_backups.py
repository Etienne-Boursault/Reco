"""Tests pour `tools/extract_from_acast_backups.py`.

Couvre l'orchestration : swap temporaire de transcripts + appel subprocess à
`extract_recos.py`. Les appels subprocess sont mockés — aucune exécution réelle.
"""
from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

import common
import extract_from_acast_backups as efab


@pytest.fixture
def tmp_trans(tmp_path: Path, monkeypatch):
    """Crée un répertoire de transcripts avec backup .acast.txt pour 2 guids."""
    trans_root = tmp_path / "transcripts"
    source = "un-bon-moment"
    src_dir = trans_root / source
    src_dir.mkdir(parents=True)

    monkeypatch.setattr(common, "TRANSCRIPTS_DIR", trans_root)
    monkeypatch.setattr(efab, "TRANSCRIPTS_DIR", trans_root)

    guids = ["G1", "G2"]
    # G1 a un YT actif + un backup acast.
    (src_dir / "G1.txt").write_text("YT content G1", encoding="utf-8")
    (src_dir / "G1.acast.txt").write_text("ACAST content G1", encoding="utf-8")
    # G2 a un backup acast mais pas de YT.
    (src_dir / "G2.acast.txt").write_text("ACAST content G2", encoding="utf-8")

    guids_file = tmp_path / "guids.txt"
    guids_file.write_text("G1\nG2\nG3\n   \n", encoding="utf-8")  # G3 sans backup

    return SimpleNamespace(
        trans_dir=src_dir, source=source, guids=guids,
        guids_file=guids_file,
    )


# ===== _swap ===============================================================
def test_swap_renames(tmp_path):
    src = tmp_path / "a.txt"
    src.write_text("hello", encoding="utf-8")
    dst = tmp_path / "b.txt"
    efab._swap(src, dst)
    assert not src.exists()
    assert dst.read_text(encoding="utf-8") == "hello"


def test_swap_refuses_overwrite(tmp_path):
    src = tmp_path / "a.txt"
    src.write_text("x", encoding="utf-8")
    dst = tmp_path / "b.txt"
    dst.write_text("y", encoding="utf-8")
    with pytest.raises(FileExistsError):
        efab._swap(src, dst)


# ===== restore_initial =====================================================
def test_restore_initial_after_swap(tmp_trans):
    """État simulé en plein swap : txt=acast, yt.tmp=yt → restaure."""
    d = tmp_trans.trans_dir
    # On simule l'état post-étape-2 : pas de .acast.txt, txt contient l'acast,
    # yt.tmp.txt contient le yt.
    (d / "G1.acast.txt").unlink()
    (d / "G1.txt").write_text("ACAST content G1", encoding="utf-8")
    (d / "G1.yt.tmp.txt").write_text("YT content G1", encoding="utf-8")

    efab.restore_initial("G1", d)

    assert (d / "G1.txt").read_text(encoding="utf-8") == "YT content G1"
    assert (d / "G1.acast.txt").read_text(encoding="utf-8") == "ACAST content G1"
    assert not (d / "G1.yt.tmp.txt").exists()


def test_restore_initial_acast_exists_drops_txt(tmp_trans):
    """État anormal : à la fois .acast.txt et un txt courant + yt.tmp ; on jette le txt."""
    d = tmp_trans.trans_dir
    (d / "G1.yt.tmp.txt").write_text("YT", encoding="utf-8")
    # G1.txt et G1.acast.txt existent déjà (état pollué).
    efab.restore_initial("G1", d)
    # txt est restauré depuis yt.tmp ; le .acast.txt initial est conservé.
    assert (d / "G1.txt").read_text(encoding="utf-8") == "YT"
    assert (d / "G1.acast.txt").exists()


def test_restore_initial_noop(tmp_trans):
    """Pas de yt.tmp.txt → rien à faire."""
    d = tmp_trans.trans_dir
    before = set(p.name for p in d.iterdir())
    efab.restore_initial("G1", d)
    after = set(p.name for p in d.iterdir())
    assert before == after


# ===== run_extraction ======================================================
def test_run_extraction_success(monkeypatch, caplog):
    fake = MagicMock(return_value=SimpleNamespace(
        returncode=0,
        stdout="ligne1\nligne2\nrésumé final",
        stderr="",
    ))
    monkeypatch.setattr(efab.subprocess, "run", fake)
    efab.run_extraction("GUID", "src", "anthropic")
    fake.assert_called_once()
    cmd = fake.call_args.args[0]
    assert "--guid" in cmd and "GUID" in cmd
    assert "--provider" in cmd and "anthropic" in cmd


def test_run_extraction_failure(monkeypatch, caplog):
    fake = MagicMock(return_value=SimpleNamespace(
        returncode=1, stdout="", stderr="boom error",
    ))
    monkeypatch.setattr(efab.subprocess, "run", fake)
    # Doit logger l'erreur mais ne pas lever.
    efab.run_extraction("GUID", "src", "openai")
    assert fake.called


# ===== main() ==============================================================
def test_main_orchestrates_swap_and_subprocess(tmp_trans, monkeypatch):
    calls: list[list[str]] = []

    def fake_run(cmd, **kwargs):
        # Pendant l'extraction, vérifier que le swap a eu lieu : pour G1, le
        # transcript actif doit contenir l'acast.
        # On extrait le --guid pour identifier l'épisode courant.
        guid = cmd[cmd.index("--guid") + 1]
        txt = tmp_trans.trans_dir / f"{guid}.txt"
        assert txt.exists(), "le transcript actif doit exister durant l'extraction"
        assert txt.read_text(encoding="utf-8").startswith("ACAST")
        calls.append(list(cmd))
        return SimpleNamespace(returncode=0, stdout="ok\nfini", stderr="")

    monkeypatch.setattr(efab.subprocess, "run", fake_run)
    monkeypatch.setattr(sys, "argv", [
        "extract_from_acast_backups.py",
        "--source", tmp_trans.source,
        "--guids-file", str(tmp_trans.guids_file),
    ])

    efab.main()

    # 2 guids (G1, G2) × 2 providers (anthropic, openai) = 4 appels.
    # G3 est skippé (pas de backup) ; ligne vide ignorée.
    assert len(calls) == 4
    providers_used = sorted({c[c.index("--provider") + 1] for c in calls})
    assert providers_used == ["anthropic", "openai"]

    # État final : YT restauré, backup acast restauré, pas de .yt.tmp.txt.
    assert (tmp_trans.trans_dir / "G1.txt").read_text(encoding="utf-8") == "YT content G1"
    assert (tmp_trans.trans_dir / "G1.acast.txt").read_text(encoding="utf-8") == "ACAST content G1"
    assert not (tmp_trans.trans_dir / "G1.yt.tmp.txt").exists()

    # G2 n'avait pas de YT au départ : après cycle, .txt doit être absent et
    # .acast.txt restauré.
    assert not (tmp_trans.trans_dir / "G2.txt").exists()
    assert (tmp_trans.trans_dir / "G2.acast.txt").read_text(encoding="utf-8") == "ACAST content G2"


def test_main_handles_subprocess_failure_in_extraction(tmp_trans, monkeypatch):
    """Si subprocess échoue (returncode≠0), main() doit quand même restaurer."""
    monkeypatch.setattr(efab.subprocess, "run", lambda *a, **k: SimpleNamespace(
        returncode=2, stdout="", stderr="kaput",
    ))
    monkeypatch.setattr(sys, "argv", [
        "extract_from_acast_backups.py",
        "--source", tmp_trans.source,
        "--guids-file", str(tmp_trans.guids_file),
    ])
    efab.main()
    # État restauré malgré les échecs.
    assert (tmp_trans.trans_dir / "G1.txt").read_text(encoding="utf-8") == "YT content G1"
    assert (tmp_trans.trans_dir / "G1.acast.txt").exists()


def test_main_no_acast_backup_skipped(tmp_path, monkeypatch):
    """Tous les guids sans backup → rien à faire, pas d'appel subprocess."""
    trans_root = tmp_path / "transcripts"
    src = trans_root / "src1"
    src.mkdir(parents=True)
    monkeypatch.setattr(common, "TRANSCRIPTS_DIR", trans_root)
    monkeypatch.setattr(efab, "TRANSCRIPTS_DIR", trans_root)

    gf = tmp_path / "guids.txt"
    gf.write_text("X1\nX2\n", encoding="utf-8")

    fake = MagicMock()
    monkeypatch.setattr(efab.subprocess, "run", fake)
    monkeypatch.setattr(sys, "argv", [
        "extract_from_acast_backups.py", "--source", "src1",
        "--guids-file", str(gf),
    ])
    efab.main()
    fake.assert_not_called()


def test_main_swap_error_still_restores(tmp_trans, monkeypatch):
    """Si _swap lève (collision), finally restaure malgré l'erreur."""
    # Créer un yt.tmp.txt préexistant pour G1 -> _swap(txt -> yt.tmp) va lever.
    (tmp_trans.trans_dir / "G1.yt.tmp.txt").write_text("collision", encoding="utf-8")

    fake = MagicMock(return_value=SimpleNamespace(returncode=0, stdout="a\nb", stderr=""))
    monkeypatch.setattr(efab.subprocess, "run", fake)
    monkeypatch.setattr(sys, "argv", [
        "extract_from_acast_backups.py", "--source", tmp_trans.source,
        "--guids-file", str(tmp_trans.guids_file),
    ])
    # main() ne capture pas FileExistsError → elle remonte.
    with pytest.raises(FileExistsError):
        efab.main()
    # Le finally a tourné : on n'a pas créé d'état corrompu non récupérable.
    # G1.txt existe toujours (jamais déplacé puisque _swap a levé avant).
    assert (tmp_trans.trans_dir / "G1.txt").exists()
