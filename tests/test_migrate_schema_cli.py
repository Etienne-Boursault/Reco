"""Tests CLI `tools/migrate_schema.py`.

Mode défaut = `--dry-run`. `--apply` explicite pour écrire. Sortie JSON
sur stdout pour faciliter le parsing CI.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import migrate_schema


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def synthetic_dataset(tmp_path: Path, monkeypatch) -> Path:
    """Crée un mini-dataset items/un-bon-moment/*.json en v1 et redirige
    les constantes de path du CLI."""
    items = tmp_path / "items" / "un-bon-moment"
    items.mkdir(parents=True)
    for i, name in enumerate(("a", "b", "c")):
        (items / f"{name}.json").write_text(
            json.dumps({"id": name, "schemaVersion": 1, "title": name, "types": ["film"]}),
            encoding="utf-8",
        )
    monkeypatch.setattr(migrate_schema, "ITEMS_BASE_DIR", tmp_path / "items")
    monkeypatch.setattr(migrate_schema, "MENTIONS_BASE_DIR", tmp_path / "mentions")
    monkeypatch.setattr(migrate_schema, "SOURCES_BASE_DIR", tmp_path / "sources")
    return tmp_path


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_cli_dry_run_is_default(synthetic_dataset, capsys):
    """Pas de --apply → dry-run par défaut, rien n'est écrit."""
    rc = migrate_schema.main([
        "--entity", "item", "--to-version", "2", "--source", "un-bon-moment",
    ])
    assert rc == 0
    out = capsys.readouterr().out
    payload = json.loads(out)
    assert payload["dry_run"] is True
    assert payload["n_migrated"] == 3
    # Disque non modifié.
    items = synthetic_dataset / "items" / "un-bon-moment"
    for p in items.glob("*.json"):
        assert json.loads(p.read_text(encoding="utf-8"))["schemaVersion"] == 1


def test_cli_apply_writes_to_disk(synthetic_dataset, capsys):
    """--apply écrit réellement sur disque."""
    rc = migrate_schema.main([
        "--entity", "item", "--to-version", "2",
        "--source", "un-bon-moment", "--apply",
    ])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["dry_run"] is False
    assert payload["n_migrated"] == 3
    items = synthetic_dataset / "items" / "un-bon-moment"
    for p in items.glob("*.json"):
        assert json.loads(p.read_text(encoding="utf-8"))["schemaVersion"] == 2


def test_cli_dry_run_and_apply_mutually_exclusive(synthetic_dataset):
    """--dry-run et --apply ensemble → erreur argparse."""
    with pytest.raises(SystemExit):
        migrate_schema.main([
            "--entity", "item", "--to-version", "2",
            "--source", "un-bon-moment", "--dry-run", "--apply",
        ])


def test_cli_rejects_unknown_entity(synthetic_dataset, capsys):
    """Entité inconnue → argparse refuse (SystemExit non-zéro)."""
    with pytest.raises(SystemExit) as exc:
        migrate_schema.main([
            "--entity", "inexistant", "--to-version", "2",
            "--source", "un-bon-moment",
        ])
    assert exc.value.code != 0


def test_cli_rejects_invalid_source_id(synthetic_dataset):
    """source_id invalide (path traversal) → SystemExit."""
    rc = migrate_schema.main([
        "--entity", "item", "--to-version", "2",
        "--source", "../etc/passwd",
    ])
    assert rc != 0


def test_cli_returns_3_on_unsupported_target(synthetic_dataset, capsys):
    """target_version trop élevé → code retour 3, message stderr."""
    rc = migrate_schema.main([
        "--entity", "item", "--to-version", "99",
        "--source", "un-bon-moment",
    ])
    assert rc == 3
    err = capsys.readouterr().err
    assert "99" in err


def test_cli_returns_4_on_lock_busy(synthetic_dataset, monkeypatch, capsys):
    """ServerLockBusy/PipelineLockBusy → code retour 4."""
    import contextlib

    @contextlib.contextmanager
    def busy_lock(*, force: bool = False):
        raise migrate_schema.review_lock.ServerLockBusy("review_server actif")
        yield  # pragma: no cover

    monkeypatch.setattr(
        migrate_schema.review_lock, "acquire_pipeline_lock", busy_lock,
    )
    rc = migrate_schema.main([
        "--entity", "item", "--to-version", "2",
        "--source", "un-bon-moment",
    ])
    assert rc == 4
    assert "review_server" in capsys.readouterr().err


def test_cli_acquires_pipeline_lock(synthetic_dataset, monkeypatch, capsys):
    """Le CLI doit invoquer `review_lock.acquire_pipeline_lock`."""
    called: dict[str, bool] = {"locked": False}

    import contextlib
    @contextlib.contextmanager
    def fake_lock(*, force: bool = False):
        called["locked"] = True
        yield

    monkeypatch.setattr(migrate_schema.review_lock, "acquire_pipeline_lock", fake_lock)
    rc = migrate_schema.main([
        "--entity", "item", "--to-version", "2", "--source", "un-bon-moment",
    ])
    assert rc == 0
    assert called["locked"] is True


# ---------------------------------------------------------------------------
# Lock libéré sur exception (B7) — vérifie la sémantique context-manager
# ---------------------------------------------------------------------------


def test_cli_releases_lock_when_runner_raises(synthetic_dataset, monkeypatch):
    """Si `runner.run` lève, le verrou pipeline DOIT être libéré (cm __exit__).

    Sinon un crash unique condamnerait toutes les exécutions ultérieures.
    """
    import contextlib

    enter_count = {"n": 0}
    exit_count = {"n": 0}

    @contextlib.contextmanager
    def tracking_lock(*, force: bool = False):
        enter_count["n"] += 1
        try:
            yield
        finally:
            exit_count["n"] += 1

    monkeypatch.setattr(
        migrate_schema.review_lock, "acquire_pipeline_lock", tracking_lock,
    )

    # On force `runner.run` à lever une exception non-prévue (TypeError).
    class _BoomRunner:
        def __init__(self, **kwargs):
            pass
        def run(self, **kwargs):
            raise TypeError("explosion runtime")

    monkeypatch.setattr(migrate_schema, "MigrationRunner", _BoomRunner)

    with pytest.raises(TypeError, match="explosion"):
        migrate_schema.main([
            "--entity", "item", "--to-version", "2", "--source", "un-bon-moment",
        ])
    # Vérifie que la phase exit a bien été exécutée (== verrou libéré).
    assert enter_count["n"] == 1
    assert exit_count["n"] == 1


# ---------------------------------------------------------------------------
# CLI utilise KNOWN_ENTITIES (B8) — SSOT
# ---------------------------------------------------------------------------


def test_cli_choices_match_known_entities(synthetic_dataset):
    """`--entity` accepte EXACTEMENT les entités déclarées dans KNOWN_ENTITIES."""
    from migrations.registry import KNOWN_ENTITIES

    parser = migrate_schema._build_parser()
    # Inspect la spec argparse pour récupérer les choices effectives.
    entity_action = next(
        a for a in parser._actions if a.dest == "entity"
    )
    assert set(entity_action.choices) == set(KNOWN_ENTITIES)


# ---------------------------------------------------------------------------
# Anti-path-traversal (vérif que l'import SSOT du regex marche)
# ---------------------------------------------------------------------------


def test_cli_source_id_regex_imported_from_repository_base():
    """Le regex `_RE_SOURCE_ID` est importé depuis `repository._base` (SSOT)."""
    from repository._base import _SOURCE_ID_PATTERN
    assert migrate_schema._RE_SOURCE_ID is _SOURCE_ID_PATTERN
