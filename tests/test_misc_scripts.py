"""Tests des petits scripts utilitaires (sans I/O réseau) :

- refresh_watch_provider_urls.py : re-map les URLs des watchProviders.
- extract_from_acast_backups.py : helpers de swap de fichiers.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest


# ===== refresh_watch_provider_urls ========================================
def test_refresh_watch_provider_urls_updates_urls(monkeypatch, tmp_path: Path):
    """Re-map de [{label: 'Apple TV Store', url: 'old-google-search'}]
    vers [{label: 'Apple TV Store', url: 'tv.apple.com/...'}]."""
    import common, refresh_watch_provider_urls as refresh
    recos_dir = tmp_path / "recos" / "ubm"
    recos_dir.mkdir(parents=True)
    monkeypatch.setattr(common, "RECOS_DIR", tmp_path / "recos")

    (recos_dir / "001.json").write_text(json.dumps({
        "title": "Mortel",
        "watchProviders": [
            {"label": "Apple TV Store", "url": "https://google.com/search?q=old", "ethics": "neutral"},
            {"label": "Netflix",         "url": "https://google.com/search?q=old", "ethics": "neutral"},
        ],
    }), encoding="utf-8")

    monkeypatch.setattr(sys, "argv", ["refresh", "--source", "ubm"])
    refresh.main()

    out = json.loads((recos_dir / "001.json").read_text(encoding="utf-8"))
    urls = [p["url"] for p in out["watchProviders"]]
    assert any("tv.apple.com" in u for u in urls)
    assert any("netflix.com" in u for u in urls)


def test_refresh_skips_recos_without_providers(monkeypatch, tmp_path: Path):
    """Les recos sans watchProviders sont ignorées (livres, musique, etc.)."""
    import common, refresh_watch_provider_urls as refresh
    recos_dir = tmp_path / "recos" / "ubm"
    recos_dir.mkdir(parents=True)
    monkeypatch.setattr(common, "RECOS_DIR", tmp_path / "recos")

    (recos_dir / "001.json").write_text(json.dumps({
        "title": "Un livre",
        "type": "livre",
    }), encoding="utf-8")

    monkeypatch.setattr(sys, "argv", ["refresh", "--source", "ubm"])
    refresh.main()
    # Inchangé (pas de watchProviders ajoutés).
    out = json.loads((recos_dir / "001.json").read_text(encoding="utf-8"))
    assert "watchProviders" not in out


# ===== extract_from_acast_backups : swap idempotent =======================
def test_restore_initial_no_op_when_clean(tmp_path: Path):
    """restore_initial sur un état propre (pas de .yt.tmp.txt) ne change rien."""
    from extract_from_acast_backups import restore_initial
    (tmp_path / "abc.txt").write_text("yt content", encoding="utf-8")
    (tmp_path / "abc.acast.txt").write_text("acast content", encoding="utf-8")
    restore_initial("abc", tmp_path)
    # État inchangé
    assert (tmp_path / "abc.txt").read_text(encoding="utf-8") == "yt content"
    assert (tmp_path / "abc.acast.txt").read_text(encoding="utf-8") == "acast content"


def test_restore_initial_swaps_back_when_interrupted(tmp_path: Path):
    """Si .yt.tmp.txt existe (swap en cours interrompu), on remet l'état initial :
    le .txt redevient le YT, et l'Acast retourne en .acast.txt."""
    from extract_from_acast_backups import restore_initial
    # Simuler un état "swap fait, extraction interrompue" :
    # txt = contenu Acast, yt.tmp.txt = contenu YT, pas de .acast.txt.
    (tmp_path / "abc.txt").write_text("acast", encoding="utf-8")
    (tmp_path / "abc.yt.tmp.txt").write_text("yt", encoding="utf-8")

    restore_initial("abc", tmp_path)
    # Après restore : .txt = yt (le bon), .acast.txt = acast (rétabli en backup)
    assert (tmp_path / "abc.txt").read_text(encoding="utf-8") == "yt"
    assert (tmp_path / "abc.acast.txt").read_text(encoding="utf-8") == "acast"
    assert not (tmp_path / "abc.yt.tmp.txt").exists()


def test_swap_raises_when_destination_exists(tmp_path: Path):
    """_swap refuse d'écraser un fichier existant (filet de sécurité)."""
    from extract_from_acast_backups import _swap
    (tmp_path / "a").write_text("a", encoding="utf-8")
    (tmp_path / "b").write_text("b", encoding="utf-8")
    with pytest.raises(FileExistsError):
        _swap(tmp_path / "a", tmp_path / "b")
