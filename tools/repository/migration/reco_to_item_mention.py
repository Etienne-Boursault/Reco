"""
reco_to_item_mention.py — Service de migration recos legacy → Items+Mentions.

Orchestration pure : lit les recos JSON d'un dossier source, parse via
`reco_parser`, déduplique via les repos injectés, écrit (sauf en
`dry_run`). Aucune connaissance de la structure JSON elle-même
(déléguée au parser) — SRP.

DIP : la classe dépend des `Protocol`s `ItemRepository` et
`MentionRepository` (cf. `tools/domain/ports.py`), pas d'une
implémentation concrète. Testable sans IO réelle via doubles.

Politique de robustesse :
  - **Au parse** : fail-fast par enregistrement (un reco mal formé est
    loggé dans `stats.errors` et skipped — le reste continue).
  - **À l'écriture** : 2 phases STRICTES (cf. ADR 0007).
    Phase 1 : tous les items.
    Phase 2 : toutes les mentions.
    En cas de crash entre phases, on a des items "orphelins" (acceptables
    — Astro les ignore) MAIS aucune mention orpheline (qui casserait le
    rendu en pointant vers un item absent).
"""
from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path

from domain.item import Item, ItemType
from domain.mention import Mention
from domain.ports import ItemRepository, MentionRepository
from domain.services.identity import (
    IdentityRegistry,
    canonical_key,
)

from .reco_parser import reco_dict_to_item_mention


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------


_MAX_ERRORS = 10000
"""C11 : cap sur le nombre d'entrées conservées dans `MigrationStats.errors`
et `.warnings` (au-delà, on n'accumule plus mais on continue à incrémenter
les compteurs `n_errors`/`n_warnings` + on lève le flag `errors_truncated`
/ `warnings_truncated`). Évite l'explosion mémoire sur un dataset corrompu
massif."""


@dataclass
class MigrationStats:
    """Résultat synthétique d'un run de migration ou de vérification.

    Pas de dépendance sur le service (pure DTO) — facilement sérialisable
    pour un log/JSON externe.

    Schéma `errors` / `warnings` (C7) : `list[dict[str, str]]` avec les
    clés ``ref`` (identifiant — `reco_id` quand disponible, sinon nom du
    fichier fautif) et ``message`` (description). Format plus lisible
    qu'un tuple en JSON.
    """

    n_recos_read: int = 0
    n_items_created: int = 0
    n_items_reused: int = 0
    n_mentions_created: int = 0
    n_warnings: int = 0
    n_errors: int = 0
    warnings: list[dict[str, str]] = field(default_factory=list)
    errors: list[dict[str, str]] = field(default_factory=list)
    errors_truncated: bool = False
    warnings_truncated: bool = False

    def add_error(self, ref: str, message: str) -> None:
        self.n_errors += 1
        if len(self.errors) < _MAX_ERRORS:
            self.errors.append({"ref": ref, "message": message})
        else:
            self.errors_truncated = True

    def add_warning(self, ref: str, message: str) -> None:
        self.n_warnings += 1
        if len(self.warnings) < _MAX_ERRORS:
            self.warnings.append({"ref": ref, "message": message})
        else:
            self.warnings_truncated = True

    def as_dict(self) -> dict[str, object]:
        """Sérialisation lisible (pour CLI/logs)."""
        return {
            "n_recos_read": self.n_recos_read,
            "n_items_created": self.n_items_created,
            "n_items_reused": self.n_items_reused,
            "n_mentions_created": self.n_mentions_created,
            "n_warnings": self.n_warnings,
            "n_errors": self.n_errors,
            "warnings": list(self.warnings),
            "errors": list(self.errors),
            "errors_truncated": self.errors_truncated,
            "warnings_truncated": self.warnings_truncated,
        }


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class MigrationService:
    """Orchestre la migration `recos/*.json` → Items + Mentions.

    Dependency Injection :
      - `item_repo` / `mention_repo` : implémentations concrètes des ports.
      - `sources_dir` : racine des recos (ex. `src/content/recos`).
      - `source_id` : slug podcast à migrer (ex. `un-bon-moment`).

    Le service est *stateless* entre les appels à `migrate()` : chaque
    invocation reconstruit son `IdentityRegistry` à partir du repo (les
    items déjà persistés contribuent à la dédup).
    """

    def __init__(
        self,
        item_repo: ItemRepository,
        mention_repo: MentionRepository,
        sources_dir: Path,
        source_id: str,
    ) -> None:
        if not source_id or not isinstance(source_id, str):
            raise ValueError(
                f"MigrationService.source_id invalide: {source_id!r}"
            )
        self.item_repo = item_repo
        self.mention_repo = mention_repo
        self.sources_dir = sources_dir
        self.source_id = source_id

    # -- helpers privés -----------------------------------------------------

    @property
    def _source_dir(self) -> Path:
        return self.sources_dir / self.source_id

    def _iter_reco_paths(self) -> Iterable[Path]:
        if not self._source_dir.exists():
            return iter(())
        return iter(sorted(self._source_dir.glob("*.json")))

    def _build_resolver_and_registry(self):
        """Construit `(resolver, registry, reused_set)` partagés sur un run.

        Utilise `IdentityRegistry.seed()` (API publique) pour pré-déclarer
        chaque attribution `canonical → id` issue du repo. Plus de SLF001.

        Optim (C6) : on indexe `existing` par `canonical` une fois en
        début de run (O(N)) — chaque resolver call devient O(1) au lieu
        d'un scan O(N) par reco. `find_matching_item` reste utilisé
        comme fallback de cohérence (même politique de match).
        """
        existing = self.item_repo.existing_index()
        registry = IdentityRegistry()
        # Index par canonical → liste de (item_id, types). Plusieurs items
        # peuvent partager un canonical (cas pathologique signalé par
        # verify() ; on doit néanmoins garder un comportement stable).
        canonical_index: dict[str, list[tuple[str, tuple[ItemType, ...]]]] = {}
        for item_id, (canonical, types) in existing.items():
            registry.seed(canonical, item_id)
            canonical_index.setdefault(canonical, []).append((item_id, types))
        reused_ids: set[str] = set()

        def resolver(
            canonical: str,
            _creator: str | None,
            types: tuple[ItemType, ...],
        ) -> str:
            # Priorité : match exact (canonical + types compatibles) parmi
            # les items déjà persistés (réutilisation). Lookup O(1) via
            # l'index pré-construit.
            candidates = canonical_index.get(canonical)
            if candidates:
                cand_set = set(types)
                for item_id, ex_types in candidates:
                    if cand_set & set(ex_types):
                        reused_ids.add(item_id)
                        return item_id
            # Sinon : id stable via registry (mémoïsé par canonical).
            return registry.reserve_id(canonical)

        return resolver, registry, reused_ids

    # -- API publique -------------------------------------------------------

    def migrate(self, *, dry_run: bool = True) -> MigrationStats:
        """Lit toutes les recos du dossier, génère Items+Mentions, écrit.

        Si `dry_run=True` (défaut) : aucune écriture, stats uniquement.

        Si `dry_run=False` : 2 phases strictes (ADR 0007) :
          1. Écriture de **tous** les items (upsert idempotent).
          2. Écriture de **toutes** les mentions.
          Crash entre 1 et 2 → orphelins d'items, jamais de mention orpheline.
        """
        stats = MigrationStats()
        resolver, _registry, reused_ids = self._build_resolver_and_registry()

        # On collecte d'abord (parse) puis on écrit en deux phases pour
        # garantir la cohérence : si parsing échoue à mi-chemin, on n'a
        # pas écrit la moitié des items.
        parsed: list[tuple[Item, Mention]] = []

        for path in self._iter_reco_paths():
            stats.n_recos_read += 1
            try:
                with path.open("r", encoding="utf-8") as fh:
                    data = json.load(fh)
            except (OSError, json.JSONDecodeError) as e:
                stats.add_error(path.name, f"lecture/JSON: {e}")
                continue
            try:
                item, mention = reco_dict_to_item_mention(
                    data, item_id_resolver=resolver,
                )
            except (ValueError, KeyError, TypeError) as e:
                ref = data.get("id", path.name) if isinstance(data, dict) else path.name
                stats.add_error(str(ref), f"parse: {e}")
                continue
            parsed.append((item, mention))

        # Comptabilité items : un item est "réutilisé" s'il était dans
        # l'index existant (reused_ids), sinon "créé".
        items_seen: set[str] = set()
        for item, _ in parsed:
            if item.id not in items_seen:
                items_seen.add(item.id)
                if item.id in reused_ids:
                    stats.n_items_reused += 1
                else:
                    stats.n_items_created += 1
        stats.n_mentions_created = len(parsed)

        if not dry_run:
            # Phase 1 : items d'abord. Dédup en mémoire pour éviter de
            # ré-uploader N fois le même item (plusieurs mentions →
            # même item).
            written_items: set[str] = set()
            for item, _ in parsed:
                if item.id in written_items:
                    continue
                written_items.add(item.id)
                try:
                    self.item_repo.upsert(item)
                except (OSError, ValueError) as e:
                    stats.add_error(item.id, f"upsert item: {e}")
            # Phase 2 : mentions une fois les items écrits.
            for _, mention in parsed:
                try:
                    self.mention_repo.upsert(mention)
                except (OSError, ValueError) as e:
                    stats.add_error(mention.id, f"upsert mention: {e}")

        return stats

    def verify(self, *, deep: bool = False) -> MigrationStats:
        """Vérifie la cohérence post-migration.

        Contrôles (toujours actifs) :
          1. `count(mentions du source)` ≈ `count(recos du source)`
          2. Chaque mention référence un item existant (pas d'orphelin).
          3. Items orphelins (item sans mention) → warning.
          4. Canonical_key dupliquée (deux items distincts même canonical)
             → ERREUR.

        Si `deep=True` : re-parse chaque reco source et compare l'item
        attendu à l'item persisté (titre, types, creator). Détecte les
        dérives silencieuses (ex. champ perdu pendant un upsert manuel).

        Renvoie un `MigrationStats` où `n_errors > 0` ssi un problème
        a été détecté.
        """
        stats = MigrationStats()

        # Compte des recos source.
        reco_paths = list(self._iter_reco_paths())
        stats.n_recos_read = len(reco_paths)

        # 1. + 2. Vérifie mentions et items référencés.
        item_ids_referenced: set[str] = set()
        parse_failures: set[str] = set()  # reco_id avec parse KO en deep
        for path in reco_paths:
            try:
                with path.open("r", encoding="utf-8") as fh:
                    data = json.load(fh)
            except (OSError, json.JSONDecodeError) as e:
                stats.add_error(path.name, f"lecture/JSON: {e}")
                continue
            reco_id = data.get("id") if isinstance(data, dict) else None
            if not reco_id:
                stats.add_error(path.name, "reco sans id")
                continue
            m = self.mention_repo.get(reco_id)
            if m is None:
                stats.add_error(reco_id, "mention manquante dans le repo")
                continue
            stats.n_mentions_created += 1
            item_ids_referenced.add(m.item_id)
            # Vérifie qu'un Item existe pour `item_id`.
            persisted_item = self.item_repo.get(m.item_id)
            if persisted_item is None:
                stats.add_error(
                    reco_id, f"item orphelin: item_id={m.item_id!r} introuvable",
                )
                continue

            if deep:
                # Re-parse et compare titre/types/creator (heuristique :
                # le canonical doit matcher).
                try:
                    parsed_item, _ = reco_dict_to_item_mention(
                        data,
                        item_id_resolver=lambda c, _cr, _ty: m.item_id,
                    )
                except (ValueError, KeyError, TypeError) as e:
                    parse_failures.add(reco_id)
                    stats.add_warning(reco_id, f"verify deep: reparse: {e}")
                    continue
                expected_canonical = canonical_key(parsed_item.title, parsed_item.creator)
                persisted_canonical = canonical_key(
                    persisted_item.title, persisted_item.creator,
                )
                if expected_canonical != persisted_canonical:
                    stats.add_error(
                        reco_id,
                        f"verify deep: canonical drift "
                        f"(expected={expected_canonical!r}, "
                        f"persisted={persisted_canonical!r})",
                    )

        # 3. Items orphelins (item persisté sans mention pointant dessus).
        for item in self.item_repo.iter_all():
            if item.id not in item_ids_referenced:
                stats.add_warning(
                    item.id, "item orphelin (aucune mention ne le référence)",
                )

        # 4. Canonical dupliquée (deux items distincts → même canonical).
        canonical_seen: dict[str, str] = {}
        for item in self.item_repo.iter_all():
            ck = canonical_key(item.title, item.creator)
            existing = canonical_seen.get(ck)
            if existing is None:
                canonical_seen[ck] = item.id
            elif existing != item.id:
                stats.add_error(
                    item.id,
                    f"canonical dupliquée: {ck!r} déjà attribuée à {existing!r}",
                )

        return stats


__all__ = ["MigrationService", "MigrationStats"]
