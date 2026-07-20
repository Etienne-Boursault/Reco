"""retry_gpt4o.py — Retente l'extraction gpt-4o sur les épisodes
qui ont raté à cause du rate limit OpenAI (30K TPM).
Ajoute une pause entre chunks pour rester sous la limite.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).parent.parent
TOOLS = ROOT / "tools"
sys.path.insert(0, str(TOOLS))

from common import (  # noqa: E402
    log, load_source, make_openai_client, transcript_path_for,
)
from extract_recos import (  # noqa: E402
    _call_llm, _chunk_transcript, _normalize_reco, _dedupe,
)

SOURCE_ID = "un-bon-moment"
OUT_DIR = TOOLS / "output" / "whisper-cmp" / "llm-cmp" / "openai_gpt-4o"
SLEEP_BETWEEN_CHUNKS = 25  # secondes — ~ 8K tokens / 25s = 19.2K TPM, OK
PROVIDER = "openai"
MODEL = "gpt-4o"


def main() -> None:
    # Identifie les guids à 0 recos = ratés.
    failed: list[str] = []
    for p in OUT_DIR.glob("*.json"):
        if json.loads(p.read_text(encoding="utf-8")) == []:
            failed.append(p.stem)
    if not failed:
        print("Aucun épisode à retenter.")
        return
    print(f"À retenter : {len(failed)} épisode(s)")
    for g in failed:
        print(f"  - {g}")

    src = load_source(SOURCE_ID)
    podcast_title = src.get("title", SOURCE_ID)
    hosts = ", ".join(src.get("hosts", [])) or "inconnus"
    client = make_openai_client()

    for guid in failed:
        tpath = transcript_path_for(SOURCE_ID, guid)
        text = tpath.read_text(encoding="utf-8")
        chunks = _chunk_transcript(text)
        log.info("[%s] %d chunks, sleep %ds entre chunks", guid, len(chunks),
                 SLEEP_BETWEEN_CHUNKS)
        raw: list[dict] = []
        for i, c in enumerate(chunks, 1):
            for attempt in range(3):
                try:
                    raw.extend(_call_llm(client, MODEL, podcast_title, hosts, c, PROVIDER))
                    break
                except Exception as exc:  # noqa: BLE001
                    msg = str(exc)
                    if "429" in msg or "rate_limit" in msg.lower():
                        log.warning("  chunk %d 429, sleep 60s (attempt %d)", i, attempt+1)
                        time.sleep(60)
                    else:
                        log.error("  chunk %d échec %s", i, exc)
                        break
            log.info("  chunk %d/%d : %d candidats cumulés", i, len(chunks), len(raw))
            if i < len(chunks):
                time.sleep(SLEEP_BETWEEN_CHUNKS)
        normalized = [r for r in (_normalize_reco(x) for x in raw) if r]
        deduped = _dedupe(normalized)
        of = OUT_DIR / f"{guid}.json"
        of.write_text(json.dumps(deduped, ensure_ascii=False, indent=2), encoding="utf-8")
        log.info("[%s] %d recos écrites (vs 0 avant)", guid, len(deduped))


if __name__ == "__main__":
    main()
