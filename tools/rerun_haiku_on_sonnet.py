"""rerun_haiku_on_sonnet.py — Re-traite avec Haiku les 11 épisodes déjà
extraits avec Sonnet 4.6, pour récupérer les recos que Haiku trouve en plus.

Garantie : aucune suppression. _persist_recos merge par titre normalisé.
Coût attendu : ~$1.10 (Haiku 4.5 ~$0.10/ép × 11).
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
TOOLS = ROOT / "tools"
sys.path.insert(0, str(TOOLS))

from common import log, recos_dir_for  # noqa: E402

SOURCE_ID = "un-bon-moment"
PROGRESS_FILE = TOOLS / "output" / "whisper-cmp" / "auto_progress.json"
PYTHON = sys.executable


def _count(guid: str) -> dict[str, int]:
    counts = {"total": 0, "anthropic": 0, "openai": 0, "both": 0}
    for p in recos_dir_for(SOURCE_ID).glob("*.json"):
        d = json.loads(p.read_text(encoding="utf-8"))
        if d.get("episodeGuid") != guid:
            continue
        counts["total"] += 1
        ex = set(d.get("extractors") or [])
        if "anthropic" in ex: counts["anthropic"] += 1
        if "openai" in ex: counts["openai"] += 1
        if {"anthropic", "openai"}.issubset(ex): counts["both"] += 1
    return counts


def main() -> None:
    p = json.loads(PROGRESS_FILE.read_text(encoding="utf-8"))
    sonnet_eps = p["done"][:11]
    log.info("Re-traitement Haiku sur %d épisode(s) (les 11 premiers Sonnet)",
             len(sonnet_eps))
    for i, guid in enumerate(sonnet_eps, 1):
        before = _count(guid)
        log.info("[%d/%d] %s  before=%s", i, len(sonnet_eps), guid, before)
        cmd = [PYTHON, str(TOOLS / "extract_recos.py"),
               "--source", SOURCE_ID, "--provider", "anthropic", "--guid", guid]
        r = subprocess.run(cmd, capture_output=True, text=True,
                           encoding="utf-8", errors="replace")
        if r.returncode != 0:
            log.warning("extract échoué : %s", r.stderr[-400:])
            continue
        after = _count(guid)
        log.info("[%d/%d] %s  after=%s  Δ=%d", i, len(sonnet_eps), guid, after,
                 after["total"] - before["total"])
        # Mise à jour auto_progress
        if guid in p["stats"]:
            p["stats"][guid]["after"] = after
            p["stats"][guid]["delta"] = {
                k: after[k] - p["stats"][guid]["before"].get(k, 0) for k in after
            }
    PROGRESS_FILE.write_text(json.dumps(p, ensure_ascii=False, indent=2),
                             encoding="utf-8")
    log.info("Terminé. Stats auto_progress.json mises à jour.")


if __name__ == "__main__":
    main()
