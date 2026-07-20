"""Fixtures pour search/ — réutilise les fixtures cache/ via import direct.

`pythonpath` inclut `tests/` (cf. pyproject) — l'import `cache.conftest`
fonctionne après création des __init__.py côté tests/cache.
"""
from __future__ import annotations

# Import via le chemin pythonpath: `tests/` est dans sys.path, donc
# `cache.conftest` pointe `tests/cache/conftest.py`. Mais comme `cache`
# est ALSO un package sous `tools/`, on évite la collision en redéfinissant
# localement les fixtures (DRY-sacrifice acceptable, ~30 lignes).
import json
from pathlib import Path

import pytest

from cache.builder import CacheBuilder


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


@pytest.fixture
def fake_content_dirs(tmp_path: Path) -> tuple[Path, Path, Path]:
    items_dir = tmp_path / "items"
    mentions_dir = tmp_path / "mentions"
    episodes_dir = tmp_path / "episodes"
    src_a = "podcast-a"
    (items_dir / src_a).mkdir(parents=True)
    (mentions_dir / src_a).mkdir(parents=True)
    (episodes_dir / src_a).mkdir(parents=True)
    _write_json(
        items_dir / src_a / "item-001.json",
        {"id": "item-001", "schemaVersion": 1, "title": "Parasite", "types": ["film"]},
    )
    _write_json(
        episodes_dir / src_a / "ep-A1.json",
        {
            "guid": "ep-A1",
            "schemaVersion": 1,
            "title": "Avec Bong Joon-ho",
            "hosts": ["Kyan"],
            "guests": [],
            "guestsParsed": ["Bong Joon-ho"],
        },
    )
    _write_json(
        mentions_dir / src_a / "men-A1.json",
        {
            "id": "men-A1",
            "schemaVersion": 1,
            "itemId": "item-001",
            "kind": "reco",
            "recommendedBy": "Bong Joon-ho",
            "sourceRef": {
                "episodeGuid": "ep-A1",
                "sourceId": src_a,
                "timestamp": "00:12:34",
            },
        },
    )
    src_b = "podcast-b"
    (items_dir / src_b).mkdir(parents=True)
    (mentions_dir / src_b).mkdir(parents=True)
    (episodes_dir / src_b).mkdir(parents=True)
    _write_json(
        items_dir / src_b / "item-B1.json",
        {"id": "item-B1", "schemaVersion": 1, "title": "Mortel", "types": ["serie"]},
    )
    _write_json(
        episodes_dir / src_b / "ep-B1.json",
        {
            "guid": "ep-B1",
            "schemaVersion": 1,
            "title": "Pilote",
            "hosts": ["Host B"],
            "guests": ["Invité B"],
            "guestsParsed": ["Invité B"],
        },
    )
    _write_json(
        mentions_dir / src_b / "men-B1.json",
        {
            "id": "men-B1",
            "schemaVersion": 1,
            "itemId": "item-B1",
            "kind": "reco",
            "recommendedBy": "Invité B",
            "sourceRef": {"episodeGuid": "ep-B1", "sourceId": src_b, "timestamp": 42},
        },
    )
    return items_dir, mentions_dir, episodes_dir


@pytest.fixture
def built_cache(
    tmp_path: Path, fake_content_dirs: tuple[Path, Path, Path]
) -> tuple[Path, CacheBuilder]:
    items_dir, mentions_dir, episodes_dir = fake_content_dirs
    db_path = tmp_path / "cache" / "reco.sqlite"
    builder = CacheBuilder(
        db_path=db_path,
        items_dir=items_dir,
        mentions_dir=mentions_dir,
        episodes_dir=episodes_dir,
    )
    builder.build()
    return db_path, builder
