"""C1 (revue 2026-07-19) — les scripts CLI doivent s'exécuter en STANDALONE
(`python tools/x.py`, sans PYTHONPATH) comme documenté.

pytest met la racine du repo sur `sys.path` (via `pythonpath = ["tools","tests"]`
+ le cwd de `python -m pytest`), ce qui masquait totalement les imports cassés
(`from tools.config…` mélangés à `from common…`). Ce test relance chaque script
dans un subprocess à l'ENVIRONNEMENT NEUTRE (PYTHONPATH retiré) pour reproduire
l'exécution réelle et rattraper la régression à la source.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
TOOLS = REPO_ROOT / "tools"

# Scripts CLI à interface argparse (`--help` sort en 0 sans effet de bord).
CLI_SCRIPTS = [
    "match_youtube.py",
    "extract_recos.py",
    "run_pipeline.py",
    "fetch_episodes.py",
    "transcribe.py",
]

# Symptômes exacts de la régression C1 (imports internes cassés) — à distinguer
# d'une dépendance tierce manquante (problème d'environnement, hors sujet).
_C1_SYMPTOMS = (
    "No module named 'tools'",
    "No module named 'common'",
    "No module named 'config'",
)


@pytest.mark.parametrize("script", CLI_SCRIPTS)
def test_cli_script_runs_standalone(script: str) -> None:
    path = TOOLS / script
    if not path.exists():
        pytest.skip(f"{script} absent")
    # Environnement neutre : on retire PYTHONPATH pour reproduire `python
    # tools/x.py` lancé « à la main » (seul le dossier du script sur sys.path).
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    proc = subprocess.run(
        [sys.executable, str(path), "--help"],
        capture_output=True, text=True, timeout=90,
        cwd=str(REPO_ROOT), env=env,
    )
    combined = proc.stdout + proc.stderr
    for symptom in _C1_SYMPTOMS:
        assert symptom not in combined, f"{script} : régression C1 → {combined[-800:]}"
    assert proc.returncode == 0, f"{script} : rc={proc.returncode}\n{combined[-800:]}"
