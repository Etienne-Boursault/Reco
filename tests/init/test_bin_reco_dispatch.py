"""Smoke tests pour ``bin/reco`` (thin Node wrapper).

Requiert ``node`` dans le PATH ; sinon skip.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
BIN = ROOT / "bin" / "reco"


def _have_node() -> bool:
    return shutil.which("node") is not None


@pytest.mark.skipif(not _have_node(), reason="node introuvable dans le PATH")
def test_bin_reco_help_lists_commands() -> None:
    res = subprocess.run(
        ["node", str(BIN), "--help"],
        capture_output=True, text=True, timeout=10,
    )
    # --help → exit 0 ; affichage sur stderr (cf. printHelp()).
    assert res.returncode == 0
    combined = (res.stdout + res.stderr).lower()
    for cmd in ("init", "build", "audit", "lint", "enrich", "embed", "reports"):
        assert cmd in combined, f"commande {cmd} absente du --help"


@pytest.mark.skipif(not _have_node(), reason="node introuvable dans le PATH")
def test_bin_reco_unknown_command_exits_2() -> None:
    res = subprocess.run(
        ["node", str(BIN), "nope-not-a-command"],
        capture_output=True, text=True, timeout=10,
    )
    assert res.returncode == 2
    assert "unknown command" in res.stderr.lower()


@pytest.mark.skipif(not _have_node(), reason="node introuvable dans le PATH")
def test_bin_reco_no_args_exits_2() -> None:
    res = subprocess.run(
        ["node", str(BIN)],
        capture_output=True, text=True, timeout=10,
    )
    assert res.returncode == 2
