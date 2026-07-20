"""Tests de `tools.repository.mention_repo.MentionRepoJson` — couverture 100%."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from domain.mention import (
    Mention,
    MentionKind,
    MentionStatus,
    SourceRef,
    TranscriptSource,
)
from repository.mention_repo import MentionRepoJson


SOURCE = "un-bon-moment"


def _mk(mention_id: str = "m-001", item_id: str = "abc12345", **kw) -> Mention:
    base = dict(
        id=mention_id,
        item_id=item_id,
        source_ref=SourceRef(source_id=SOURCE, episode_guid="e1"),
    )
    base.update(kw)
    return Mention(**base)


# ---------------------------------------------------------------------------
# get
# ---------------------------------------------------------------------------


def test_get_returns_none_when_file_missing(tmp_path):
    repo = MentionRepoJson(tmp_path, SOURCE)
    assert repo.get("m-001") is None


def test_get_returns_none_when_dir_missing(tmp_path):
    repo = MentionRepoJson(tmp_path / "nope", SOURCE)
    assert repo.get("m-001") is None


def test_get_returns_mention_after_upsert(tmp_path):
    repo = MentionRepoJson(tmp_path, SOURCE)
    m = _mk()
    repo.upsert(m)
    assert repo.get("m-001") == m


def test_get_returns_none_on_corrupted_json(tmp_path):
    repo = MentionRepoJson(tmp_path, SOURCE)
    d = tmp_path / SOURCE
    d.mkdir(parents=True)
    (d / "m-001.json").write_text("{not json", encoding="utf-8")
    assert repo.get("m-001") is None


def test_get_returns_none_on_invalid_payload(tmp_path):
    repo = MentionRepoJson(tmp_path, SOURCE)
    d = tmp_path / SOURCE
    d.mkdir(parents=True)
    (d / "m-001.json").write_text(
        json.dumps({"id": "m-1", "itemId": "BAD!"}), encoding="utf-8",
    )
    assert repo.get("m-001") is None


# ---------------------------------------------------------------------------
# upsert
# ---------------------------------------------------------------------------


def test_upsert_creates_new_file(tmp_path):
    repo = MentionRepoJson(tmp_path, SOURCE)
    assert repo.upsert(_mk()) is True
    assert (tmp_path / SOURCE / "m-001.json").exists()


def test_upsert_no_op_when_unchanged(tmp_path):
    repo = MentionRepoJson(tmp_path, SOURCE)
    m = _mk()
    assert repo.upsert(m) is True
    assert repo.upsert(m) is False


def test_upsert_updates_file(tmp_path):
    repo = MentionRepoJson(tmp_path, SOURCE)
    repo.upsert(_mk(quote="Old"))
    assert repo.upsert(_mk(quote="New")) is True
    assert repo.get("m-001").quote == "New"


def test_upsert_atomic_failure(tmp_path, monkeypatch):
    repo = MentionRepoJson(tmp_path, SOURCE)
    repo.upsert(_mk(quote="Original"))
    path = tmp_path / SOURCE / "m-001.json"
    original = path.read_bytes()
    import repository._base as base_mod
    monkeypatch.setattr(
        base_mod, "atomic_write_text",
        lambda *a, **k: (_ for _ in ()).throw(OSError("disk")),
    )
    with pytest.raises(OSError):
        repo.upsert(_mk(quote="New"))
    assert path.read_bytes() == original


def test_upsert_overwrites_when_existing_unreadable(tmp_path, monkeypatch):
    repo = MentionRepoJson(tmp_path, SOURCE)
    repo.upsert(_mk(quote="Old"))
    path = tmp_path / SOURCE / "m-001.json"
    real_read_text = Path.read_text

    def flaky(self, *args, **kwargs):
        if self == path:
            raise OSError("io fail")
        return real_read_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", flaky)
    assert repo.upsert(_mk(quote="New")) is True
    monkeypatch.undo()
    assert repo.get("m-001").quote == "New"


# ---------------------------------------------------------------------------
# list_for_item / list_for_episode
# ---------------------------------------------------------------------------


def test_list_for_item_filters_by_item_id(tmp_path):
    repo = MentionRepoJson(tmp_path, SOURCE)
    repo.upsert(_mk("m-1", item_id="abc12345"))
    repo.upsert(_mk("m-2", item_id="def67890"))
    repo.upsert(_mk("m-3", item_id="abc12345"))
    found = repo.list_for_item("abc12345")
    assert {m.id for m in found} == {"m-1", "m-3"}


def test_list_for_item_empty_when_no_match(tmp_path):
    repo = MentionRepoJson(tmp_path, SOURCE)
    repo.upsert(_mk("m-1", item_id="abc12345"))
    assert repo.list_for_item("def67890") == []


def test_list_for_item_empty_when_dir_missing(tmp_path):
    repo = MentionRepoJson(tmp_path / "nope", SOURCE)
    assert repo.list_for_item("abc12345") == []


def test_list_for_episode_filters_by_source_and_guid(tmp_path):
    repo = MentionRepoJson(tmp_path, SOURCE)
    repo.upsert(_mk(
        "m-1", source_ref=SourceRef(source_id=SOURCE, episode_guid="e1"),
    ))
    repo.upsert(_mk(
        "m-2", source_ref=SourceRef(source_id=SOURCE, episode_guid="e2"),
    ))
    repo.upsert(_mk(
        "m-3", source_ref=SourceRef(source_id="other", episode_guid="e1"),
    ))
    found = repo.list_for_episode(SOURCE, "e1")
    assert {m.id for m in found} == {"m-1"}


def test_list_for_episode_empty(tmp_path):
    repo = MentionRepoJson(tmp_path, SOURCE)
    assert repo.list_for_episode(SOURCE, "e1") == []


def test_list_for_item_skips_corrupted(tmp_path):
    repo = MentionRepoJson(tmp_path, SOURCE)
    repo.upsert(_mk("m-1"))
    (tmp_path / SOURCE / "broken.json").write_text("{nope", encoding="utf-8")
    assert len(repo.list_for_item("abc12345")) == 1


# ---------------------------------------------------------------------------
# Path validation
# ---------------------------------------------------------------------------


def test_get_validates_id_format(tmp_path):
    repo = MentionRepoJson(tmp_path, SOURCE)
    with pytest.raises(ValueError):
        repo.get("Invalid!")


def test_get_blocks_path_traversal(tmp_path):
    repo = MentionRepoJson(tmp_path, SOURCE)
    with pytest.raises(ValueError):
        repo.get("../evil")


# ---------------------------------------------------------------------------
# Conformité Protocol
# ---------------------------------------------------------------------------


def test_repo_implements_mention_repository_protocol(tmp_path):
    from domain.ports import MentionRepository
    repo: MentionRepository = MentionRepoJson(tmp_path, SOURCE)
    assert repo.get("m-001") is None
    assert repo.list_for_item("abc12345") == []
    assert repo.list_for_episode(SOURCE, "e1") == []


# ---------------------------------------------------------------------------
# Disque : forme camelCase
# ---------------------------------------------------------------------------


def test_upsert_writes_camelcase(tmp_path):
    repo = MentionRepoJson(tmp_path, SOURCE)
    repo.upsert(_mk())
    data = json.loads(
        (tmp_path / SOURCE / "m-001.json").read_text("utf-8"),
    )
    assert "itemId" in data
    assert "sourceRef" in data
    assert data["sourceRef"]["sourceId"] == SOURCE


# ---------------------------------------------------------------------------
# A1 — exists / iter_all / list_all / bulk_upsert / delete
# ---------------------------------------------------------------------------


def test_exists_false_when_missing(tmp_path):
    repo = MentionRepoJson(tmp_path, SOURCE)
    assert repo.exists("m-001") is False


def test_exists_true_after_upsert(tmp_path):
    repo = MentionRepoJson(tmp_path, SOURCE)
    repo.upsert(_mk())
    assert repo.exists("m-001") is True


def test_exists_validates_id(tmp_path):
    repo = MentionRepoJson(tmp_path, SOURCE)
    with pytest.raises(ValueError):
        repo.exists("../evil")


def test_list_all_returns_all(tmp_path):
    repo = MentionRepoJson(tmp_path, SOURCE)
    repo.upsert(_mk("m-001"))
    repo.upsert(_mk("m-002"))
    out = repo.list_all()
    assert {m.id for m in out} == {"m-001", "m-002"}


def test_list_all_empty_when_dir_missing(tmp_path):
    repo = MentionRepoJson(tmp_path, SOURCE)
    assert repo.list_all() == []


def test_iter_all_streams(tmp_path):
    repo = MentionRepoJson(tmp_path, SOURCE)
    repo.upsert(_mk("m-001"))
    repo.upsert(_mk("m-002"))
    out = list(repo.iter_all())
    assert {m.id for m in out} == {"m-001", "m-002"}


def test_iter_all_empty_when_dir_missing(tmp_path):
    repo = MentionRepoJson(tmp_path, SOURCE)
    assert list(repo.iter_all()) == []


def test_bulk_upsert_creates_then_updates(tmp_path):
    repo = MentionRepoJson(tmp_path, SOURCE)
    a = _mk("m-001")
    b = _mk("m-002")
    created, updated = repo.bulk_upsert([a, b])
    assert (created, updated) == (2, 0)
    # Idempotent re-run.
    created2, updated2 = repo.bulk_upsert([a, b])
    assert (created2, updated2) == (0, 0)
    # Mise à jour réelle.
    b2 = _mk("m-002", quote="modified")
    created3, updated3 = repo.bulk_upsert([b2])
    assert (created3, updated3) == (0, 1)


def test_delete_removes_file(tmp_path):
    repo = MentionRepoJson(tmp_path, SOURCE)
    repo.upsert(_mk())
    assert repo.delete("m-001") is True
    assert repo.exists("m-001") is False


def test_delete_returns_false_when_missing(tmp_path):
    repo = MentionRepoJson(tmp_path, SOURCE)
    assert repo.delete("m-001") is False


def test_delete_validates_id(tmp_path):
    repo = MentionRepoJson(tmp_path, SOURCE)
    with pytest.raises(ValueError):
        repo.delete("../evil")


def test_delete_returns_false_on_oserror(tmp_path, monkeypatch):
    repo = MentionRepoJson(tmp_path, SOURCE)
    repo.upsert(_mk())
    def boom(self):
        raise OSError("perm denied")
    monkeypatch.setattr(Path, "unlink", boom)
    assert repo.delete("m-001") is False


# ---------------------------------------------------------------------------
# source_id path-traversal guard
# ---------------------------------------------------------------------------


def test_source_id_must_be_slug(tmp_path):
    with pytest.raises(ValueError, match="source_id"):
        MentionRepoJson(tmp_path, "../evil")


def test_source_id_rejects_empty(tmp_path):
    with pytest.raises(ValueError, match="source_id"):
        MentionRepoJson(tmp_path, "")


# ---------------------------------------------------------------------------
# A9 — Atomic upsert via os.replace failure
# ---------------------------------------------------------------------------


def test_upsert_atomic_failure_keeps_old_file_via_os_replace(tmp_path, monkeypatch):
    import os
    repo = MentionRepoJson(tmp_path, SOURCE)
    original = _mk(quote="original")
    repo.upsert(original)
    path = tmp_path / SOURCE / "m-001.json"
    original_bytes = path.read_bytes()
    real_replace = os.replace
    def flaky_replace(src, dst):
        if str(dst) == str(path):
            raise OSError("simulated replace failure")
        return real_replace(src, dst)
    monkeypatch.setattr(os, "replace", flaky_replace)
    with pytest.raises(OSError, match="simulated replace failure"):
        repo.upsert(_mk(quote="new"))
    assert path.read_bytes() == original_bytes


# ---------------------------------------------------------------------------
# Protocol runtime check
# ---------------------------------------------------------------------------


def test_repo_isinstance_mention_repository_runtime(tmp_path):
    from domain.ports import MentionRepository
    repo = MentionRepoJson(tmp_path, SOURCE)
    assert isinstance(repo, MentionRepository)
