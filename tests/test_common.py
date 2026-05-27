"""Tests des utilitaires partagés du pipeline (tools/common.py)."""
from __future__ import annotations

import json
from pathlib import Path

from common import reco_prefix, slugify, write_json_if_changed


# ===== slugify ============================================================
def test_slugify_strips_accents_and_case():
    assert slugify("Bérengère KRIEF") == "berengere-krief"


def test_slugify_collapses_punctuation():
    assert slugify("Hello, World! / Test") == "hello-world-test"


def test_slugify_fallback_for_empty_or_pure_special():
    assert slugify("") == "x"
    assert slugify("@@@") == "x"


def test_slugify_keeps_digits():
    assert slugify("Saison 5 — Épisode 32") == "saison-5-episode-32"


# ===== reco_prefix ========================================================
def test_reco_prefix_initials_for_compound_slug():
    assert reco_prefix("un-bon-moment") == "ubm"
    assert reco_prefix("la-derniere-sur-nova") == "ldsn"


def test_reco_prefix_single_word_uses_first_chars():
    # un seul segment → les 3 premières lettres
    assert reco_prefix("flood") == "flo"


def test_reco_prefix_always_non_empty():
    # Garantie : jamais de chaîne vide (utilisée comme préfixe d'IDs).
    assert reco_prefix("") != ""


# ===== write_json_if_changed ==============================================
def test_write_json_creates_when_missing(tmp_path: Path):
    target = tmp_path / "out.json"
    written = write_json_if_changed(target, {"a": 1})
    assert written is True
    assert target.exists()
    assert json.loads(target.read_text(encoding="utf-8")) == {"a": 1}


def test_write_json_skips_when_content_unchanged(tmp_path: Path):
    target = tmp_path / "out.json"
    write_json_if_changed(target, {"a": 1})
    # 2e écriture du même contenu → aucun écrit (idempotence).
    written = write_json_if_changed(target, {"a": 1})
    assert written is False


def test_write_json_writes_when_content_changes(tmp_path: Path):
    target = tmp_path / "out.json"
    write_json_if_changed(target, {"a": 1})
    written = write_json_if_changed(target, {"a": 2})
    assert written is True
    assert json.loads(target.read_text(encoding="utf-8")) == {"a": 2}


def test_write_json_preserves_accents_utf8(tmp_path: Path):
    target = tmp_path / "out.json"
    write_json_if_changed(target, {"name": "Bérengère"})
    text = target.read_text(encoding="utf-8")
    # Le contenu doit être en UTF-8 lisible (pas d'\uXXXX).
    assert "Bérengère" in text


# ===== load_source ========================================================
def test_load_source_raises_when_missing(monkeypatch, tmp_path: Path):
    import common
    monkeypatch.setattr(common, "SOURCES_DIR", tmp_path)
    import pytest
    with pytest.raises(FileNotFoundError):
        common.load_source("inconnu")


def test_load_source_returns_data(monkeypatch, tmp_path: Path):
    import common
    monkeypatch.setattr(common, "SOURCES_DIR", tmp_path)
    (tmp_path / "ubm.json").write_text('{"id": "ubm", "title": "UBM"}', encoding="utf-8")
    data = common.load_source("ubm")
    assert data["title"] == "UBM"


# ===== list_episode_files =================================================
def test_list_episode_files_empty_when_dir_absent(monkeypatch, tmp_path: Path):
    import common
    monkeypatch.setattr(common, "EPISODES_DIR", tmp_path)
    # Aucun sous-dossier pour 'ubm' → liste vide.
    assert common.list_episode_files("ubm") == []


def test_list_episode_files_returns_sorted(monkeypatch, tmp_path: Path):
    import common
    monkeypatch.setattr(common, "EPISODES_DIR", tmp_path)
    src_dir = tmp_path / "ubm"
    src_dir.mkdir()
    (src_dir / "b.json").write_text("{}", encoding="utf-8")
    (src_dir / "a.json").write_text("{}", encoding="utf-8")
    (src_dir / "ignore.txt").write_text("x", encoding="utf-8")  # filtre *.json
    files = common.list_episode_files("ubm")
    assert [p.name for p in files] == ["a.json", "b.json"]


# ===== Chemins helpers ====================================================
def test_path_helpers_compose_correctly():
    from common import (
        episodes_dir_for, recos_dir_for, transcript_path_for,
        EPISODES_DIR, RECOS_DIR, TRANSCRIPTS_DIR,
    )
    assert episodes_dir_for("ubm") == EPISODES_DIR / "ubm"
    assert recos_dir_for("ubm") == RECOS_DIR / "ubm"
    # transcript : le guid est slugifié pour éviter les chars problématiques.
    p = transcript_path_for("ubm", "abc-123")
    assert p.parent == TRANSCRIPTS_DIR / "ubm"
    assert p.name == "abc-123.txt"


def test_transcript_path_slugifies_guid():
    from common import transcript_path_for
    # Si le guid contient des caractères spéciaux, ils sont normalisés.
    p = transcript_path_for("ubm", "Bérengère")
    assert "berengere" in p.name


# ===== get_logger =========================================================
def test_get_logger_returns_same_logger_idempotent():
    import common, logging
    l1 = common.get_logger("reco-test-x")
    l2 = common.get_logger("reco-test-x")
    assert l1 is l2  # même instance, par nom
    assert l1.level == logging.INFO
