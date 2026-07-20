"""Tests du loader de config (couche IO — lecture disque)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.config.loader import (
    ConfigLoadError,
    DEFAULT_SOURCES_DIR,
    load_source_config,
)
from tools.config.schema import SourceConfig


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def sources_dir(tmp_path: Path) -> Path:
    """Dossier sources temporaire isolé."""
    d = tmp_path / "sources"
    d.mkdir()
    return d


def _write(p: Path, payload: dict) -> Path:
    p.write_text(json.dumps(payload), encoding="utf-8")
    return p


def _valid_payload(**overrides) -> dict:
    base = {
        "id": "demo",
        "title": "Demo",
        "reco_prefix": "dm",
        "hosts": ["Alice", "Bob"],
        "description": "Une démo.",
        "rss_url": "https://example.com/rss",
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# Cas heureux
# ---------------------------------------------------------------------------


def test_load_valid_config_from_json(sources_dir: Path):
    _write(sources_dir / "demo.json", _valid_payload())
    cfg = load_source_config("demo", sources_dir=sources_dir)
    assert isinstance(cfg, SourceConfig)
    assert cfg.id == "demo"
    assert cfg.title == "Demo"
    assert cfg.hosts == ("Alice", "Bob")


def test_load_uses_default_sources_dir_when_unset(monkeypatch, sources_dir: Path):
    """Si `sources_dir` n'est pas fourni, on tape le chemin par défaut."""
    _write(sources_dir / "demo.json", _valid_payload())
    monkeypatch.setattr(
        "tools.config.loader.DEFAULT_SOURCES_DIR", sources_dir
    )
    cfg = load_source_config("demo")
    assert cfg.id == "demo"


def test_default_sources_dir_points_to_content_sources():
    """Sanity : la racine défaut est bien `src/content/sources` du projet."""
    assert DEFAULT_SOURCES_DIR.name == "sources"
    assert DEFAULT_SOURCES_DIR.parent.name == "content"


# ---------------------------------------------------------------------------
# Erreurs
# ---------------------------------------------------------------------------


def test_load_missing_file_raises_clear_error(sources_dir: Path):
    with pytest.raises(ConfigLoadError, match="introuvable"):
        load_source_config("ghost", sources_dir=sources_dir)


def test_load_invalid_json_raises_clear_error(sources_dir: Path):
    (sources_dir / "bad.json").write_text("{not json", encoding="utf-8")
    with pytest.raises(ConfigLoadError, match="JSON invalide"):
        load_source_config("bad", sources_dir=sources_dir)


def test_load_missing_required_field_raises(sources_dir: Path):
    """Schéma incomplet → erreur explicite."""
    _write(sources_dir / "demo.json", {"id": "demo"})  # title manquant
    with pytest.raises(ConfigLoadError, match="title|reco_prefix|hosts"):
        load_source_config("demo", sources_dir=sources_dir)


def test_load_invalid_field_raises(sources_dir: Path):
    """Validation domaine → erreur de loader (encapsule la ValueError)."""
    _write(
        sources_dir / "demo.json",
        _valid_payload(reco_prefix="UPPERCASE"),
    )
    with pytest.raises(ConfigLoadError, match="reco_prefix"):
        load_source_config("demo", sources_dir=sources_dir)


def test_load_extra_fields_does_not_crash(sources_dir: Path, caplog):
    """Champs inconnus → warning, pas d'erreur."""
    import logging
    _write(
        sources_dir / "demo.json",
        _valid_payload(future_field="ignored"),
    )
    with caplog.at_level(logging.WARNING, logger="reco.config"):
        cfg = load_source_config("demo", sources_dir=sources_dir)
    assert cfg.id == "demo"
    assert any("future_field" in r.message for r in caplog.records)


# ---------------------------------------------------------------------------
# Résolution de chemin
# ---------------------------------------------------------------------------


def test_path_resolution_via_sources_dir(sources_dir: Path):
    """Le loader cherche `<sources_dir>/<id>.json` — pas de chemin caché."""
    _write(sources_dir / "demo.json", _valid_payload())
    other = sources_dir.parent / "other"
    other.mkdir()
    # Même id, autre dossier : ne doit PAS être trouvé.
    with pytest.raises(ConfigLoadError):
        load_source_config("demo", sources_dir=other)


def test_id_mismatch_between_filename_and_payload(sources_dir: Path):
    """Mismatch filename/id payload → erreur claire."""
    _write(sources_dir / "demo.json", _valid_payload(id="other"))
    with pytest.raises(ConfigLoadError, match="mismatch|id"):
        load_source_config("demo", sources_dir=sources_dir)


def test_id_is_deduced_from_filename_when_missing_in_payload(sources_dir: Path):
    """Si le payload omet `id`, on l'injecte depuis le nom de fichier
    (issue #20)."""
    payload = _valid_payload()
    payload.pop("id")
    _write(sources_dir / "demo.json", payload)
    cfg = load_source_config("demo", sources_dir=sources_dir)
    assert cfg.id == "demo"
