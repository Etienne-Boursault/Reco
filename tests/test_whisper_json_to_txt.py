"""Tests pour `tools/whisper_json_to_txt.py`."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

import whisper_json_to_txt as wjt


def _whisper_json(segments):
    """Fabrique un dict au format whisper.cpp."""
    return {
        "transcription": [
            {"offsets": {"from": ms, "to": ms + 1000}, "text": txt}
            for ms, txt in segments
        ]
    }


def test_convert_writes_timestamped_lines(tmp_path: Path):
    src = tmp_path / "in.json"
    dst = tmp_path / "out.txt"
    src.write_text(json.dumps(_whisper_json([
        (0, "Bonjour le monde"),
        (3_600_000, "  texte une heure plus tard  "),  # 1h
    ])), encoding="utf-8")
    n = wjt.convert(src, dst)
    assert n == 2
    out = dst.read_text(encoding="utf-8")
    assert "[00:00:00] Bonjour le monde" in out
    assert "[01:00:00] texte une heure plus tard" in out
    # Trim côté texte appliqué.
    assert "  texte" not in out


def test_convert_empty_transcription(tmp_path: Path):
    src = tmp_path / "in.json"
    dst = tmp_path / "out.txt"
    src.write_text(json.dumps({"transcription": []}), encoding="utf-8")
    n = wjt.convert(src, dst)
    assert n == 0
    # Le fichier de sortie contient au moins un saut de ligne (newline final).
    assert dst.read_text(encoding="utf-8") == "\n"


def test_convert_handles_invalid_utf8(tmp_path: Path):
    """`errors='replace'` permet de relire un fichier corrompu sans planter."""
    src = tmp_path / "in.json"
    # Bytes invalides UTF-8 dans un champ texte (whisper.cpp peut produire ça).
    raw = b'{"transcription": [{"offsets": {"from": 0, "to": 100}, "text": "h\xff"}]}'
    src.write_bytes(raw)
    dst = tmp_path / "out.txt"
    n = wjt.convert(src, dst)
    assert n == 1


def test_main_uses_argparse(tmp_path: Path, monkeypatch):
    src = tmp_path / "in.json"
    dst = tmp_path / "out.txt"
    src.write_text(json.dumps(_whisper_json([(0, "salut")])), encoding="utf-8")

    monkeypatch.setattr(sys, "argv", [
        "whisper_json_to_txt.py",
        "--input", str(src),
        "--output", str(dst),
    ])
    wjt.main()
    assert "[00:00:00] salut" in dst.read_text(encoding="utf-8")


def test_main_requires_input_and_output(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["whisper_json_to_txt.py"])
    with pytest.raises(SystemExit):
        wjt.main()
