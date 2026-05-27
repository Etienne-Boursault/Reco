"""Configuration partagée des tests. Le pyproject.toml ajoute `tools/` au
pythonpath, donc on peut importer `common`, `match_youtube`, etc. directement."""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pytest


@pytest.fixture
def anthropic_client_returning():
    """Factory : fabrique un MagicMock Anthropic dont messages.create renvoie
    un message texte donné. Mutualise un helper qui était dupliqué entre
    test_ocr_thumbnails.py et test_rematch_with_ocr_main.py."""

    def _make(text: str):
        block = SimpleNamespace(type="text", text=text)
        msg = SimpleNamespace(content=[block])
        client = MagicMock()
        client.messages.create.return_value = msg
        return client

    return _make


@pytest.fixture
def tmp_episode_json(tmp_path: Path):
    """Factory qui crée un fichier JSON d'épisode à `tmp_path / file`."""

    def _make(name: str, data: dict[str, Any]) -> Path:
        p = tmp_path / name
        p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        return p

    return _make
