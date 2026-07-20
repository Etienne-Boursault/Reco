"""rerun_28_eps_with_history.py — Re-extract Haiku + gpt-4o-mini sur les 28
ép déjà processés par l'orchestrateur, pour remplacer les entrées
"(assumed)" du backfill par les vraies signatures (large-v3-turbo + youtube
+ haiku-4-5/gpt-4o-mini).

Le merge_history dedup par signature : une vraie entrée écrase l'assumed
quand elles partagent (transcriptModel, transcriptSource, llmProvider,
llmModel). Pour les autres, ajoute une nouvelle entrée.

Effet de bord : top-level `transcriptSource` flippe à "youtube" pour les
recos qui sont vraiment matched par le YT transcript → fix de l'offset.

Coût : ~$4 (28 ép × Haiku ~$0.10 + gpt-4o-mini ~$0.014).
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
TOOLS = ROOT / "tools"
sys.path.insert(0, str(TOOLS))

from common import log  # noqa: E402

PROGRESS = TOOLS / "output" / "whisper-cmp" / "auto_progress.json"
PYTHON = sys.executable


def main() -> None:
    p = json.loads(PROGRESS.read_text(encoding="utf-8"))
    done = p["done"]
    log.info("Re-extract %d ép avec historique propre", len(done))
    for i, guid in enumerate(done, 1):
        for provider in ("anthropic", "openai"):
            log.info("[%d/%d] %s — %s", i, len(done), guid, provider)
            cmd = [PYTHON, str(TOOLS / "extract_recos.py"),
                   "--source", "un-bon-moment",
                   "--provider", provider, "--guid", guid]
            r = subprocess.run(cmd, capture_output=True, text=True,
                               encoding="utf-8", errors="replace")
            if r.returncode != 0:
                log.warning("KO : %s", r.stderr[-300:])
    log.info("Terminé.")


if __name__ == "__main__":
    main()
