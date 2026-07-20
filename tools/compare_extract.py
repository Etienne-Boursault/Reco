"""compare_extract.py — Extraction comparative figée (Whisper-model study).

Lit les transcripts dans tools/output/whisper-cmp/<model>/<guid>.txt, lance
les MÊMES LLMs avec les MÊMES paramètres pour les 3 modèles Whisper :
- small (baseline = transcript de production dans tools/output/transcripts/)
- medium / large-v3 (rapatriés du laptop GPU)

Écrit les recos brutes dans tools/output/whisper-cmp/<model>/recos/<guid>_<provider>.json
SANS toucher à src/content/recos. Produit un récap CSV à la fin.

Garde les **mêmes modèles LLM** pour les 3 versions : seul le transcript
varie. Anthropic = claude-sonnet-4-6 (défaut extract_recos), OpenAI = gpt-5
(défaut extract_recos).

Usage :
  python tools/compare_extract.py --source un-bon-moment
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

# Imports relatifs au répertoire tools/.
sys.path.insert(0, str(Path(__file__).parent))
from common import (  # noqa: E402
    log, load_source, read_json, transcript_path_for, make_anthropic_client,
    make_openai_client,
)
from extract_recos import (  # noqa: E402
    MODEL as DEFAULT_ANTHROPIC_MODEL,
    OPENAI_MODEL as DEFAULT_OPENAI_MODEL,
    _call_llm,
    _chunk_transcript,
    _normalize_reco,
    _dedupe,
)


SOURCE_DIR = Path(__file__).parent
CMP_DIR = SOURCE_DIR / "output" / "whisper-cmp"
BASELINE_DIR = SOURCE_DIR / "output" / "transcripts"

PROVIDERS = ("anthropic", "openai")


def _read_guids(source_id: str) -> list[str]:
    """Liste des guids à comparer = ceux du dispatch comparison."""
    f = SOURCE_DIR / "dispatch" / "whisper_compare_guids.txt"
    return [g.strip() for g in f.read_text(encoding="utf-8").splitlines() if g.strip()]


def _transcript_for(source_id: str, model: str, guid: str) -> Path:
    """Chemin du transcript selon le modèle. small = production."""
    if model == "small":
        return transcript_path_for(source_id, guid)
    return CMP_DIR / model / f"{guid}.txt"


def _extract(client: Any, provider: str, llm_model: str,
             podcast_title: str, hosts: str, transcript: str) -> list[dict]:
    """Appelle le LLM sur tous les chunks, retourne les recos brutes."""
    chunks = _chunk_transcript(transcript)
    raw: list[dict] = []
    for i, c in enumerate(chunks, 1):
        log.info("    chunk %d/%d…", i, len(chunks))
        raw.extend(_call_llm(client, llm_model, podcast_title, hosts, c, provider))
    normalized = [r for r in (_normalize_reco(x) for x in raw) if r]
    return _dedupe(normalized)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--source", required=True)
    ap.add_argument("--models", nargs="+",
                    default=["small", "medium", "large-v3"],
                    help="Modèles Whisper à comparer (small = baseline).")
    args = ap.parse_args()

    src = load_source(args.source)
    podcast_title = src.get("title", args.source)
    hosts = ", ".join(src.get("hosts", [])) or "inconnus"
    guids = _read_guids(args.source)
    log.info("Comparaison sur %d épisode(s) × %d modèle(s) × 2 LLM",
             len(guids), len(args.models))

    clients = {
        "anthropic": (make_anthropic_client(), DEFAULT_ANTHROPIC_MODEL),
        "openai":    (make_openai_client(),    DEFAULT_OPENAI_MODEL),
    }
    log.info("LLM figés : Anthropic=%s · OpenAI=%s",
             DEFAULT_ANTHROPIC_MODEL, DEFAULT_OPENAI_MODEL)

    results: list[dict] = []  # rows pour le CSV final
    for model in args.models:
        for guid in guids:
            tpath = _transcript_for(args.source, model, guid)
            if not tpath.exists():
                log.warning("[%s/%s] transcript manquant : %s", model, guid, tpath)
                continue
            text = tpath.read_text(encoding="utf-8")
            chars = len(text)
            for provider in PROVIDERS:
                out_dir = CMP_DIR / model / "recos"
                out_dir.mkdir(parents=True, exist_ok=True)
                out_file = out_dir / f"{guid}_{provider}.json"
                if out_file.exists():
                    recos = json.loads(out_file.read_text(encoding="utf-8"))
                    log.info("[%s/%s/%s] cache hit (%d recos)",
                             model, guid, provider, len(recos))
                else:
                    log.info("[%s/%s/%s] extraction…", model, guid, provider)
                    client, llm_model = clients[provider]
                    recos = _extract(client, provider, llm_model,
                                     podcast_title, hosts, text)
                    out_file.write_text(
                        json.dumps(recos, ensure_ascii=False, indent=2),
                        encoding="utf-8",
                    )
                results.append({
                    "model": model, "guid": guid, "provider": provider,
                    "chars": chars, "n_recos": len(recos),
                })

    # Récap CSV pour comparaison rapide.
    csv = CMP_DIR / "comparison.csv"
    csv.parent.mkdir(parents=True, exist_ok=True)
    with csv.open("w", encoding="utf-8") as f:
        f.write("model,guid,provider,chars,n_recos\n")
        for r in results:
            f.write(f"{r['model']},{r['guid']},{r['provider']},"
                    f"{r['chars']},{r['n_recos']}\n")
    log.info("CSV récap : %s", csv)

    # Tableau pivot lisible : modèle × guid (somme des 2 LLMs).
    print("\nRécap : nombre de recos extraites par épisode × modèle Whisper")
    print(f"{'guid':<36} {'small':>8} {'medium':>8} {'large-v3':>10}")
    by_guid: dict[str, dict[str, int]] = {}
    for r in results:
        by_guid.setdefault(r["guid"], {}).setdefault(r["model"], 0)
        by_guid[r["guid"]][r["model"]] += r["n_recos"]
    for guid, row in by_guid.items():
        print(f"{guid:<36} {row.get('small', 0):>8} {row.get('medium', 0):>8} "
              f"{row.get('large-v3', 0):>10}")


if __name__ == "__main__":
    main()
