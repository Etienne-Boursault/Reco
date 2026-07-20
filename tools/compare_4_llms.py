"""compare_4_llms.py — Étude comparative 4 LLM sur les 10 épisodes
déjà transcrits en large-v3-turbo.

Lance les 4 modèles sur le même transcript :
  - Anthropic claude-sonnet-4-6  (~$3/M in, $15/M out)
  - Anthropic claude-haiku-4-5    (~$0.80/M in, $4/M out)
  - OpenAI    gpt-4o              (~$2.50/M in, $10/M out)
  - OpenAI    gpt-4o-mini         (~$0.15/M in, $0.60/M out)

Sortie : tools/output/whisper-cmp/llm-cmp/<provider>_<model>/<guid>.json
SANS toucher à src/content/recos. Affiche un tableau récap à la fin.

Usage :
  python tools/compare_4_llms.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).parent.parent
TOOLS = ROOT / "tools"
sys.path.insert(0, str(TOOLS))

from common import (  # noqa: E402
    log, load_source, make_anthropic_client, make_openai_client,
    transcript_path_for,
)
from extract_recos import (  # noqa: E402
    _call_llm, _chunk_transcript, _normalize_reco, _dedupe,
)

SOURCE_ID = "un-bon-moment"
OUT_DIR = TOOLS / "output" / "whisper-cmp" / "llm-cmp"
PROGRESS_FILE = TOOLS / "output" / "whisper-cmp" / "auto_progress.json"

# (provider, modèle, label_safe_pour_path)
# Sonnet 4.6 + gpt-4o-mini sont DÉJÀ extraits via auto_compare_large.py vers
# src/content/recos — on les récupère depuis là (filtre extractors=...) pour
# ne pas re-cramer des tokens. Ici on n'extrait que les 2 modèles nouveaux.
TARGETS = [
    ("anthropic", "claude-haiku-4-5", "anthropic_haiku-4-5"),
    ("openai",    "gpt-4o",           "openai_gpt-4o"),
]
# Les labels existants (depuis src/content/recos) :
EXISTING_LABELS = ["anthropic_sonnet-4-6", "openai_gpt-4o-mini"]


def _normalize_title(t: str) -> str:
    return "".join(c for c in t.lower() if c.isalnum() or c.isspace()).strip()


def _extract(client: Any, provider: str, llm_model: str,
             podcast_title: str, hosts: str, transcript: str) -> list[dict]:
    chunks = _chunk_transcript(transcript)
    raw: list[dict] = []
    for c in chunks:
        raw.extend(_call_llm(client, llm_model, podcast_title, hosts, c, provider))
    normalized = [r for r in (_normalize_reco(x) for x in raw) if r]
    return _dedupe(normalized)


def main() -> None:
    src = load_source(SOURCE_ID)
    podcast_title = src.get("title", SOURCE_ID)
    hosts = ", ".join(src.get("hosts", [])) or "inconnus"

    # 10 épisodes déjà transcrits en turbo (depuis auto_progress.json).
    progress = json.loads(PROGRESS_FILE.read_text(encoding="utf-8"))
    guids = progress["done"]
    log.info("Comparaison 4 LLM sur %d épisode(s) (transcripts large-v3-turbo).",
             len(guids))

    clients = {
        "anthropic": make_anthropic_client(),
        "openai":    make_openai_client(),
    }

    # Cache : si un fichier de sortie existe déjà, on saute (idempotent).
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    for provider, model, label in TARGETS:
        outdir = OUT_DIR / label
        outdir.mkdir(parents=True, exist_ok=True)
        for guid in guids:
            of = outdir / f"{guid}.json"
            if of.exists():
                log.info("[%s/%s] cache hit", label, guid)
                continue
            tpath = transcript_path_for(SOURCE_ID, guid)
            if not tpath.exists():
                log.warning("[%s/%s] transcript manquant", label, guid)
                continue
            text = tpath.read_text(encoding="utf-8")
            log.info("[%s/%s] %d chars, extraction…", label, guid, len(text))
            try:
                recos = _extract(clients[provider], provider, model,
                                 podcast_title, hosts, text)
            except Exception as exc:  # noqa: BLE001
                log.warning("[%s/%s] échec : %s", label, guid, exc)
                recos = []
            of.write_text(json.dumps(recos, ensure_ascii=False, indent=2),
                          encoding="utf-8")
            log.info("[%s/%s] %d recos écrites", label, guid, len(recos))

    # ===== Stats =====
    # Pour chaque modèle : nb recos / épisode + total
    # Intersections par paire pour signal de confiance
    print()
    print("=" * 80)
    print("COMPARAISON 4 LLM — synthèse")
    print("=" * 80)

    per_model: dict[str, dict[str, set[str]]] = {}
    for _p, _m, label in TARGETS:
        per_model[label] = {}
        for guid in guids:
            of = OUT_DIR / label / f"{guid}.json"
            if of.exists():
                items = json.loads(of.read_text(encoding="utf-8"))
                per_model[label][guid] = {_normalize_title(r["title"]) for r in items}
            else:
                per_model[label][guid] = set()

    # Récupère Sonnet 4.6 + gpt-4o-mini depuis src/content/recos (par extractor).
    from common import recos_dir_for  # noqa: PLC0415
    recos_dir = recos_dir_for(SOURCE_ID)
    for label, ex in [("anthropic_sonnet-4-6", "anthropic"),
                      ("openai_gpt-4o-mini",    "openai")]:
        per_model[label] = {g: set() for g in guids}
        for p in recos_dir.glob("*.json"):
            d = json.loads(p.read_text(encoding="utf-8"))
            g = d.get("episodeGuid")
            if g in per_model[label] and ex in (d.get("extractors") or []):
                per_model[label][g].add(_normalize_title(d.get("title", "")))

    # Tableau totaux
    print(f"\n{'Modèle':<32} {'Total':>7} {'/épisode':>10}")
    print("-" * 60)
    totals = {}
    for label in per_model:
        t = sum(len(s) for s in per_model[label].values())
        totals[label] = t
        avg = t / len(guids)
        print(f"{label:<32} {t:>7} {avg:>10.1f}")

    # Tableau intersections (recall croisé)
    labels = list(per_model.keys())
    print(f"\n{'Paire':<55} {'∩ recos':>10} {'% min':>8} {'% max':>8}")
    print("-" * 90)
    for i in range(len(labels)):
        for j in range(i+1, len(labels)):
            la, lb = labels[i], labels[j]
            inter = sum(len(per_model[la][g] & per_model[lb][g]) for g in guids)
            ta = totals[la]; tb = totals[lb]
            pct_min = inter / min(ta, tb) * 100 if min(ta, tb) else 0
            pct_max = inter / max(ta, tb) * 100 if max(ta, tb) else 0
            pair = f"{la}  ∩  {lb}"
            print(f"{pair:<55} {inter:>10} {pct_min:>7.1f}% {pct_max:>7.1f}%")

    # Per-episode breakdown
    print(f"\nDétail par épisode :")
    cols = "  ".join(f"{l[10:25]:>16}" for l in labels)
    print(f"{'guid':<40} {cols}")
    print("-" * (40 + len(cols)))
    for g in guids:
        cells = "  ".join(f"{len(per_model[l][g]):>16}" for l in labels)
        print(f"{g:<40} {cells}")

    # CSV
    csv_path = OUT_DIR / "compare_4_llms.csv"
    with csv_path.open("w", encoding="utf-8") as f:
        f.write("guid," + ",".join(labels) + "\n")
        for g in guids:
            f.write(g + "," + ",".join(str(len(per_model[l][g])) for l in labels) + "\n")
        f.write("TOTAL," + ",".join(str(totals[l]) for l in labels) + "\n")
    print(f"\nCSV récap : {csv_path}")


if __name__ == "__main__":
    main()
