"""Smoke test E2E : ``python -m tools.reco_init --ci ...`` via subprocess."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_cli_module_writes_file(tmp_path: Path) -> None:
    res = subprocess.run(
        [
            sys.executable, "-m", "tools.reco_init",
            "--ci",
            "--slug=smoke",
            "--name=Smoke Test",
            "--rss-url=https://example.com/rss",
            f"--output-dir={tmp_path}",
        ],
        cwd=ROOT,
        capture_output=True, text=True, timeout=20,
    )
    assert res.returncode == 0, (res.stdout, res.stderr)
    path = tmp_path / "smoke.json"
    assert path.exists()
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["id"] == "smoke"
    assert data["title"] == "Smoke Test"


def test_cli_module_version_flag() -> None:
    res = subprocess.run(
        [sys.executable, "-m", "tools.reco_init", "--version"],
        cwd=ROOT,
        capture_output=True, text=True, timeout=10,
    )
    assert res.returncode == 0
    assert "reco init" in (res.stdout + res.stderr).lower()
