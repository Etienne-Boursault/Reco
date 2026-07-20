"""Tests pour `MigrationRunner` — orchestration des migrations versionnées.

Le runner :
  - reçoit les répertoires (items_dir/mentions_dir/sources_dir) à muter ;
  - charge chaque fichier JSON, applique la chaîne de migrations, écrit ;
  - mode dry-run par défaut (rien sur disque), mode apply explicite ;
  - reporte des stats {n_migrated, n_skipped, n_errors, from_version, to_version}.

Stratégie de test : tmp_path + fichiers JSON synthétiques. Pas de
dépendance au dataset réel.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from migrations.runner import MigrationRunner, MigrationStats


# ---------------------------------------------------------------------------
# Fixtures locales
# ---------------------------------------------------------------------------


def _write_item(dir_: Path, item_id: str, schema_version: int) -> Path:
    """Écrit un item JSON minimal sur disque (schema_version configurable)."""
    dir_.mkdir(parents=True, exist_ok=True)
    payload = {
        "id": item_id,
        "schemaVersion": schema_version,
        "title": f"Title {item_id}",
        "types": ["film"],
    }
    p = dir_ / f"{item_id}.json"
    p.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return p


@pytest.fixture
def items_dir(tmp_path: Path) -> Path:
    """Dossier `tmp/items/un-bon-moment/` avec 3 items en v1."""
    d = tmp_path / "items" / "un-bon-moment"
    _write_item(d, "aaa", schema_version=1)
    _write_item(d, "bbb", schema_version=1)
    _write_item(d, "ccc", schema_version=1)
    return d


@pytest.fixture
def runner(tmp_path: Path) -> MigrationRunner:
    return MigrationRunner(
        items_base_dir=tmp_path / "items",
        mentions_base_dir=tmp_path / "mentions",
        sources_base_dir=tmp_path / "sources",
    )


# ---------------------------------------------------------------------------
# Comportement de base
# ---------------------------------------------------------------------------


def test_runner_no_op_when_already_at_target_version(
    runner: MigrationRunner, items_dir: Path
):
    """Items en v1 + target=1 → aucun migration appliquée, n_skipped=N."""
    stats = runner.run(
        entity="item", source_id="un-bon-moment", target_version=1, dry_run=False,
    )
    assert isinstance(stats, MigrationStats)
    assert stats.n_migrated == 0
    assert stats.n_skipped == 3
    assert stats.from_version == 1
    assert stats.to_version == 1
    # Fichiers inchangés sur disque.
    for p in items_dir.glob("*.json"):
        assert json.loads(p.read_text(encoding="utf-8"))["schemaVersion"] == 1


def test_runner_applies_chain_v1_to_v2(
    runner: MigrationRunner, items_dir: Path
):
    """Items en v1 + target=2 → tous migrés, n_migrated=3."""
    stats = runner.run(
        entity="item", source_id="un-bon-moment", target_version=2, dry_run=False,
    )
    assert stats.n_migrated == 3
    assert stats.n_skipped == 0
    assert stats.from_version == 1
    assert stats.to_version == 2
    # Disque effectivement bumpé.
    for p in items_dir.glob("*.json"):
        assert json.loads(p.read_text(encoding="utf-8"))["schemaVersion"] == 2


def test_runner_dry_run_writes_nothing(
    runner: MigrationRunner, items_dir: Path
):
    """Dry-run rapporte les stats mais ne touche pas le disque."""
    stats = runner.run(
        entity="item", source_id="un-bon-moment", target_version=2, dry_run=True,
    )
    assert stats.n_migrated == 3
    assert stats.n_skipped == 0
    # Aucun fichier touché.
    for p in items_dir.glob("*.json"):
        assert json.loads(p.read_text(encoding="utf-8"))["schemaVersion"] == 1


def test_runner_apply_writes_atomically(
    runner: MigrationRunner, items_dir: Path
):
    """`dry_run=False` écrit réellement. Pas de tmp file résiduel."""
    runner.run(
        entity="item", source_id="un-bon-moment", target_version=2, dry_run=False,
    )
    # Aucun .tmp ou .partial résiduel.
    leftovers = list(items_dir.glob("*.tmp")) + list(items_dir.glob("*.partial"))
    assert leftovers == []


def test_runner_idempotent_on_rerun(
    runner: MigrationRunner, items_dir: Path
):
    """Apply puis re-run target=2 → 2e run = no-op (déjà à v2)."""
    s1 = runner.run(
        entity="item", source_id="un-bon-moment", target_version=2, dry_run=False,
    )
    assert s1.n_migrated == 3
    s2 = runner.run(
        entity="item", source_id="un-bon-moment", target_version=2, dry_run=False,
    )
    assert s2.n_migrated == 0
    assert s2.n_skipped == 3


def test_runner_reports_stats_correctly_as_dict(
    runner: MigrationRunner, items_dir: Path
):
    """`MigrationStats.to_dict()` expose les champs attendus (UX CLI / JSON)."""
    stats = runner.run(
        entity="item", source_id="un-bon-moment", target_version=2, dry_run=True,
    )
    d = stats.to_dict()
    assert d["entity"] == "item"
    assert d["source_id"] == "un-bon-moment"
    assert d["from_version"] == 1
    assert d["to_version"] == 2
    assert d["n_migrated"] == 3
    assert d["n_skipped"] == 0
    assert d["n_errors"] == 0
    assert d["dry_run"] is True


# ---------------------------------------------------------------------------
# Robustesse
# ---------------------------------------------------------------------------


def test_runner_skips_files_already_at_higher_version(
    runner: MigrationRunner, items_dir: Path
):
    """Mix v1 / v2 + target=2 → v2 sont skip, v1 sont migrés."""
    _write_item(items_dir, "ddd", schema_version=2)
    stats = runner.run(
        entity="item", source_id="un-bon-moment", target_version=2, dry_run=False,
    )
    assert stats.n_migrated == 3  # aaa/bbb/ccc
    assert stats.n_skipped == 1   # ddd déjà à v2


def test_runner_counts_errors_on_corrupted_file(
    runner: MigrationRunner, items_dir: Path
):
    """Un fichier JSON invalide → comptabilisé en `n_errors`, pas crash."""
    bad = items_dir / "broken.json"
    bad.write_text("{not valid json", encoding="utf-8")
    stats = runner.run(
        entity="item", source_id="un-bon-moment", target_version=2, dry_run=False,
    )
    assert stats.n_errors == 1
    # Les autres items sont quand même migrés.
    assert stats.n_migrated == 3


def test_runner_raises_on_unknown_entity(runner: MigrationRunner):
    """Une entité inconnue lève (registry-level)."""
    from migrations.registry import UnknownEntityError
    with pytest.raises(UnknownEntityError):
        runner.run(
            entity="inexistant", source_id="un-bon-moment",
            target_version=2, dry_run=True,
        )


def test_runner_raises_on_target_below_one(runner: MigrationRunner):
    """target_version < 1 est rejeté côté runner (propagation registry)."""
    from migrations.registry import UnsupportedTargetVersionError
    with pytest.raises(UnsupportedTargetVersionError):
        runner.run(
            entity="item", source_id="un-bon-moment",
            target_version=0, dry_run=True,
        )


def test_runner_handles_empty_source_dir(runner: MigrationRunner, tmp_path: Path):
    """Source vide ou dossier inexistant → stats à 0, pas d'erreur."""
    stats = runner.run(
        entity="item", source_id="never-existed",
        target_version=2, dry_run=False,
    )
    assert stats.n_migrated == 0
    assert stats.n_skipped == 0
    assert stats.n_errors == 0


def test_runner_supports_mention_entity(runner: MigrationRunner, tmp_path: Path):
    """Le runner sait migrer les mentions (pas seulement les items)."""
    mentions_dir = tmp_path / "mentions" / "un-bon-moment"
    mentions_dir.mkdir(parents=True)
    (mentions_dir / "m1.json").write_text(
        json.dumps({"id": "m1", "schemaVersion": 1, "title": "X"}),
        encoding="utf-8",
    )
    stats = runner.run(
        entity="mention", source_id="un-bon-moment",
        target_version=2, dry_run=False,
    )
    assert stats.n_migrated == 1
    assert stats.from_version == 1
    assert stats.to_version == 2


def test_runner_supports_source_entity(runner: MigrationRunner, tmp_path: Path):
    """Les sources vivent à plat dans `sources_dir/<id>.json` (pas de sous-dossier)."""
    sources_dir = tmp_path / "sources"
    sources_dir.mkdir(parents=True)
    (sources_dir / "un-bon-moment.json").write_text(
        json.dumps({"id": "un-bon-moment", "schemaVersion": 1, "title": "UBM"}),
        encoding="utf-8",
    )
    stats = runner.run(
        entity="source", source_id="un-bon-moment",
        target_version=2, dry_run=False,
    )
    assert stats.n_migrated == 1


# ---------------------------------------------------------------------------
# MigrationStats VO
# ---------------------------------------------------------------------------


def test_runner_skips_migrations_below_current_version(
    runner: MigrationRunner, tmp_path: Path, monkeypatch
):
    """Si une chaîne contient des migrations en amont de current_version,
    elles sont skip (cas ré-exécution partielle).

    On force le scan à renvoyer une chaîne contenant une migration v0→v1
    déjà passée, suivie de v1→v2.
    """
    d = tmp_path / "items" / "un-bon-moment"
    _write_item(d, "x", schema_version=1)

    from migrations import runner as runner_mod

    class _Noop01:
        SOURCE_VERSION = 0
        TARGET_VERSION = 1
        ENTITY = "item"
        def migrate_one(self, data):  # pragma: no cover - skip path
            raise AssertionError("ne doit pas être appelée")

    real_discover = runner_mod.discover_migration_chain

    def fake_discover(entity, target_version):
        chain = real_discover(entity, target_version)
        return [_Noop01(), *chain]

    monkeypatch.setattr(runner_mod, "discover_migration_chain", fake_discover)
    stats = runner.run(
        entity="item", source_id="un-bon-moment",
        target_version=2, dry_run=False,
    )
    assert stats.n_migrated == 1
    assert stats.n_errors == 0


def test_runner_counts_migration_failures_as_errors(
    runner: MigrationRunner, tmp_path: Path, monkeypatch
):
    """Si `migrate_one` lève (ValueError/KeyError), c'est un n_errors,
    pas un crash."""
    d = tmp_path / "items" / "un-bon-moment"
    _write_item(d, "x", schema_version=1)

    from migrations import runner as runner_mod

    class _Bad:
        SOURCE_VERSION = 1
        TARGET_VERSION = 2
        ENTITY = "item"
        def migrate_one(self, data):
            raise ValueError("simulated migration bug")

    monkeypatch.setattr(
        runner_mod, "discover_migration_chain",
        lambda entity, target_version: [_Bad()],
    )
    stats = runner.run(
        entity="item", source_id="un-bon-moment",
        target_version=2, dry_run=False,
    )
    assert stats.n_errors == 1
    assert stats.n_migrated == 0
    assert any("simulated migration bug" in e for e in stats.errors)


def test_migration_stats_defaults():
    """`MigrationStats` instanciable avec valeurs nulles."""
    s = MigrationStats(
        entity="item",
        source_id="x",
        from_version=1,
        to_version=2,
        dry_run=True,
    )
    assert s.n_migrated == 0
    assert s.n_skipped == 0
    assert s.n_errors == 0


# ---------------------------------------------------------------------------
# from_version réel (CRITIQUE #3) + observed_from_versions
# ---------------------------------------------------------------------------


def test_runner_reports_real_from_version_min_of_observed(
    runner: MigrationRunner, items_dir: Path,
):
    """`from_version` = min(versions rencontrées), pas un hardcode.

    Dataset mix v1+v2 → from_version=1 ; v2 only → from_version=2.
    """
    _write_item(items_dir, "ddd", schema_version=2)
    stats = runner.run(
        entity="item", source_id="un-bon-moment", target_version=2, dry_run=True,
    )
    assert stats.from_version == 1  # min(1, 2)


def test_runner_from_version_is_zero_when_no_files(runner: MigrationRunner):
    """Dataset vide → from_version=0 (signal "rien à dire", pas un faux 1)."""
    stats = runner.run(
        entity="item", source_id="never-existed",
        target_version=2, dry_run=True,
    )
    assert stats.from_version == 0


def test_runner_exposes_observed_from_versions_histogram(
    runner: MigrationRunner, items_dir: Path,
):
    """`observed_from_versions` documente le mix de versions d'entrée."""
    _write_item(items_dir, "ddd", schema_version=2)
    stats = runner.run(
        entity="item", source_id="un-bon-moment", target_version=2, dry_run=True,
    )
    d = stats.to_dict()
    # 3 fichiers en v1 + 1 fichier en v2.
    assert d["observed_from_versions"] == {"1": 3, "2": 1}


# ---------------------------------------------------------------------------
# Coercion stricte schemaVersion (B4)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("bad_value", [True, False, "2", 2.0, [], {}])
def test_runner_rejects_non_int_schema_version(
    runner: MigrationRunner, tmp_path: Path, bad_value,
):
    """`schemaVersion` non-int strict → n_errors, pas un silent-wrong.

    Cas piégeurs : `True` est `int` en Python mais sémantiquement faux,
    `"2"` peut être trompeur (`int("2") == 2`), `2.0` perd le typing.
    """
    d = tmp_path / "items" / "un-bon-moment"
    d.mkdir(parents=True)
    (d / "x.json").write_text(
        json.dumps({"id": "x", "schemaVersion": bad_value, "title": "X"}),
        encoding="utf-8",
    )
    stats = runner.run(
        entity="item", source_id="un-bon-moment", target_version=2, dry_run=True,
    )
    assert stats.n_errors == 1
    assert any("schemaVersion" in e for e in stats.errors)
    assert stats.n_migrated == 0


def test_runner_accepts_missing_schema_version_as_v1(
    runner: MigrationRunner, tmp_path: Path,
):
    """Champ absent → traité comme v1 (compat datasets pré-versioning)."""
    d = tmp_path / "items" / "un-bon-moment"
    d.mkdir(parents=True)
    (d / "x.json").write_text(json.dumps({"id": "x"}), encoding="utf-8")
    stats = runner.run(
        entity="item", source_id="un-bon-moment", target_version=2, dry_run=False,
    )
    assert stats.n_migrated == 1
    assert stats.n_errors == 0


def test_runner_rejects_negative_schema_version(
    runner: MigrationRunner, tmp_path: Path,
):
    """`schemaVersion=0` ou négatif → n_errors."""
    d = tmp_path / "items" / "un-bon-moment"
    d.mkdir(parents=True)
    (d / "x.json").write_text(
        json.dumps({"id": "x", "schemaVersion": 0}), encoding="utf-8",
    )
    stats = runner.run(
        entity="item", source_id="un-bon-moment", target_version=2, dry_run=True,
    )
    assert stats.n_errors == 1


# ---------------------------------------------------------------------------
# Broader except (B5) — TypeError / AttributeError / RuntimeError
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "exc_cls", [TypeError, AttributeError, RuntimeError, ValueError, KeyError],
)
def test_runner_catches_any_exception_from_migration(
    runner: MigrationRunner, tmp_path: Path, monkeypatch, exc_cls,
):
    """Toute exception (pas seulement ValueError/KeyError) est comptabilisée."""
    d = tmp_path / "items" / "un-bon-moment"
    _write_item(d, "x", schema_version=1)

    from migrations import runner as runner_mod

    class _Bad:
        SOURCE_VERSION = 1
        TARGET_VERSION = 2
        ENTITY = "item"
        def migrate_one(self, data):
            raise exc_cls(f"boom: {exc_cls.__name__}")

    monkeypatch.setattr(
        runner_mod, "discover_migration_chain",
        lambda entity, target_version: [_Bad()],
    )
    stats = runner.run(
        entity="item", source_id="un-bon-moment",
        target_version=2, dry_run=False,
    )
    assert stats.n_errors == 1
    assert stats.n_migrated == 0
    assert any(exc_cls.__name__ in e or "boom" in e for e in stats.errors)


# ---------------------------------------------------------------------------
# Atomicité mid-chain failure (CRITIQUE #4)
# ---------------------------------------------------------------------------


def test_runner_keeps_file_intact_when_intermediate_migration_fails(
    runner: MigrationRunner, tmp_path: Path, monkeypatch,
):
    """Chaîne v1→v2→v3 où v2→v3 lève : fichier reste à v1 sur disque.

    Garantit l'atomicité **par fichier** (tout-ou-rien). Pas d'écriture
    intermédiaire à v2.
    """
    d = tmp_path / "items" / "un-bon-moment"
    _write_item(d, "x", schema_version=1)

    from migrations import runner as runner_mod

    class _Ok12:
        SOURCE_VERSION = 1
        TARGET_VERSION = 2
        ENTITY = "item"
        def migrate_one(self, data):
            out = dict(data)
            out["schemaVersion"] = 2
            return out

    class _Boom23:
        SOURCE_VERSION = 2
        TARGET_VERSION = 3
        ENTITY = "item"
        def migrate_one(self, data):
            raise RuntimeError("v2->v3 cassée")

    monkeypatch.setattr(
        runner_mod, "discover_migration_chain",
        lambda entity, target_version: [_Ok12(), _Boom23()],
    )
    stats = runner.run(
        entity="item", source_id="un-bon-moment",
        target_version=3, dry_run=False,
    )
    assert stats.n_migrated == 0
    assert stats.n_errors == 1
    # Le fichier sur disque est INTACT à v1 (atomicité par-fichier).
    p = d / "x.json"
    on_disk = json.loads(p.read_text(encoding="utf-8"))
    assert on_disk["schemaVersion"] == 1


# ---------------------------------------------------------------------------
# Chain provider injectable (B3)
# ---------------------------------------------------------------------------


def test_runner_accepts_injected_chain_provider(tmp_path: Path):
    """`chain_provider=` injecté supplante `discover_migration_chain`."""
    d = tmp_path / "items" / "un-bon-moment"
    _write_item(d, "x", schema_version=1)

    class _Fake:
        SOURCE_VERSION = 1
        TARGET_VERSION = 2
        ENTITY = "item"
        def migrate_one(self, data):
            out = dict(data)
            out["schemaVersion"] = 2
            out["injected"] = True
            return out

    calls: list[tuple[str, int]] = []

    def fake_provider(entity: str, target_version: int):
        calls.append((entity, target_version))
        return [_Fake()]

    runner = MigrationRunner(
        items_base_dir=tmp_path / "items",
        mentions_base_dir=tmp_path / "mentions",
        sources_base_dir=tmp_path / "sources",
        chain_provider=fake_provider,
    )
    stats = runner.run(
        entity="item", source_id="un-bon-moment", target_version=2, dry_run=False,
    )
    assert stats.n_migrated == 1
    assert calls == [("item", 2)]
    on_disk = json.loads((d / "x.json").read_text(encoding="utf-8"))
    assert on_disk["injected"] is True


# ---------------------------------------------------------------------------
# Truncation des messages d'erreur (C6)
# ---------------------------------------------------------------------------


def test_runner_truncates_errors_above_cap(
    runner: MigrationRunner, tmp_path: Path,
):
    """Au-delà de _MAX_ERRORS_KEPT erreurs, le tableau est tronqué.

    n_errors reste exact, mais `errors` est borné pour éviter d'exploser
    le JSON / la mémoire si tout le dataset est corrompu.
    """
    from migrations.runner import _MAX_ERRORS_KEPT

    d = tmp_path / "items" / "un-bon-moment"
    d.mkdir(parents=True)
    # Crée _MAX_ERRORS_KEPT + 5 fichiers JSON corrompus.
    n_files = _MAX_ERRORS_KEPT + 5
    for i in range(n_files):
        (d / f"f{i:04d}.json").write_text("{not json", encoding="utf-8")
    stats = runner.run(
        entity="item", source_id="un-bon-moment",
        target_version=2, dry_run=True,
    )
    assert stats.n_errors == n_files
    # `errors` contient au plus _MAX_ERRORS_KEPT messages + 1 marqueur.
    assert len(stats.errors) == _MAX_ERRORS_KEPT + 1
    assert "tronquée" in stats.errors[-1]


# ---------------------------------------------------------------------------
# Logging structuré (B11)
# ---------------------------------------------------------------------------


def test_runner_emits_structured_log_events(
    runner: MigrationRunner, items_dir: Path, caplog,
):
    """Le runner émet des logs `migrations.runner` aux étapes-clés."""
    import logging
    caplog.set_level(logging.INFO, logger="migrations.runner")
    runner.run(
        entity="item", source_id="un-bon-moment", target_version=2, dry_run=True,
    )
    messages = [r.getMessage() for r in caplog.records]
    assert any("migration.run.start" in m for m in messages)
    assert any("migration.run.end" in m for m in messages)
