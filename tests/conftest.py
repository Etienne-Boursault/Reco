"""Configuration partagée des tests. Le pyproject.toml ajoute `tools/` au
pythonpath, donc on peut importer `common`, `match_youtube`, etc. directement."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest


@pytest.fixture
def tmp_episode_json(tmp_path: Path):
    """Factory qui crée un fichier JSON d'épisode à `tmp_path / file`."""

    def _make(name: str, data: dict[str, Any]) -> Path:
        p = tmp_path / name
        p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        return p

    return _make
