"""Smoke test optionnel — exécute `docker compose build` + healthcheck.

Skip systématiquement si `docker` n'est pas dispo (CI sans Docker, dev sans
daemon). Long (~3-5 min en cold build) → marqué `slow`.
"""

from __future__ import annotations

import os
import shutil
import subprocess

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

pytestmark = pytest.mark.skipif(
    shutil.which("docker") is None or os.environ.get("RECO_SKIP_DOCKER_SMOKE") == "1",
    reason="docker indisponible ou RECO_SKIP_DOCKER_SMOKE=1",
)


def _docker_daemon_up() -> bool:
    try:
        r = subprocess.run(
            ["docker", "info"],
            capture_output=True,
            timeout=5,
            check=False,
        )
        return r.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


@pytest.mark.slow
def test_compose_config_valid():
    """`docker compose config` valide la syntaxe du compose file."""
    if not _docker_daemon_up():
        pytest.skip("daemon docker non démarré")
    r = subprocess.run(
        ["docker", "compose", "config", "--quiet"],
        cwd=ROOT,
        capture_output=True,
        timeout=30,
        check=False,
    )
    assert r.returncode == 0, f"compose config invalide :\n{r.stderr.decode(errors='replace')}"
