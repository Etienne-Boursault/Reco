"""
whisper_json_to_txt.py — Convertit un transcript whisper.cpp (JSON) en .txt
formaté `[HH:MM:SS] texte` ligne à ligne.

Utilisé pour récupérer un transcript inachevé depuis le `cur.json` du worker
portable (whisper.cpp), quand le fichier final `.txt` n'a pas pu être écrit.

Le JSON attendu (format whisper.cpp) :
    {
      "transcription": [
        {"offsets": {"from": 0, "to": 1500}, "text": "..."},
        ...
      ]
    }

Usage :
    python whisper_json_to_txt.py --input cur.json --output transcript.txt
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from common import format_timestamp, log


def convert(input_path: Path, output_path: Path) -> int:
    """Lit `input_path` (JSON whisper.cpp) et écrit `output_path` (.txt).

    Renvoie le nombre de segments écrits.
    """
    with open(input_path, encoding="utf-8", errors="replace") as f:
        data = json.load(f)

    lines: list[str] = []
    for segment in data.get("transcription", []):
        # Offsets sont en millisecondes côté whisper.cpp.
        ms = segment["offsets"]["from"]
        ts = format_timestamp(ms // 1000)
        lines.append(f"[{ts}] {segment['text'].strip()}")

    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    log.info("OK %d segments -> %s", len(lines), output_path)
    return len(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path,
                        help="Fichier JSON whisper.cpp à convertir.")
    parser.add_argument("--output", required=True, type=Path,
                        help="Fichier .txt de sortie.")
    args = parser.parse_args()
    convert(args.input, args.output)


if __name__ == "__main__":
    main()
