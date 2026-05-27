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
