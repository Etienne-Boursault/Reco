"""Tests TDD pour `tools.lint.loaders` (CR archi #4/#6, H7)."""
from __future__ import annotations

import json
from pathlib import Path

from lint.loaders import JsonDatasetLoader, _load_jsons_with_errors
from lint.rules.base import Severity


def _seed(tmp_path: Path, source_id: str) -> dict[str, Path]:
    r = tmp_path / "recos" / source_id
    e = tmp_path / "episodes" / source_id
    i = tmp_path / "items" / source_id
    m = tmp_path / "mentions" / source_id
    for d in (r, e, i, m):
        d.mkdir(parents=True, exist_ok=True)
    return {"recos": r, "episodes": e, "items": i, "mentions": m}


class _FakeRepo:
    def __init__(self, base_dir, source_id):
        self.base_dir = base_dir
        self.source_id = source_id

    def iter_all(self):
        return iter(())


def test_load_jsons_returns_empty_when_dir_missing(tmp_path):
    payloads, issues = _load_jsons_with_errors(
        tmp_path / "nope", source_id="x",
    )
    assert payloads == ()
    assert issues == ()


def test_load_jsons_emits_dataset_io_issue_for_bad_json(tmp_path, capsys):
    """H7 : fichier illisible → stderr + LintIssue synthétique."""
    (tmp_path / "bad.json").write_text("garbage", encoding="utf-8")
    payloads, issues = _load_jsons_with_errors(tmp_path, source_id="x")
    assert payloads == ()
    assert len(issues) == 1
    assert issues[0].rule == "dataset_io"
    assert issues[0].severity == Severity.WARNING
    err = capsys.readouterr().err
    assert "dataset_io" in err


def test_load_jsons_emits_io_issue_for_non_dict_payload(tmp_path):
    (tmp_path / "arr.json").write_text(json.dumps([1, 2]), encoding="utf-8")
    payloads, issues = _load_jsons_with_errors(tmp_path, source_id="x")
    assert payloads == ()
    assert len(issues) == 1
    assert "non-dict" in issues[0].message


def test_load_jsons_returns_valid_payloads(tmp_path):
    (tmp_path / "ok.json").write_text(json.dumps({"a": 1}), encoding="utf-8")
    payloads, issues = _load_jsons_with_errors(tmp_path, source_id="x")
    assert len(payloads) == 1
    assert payloads[0] == {"a": 1}
    assert issues == ()


def test_json_dataset_loader_builds_context(tmp_path):
    seeds = _seed(tmp_path, "ubm")
    (seeds["recos"] / "1.json").write_text(
        json.dumps({"id": "ubm-1", "title": "T"}), encoding="utf-8",
    )
    (seeds["episodes"] / "1.json").write_text(
        json.dumps({"guid": "g", "title": "ep"}), encoding="utf-8",
    )

    loader = JsonDatasetLoader(
        recos_base=tmp_path / "recos",
        episodes_base=tmp_path / "episodes",
        items_base=tmp_path / "items",
        mentions_base=tmp_path / "mentions",
        source_registry_get=lambda _id: None,
        item_repo_factory=_FakeRepo,
        mention_repo_factory=_FakeRepo,
    )
    ctx, issues = loader.load("ubm")
    assert ctx.source_id == "ubm"
    assert len(ctx.recos) == 1
    assert len(ctx.episodes) == 1
    assert issues == ()


def test_json_dataset_loader_aggregates_io_issues(tmp_path):
    seeds = _seed(tmp_path, "ubm")
    (seeds["recos"] / "bad.json").write_text("garbage", encoding="utf-8")
    (seeds["episodes"] / "bad.json").write_text("garbage", encoding="utf-8")

    loader = JsonDatasetLoader(
        recos_base=tmp_path / "recos",
        episodes_base=tmp_path / "episodes",
        items_base=tmp_path / "items",
        mentions_base=tmp_path / "mentions",
        source_registry_get=lambda _id: None,
        item_repo_factory=_FakeRepo,
        mention_repo_factory=_FakeRepo,
    )
    ctx, issues = loader.load("ubm")
    assert len(issues) == 2  # recos + episodes


def test_json_dataset_loader_tolerates_registry_exception(tmp_path):
    _seed(tmp_path, "ubm")

    def _boom(_id):
        raise RuntimeError("nope")

    loader = JsonDatasetLoader(
        recos_base=tmp_path / "recos",
        episodes_base=tmp_path / "episodes",
        items_base=tmp_path / "items",
        mentions_base=tmp_path / "mentions",
        source_registry_get=_boom,
        item_repo_factory=_FakeRepo,
        mention_repo_factory=_FakeRepo,
    )
    ctx, _ = loader.load("ubm")
    assert ctx.source_config is None
