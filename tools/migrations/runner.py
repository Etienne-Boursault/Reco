"""
runner.py — Orchestrateur des migrations sur un dataset JSON-on-disk.

Le `MigrationRunner` :
  - reçoit les répertoires racines (items/mentions/sources) ;
  - pour chaque fichier de l'entité demandée, lit le `schemaVersion`,
    applique la chaîne de migrations, écrit (mode apply) ou skip (dry-run) ;
  - reporte des stats (`MigrationStats`) au format JSON-sérialisable.

Décisions :
  - Items et mentions vivent dans `<base_dir>/<source_id>/*.json`.
  - Sources vivent à plat dans `<base_dir>/<source_id>.json`.
  - Écritures atomiques via `common.atomic_write_text` (Windows-safe).
  - Fichier corrompu → comptabilisé en `n_errors`, pas crash.
  - Idempotence : un item déjà au-dessus de `target_version` → skip.

Atomicité (cf. ADR 0010) :
  - **Par fichier** : chaque écriture est atomique (`atomic_write_text` :
    écrit dans `<path>.tmp`, fsync, rename). Soit le fichier est intégralement
    à `target_version`, soit il reste intact à sa version précédente.
    Si une étape intermédiaire de la chaîne v_N→v_{N+1} lève, **rien**
    n'est écrit pour ce fichier — il reste à `current_version` sur disque.
  - **Global (multi-fichiers)** : pas d'atomicité transactionnelle. Un
    `kill -9` ou panic mid-run laisse le dataset hétérogène (certains
    fichiers migrés, d'autres non). Mitigation : ré-exécuter le runner
    (idempotent — les fichiers déjà migrés sont skip).

Pas de thread-safety (cf. `docs/yagni.md`).
"""
from __future__ import annotations

import json
import logging
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from common import atomic_write_text

from .registry import discover_migration_chain

logger = logging.getLogger("migrations.runner")

# Plafond du nombre de messages d'erreur conservés dans MigrationStats.errors.
# Au-delà, on incrémente quand même n_errors mais on tronque le tableau
# pour éviter qu'un dataset corrompu massif ne fasse exploser la mémoire / le JSON.
_MAX_ERRORS_KEPT = 100


@runtime_checkable
class Migration(Protocol):
    """Contrat d'une migration v_SOURCE → v_TARGET.

    Pure : `migrate_one` ne fait pas d'IO et ne mute pas son argument.
    """

    SOURCE_VERSION: int
    TARGET_VERSION: int
    ENTITY: str  # "item" | "mention" | "source"

    def migrate_one(self, data: dict[str, Any]) -> dict[str, Any]: ...


@dataclass(frozen=True)
class MigrationStats:
    """Stats d'exécution d'une migration (JSON-sérialisable).

    Sémantique des champs version :
      - `from_version` : plus petite `schemaVersion` rencontrée sur disque
        (= la "borne basse" effective du run). Pour les datasets homogènes,
        c'est la version d'origine de tous les fichiers ; pour les datasets
        mixtes, c'est `min(versions(fichiers))`. 0 si aucun fichier traité.
      - `to_version` : la cible demandée à `run()`.
      - `observed_from_versions` : histogramme des versions d'entrée
        rencontrées (dict {version: count}). Plus informatif pour l'audit
        qu'une seule borne.
    """

    entity: str
    source_id: str
    from_version: int
    to_version: int
    dry_run: bool
    n_migrated: int = 0
    n_skipped: int = 0
    n_errors: int = 0
    errors: tuple[str, ...] = field(default_factory=tuple)
    observed_from_versions: tuple[tuple[int, int], ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        """Représentation dict-only (pour `json.dumps`).

        Le tuple immuable `observed_from_versions` est exporté en dict
        pour faciliter le parsing CI / jq.
        """
        return {
            "entity": self.entity,
            "source_id": self.source_id,
            "from_version": self.from_version,
            "to_version": self.to_version,
            "dry_run": self.dry_run,
            "n_migrated": self.n_migrated,
            "n_skipped": self.n_skipped,
            "n_errors": self.n_errors,
            "errors": list(self.errors),
            "observed_from_versions": {
                str(v): c for v, c in self.observed_from_versions
            },
        }


class MigrationRunner:
    """Orchestre l'exécution des migrations sur le disque.

    Single-threaded by design. Idempotent : ré-exécuter à la même cible
    est sûr (chaque fichier est skip si déjà au-dessus).
    """

    def __init__(
        self,
        items_base_dir: Path,
        mentions_base_dir: Path,
        sources_base_dir: Path,
        *,
        chain_provider: Callable[[str, int], list["Migration"]] | None = None,
    ) -> None:
        """Construit le runner.

        Args:
            items_base_dir/mentions_base_dir/sources_base_dir: racines des
                datasets versionnés.
            chain_provider: fonction `(entity, target_version) -> list[Migration]`.
                Par défaut, utilise `registry.discover_migration_chain`. Injectable
                pour les tests (évite le monkeypatch global) et pour les sous-classes
                avancées (cache custom, registry alternatif).
        """
        self.items_base_dir = items_base_dir
        self.mentions_base_dir = mentions_base_dir
        self.sources_base_dir = sources_base_dir
        # NB : on stocke `None` quand l'appelant n'a pas injecté de provider
        # explicite, et on résout `discover_migration_chain` au runtime via
        # `_resolve_chain_provider()`. Permet aux tests historiques de
        # monkeypatcher `migrations.runner.discover_migration_chain` sans
        # casser la résolution.
        self._chain_provider: Callable[[str, int], list["Migration"]] | None = (
            chain_provider
        )

    def _resolve_chain_provider(self) -> Callable[[str, int], list["Migration"]]:
        """Renvoie le provider effectif (injecté ou défaut module-level)."""
        if self._chain_provider is not None:
            return self._chain_provider
        # Lookup module-level pour respecter d'éventuels monkeypatch de test.
        return discover_migration_chain

    # -- Localisation des fichiers ----------------------------------------

    def _iter_paths(self, entity: str, source_id: str) -> Iterable[Path]:
        """Itère sur les fichiers JSON d'une entité pour `source_id`.

        Stratégie déclarative par entité (évite la cascade de `if`) :
          - item / mention : `<base>/<source_id>/*.json`
          - source         : `<base>/<source_id>.json` (un seul fichier).

        Pour ajouter une entité, étendre `_PATH_STRATEGIES` ci-dessous.
        """
        strategy = self._PATH_STRATEGIES.get(entity)
        if strategy is None:  # pragma: no cover - entity déjà validé en amont
            return []
        return strategy(self, source_id)

    def _iter_flat(self, source_id: str) -> list[Path]:
        """Layout 1 fichier par source (sources)."""
        p = self.sources_base_dir / f"{source_id}.json"
        return [p] if p.exists() else []

    def _iter_per_source_dir_items(self, source_id: str) -> list[Path]:
        """Layout `<items_dir>/<source_id>/*.json`."""
        d = self.items_base_dir / source_id
        return sorted(d.glob("*.json")) if d.is_dir() else []

    def _iter_per_source_dir_mentions(self, source_id: str) -> list[Path]:
        """Layout `<mentions_dir>/<source_id>/*.json`."""
        d = self.mentions_base_dir / source_id
        return sorted(d.glob("*.json")) if d.is_dir() else []

    # Table déclarative entity -> strategy (SSOT du layout disque).
    _PATH_STRATEGIES: dict[str, Callable[["MigrationRunner", str], list[Path]]] = {
        "item": _iter_per_source_dir_items,
        "mention": _iter_per_source_dir_mentions,
        "source": _iter_flat,
    }

    # -- Exécution --------------------------------------------------------

    def run(
        self,
        entity: str,
        source_id: str,
        target_version: int,
        *,
        dry_run: bool = True,
    ) -> MigrationStats:
        """Migre tous les fichiers d'`entity`/`source_id` vers `target_version`.

        Lève `UnknownEntityError` / `UnsupportedTargetVersionError` côté
        registry. Tout autre échec (lecture JSON, migration unitaire) est
        comptabilisé en `n_errors` sans interrompre le run.

        Atomicité : voir la docstring du module. Si une étape intermédiaire
        de la chaîne v_N→v_{N+1} lève, le fichier reste **intact** sur disque
        (rien n'est écrit pour ce fichier).
        """
        chain = self._resolve_chain_provider()(entity, target_version)
        paths = list(self._iter_paths(entity, source_id))
        logger.info(
            "migration.run.start entity=%s source_id=%s target=%s dry_run=%s n_paths=%d",
            entity, source_id, target_version, dry_run, len(paths),
        )
        n_migrated = 0
        n_skipped = 0
        n_errors = 0
        errors: list[str] = []
        observed: dict[int, int] = {}
        for path in paths:
            try:
                raw = path.read_text(encoding="utf-8")
                data = json.loads(raw)
            except (OSError, ValueError, json.JSONDecodeError) as exc:
                n_errors += 1
                _append_error(errors, f"{path.name}: {exc}")
                logger.warning("migration.read_error path=%s exc=%s", path, exc)
                continue
            try:
                current_version = _coerce_schema_version(data.get("schemaVersion"))
            except ValueError as exc:
                n_errors += 1
                _append_error(errors, f"{path.name}: {exc}")
                logger.warning("migration.schema_version_error path=%s exc=%s", path, exc)
                continue
            observed[current_version] = observed.get(current_version, 0) + 1
            if current_version >= target_version:
                n_skipped += 1
                continue
            # Applique la chaîne à partir du current_version.
            # Le `try` couvre uniquement l'exécution de la migration : si une
            # étape lève (v2→v3 par ex.), aucune écriture n'a lieu, le fichier
            # reste à `current_version` sur disque (atomicité par-fichier).
            try:
                migrated = data
                for mig in chain:
                    if mig.SOURCE_VERSION < current_version:
                        continue
                    migrated = mig.migrate_one(migrated)
            except (KeyboardInterrupt, SystemExit):  # pragma: no cover
                # Ne JAMAIS attraper ces deux-là (Ctrl-C, sys.exit()).
                raise
            except Exception as exc:  # noqa: BLE001 — fail-soft volontaire
                # Tout autre échec (ValueError/KeyError/TypeError/AttributeError/...)
                # est comptabilisé en n_errors sans interrompre le run global.
                n_errors += 1
                _append_error(errors, f"{path.name}: migration failed: {exc}")
                logger.warning(
                    "migration.apply_error path=%s exc_type=%s exc=%s",
                    path, type(exc).__name__, exc,
                )
                continue
            if not dry_run:
                new_text = (
                    json.dumps(
                        migrated,
                        ensure_ascii=False,
                        indent=2,
                        sort_keys=True,
                    )
                    + "\n"
                )
                atomic_write_text(path, new_text)
            n_migrated += 1
        # `from_version` = la plus basse version d'entrée effectivement
        # rencontrée. 0 si dataset vide (signal "rien à dire").
        from_version = min(observed) if observed else 0
        logger.info(
            "migration.run.end entity=%s source_id=%s migrated=%d skipped=%d errors=%d",
            entity, source_id, n_migrated, n_skipped, n_errors,
        )
        return MigrationStats(
            entity=entity,
            source_id=source_id,
            from_version=from_version,
            to_version=target_version,
            dry_run=dry_run,
            n_migrated=n_migrated,
            n_skipped=n_skipped,
            n_errors=n_errors,
            errors=tuple(errors),
            observed_from_versions=tuple(sorted(observed.items())),
        )


def _append_error(errors: list[str], msg: str) -> None:
    """Ajoute une erreur en bornant la taille à `_MAX_ERRORS_KEPT`.

    Au-delà du plafond, on conserve un marqueur de troncature et on
    ignore les ajouts suivants. Le compteur `n_errors` côté runner
    reste exact (l'erreur est quand même comptée).
    """
    if len(errors) < _MAX_ERRORS_KEPT:
        errors.append(msg)
    elif len(errors) == _MAX_ERRORS_KEPT:
        errors.append(
            f"... ({_MAX_ERRORS_KEPT} premières erreurs conservées, suite tronquée)"
        )


def _coerce_schema_version(raw: Any) -> int:
    """Coerce `schemaVersion` en `int` strictement.

    Accepte uniquement :
      - `None` (champ absent) -> 1 (compat datasets pré-versioning) ;
      - `int` non-`bool` (Python : `True`/`False` sont des `int`) >= 1.

    Rejette : `bool`, `str`, `float`, structures imbriquées. Évite les
    silently-wrong où `int(True) == 1` ou `int("2") == 2` masqueraient
    une corruption du fichier.
    """
    if raw is None:
        return 1
    if isinstance(raw, bool) or not isinstance(raw, int):
        raise ValueError(
            f"schemaVersion invalide: attendu int>=1, reçu {type(raw).__name__}={raw!r}."
        )
    if raw < 1:
        raise ValueError(f"schemaVersion invalide: {raw} < 1.")
    return raw


__all__ = ["Migration", "MigrationRunner", "MigrationStats"]
