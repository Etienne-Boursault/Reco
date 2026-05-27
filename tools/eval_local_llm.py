"""
eval_local_llm.py - Evalue un LLM local sur l'extraction des recos.

Le script appelle un serveur compatible OpenAI (llama-server) sur un lot
d'episodes deja transcrits, puis compare les titres extraits aux recos existantes
du projet. Il n'ecrit jamais dans src/content/recos.

Usage:
    python tools/eval_local_llm.py --limit 10
    python tools/eval_local_llm.py --base-url http://llm.local:8080/v1
"""
from __future__ import annotations

import argparse
import json
import time
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

import requests

from common import (
    log,
    list_episode_files,
    load_source,
    normalize_text,
    read_json,
    recos_dir_for,
    transcript_path_for,
    write_json_if_changed,
)
from extract_recos import (
    SYSTEM_PROMPT,
    USER_TEMPLATE,
    VALID_TYPES,
    _chunk_transcript,
    _dedupe,
    _extract_json_block,
    _normalize_reco,
)

DEFAULT_BASE_URL = "http://llm.local:8080/v1"
DEFAULT_MODEL = "qwen3-4b-q4_k_m"
DEFAULT_MAX_TOKENS = 2000
OUTPUT_DIR = Path(__file__).resolve().parent / "output" / "local_llm_eval"


def _load_reference_recos(source_id: str) -> dict[str, list[dict[str, Any]]]:
    """Charge les recos existantes par episodeGuid, hors discarded."""
    out: dict[str, list[dict[str, Any]]] = {}
    d = recos_dir_for(source_id)
    if not d.exists():
        return out
    for path in sorted(d.glob("*.json")):
        try:
            reco = read_json(path)
        except (OSError, ValueError, json.JSONDecodeError):
            continue
        if reco.get("status") == "discarded":
            continue
        out.setdefault(reco.get("episodeGuid", ""), []).append(reco)
    return out


def _select_episodes(source_id: str, limit: int) -> list[Path]:
    """Selectionne des episodes recents avec transcript et recos de reference."""
    refs = _load_reference_recos(source_id)
    candidates: list[tuple[str, Path]] = []
    for path in list_episode_files(source_id):
        ep = read_json(path)
        guid = ep.get("guid")
        if not guid or not refs.get(guid):
            continue
        if not transcript_path_for(source_id, guid).exists():
            continue
        candidates.append((ep.get("date") or "", path))
    candidates.sort(key=lambda item: item[0], reverse=True)
    return [path for _, path in candidates[:limit]]


def _chat_completion(
    base_url: str,
    model: str,
    system: str,
    user: str,
    timeout: int,
    max_tokens: int,
) -> str:
    """Appelle /chat/completions. Retente sans json mode si le serveur refuse."""
    url = base_url.rstrip("/") + "/chat/completions"
    payload: dict[str, Any] = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": 0.0,
        "top_p": 0.9,
        "max_tokens": max_tokens,
        "response_format": {"type": "json_object"},
    }
    resp = requests.post(url, json=payload, timeout=timeout)
    if resp.status_code == 400:
        payload.pop("response_format", None)
        resp = requests.post(url, json=payload, timeout=timeout)
    resp.raise_for_status()
    data = resp.json()
    return data["choices"][0]["message"].get("content") or ""


def _extract_chunk(
    base_url: str,
    model: str,
    podcast_title: str,
    hosts: str,
    chunk: str,
    timeout: int,
    max_tokens: int,
) -> list[dict[str, Any]]:
    prompt = "/no_think\n" + USER_TEMPLATE.format(
        podcast_title=podcast_title,
        hosts=hosts,
        types=", ".join(sorted(VALID_TYPES)),
        chunk=chunk,
    )
    system = (
        SYSTEM_PROMPT
        + "\nTu reponds sans raisonnement visible. Si le modele supporte Qwen3, "
        + "utilise le mode /no_think. La sortie doit rester un objet JSON valide."
    )
    raw = _chat_completion(base_url, model, system, prompt, timeout, max_tokens)
    try:
        data = _extract_json_block(raw)
    except json.JSONDecodeError:
        log.warning("Reponse locale non JSON ignoree.")
        return []
    recos = data.get("recos", []) if isinstance(data, dict) else []
    return [r for r in (_normalize_reco(item) for item in recos) if r]


def _title_match(local_title: str, ref_title: str) -> bool:
    """Match exact normalise, puis fuzzy strict pour variantes mineures."""
    a = normalize_text(local_title)
    b = normalize_text(ref_title)
    if not a or not b:
        return False
    if a == b:
        return True
    return SequenceMatcher(None, a, b).ratio() >= 0.88


def _compare(
    local_recos: list[dict[str, Any]],
    ref_recos: list[dict[str, Any]],
) -> dict[str, Any]:
    matched_refs: set[int] = set()
    matches: list[dict[str, str]] = []
    extras: list[str] = []

    for local in local_recos:
        hit = None
        for i, ref in enumerate(ref_recos):
            if i in matched_refs:
                continue
            if _title_match(local.get("title", ""), ref.get("title", "")):
                hit = i
                break
        if hit is None:
            extras.append(local.get("title", ""))
            continue
        matched_refs.add(hit)
        matches.append({
            "local": local.get("title", ""),
            "reference": ref_recos[hit].get("title", ""),
        })

    missed = [
        ref.get("title", "")
        for i, ref in enumerate(ref_recos)
        if i not in matched_refs
    ]
    return {
        "reference_count": len(ref_recos),
        "local_count": len(local_recos),
        "matched_count": len(matches),
        "recall": len(matches) / len(ref_recos) if ref_recos else 0.0,
        "precision_proxy": len(matches) / len(local_recos) if local_recos else 0.0,
        "matches": matches,
        "missed_reference_titles": missed,
        "extra_local_titles": extras,
    }


def evaluate(args: argparse.Namespace) -> dict[str, Any]:
    source = load_source(args.source)
    podcast_title = source.get("title", args.source)
    hosts = ", ".join(source.get("hosts", [])) or "inconnus"
    refs_by_guid = _load_reference_recos(args.source)
    episode_paths = _select_episodes(args.source, args.limit)

    started = time.perf_counter()
    results: list[dict[str, Any]] = []
    totals = {
        "reference_count": 0,
        "local_count": 0,
        "matched_count": 0,
    }

    log.info("%d episode(s) selectionne(s).", len(episode_paths))
    for index, path in enumerate(episode_paths, 1):
        ep = read_json(path)
        guid = ep["guid"]
        transcript = transcript_path_for(args.source, guid).read_text(encoding="utf-8")
        chunks = _chunk_transcript(
            transcript,
            max_chars=args.chunk_chars,
            overlap_chars=args.chunk_overlap_chars,
        )
        if args.max_chunks:
            chunks = chunks[: args.max_chunks]

        log.info("[%d/%d] %s - %d chunk(s)",
                 index, len(episode_paths), ep.get("title", path.name), len(chunks))
        raw: list[dict[str, Any]] = []
        chunk_errors: list[dict[str, str]] = []
        ep_start = time.perf_counter()
        for chunk_index, chunk in enumerate(chunks, 1):
            log.info("  chunk %d/%d", chunk_index, len(chunks))
            try:
                raw.extend(
                    _extract_chunk(
                        args.base_url,
                        args.model,
                        podcast_title,
                        hosts,
                        chunk,
                        args.timeout,
                        args.max_tokens,
                    )
                )
            except requests.RequestException as exc:
                message = str(exc)
                response = getattr(exc, "response", None)
                if response is not None:
                    message = f"{message} :: {response.text[:500]}"
                log.error("  chunk %d/%d ignore: %s",
                          chunk_index, len(chunks), message)
                chunk_errors.append({"chunk": str(chunk_index), "error": message})
        local_recos = _dedupe(raw)
        ref_recos = refs_by_guid.get(guid, [])
        comparison = _compare(local_recos, ref_recos)
        for key in totals:
            totals[key] += comparison[key]

        results.append({
            "guid": guid,
            "title": ep.get("youtubeTitle") or ep.get("title"),
            "date": ep.get("date"),
            "seconds": round(time.perf_counter() - ep_start, 2),
            "chunk_count": len(chunks),
            "chunk_errors": chunk_errors,
            "local_recos": local_recos,
            "comparison": comparison,
        })

    summary = {
        **totals,
        "episode_count": len(results),
        "recall": totals["matched_count"] / totals["reference_count"]
        if totals["reference_count"] else 0.0,
        "precision_proxy": totals["matched_count"] / totals["local_count"]
        if totals["local_count"] else 0.0,
        "seconds": round(time.perf_counter() - started, 2),
    }
    return {
        "source": args.source,
        "base_url": args.base_url,
        "model": args.model,
        "limit": args.limit,
        "chunk_chars": args.chunk_chars,
        "summary": summary,
        "episodes": results,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Evalue un LLM local compatible OpenAI sur les transcripts."
    )
    parser.add_argument("--source", default="un-bon-moment")
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--chunk-chars", type=int, default=8_000)
    parser.add_argument("--chunk-overlap-chars", type=int, default=500)
    parser.add_argument("--max-chunks", type=int, default=None)
    parser.add_argument("--max-tokens", type=int, default=DEFAULT_MAX_TOKENS)
    parser.add_argument("--timeout", type=int, default=900)
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--dry-run", action="store_true",
                        help="Liste les episodes selectionnes sans appeler le LLM.")
    args = parser.parse_args()

    if args.dry_run:
        for path in _select_episodes(args.source, args.limit):
            ep = read_json(path)
            refs = _load_reference_recos(args.source).get(ep["guid"], [])
            print(f"{ep.get('date', '')}\t{ep['guid']}\t{len(refs)} recos\t{ep.get('title', path.name)}")
        return

    report = evaluate(args)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out = args.output or OUTPUT_DIR / (
        f"{args.source}-{args.model}-{int(time.time())}.json"
    )
    write_json_if_changed(out, report)
    s = report["summary"]
    log.info(
        "Eval terminee: episodes=%d, recall=%.1f%%, precision_proxy=%.1f%%, output=%s",
        s["episode_count"],
        s["recall"] * 100,
        s["precision_proxy"] * 100,
        out,
    )


if __name__ == "__main__":
    main()
