"""Tests du formatage de l'inventaire (tools/inventory_md.py)."""
from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

import pytest

import inventory_md
from inventory_md import fmt_dur


def test_fmt_dur_zero_returns_dash():
    assert fmt_dur(0) == "—"
    assert fmt_dur(None) == "—"


def test_fmt_dur_under_a_minute():
    assert fmt_dur(45) == "0mn45"


def test_fmt_dur_exact_minute():
    assert fmt_dur(60) == "1mn00"


def test_fmt_dur_typical_episode():
    # 1h30m05 = 5405 secondes
    assert fmt_dur(5405) == "90mn05"


def test_fmt_dur_pads_seconds_to_two_digits():
    """Les secondes sont toujours sur 2 chiffres (« 5mn05 », pas « 5mn5 »)."""
    assert fmt_dur(305) == "5mn05"


# ===== generate() =========================================================
@pytest.fixture
def isolated_tree(tmp_path: Path, monkeypatch):
    """Redirige tous les chemins du projet vers un tmp_path isolé."""
    eps_dir = tmp_path / "src" / "content" / "episodes"
    recos_dir = tmp_path / "src" / "content" / "recos"
    transcripts_dir = tmp_path / "tools" / "output" / "transcripts"
    monkeypatch.setattr(inventory_md, "EPISODES_DIR", eps_dir)
    monkeypatch.setattr(inventory_md, "RECOS_DIR", recos_dir)
    monkeypatch.setattr(inventory_md, "TRANSCRIPTS_DIR", transcripts_dir)
    monkeypatch.setattr(inventory_md, "PROJECT_ROOT", tmp_path)
    return tmp_path


def _write_episode(eps_dir: Path, source: str, guid: str, **extra):
    src_dir = eps_dir / source
    src_dir.mkdir(parents=True, exist_ok=True)
    data = {"guid": guid, "title": f"Episode {guid}", **extra}
    (src_dir / f"{guid}.json").write_text(json.dumps(data), encoding="utf-8")


def test_generate_writes_markdown_with_table(isolated_tree, monkeypatch):
    """generate() crée le .md attendu avec en-tête + tableau."""
    eps_dir = isolated_tree / "src" / "content" / "episodes"
    _write_episode(eps_dir, "ubm", "g1", season=5, number=32,
                   youtubeUrl="https://yt/x", youtubeDuration=3600,
                   audioDuration=3700)
    _write_episode(eps_dir, "ubm", "g2", number=99,
                   audioDuration=3700, youtubeDuration=600)  # extrait
    out = inventory_md.generate("ubm")
    text = out.read_text(encoding="utf-8")
    assert "# Inventaire complet — ubm" in text
    assert date.today().isoformat() in text
    assert "S5E32" in text
    assert "#99" in text
    # Le 2e est un extrait → marqueur ⚠️ présent.
    assert "⚠️" in text


def test_generate_handles_empty_source(isolated_tree):
    """Aucun épisode → fichier généré quand même, table vide."""
    (isolated_tree / "src" / "content" / "episodes" / "vide").mkdir(parents=True)
    out = inventory_md.generate("vide")
    assert out.exists()
    text = out.read_text(encoding="utf-8")
    assert "Total : 0 épisodes" in text


def test_generate_counts_recos_per_guid(isolated_tree):
    eps_dir = isolated_tree / "src" / "content" / "episodes"
    recos_dir = isolated_tree / "src" / "content" / "recos" / "ubm"
    recos_dir.mkdir(parents=True)
    _write_episode(eps_dir, "ubm", "g1", number=1)
    for i in range(3):
        (recos_dir / f"{i}.json").write_text(
            json.dumps({"episodeGuid": "g1"}), encoding="utf-8")
    out = inventory_md.generate("ubm")
    text = out.read_text(encoding="utf-8")
    assert "1/1 avec recos" in text
    assert "3 recos extraites" in text


def test_main_uses_argparse(monkeypatch, isolated_tree):
    """main() lit --source via argparse, sans valeur par défaut hardcodée."""
    eps_dir = isolated_tree / "src" / "content" / "episodes"
    _write_episode(eps_dir, "podcast-2", "h1", number=1)
    monkeypatch.setattr(sys, "argv", ["inventory_md.py", "--source", "podcast-2"])
    inventory_md.main()
    out = isolated_tree / "docs" / "inventaire-podcast-2.md"
    assert out.exists()


def test_main_requires_source(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["inventory_md.py"])
    with pytest.raises(SystemExit):
        inventory_md.main()


def test_truncate_long_title_in_output(isolated_tree):
    eps_dir = isolated_tree / "src" / "content" / "episodes"
    long_title = "x" * 200
    _write_episode(eps_dir, "ubm", "g1", number=1, title=long_title)
    out = inventory_md.generate("ubm")
    text = out.read_text(encoding="utf-8")
    # Le titre tronqué doit contenir l'ellipse (caractère unicode … = U+2026).
    assert "…" in text
    assert "x" * 200 not in text


def test_episode_without_season_or_number_renders_dash(isolated_tree):
    """Un épisode sans season ni number → label « — » et table générée sans erreur."""
    eps_dir = isolated_tree / "src" / "content" / "episodes"
    _write_episode(eps_dir, "ubm", "g1")  # ni season, ni number
    out = inventory_md.generate("ubm")
    text = out.read_text(encoding="utf-8")
    # Pas de S/N → ligne avec « — » dans la 1ère colonne après le pipe.
    assert "| — |" in text


def test_transcript_acast_only_no_yt_marks_audio_source(isolated_tree):
    """Transcript présent sans youtubeUrl → cellule « Acast »."""
    eps_dir = isolated_tree / "src" / "content" / "episodes"
    transcripts_dir = isolated_tree / "tools" / "output" / "transcripts" / "ubm"
    transcripts_dir.mkdir(parents=True)
    _write_episode(eps_dir, "ubm", "guidA", number=1)
    (transcripts_dir / "guidA.txt").write_text("ok", encoding="utf-8")
    out = inventory_md.generate("ubm")
    assert "🎧 Acast" in out.read_text(encoding="utf-8")


def test_transcript_but_no_recos_marks_failed(isolated_tree):
    """Transcript présent, 0 recos extraites → cellule « ❌ »."""
    eps_dir = isolated_tree / "src" / "content" / "episodes"
    transcripts_dir = isolated_tree / "tools" / "output" / "transcripts" / "ubm"
    transcripts_dir.mkdir(parents=True)
    _write_episode(eps_dir, "ubm", "guidB", number=1,
                   youtubeUrl="https://yt/x")
    (transcripts_dir / "guidB.txt").write_text("ok", encoding="utf-8")
    out = inventory_md.generate("ubm")
    # On retrouve un « ❌ » dans la colonne recos (présence du symbole suffit).
    assert "❌" in out.read_text(encoding="utf-8")


def test_yt_retranscribe_guid_marked(isolated_tree):
    eps_dir = isolated_tree / "src" / "content" / "episodes"
    guid = next(iter(inventory_md.YT_RETRANSCRIBE_GUIDS))
    _write_episode(eps_dir, "ubm", guid, number=1)
    out = inventory_md.generate("ubm")
    text = out.read_text(encoding="utf-8")
    # Pas de transcript .txt → « en cours ».
    assert "⏳ en cours" in text
