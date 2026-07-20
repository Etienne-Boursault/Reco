"""Tests de `tools.repository.migration.reco_to_item_mention.MigrationService`.

Utilise les vrais `ItemRepoJson` / `MentionRepoJson` (via `tmp_path`) pour
exercer le service en conditions proches de la prod, et des doubles
ciblés pour les cas où on veut isoler une trajectoire d'erreur.
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from domain.item import Item, ItemType
from domain.mention import Mention, MentionKind, MentionStatus, SourceRef
from domain.services.identity import canonical_key
from repository.item_repo import ItemRepoJson
from repository.mention_repo import MentionRepoJson
from repository.migration import MigrationService, MigrationStats

# ---------------------------------------------------------------------------
# Constantes & helpers
# ---------------------------------------------------------------------------

SOURCE = "un-bon-moment"
FIXTURE_BASE = Path(__file__).parent / "fixtures" / "migration"


def _copy_fixture(name: str, dest_root: Path) -> Path:
    """Copie `fixtures/migration/<name>/*` dans `dest_root/<SOURCE>/`."""
    src = FIXTURE_BASE / name
    dst = dest_root / SOURCE
    dst.mkdir(parents=True, exist_ok=True)
    for f in src.glob("*.json"):
        shutil.copy(f, dst / f.name)
    return dest_root


def _service(tmp_path: Path, fixture: str | None = None) -> tuple[
    MigrationService, ItemRepoJson, MentionRepoJson,
]:
    """Construit un service avec repos sur tmp_path."""
    recos_root = tmp_path / "recos"
    if fixture:
        _copy_fixture(fixture, recos_root)
    item_repo = ItemRepoJson(tmp_path / "items", SOURCE)
    mention_repo = MentionRepoJson(tmp_path / "mentions", SOURCE)
    svc = MigrationService(item_repo, mention_repo, recos_root, SOURCE)
    return svc, item_repo, mention_repo


# ---------------------------------------------------------------------------
# Constructeur
# ---------------------------------------------------------------------------


def test_migration_service_rejects_empty_source_id(tmp_path):
    item_repo = ItemRepoJson(tmp_path / "i", SOURCE)
    mention_repo = MentionRepoJson(tmp_path / "m", SOURCE)
    with pytest.raises(ValueError, match="source_id"):
        MigrationService(item_repo, mention_repo, tmp_path / "r", "")


def test_migration_service_rejects_non_str_source_id(tmp_path):
    item_repo = ItemRepoJson(tmp_path / "i", SOURCE)
    mention_repo = MentionRepoJson(tmp_path / "m", SOURCE)
    with pytest.raises(ValueError, match="source_id"):
        MigrationService(item_repo, mention_repo, tmp_path / "r", 42)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# migrate — cas vides
# ---------------------------------------------------------------------------


def test_migrate_empty_source_returns_zero_stats(tmp_path):
    svc, _i, _m = _service(tmp_path)  # pas de fixture
    stats = svc.migrate()
    assert stats.n_recos_read == 0
    assert stats.n_items_created == 0
    assert stats.n_mentions_created == 0
    assert stats.n_errors == 0


def test_migrate_missing_source_dir_returns_zero(tmp_path):
    svc, _i, _m = _service(tmp_path)
    # _source_dir n'existe carrément pas — _iter_reco_paths renvoie iter(())
    assert not svc._source_dir.exists()
    stats = svc.migrate()
    assert stats.n_recos_read == 0


# ---------------------------------------------------------------------------
# migrate — minimal
# ---------------------------------------------------------------------------


def test_migrate_single_reco_creates_item_and_mention(tmp_path):
    svc, item_repo, mention_repo = _service(tmp_path)
    # 1 reco minimal
    recos_root = tmp_path / "recos"
    d = recos_root / SOURCE
    d.mkdir(parents=True)
    (d / "0001.json").write_text(json.dumps({
        "id": "ubm-x1", "sourceId": SOURCE, "title": "Solo", "types": ["film"],
    }), encoding="utf-8")

    stats = svc.migrate(dry_run=False)
    assert stats.n_recos_read == 1
    assert stats.n_items_created == 1
    assert stats.n_items_reused == 0
    assert stats.n_mentions_created == 1
    assert stats.n_errors == 0

    # vérif disque
    mention = mention_repo.get("ubm-x1")
    assert mention is not None
    item = item_repo.get(mention.item_id)
    assert item is not None
    assert item.title == "Solo"


def test_migrate_minimal_fixture_three_distinct_items(tmp_path):
    svc, item_repo, mention_repo = _service(tmp_path, fixture="recos_minimal")
    stats = svc.migrate(dry_run=False)
    assert stats.n_recos_read == 3
    assert stats.n_items_created == 3
    assert stats.n_mentions_created == 3
    assert stats.n_errors == 0
    assert len(item_repo.list_all()) == 3


# ---------------------------------------------------------------------------
# Dedup
# ---------------------------------------------------------------------------


def test_migrate_dedup_fixture_reuses_item_across_recos(tmp_path):
    svc, item_repo, mention_repo = _service(tmp_path, fixture="recos_dedup")
    stats = svc.migrate(dry_run=False)
    assert stats.n_recos_read == 4
    # 0001 & 0002 partagent canonical_key → 1 item Titanic + 1 Dune + 1 Inception
    assert stats.n_items_created == 3
    assert stats.n_mentions_created == 4
    assert len(item_repo.list_all()) == 3
    # Les 2 mentions Titanic pointent vers le MÊME item.
    m1 = mention_repo.get("ubm-d01")
    m2 = mention_repo.get("ubm-d02")
    assert m1.item_id == m2.item_id


def test_migrate_two_recos_same_canonical_reuses_item_in_single_run(tmp_path):
    """Sans Item préexistant : les deux recos partagent le même nouveau id."""
    svc, item_repo, _m = _service(tmp_path)
    d = tmp_path / "recos" / SOURCE
    d.mkdir(parents=True)
    for i, suffix in enumerate(("aa", "bb"), start=1):
        (d / f"000{i}.json").write_text(json.dumps({
            "id": f"ubm-{suffix}", "sourceId": SOURCE,
            "title": "Memento", "creator": "Nolan", "types": ["film"],
        }), encoding="utf-8")
    stats = svc.migrate(dry_run=False)
    assert stats.n_items_created == 1
    assert stats.n_mentions_created == 2
    assert len(item_repo.list_all()) == 1


def test_migrate_with_preexisting_item_marks_as_reused(tmp_path):
    """Un Item déjà persisté avec même canonical → réutilisation."""
    svc, item_repo, _m = _service(tmp_path)
    # Pré-insère un Item Titanic.
    existing = Item(
        id="titanicid",
        types=(ItemType.FILM,),
        title="Titanic",
        creator="James Cameron",
    )
    item_repo.upsert(existing)
    # Recos qui matchent le canonical.
    d = tmp_path / "recos" / SOURCE
    d.mkdir(parents=True)
    (d / "0001.json").write_text(json.dumps({
        "id": "ubm-r1", "sourceId": SOURCE,
        "title": "Titanic", "creator": "James Cameron", "types": ["film"],
    }), encoding="utf-8")
    stats = svc.migrate(dry_run=False)
    assert stats.n_items_reused == 1
    assert stats.n_items_created == 0
    assert stats.n_mentions_created == 1


# ---------------------------------------------------------------------------
# Dry-run vs apply
# ---------------------------------------------------------------------------


def test_migrate_dry_run_writes_nothing(tmp_path):
    svc, item_repo, mention_repo = _service(tmp_path, fixture="recos_minimal")
    stats = svc.migrate(dry_run=True)
    # Stats remplies, mais disque vide côté items/mentions.
    assert stats.n_recos_read == 3
    assert stats.n_items_created == 3
    assert item_repo.list_all() == []
    assert mention_repo.get("ubm-0001") is None


def test_migrate_apply_writes_to_repo(tmp_path):
    svc, item_repo, mention_repo = _service(tmp_path, fixture="recos_minimal")
    svc.migrate(dry_run=False)
    assert len(item_repo.list_all()) == 3
    assert mention_repo.get("ubm-0001") is not None


# ---------------------------------------------------------------------------
# Idempotence
# ---------------------------------------------------------------------------


def test_migrate_idempotent(tmp_path):
    svc, item_repo, mention_repo = _service(tmp_path, fixture="recos_minimal")
    s1 = svc.migrate(dry_run=False)
    items_after_run1 = sorted(p.name for p in (tmp_path / "items" / SOURCE).glob("*.json"))
    s2 = svc.migrate(dry_run=False)
    items_after_run2 = sorted(p.name for p in (tmp_path / "items" / SOURCE).glob("*.json"))
    assert items_after_run1 == items_after_run2
    # Au 2e run, tous les items sont "reused".
    assert s2.n_items_reused == 3
    assert s2.n_items_created == 0
    # Au 1er run, ils étaient tous "created".
    assert s1.n_items_created == 3


# ---------------------------------------------------------------------------
# Robustesse — fichiers corrompus
# ---------------------------------------------------------------------------


def test_migrate_corrupted_reco_logged_and_skipped(tmp_path):
    svc, item_repo, _m = _service(tmp_path, fixture="recos_corrupted")
    stats = svc.migrate(dry_run=False)
    assert stats.n_recos_read == 2
    # bad.json → erreur de lecture/JSON
    # invalid.json → erreur de parse (title/types vides)
    assert stats.n_errors == 2
    assert stats.n_items_created == 0
    assert stats.n_mentions_created == 0
    # Un message d'erreur identifie chaque fichier fautif.
    refs = [e["ref"] for e in stats.errors]
    assert "bad.json" in refs
    assert "ubm-bad-01" in refs  # le 2e a un id valide → on l'utilise


def test_migrate_continues_after_error(tmp_path):
    """Erreurs n'arrêtent pas la migration des fichiers suivants."""
    svc, _i, mention_repo = _service(tmp_path)
    d = tmp_path / "recos" / SOURCE
    d.mkdir(parents=True)
    (d / "0001.json").write_text("not json", encoding="utf-8")
    (d / "0002.json").write_text(json.dumps({
        "id": "ubm-ok", "sourceId": SOURCE, "title": "OK", "types": ["film"],
    }), encoding="utf-8")
    stats = svc.migrate(dry_run=False)
    assert stats.n_errors == 1
    assert stats.n_mentions_created == 1
    assert mention_repo.get("ubm-ok") is not None


def test_migrate_handles_non_dict_json_payload(tmp_path):
    """Un JSON qui est une liste (pas un dict) doit être loggé proprement."""
    svc, _i, _m = _service(tmp_path)
    d = tmp_path / "recos" / SOURCE
    d.mkdir(parents=True)
    (d / "list.json").write_text(json.dumps([1, 2, 3]), encoding="utf-8")
    stats = svc.migrate(dry_run=False)
    assert stats.n_errors == 1
    # Fallback ref = nom du fichier (pas d'id dans une liste).
    refs = [e["ref"] for e in stats.errors]
    assert "list.json" in refs


# ---------------------------------------------------------------------------
# Upsert errors propagation (cas pathologique)
# ---------------------------------------------------------------------------


class _BoomItemRepo:
    """Item repo qui lève sur upsert (test du chemin d'erreur)."""
    def __init__(self, base):
        self._base = base
    def get(self, _id): return self._base.get(_id)
    def exists(self, _id): return self._base.exists(_id)
    def list_all(self): return self._base.list_all()
    def iter_all(self): return self._base.iter_all()
    def existing_index(self): return self._base.existing_index()
    def upsert(self, _item):
        raise OSError("simulated disk full")
    def bulk_upsert(self, items):
        # Le test stocke en boucle ; conserver la sémantique d'erreur.
        for it in items:
            self.upsert(it)
        return (0, 0)
    def delete(self, _id): return self._base.delete(_id)


def test_migrate_upsert_error_recorded(tmp_path):
    """Une OSError au upsert apparaît dans stats.errors."""
    base = ItemRepoJson(tmp_path / "items", SOURCE)
    item_repo = _BoomItemRepo(base)
    mention_repo = MentionRepoJson(tmp_path / "mentions", SOURCE)
    svc = MigrationService(item_repo, mention_repo, tmp_path / "recos", SOURCE)

    d = tmp_path / "recos" / SOURCE
    d.mkdir(parents=True)
    (d / "0001.json").write_text(json.dumps({
        "id": "ubm-x", "sourceId": SOURCE, "title": "T", "types": ["film"],
    }), encoding="utf-8")
    stats = svc.migrate(dry_run=False)
    # Le parse OK, le upsert item KO → 1 erreur enregistrée (ref = item.id).
    # ADR 0007 : la phase 1 (items) échoue ; phase 2 (mentions) reste tentée
    # mais la mention sera orpheline → cas pathologique signalé par verify().
    assert stats.n_recos_read == 1
    assert stats.n_errors == 1
    # L'erreur référence l'item (phase 1), pas la mention (phase 2).
    entry = stats.errors[0]
    assert "upsert item" in entry["message"]


# ---------------------------------------------------------------------------
# verify
# ---------------------------------------------------------------------------


def test_verify_all_mentions_have_item(tmp_path):
    svc, _i, _m = _service(tmp_path, fixture="recos_minimal")
    svc.migrate(dry_run=False)
    stats = svc.verify()
    assert stats.n_recos_read == 3
    assert stats.n_mentions_created == 3
    assert stats.n_errors == 0


def test_verify_detects_missing_mention(tmp_path):
    """Si une mention attendue n'est pas dans le repo → erreur."""
    svc, _i, _m = _service(tmp_path, fixture="recos_minimal")
    # On NE migre PAS → toutes les mentions sont absentes.
    stats = svc.verify()
    assert stats.n_recos_read == 3
    assert stats.n_errors == 3
    assert all("mention manquante" in e["message"] for e in stats.errors)


def test_verify_detects_orphan_item(tmp_path):
    """Une mention pointant vers un item_id absent → erreur d'orphelin."""
    svc, item_repo, mention_repo = _service(tmp_path, fixture="recos_minimal")
    svc.migrate(dry_run=False)
    # Force le drame : on écrase une mention avec un item_id bidon.
    orphan = Mention(
        id="ubm-0001",
        item_id="ghost001",
        source_ref=SourceRef(source_id=SOURCE),
    )
    mention_repo.upsert(orphan)
    stats = svc.verify()
    # Au moins une erreur d'orphelin.
    assert any("orphelin" in e["message"] for e in stats.errors)


def test_verify_with_corrupted_reco(tmp_path):
    svc, _i, _m = _service(tmp_path, fixture="recos_corrupted")
    stats = svc.verify()
    # bad.json → erreur JSON ; invalid.json → "reco sans id" si on est strict,
    # mais comme invalid a bien un id, c'est plutôt "mention manquante".
    assert stats.n_errors >= 1
    refs = [e["ref"] for e in stats.errors]
    assert "bad.json" in refs


def test_verify_with_missing_reco_id(tmp_path):
    """Un JSON valide mais sans `id` est signalé."""
    svc, _i, _m = _service(tmp_path)
    d = tmp_path / "recos" / SOURCE
    d.mkdir(parents=True)
    (d / "no_id.json").write_text(json.dumps({"title": "x"}), encoding="utf-8")
    stats = svc.verify()
    assert any("sans id" in e["message"] for e in stats.errors)


# ---------------------------------------------------------------------------
# Complet — fixture avec tous les champs
# ---------------------------------------------------------------------------


def test_migrate_complete_fixture_preserves_all_data(tmp_path):
    svc, item_repo, mention_repo = _service(tmp_path, fixture="recos_complete")
    stats = svc.migrate(dry_run=False)
    assert stats.n_recos_read == 5
    assert stats.n_errors == 0
    # Mortel : externalIds + extractionHistory + watchProvider.
    m = mention_repo.get("ubm-c01")
    assert m.recommended_by == "Hakim Jemili"
    assert m.status == MentionStatus.VALIDATED
    assert m.extraction_history[0].llm_model == "claude-haiku-4-5"
    assert m.extraction_history[0].extra["timestamp_at_extraction"] == "00:58:17"
    item = item_repo.get(m.item_id)
    assert item.external_ids.tmdb == 94801
    assert item.watch_providers[0].name == "Netflix"
    # ADR 0006 : spectacle/lieu/video préservés en types first-class.
    expected_legacy = {
        "ubm-c02": ItemType.SHOW,
        "ubm-c03": ItemType.PLACE,
        "ubm-c05": ItemType.VIDEO,
    }
    for rid, expected_type in expected_legacy.items():
        mm = mention_repo.get(rid)
        ii = item_repo.get(mm.item_id)
        assert expected_type in ii.types, (
            f"{rid}: attendu {expected_type} dans {ii.types}"
        )
    # citation préservée
    c3 = mention_repo.get("ubm-c03")
    assert c3.kind == MentionKind.CITATION
    assert c3.status == MentionStatus.DISCARDED


# ---------------------------------------------------------------------------
# MigrationStats — DTO
# ---------------------------------------------------------------------------


def test_migration_stats_as_dict_round_trip():
    s = MigrationStats()
    s.n_recos_read = 5
    s.add_error("x", "boom")
    d = s.as_dict()
    assert d["n_recos_read"] == 5
    assert d["n_errors"] == 1
    assert d["errors"] == [{"ref": "x", "message": "boom"}]


def test_migration_stats_defaults_empty():
    s = MigrationStats()
    assert s.as_dict() == {
        "n_recos_read": 0,
        "n_items_created": 0,
        "n_items_reused": 0,
        "n_mentions_created": 0,
        "n_warnings": 0,
        "n_errors": 0,
        "warnings": [],
        "errors": [],
        "errors_truncated": False,
        "warnings_truncated": False,
    }


# ---------------------------------------------------------------------------
# Canonical key invariant (smoke)
# ---------------------------------------------------------------------------


def test_canonical_key_invariant_used_for_dedup(tmp_path):
    """Vérifie que la dédup utilise canonical_key (et pas l'égalité brute de titre)."""
    svc, _item_repo, mention_repo = _service(tmp_path)
    d = tmp_path / "recos" / SOURCE
    d.mkdir(parents=True)
    # "Mémo" vs "Memo" — diacritiques canonisés.
    (d / "0001.json").write_text(json.dumps({
        "id": "ubm-a", "sourceId": SOURCE, "title": "Mémo",
        "creator": "X", "types": ["film"],
    }), encoding="utf-8")
    (d / "0002.json").write_text(json.dumps({
        "id": "ubm-b", "sourceId": SOURCE, "title": "Memo",
        "creator": "X", "types": ["film"],
    }), encoding="utf-8")
    svc.migrate(dry_run=False)
    # Les canonical keys sont identiques.
    assert canonical_key("Mémo", "X") == canonical_key("Memo", "X")
    a = mention_repo.get("ubm-a")
    b = mention_repo.get("ubm-b")
    assert a.item_id == b.item_id


# ---------------------------------------------------------------------------
# A3 — Vraies deux phases (items puis mentions)
# ---------------------------------------------------------------------------


def test_migration_phase1_then_phase2(tmp_path):
    """L'ordre observable des upserts : tous les items, puis toutes les mentions.

    Capture la séquence via des spies pour vérifier l'invariant ADR 0007.
    """
    svc, item_repo, mention_repo = _service(tmp_path, fixture="recos_minimal")
    sequence: list[tuple[str, str]] = []

    real_item_upsert = item_repo.upsert
    real_mention_upsert = mention_repo.upsert

    def spy_item_upsert(item):
        sequence.append(("item", item.id))
        return real_item_upsert(item)

    def spy_mention_upsert(m):
        sequence.append(("mention", m.id))
        return real_mention_upsert(m)

    item_repo.upsert = spy_item_upsert  # type: ignore[method-assign]
    mention_repo.upsert = spy_mention_upsert  # type: ignore[method-assign]

    svc.migrate(dry_run=False)

    # Toutes les écritures items précèdent strictement la première mention.
    kinds = [k for k, _ in sequence]
    first_mention = kinds.index("mention")
    assert all(k == "item" for k in kinds[:first_mention])
    assert all(k == "mention" for k in kinds[first_mention:])


def test_crash_after_items_phase_leaves_no_orphan_mentions(tmp_path):
    """Si le crash survient APRÈS la phase items (au début de la phase
    mentions), on a des items orphelins (acceptable) mais ZÉRO mention
    pointant vers du vide.
    """
    svc, item_repo, mention_repo = _service(tmp_path, fixture="recos_minimal")

    real_mention_upsert = mention_repo.upsert
    calls = {"n": 0}

    def crash_after_first(m):
        calls["n"] += 1
        if calls["n"] >= 2:
            raise OSError("simulated crash during mentions phase")
        return real_mention_upsert(m)

    mention_repo.upsert = crash_after_first  # type: ignore[method-assign]
    stats = svc.migrate(dry_run=False)

    # Tous les items écrits.
    assert len(item_repo.list_all()) >= 1
    # Au moins une mention écrite, le crash est signalé en error.
    assert stats.n_errors >= 1
    # Critère ADR 0007 : aucune mention persistée ne pointe vers un item absent.
    for m in mention_repo.list_all():
        assert item_repo.get(m.item_id) is not None, (
            f"mention {m.id} pointe vers item {m.item_id!r} absent"
        )


# ---------------------------------------------------------------------------
# A4 — verify() étendu (orphelins, canonical dup, deep)
# ---------------------------------------------------------------------------


def test_verify_detects_item_without_mention(tmp_path):
    """Un item persisté sans mention qui le référence → warning."""
    svc, item_repo, _m = _service(tmp_path, fixture="recos_minimal")
    svc.migrate(dry_run=False)
    # Ajoute un item orphelin (aucune mention ne le référence).
    orphan = Item(id="orphan01", types=(ItemType.FILM,), title="Orphan")
    item_repo.upsert(orphan)
    stats = svc.verify()
    assert stats.n_warnings >= 1
    assert any(
        "orphan01" in w["ref"] and "orphelin" in w["message"]
        for w in stats.warnings
    )


def test_verify_detects_duplicate_canonical(tmp_path):
    """Deux items distincts avec même canonical_key → ERREUR."""
    svc, item_repo, _m = _service(tmp_path, fixture="recos_minimal")
    svc.migrate(dry_run=False)
    # Force deux items différents même titre+creator → même canonical.
    a = Item(id="dup00001", types=(ItemType.FILM,), title="Same", creator="X")
    b = Item(id="dup00002", types=(ItemType.FILM,), title="Same", creator="X")
    item_repo.upsert(a)
    item_repo.upsert(b)
    stats = svc.verify()
    assert any("canonical dupliquée" in e["message"] for e in stats.errors)


def test_verify_clean_dataset_zero_errors(tmp_path):
    """Un dataset propre passe verify() sans erreur ni warning."""
    svc, _i, _m = _service(tmp_path, fixture="recos_minimal")
    svc.migrate(dry_run=False)
    stats = svc.verify()
    assert stats.n_errors == 0
    assert stats.n_warnings == 0


def test_verify_deep_reparse_no_drift(tmp_path):
    """verify(deep=True) sur un dataset propre → 0 erreur."""
    svc, _i, _m = _service(tmp_path, fixture="recos_minimal")
    svc.migrate(dry_run=False)
    stats = svc.verify(deep=True)
    assert stats.n_errors == 0


def test_verify_deep_reparse_failure_emits_warning(tmp_path):
    """Si la reco source est devenue invalide APRÈS migration, deep
    re-parse échoue → warning (pas erreur)."""
    svc, _i, _m = _service(tmp_path, fixture="recos_minimal")
    svc.migrate(dry_run=False)
    # Corrompt une reco source (mais valid JSON, juste champ types vide).
    reco_dir = tmp_path / "recos" / SOURCE
    target = sorted(reco_dir.glob("*.json"))[0]
    data = json.loads(target.read_text("utf-8"))
    data["types"] = []  # types vide → reco_parser raise ValueError
    target.write_text(json.dumps(data), encoding="utf-8")
    stats = svc.verify(deep=True)
    assert stats.n_warnings >= 1
    assert any("reparse" in w["message"] for w in stats.warnings)


def test_verify_deep_detects_canonical_drift(tmp_path):
    """Si quelqu'un a écrasé manuellement le titre persisté, deep doit
    le détecter (canonical de l'item persisté ≠ celui de la reco source).
    """
    svc, item_repo, _m = _service(tmp_path, fixture="recos_minimal")
    svc.migrate(dry_run=False)
    # Récupère un item et le ré-écrit avec un titre divergent.
    items = item_repo.list_all()
    assert items
    victim = items[0]
    tampered = Item(
        id=victim.id,
        types=victim.types,
        title="Tampered Title",
        creator=victim.creator,
    )
    item_repo.upsert(tampered)
    stats = svc.verify(deep=True)
    assert any("drift" in e["message"] for e in stats.errors)


# ---------------------------------------------------------------------------
# A5 — Normalisation timestamps legacy MM:SS → 00:MM:SS
# ---------------------------------------------------------------------------


def test_migration_legacy_mmss_timestamps_pass(tmp_path):
    """Une reco avec timestamp `MM:SS` legacy doit migrer sans erreur."""
    svc, _i, mention_repo = _service(tmp_path)
    d = tmp_path / "recos" / SOURCE
    d.mkdir(parents=True)
    (d / "0001.json").write_text(json.dumps({
        "id": "ubm-ts", "sourceId": SOURCE, "title": "T", "types": ["film"],
        "timestamp": "12:34",  # legacy MM:SS
    }), encoding="utf-8")
    stats = svc.migrate(dry_run=False)
    assert stats.n_errors == 0
    m = mention_repo.get("ubm-ts")
    assert m.source_ref.timestamp == "00:12:34"


# ---------------------------------------------------------------------------
# C7 — schéma errors/warnings: list[dict[str,str]]
# ---------------------------------------------------------------------------


def test_migration_stats_add_warning_uses_dict_schema():
    s = MigrationStats()
    s.add_warning("ref-x", "watch-out")
    assert s.warnings == [{"ref": "ref-x", "message": "watch-out"}]
    assert s.n_warnings == 1


# ---------------------------------------------------------------------------
# C11 — Cap errors/warnings à _MAX_ERRORS
# ---------------------------------------------------------------------------


def test_migration_stats_errors_capped_at_max():
    from repository.migration.reco_to_item_mention import _MAX_ERRORS
    s = MigrationStats()
    # Au-delà du cap, on incrémente le compteur mais on n'accumule plus.
    for i in range(_MAX_ERRORS + 5):
        s.add_error(f"r{i}", "boom")
    assert s.n_errors == _MAX_ERRORS + 5
    assert len(s.errors) == _MAX_ERRORS
    assert s.errors_truncated is True
    # as_dict expose le flag.
    assert s.as_dict()["errors_truncated"] is True


def test_migration_stats_warnings_capped_at_max():
    from repository.migration.reco_to_item_mention import _MAX_ERRORS
    s = MigrationStats()
    for i in range(_MAX_ERRORS + 2):
        s.add_warning(f"r{i}", "meh")
    assert s.n_warnings == _MAX_ERRORS + 2
    assert len(s.warnings) == _MAX_ERRORS
    assert s.warnings_truncated is True
    assert s.as_dict()["warnings_truncated"] is True


# ---------------------------------------------------------------------------
# C6 — Resolver indexé par canonical (O(1) lookup)
# ---------------------------------------------------------------------------


def test_resolver_canonical_index_reuses_item_with_matching_types(tmp_path):
    """Réutilisation basée sur canonical + intersection de types (O(1) lookup)."""
    svc, item_repo, _m = _service(tmp_path)
    existing = Item(
        id="exist0001",
        types=(ItemType.FILM, ItemType.SERIES),
        title="Memo",
        creator="X",
    )
    item_repo.upsert(existing)
    d = tmp_path / "recos" / SOURCE
    d.mkdir(parents=True)
    (d / "0001.json").write_text(json.dumps({
        "id": "ubm-rr", "sourceId": SOURCE,
        "title": "Memo", "creator": "X", "types": ["film"],
    }), encoding="utf-8")
    stats = svc.migrate(dry_run=False)
    assert stats.n_items_reused == 1
    assert stats.n_items_created == 0


def test_resolver_canonical_index_no_type_intersection_creates_new(tmp_path):
    """Même canonical mais types disjoints → on crée un nouvel item."""
    svc, item_repo, _m = _service(tmp_path)
    existing = Item(
        id="exist0002",
        types=(ItemType.BOOK,),
        title="Memo",
        creator="X",
    )
    item_repo.upsert(existing)
    d = tmp_path / "recos" / SOURCE
    d.mkdir(parents=True)
    (d / "0001.json").write_text(json.dumps({
        "id": "ubm-rr", "sourceId": SOURCE,
        "title": "Memo", "creator": "X", "types": ["film"],
    }), encoding="utf-8")
    stats = svc.migrate(dry_run=False)
    # Pas de match → nouvel item créé.
    assert stats.n_items_created == 1
    assert stats.n_items_reused == 0
