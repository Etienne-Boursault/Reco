"""Tests de `tools.repository.item_repo.ItemRepoJson` — IO atomic sur disque.

Utilise `tmp_path` (pas de Mock). Couverture 100% requise.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from domain.item import Item, ItemType
from domain.services.identity import canonical_key
from repository.item_repo import ItemRepoJson


SOURCE = "un-bon-moment"


def _mk(item_id: str = "abc12345", **kw) -> Item:
    base = dict(id=item_id, types=(ItemType.FILM,), title="Titanic")
    base.update(kw)
    return Item(**base)


# ---------------------------------------------------------------------------
# get
# ---------------------------------------------------------------------------


def test_get_returns_none_when_file_missing(tmp_path):
    repo = ItemRepoJson(tmp_path, SOURCE)
    assert repo.get("abc12345") is None


def test_get_returns_none_when_dir_missing(tmp_path):
    # même si la racine n'a jamais été créée
    repo = ItemRepoJson(tmp_path / "nope", SOURCE)
    assert repo.get("abc12345") is None


def test_get_returns_item_after_upsert(tmp_path):
    repo = ItemRepoJson(tmp_path, SOURCE)
    item = _mk()
    repo.upsert(item)
    assert repo.get("abc12345") == item


def test_get_returns_none_on_corrupted_json(tmp_path):
    repo = ItemRepoJson(tmp_path, SOURCE)
    # Crée un fichier illisible
    d = tmp_path / SOURCE
    d.mkdir(parents=True)
    (d / "abc12345.json").write_text("{not valid json", encoding="utf-8")
    assert repo.get("abc12345") is None


def test_get_returns_none_on_invalid_item_payload(tmp_path):
    repo = ItemRepoJson(tmp_path, SOURCE)
    d = tmp_path / SOURCE
    d.mkdir(parents=True)
    # JSON valide mais Item invalide (id ne matche pas regex)
    (d / "abc12345.json").write_text(
        json.dumps({"id": "BAD!", "types": ["film"], "title": "T"}),
        encoding="utf-8",
    )
    assert repo.get("abc12345") is None


# ---------------------------------------------------------------------------
# upsert
# ---------------------------------------------------------------------------


def test_upsert_creates_new_file(tmp_path):
    repo = ItemRepoJson(tmp_path, SOURCE)
    created = repo.upsert(_mk())
    assert created is True
    assert (tmp_path / SOURCE / "abc12345.json").exists()


def test_upsert_returns_false_when_no_change(tmp_path):
    repo = ItemRepoJson(tmp_path, SOURCE)
    item = _mk()
    assert repo.upsert(item) is True
    # Deuxième upsert identique → False (idempotent)
    assert repo.upsert(item) is False


def test_upsert_updates_existing_file(tmp_path):
    repo = ItemRepoJson(tmp_path, SOURCE)
    repo.upsert(_mk(title="Old"))
    written = repo.upsert(_mk(title="New"))
    assert written is True
    assert repo.get("abc12345").title == "New"


def test_upsert_writes_camelcase_keys(tmp_path):
    repo = ItemRepoJson(tmp_path, SOURCE)
    repo.upsert(_mk())
    data = json.loads((tmp_path / SOURCE / "abc12345.json").read_text("utf-8"))
    assert "schemaVersion" in data


def test_upsert_semantic_idempotence_indent_variation(tmp_path):
    """C1 — Idempotence robuste : un fichier avec indent/sort différents
    mais sémantiquement identique ne déclenche pas de ré-écriture."""
    repo = ItemRepoJson(tmp_path, SOURCE)
    item = _mk()
    repo.upsert(item)
    path = tmp_path / SOURCE / "abc12345.json"
    # Réécris le fichier avec un autre formatage (no indent, no sort).
    payload = json.loads(path.read_text(encoding="utf-8"))
    path.write_text(json.dumps(payload), encoding="utf-8")
    mtime_before = path.stat().st_mtime_ns
    # L'upsert doit détecter la sémantique identique → False, aucun touch.
    assert repo.upsert(item) is False
    assert path.stat().st_mtime_ns == mtime_before


def test_upsert_overwrites_corrupted_existing(tmp_path):
    """C1 — Si le fichier existe mais est corrompu, l'upsert l'écrase."""
    repo = ItemRepoJson(tmp_path, SOURCE)
    d = tmp_path / SOURCE
    d.mkdir(parents=True)
    path = d / "abc12345.json"
    path.write_text("{not valid json", encoding="utf-8")
    assert repo.upsert(_mk()) is True
    # Maintenant valide.
    assert repo.get("abc12345") is not None


def test_upsert_atomic_failure_keeps_old_file(tmp_path, monkeypatch):
    """Si atomic_write_text raise, le fichier existant doit rester intact."""
    repo = ItemRepoJson(tmp_path, SOURCE)
    repo.upsert(_mk(title="Original"))
    original_path = tmp_path / SOURCE / "abc12345.json"
    original_bytes = original_path.read_bytes()

    import repository._base as base_mod

    def boom(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(base_mod, "atomic_write_text", boom)
    with pytest.raises(OSError):
        repo.upsert(_mk(title="New"))
    assert original_path.read_bytes() == original_bytes


# ---------------------------------------------------------------------------
# list_all
# ---------------------------------------------------------------------------


def test_list_all_returns_empty_when_dir_missing(tmp_path):
    repo = ItemRepoJson(tmp_path, SOURCE)
    assert repo.list_all() == []


def test_list_all_returns_empty_when_dir_empty(tmp_path):
    (tmp_path / SOURCE).mkdir(parents=True)
    repo = ItemRepoJson(tmp_path, SOURCE)
    assert repo.list_all() == []


def test_list_all_returns_all_items(tmp_path):
    repo = ItemRepoJson(tmp_path, SOURCE)
    a = _mk("abc12345", title="A")
    b = _mk("def67890", title="B")
    repo.upsert(a)
    repo.upsert(b)
    items = repo.list_all()
    assert {i.id for i in items} == {"abc12345", "def67890"}


def test_list_all_skips_corrupted_files(tmp_path):
    repo = ItemRepoJson(tmp_path, SOURCE)
    repo.upsert(_mk())
    # Ajoute un fichier corrompu — list_all doit l'ignorer
    (tmp_path / SOURCE / "broken.json").write_text("{nope", encoding="utf-8")
    items = repo.list_all()
    assert len(items) == 1
    assert items[0].id == "abc12345"


def test_list_all_ignores_non_json_files(tmp_path):
    repo = ItemRepoJson(tmp_path, SOURCE)
    repo.upsert(_mk())
    (tmp_path / SOURCE / "README.md").write_text("# notes", encoding="utf-8")
    assert len(repo.list_all()) == 1


# ---------------------------------------------------------------------------
# existing_index
# ---------------------------------------------------------------------------


def test_existing_index_empty_when_no_items(tmp_path):
    repo = ItemRepoJson(tmp_path, SOURCE)
    assert dict(repo.existing_index()) == {}


def test_existing_index_returns_canonical_key_per_item(tmp_path):
    repo = ItemRepoJson(tmp_path, SOURCE)
    item = _mk(title="Titanic", creator="James Cameron")
    repo.upsert(item)
    idx = repo.existing_index()
    assert "abc12345" in idx
    canonical, types = idx["abc12345"]
    # D9 — appel direct (l'ancienne expression "Titanic" and "James Cameron"
    # exploitait la sémantique `and` Python pour renvoyer "James Cameron",
    # ce qui était fragile et trompeur).
    assert canonical == canonical_key("Titanic", "James Cameron")
    assert types == (ItemType.FILM,)


def test_existing_index_with_corrupted(tmp_path):
    """D10 — Un fichier corrompu dans le dossier ne fait pas planter
    `existing_index` ; il est simplement omis (cf. politique défensive).
    """
    repo = ItemRepoJson(tmp_path, SOURCE)
    repo.upsert(_mk(item_id="abc12345", title="Titanic", creator="JC"))
    # Crée un fichier corrompu à côté.
    (tmp_path / SOURCE / "deadbeef.json").write_text(
        "{not valid", encoding="utf-8"
    )
    idx = repo.existing_index()
    assert "abc12345" in idx
    assert "deadbeef" not in idx


# ---------------------------------------------------------------------------
# Path validation / sécurité
# ---------------------------------------------------------------------------


def test_get_validates_id_format(tmp_path):
    """get() avec un id invalide doit lever (validation au boundary)."""
    repo = ItemRepoJson(tmp_path, SOURCE)
    with pytest.raises(ValueError):
        repo.get("Invalid!")


def test_get_blocks_path_traversal(tmp_path):
    repo = ItemRepoJson(tmp_path, SOURCE)
    with pytest.raises(ValueError):
        repo.get("../evil")


def test_get_blocks_absolute_path_attempt(tmp_path):
    repo = ItemRepoJson(tmp_path, SOURCE)
    with pytest.raises(ValueError):
        repo.get("/etc/passwd")


# ---------------------------------------------------------------------------
# Conformité au Protocol
# ---------------------------------------------------------------------------


def test_upsert_overwrites_when_existing_unreadable(tmp_path, monkeypatch):
    """Si la lecture du fichier existant échoue (OSError), l'upsert écrase
    quand même au lieu de bailler.
    """
    repo = ItemRepoJson(tmp_path, SOURCE)
    repo.upsert(_mk(title="Old"))
    path = tmp_path / SOURCE / "abc12345.json"

    real_read_text = Path.read_text

    def flaky_read_text(self, *args, **kwargs):
        if self == path:
            raise OSError("io fail")
        return real_read_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", flaky_read_text)
    written = repo.upsert(_mk(title="New"))
    assert written is True
    monkeypatch.undo()
    assert repo.get("abc12345").title == "New"


def test_repo_implements_item_repository_protocol(tmp_path):
    from domain.ports import ItemRepository
    repo: ItemRepository = ItemRepoJson(tmp_path, SOURCE)
    # Si l'attribution ci-dessus passe statiquement et que ces appels marchent
    # à runtime, le contrat est respecté.
    assert repo.get("abc12345") is None
    assert repo.list_all() == []
    assert dict(repo.existing_index()) == {}


# ---------------------------------------------------------------------------
# A1 — exists / iter_all / bulk_upsert / delete
# ---------------------------------------------------------------------------


def test_exists_false_when_missing(tmp_path):
    repo = ItemRepoJson(tmp_path, SOURCE)
    assert repo.exists("abc12345") is False


def test_exists_true_after_upsert(tmp_path):
    repo = ItemRepoJson(tmp_path, SOURCE)
    repo.upsert(_mk())
    assert repo.exists("abc12345") is True


def test_exists_validates_id(tmp_path):
    repo = ItemRepoJson(tmp_path, SOURCE)
    with pytest.raises(ValueError):
        repo.exists("../evil")


def test_iter_all_streaming_yields_items(tmp_path):
    repo = ItemRepoJson(tmp_path, SOURCE)
    repo.upsert(_mk("abc12345", title="A"))
    repo.upsert(_mk("def67890", title="B"))
    out = list(repo.iter_all())
    assert {i.id for i in out} == {"abc12345", "def67890"}


def test_iter_all_empty_when_dir_missing(tmp_path):
    repo = ItemRepoJson(tmp_path, SOURCE)
    assert list(repo.iter_all()) == []


def test_iter_all_skips_corrupted(tmp_path):
    repo = ItemRepoJson(tmp_path, SOURCE)
    repo.upsert(_mk())
    (tmp_path / SOURCE / "broken.json").write_text("{nope", encoding="utf-8")
    out = list(repo.iter_all())
    assert len(out) == 1


def test_bulk_upsert_creates_then_updates(tmp_path):
    repo = ItemRepoJson(tmp_path, SOURCE)
    a = _mk("abc12345", title="A")
    b = _mk("def67890", title="B")
    created, updated = repo.bulk_upsert([a, b])
    assert (created, updated) == (2, 0)
    # Re-bulk : idempotent (no write needed).
    created2, updated2 = repo.bulk_upsert([a, b])
    assert (created2, updated2) == (0, 0)
    # Mise à jour réelle.
    b2 = _mk("def67890", title="B2")
    created3, updated3 = repo.bulk_upsert([b2])
    assert (created3, updated3) == (0, 1)


def test_delete_removes_file(tmp_path):
    repo = ItemRepoJson(tmp_path, SOURCE)
    repo.upsert(_mk())
    assert repo.delete("abc12345") is True
    assert repo.exists("abc12345") is False


def test_delete_returns_false_when_missing(tmp_path):
    repo = ItemRepoJson(tmp_path, SOURCE)
    assert repo.delete("abc12345") is False


def test_delete_validates_id(tmp_path):
    repo = ItemRepoJson(tmp_path, SOURCE)
    with pytest.raises(ValueError):
        repo.delete("../evil")


def test_delete_returns_false_on_oserror(tmp_path, monkeypatch):
    repo = ItemRepoJson(tmp_path, SOURCE)
    repo.upsert(_mk())
    def boom(self):
        raise OSError("perm denied")
    monkeypatch.setattr(Path, "unlink", boom)
    assert repo.delete("abc12345") is False


# ---------------------------------------------------------------------------
# A10 — existing_index immutable
# ---------------------------------------------------------------------------


def test_existing_index_is_immutable(tmp_path):
    repo = ItemRepoJson(tmp_path, SOURCE)
    repo.upsert(_mk())
    idx = repo.existing_index()
    with pytest.raises(TypeError):
        idx["new"] = ("k", (ItemType.FILM,))  # type: ignore[index]


# ---------------------------------------------------------------------------
# A9 — Atomic upsert tested via os.replace failure
# ---------------------------------------------------------------------------


def test_upsert_atomic_failure_keeps_old_file_via_os_replace(tmp_path, monkeypatch):
    """Si `os.replace` échoue, le fichier original reste intact."""
    import os
    repo = ItemRepoJson(tmp_path, SOURCE)
    original = _mk(title="Original")
    repo.upsert(original)
    path = tmp_path / SOURCE / "abc12345.json"
    original_bytes = path.read_bytes()

    real_replace = os.replace
    def flaky_replace(src, dst):
        if str(dst) == str(path):
            raise OSError("simulated replace failure")
        return real_replace(src, dst)
    monkeypatch.setattr(os, "replace", flaky_replace)

    new_item = _mk(title="New")
    with pytest.raises(OSError, match="simulated replace failure"):
        repo.upsert(new_item)
    # L'original n'a pas été altéré.
    assert path.read_bytes() == original_bytes


# ---------------------------------------------------------------------------
# source_id path-traversal guard
# ---------------------------------------------------------------------------


def test_source_id_must_be_slug(tmp_path):
    with pytest.raises(ValueError, match="source_id"):
        ItemRepoJson(tmp_path, "../evil")


def test_source_id_rejects_empty(tmp_path):
    with pytest.raises(ValueError, match="source_id"):
        ItemRepoJson(tmp_path, "")


# ---------------------------------------------------------------------------
# Protocol runtime check (B5)
# ---------------------------------------------------------------------------


def test_repo_isinstance_item_repository_runtime(tmp_path):
    from domain.ports import ItemRepository
    repo = ItemRepoJson(tmp_path, SOURCE)
    assert isinstance(repo, ItemRepository)
