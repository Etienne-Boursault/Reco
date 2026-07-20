"""Fixtures partagées pour les tests cache/.

Génère un mini-dataset JSON `items`/`mentions`/`episodes` dans `tmp_path`,
puis construit un cache SQLite dans `tmp_path/cache/reco.sqlite`. Pas de
mocks — uniquement du filesystem éphémère.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from cache.builder import CacheBuilder


@pytest.fixture
def fake_content_dirs(tmp_path: Path) -> tuple[Path, Path, Path]:
    """Crée une arborescence `items/`, `mentions/`, `episodes/` avec 2 sources."""
    items_dir = tmp_path / "items"
    mentions_dir = tmp_path / "mentions"
    episodes_dir = tmp_path / "episodes"

    # --- source A : podcast-a ----------------------------------------------
    src_a = "podcast-a"
    (items_dir / src_a).mkdir(parents=True)
    (mentions_dir / src_a).mkdir(parents=True)
    (episodes_dir / src_a).mkdir(parents=True)

    _write_json(
        items_dir / src_a / "item-001.json",
        {
            "id": "item-001",
            "schemaVersion": 1,
            "title": "Parasite",
            "types": ["film"],
            "externalIds": {"tmdb": 496243, "tmdbType": "movie"},
        },
    )
    _write_json(
        items_dir / src_a / "item-002.json",
        {
            "id": "item-002",
            "schemaVersion": 1,
            "title": "Kaamelott",
            "types": ["serie"],
            "canonicalKey": "kaamelott",
            "enrichmentSuspect": True,
        },
    )
    _write_json(
        episodes_dir / src_a / "ep-A1.json",
        {
            "guid": "ep-A1",
            "schemaVersion": 1,
            "title": "Avec Bong Joon-ho",
            "hosts": ["Kyan Khojandi", "Navo"],
            "guests": [],
            "guestsParsed": ["Bong Joon-ho"],
            "sourceId": src_a,
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
            "quote": "Un film coréen génial.",
            "sourceRef": {
                "episodeGuid": "ep-A1",
                "sourceId": src_a,
                "timestamp": "00:12:34",
            },
        },
    )
    _write_json(
        mentions_dir / src_a / "men-A2.json",
        {
            "id": "men-A2",
            "schemaVersion": 1,
            "itemId": "item-002",
            "kind": "reco",
            "recommendedBy": "Kyan Khojandi",
            "sourceRef": {
                "episodeGuid": "ep-A1",
                "sourceId": src_a,
                "timestamp": "01:05:00",
            },
        },
    )

    # --- source B : podcast-b (pour tester filtre par source) --------------
    src_b = "podcast-b"
    (items_dir / src_b).mkdir(parents=True)
    (mentions_dir / src_b).mkdir(parents=True)
    (episodes_dir / src_b).mkdir(parents=True)
    _write_json(
        items_dir / src_b / "item-B1.json",
        {
            "id": "item-B1",
            "schemaVersion": 1,
            "title": "Mortel",
            "types": ["serie"],
        },
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
            "sourceId": src_b,
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
            "sourceRef": {
                "episodeGuid": "ep-B1",
                "sourceId": src_b,
                "timestamp": 42,  # int (déjà secondes)
            },
        },
    )

    # Source ignorée (préfixe __) — couvre la branche skip dans _iter_source_dirs.
    (items_dir / "__fixtures__").mkdir(parents=True)

    return items_dir, mentions_dir, episodes_dir


@pytest.fixture
def built_cache(
    tmp_path: Path, fake_content_dirs: tuple[Path, Path, Path]
) -> tuple[Path, CacheBuilder]:
    """Construit un cache SQLite et renvoie (db_path, builder)."""
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


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
