"""auto_compare_large.py — Orchestrateur de l'étude comparative large-v3.

Polle le portable (192.168.1.127:8002), récupère les nouveaux transcripts
large-v3 au fil de l'eau, et pour chaque épisode :

  1. Backup du transcript actuel vers tools/output/whisper-cmp/baseline/
  2. Remplace par le large-v3
  3. Lance extract_recos.py avec Anthropic puis OpenAI (séquentiel)
  4. Met à jour episode JSON : transcriptModel='large-v3', transcriptSource='youtube'
  5. Stat le delta de recos pour l'épisode

Tourne en boucle jusqu'à ce que tous les guids attendus soient traités,
ou jusqu'à interruption clavier.

Usage :
  python tools/auto_compare_large.py
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

import requests

ROOT = Path(__file__).parent.parent
TOOLS = ROOT / "tools"
sys.path.insert(0, str(TOOLS))
from common import (  # noqa: E402
    log, transcript_path_for, find_episode_by_guid,
    read_json, write_json_if_changed, recos_dir_for,
)

# Sources de transcripts : portable (LAPTOP) + Mac. L'orchestrateur polle les
# deux et rapatrie le premier qui produit le .txt — l'autre worker passera
# (idempotent : skip si .txt déjà présent à destination).
SOURCES = [
    ("http://192.168.1.127:8002", "un-bon-moment-large-v3-turbo"),  # portable GPU
    ("http://192.168.1.168:8003", "un-bon-moment-large-v3-turbo"),  # Mac M4 Metal
]
LAPTOP_URL = SOURCES[0][0]  # rétrocompat / 1ère source
LAPTOP_DIR = SOURCES[0][1]
SOURCE_ID = "un-bon-moment"
CMP_DIR = TOOLS / "output" / "whisper-cmp"
BASELINE_DIR = CMP_DIR / "baseline"
LARGE_DIR = CMP_DIR / "large-v3"
PROGRESS_FILE = CMP_DIR / "auto_progress.json"
GUIDS_FILE = TOOLS / "dispatch" / "whisper_large_guids.txt"
PYTHON = sys.executable
POLL_SECONDS = 60

HREF_RE = re.compile(r'href="([^"/]+\.txt)"')


def _expected_guids() -> list[str]:
    return [g.strip() for g in GUIDS_FILE.read_text(encoding="utf-8").splitlines() if g.strip()]


def _load_progress() -> dict:
    if PROGRESS_FILE.exists():
        return json.loads(PROGRESS_FILE.read_text(encoding="utf-8"))
    return {"done": [], "stats": {}}


def _save_progress(p: dict) -> None:
    PROGRESS_FILE.parent.mkdir(parents=True, exist_ok=True)
    PROGRESS_FILE.write_text(json.dumps(p, ensure_ascii=False, indent=2),
                             encoding="utf-8")


def _list_remote_transcripts() -> dict[str, str]:
    """Renvoie {guid_filename: source_base_url} en interrogeant chaque worker."""
    available: dict[str, str] = {}
    for base_url, dir_name in SOURCES:
        try:
            r = requests.get(f"{base_url}/{dir_name}/", timeout=10)
            r.raise_for_status()
        except Exception as exc:  # noqa: BLE001
            log.warning("listing %s échoué : %s", base_url, exc)
            continue
        for fname in HREF_RE.findall(r.text):
            available.setdefault(fname, f"{base_url}/{dir_name}")
    return available


def _download(guid: str, remote: dict[str, str]) -> bool:
    LARGE_DIR.mkdir(parents=True, exist_ok=True)
    dest = LARGE_DIR / f"{guid}.txt"
    if dest.exists():
        return True
    base = remote.get(f"{guid}.txt")
    if not base:
        return False
    try:
        r = requests.get(f"{base}/{guid}.txt", timeout=30)
        r.raise_for_status()
    except Exception as exc:  # noqa: BLE001
        log.warning("download %s échoué : %s", guid, exc)
        return False
    dest.write_bytes(r.content)
    log.info("✓ rapatrié %s.txt (%d bytes)", guid, len(r.content))
    return True


def _backup_baseline(guid: str) -> None:
    src = transcript_path_for(SOURCE_ID, guid)
    if not src.exists():
        return
    BASELINE_DIR.mkdir(parents=True, exist_ok=True)
    dest = BASELINE_DIR / f"{guid}.txt"
    if not dest.exists():
        shutil.copy2(src, dest)


def _count_recos(guid: str) -> dict[str, int]:
    counts = {"total": 0, "anthropic": 0, "openai": 0, "both": 0,
              "validated": 0, "discarded": 0}
    for p in recos_dir_for(SOURCE_ID).glob("*.json"):
        d = json.loads(p.read_text(encoding="utf-8"))
        if d.get("episodeGuid") != guid:
            continue
        counts["total"] += 1
        ex = set(d.get("extractors") or [])
        if "anthropic" in ex: counts["anthropic"] += 1
        if "openai" in ex: counts["openai"] += 1
        if {"anthropic", "openai"}.issubset(ex): counts["both"] += 1
        if d.get("status") == "validated": counts["validated"] += 1
        if d.get("status") == "discarded": counts["discarded"] += 1
    return counts


def _run_extract(provider: str, guid: str) -> int:
    """Lance extract_recos.py, retourne le code de sortie."""
    cmd = [PYTHON, str(TOOLS / "extract_recos.py"),
           "--source", SOURCE_ID, "--provider", provider, "--guid", guid]
    log.info("extract_recos %s %s …", provider, guid)
    r = subprocess.run(cmd, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if r.returncode != 0:
        log.warning("extract %s %s exit=%d\nSTDERR:\n%s", provider, guid,
                    r.returncode, r.stderr[-500:])
    return r.returncode


def _process(guid: str, remote: dict[str, str]) -> dict | None:
    """Pour un guid : backup + swap transcript + double extract + stats."""
    if not _download(guid, remote):
        return None
    # 1. Backup transcript existant + swap par le large-v3
    _backup_baseline(guid)
    src_large = LARGE_DIR / f"{guid}.txt"
    dest = transcript_path_for(SOURCE_ID, guid)
    dest.parent.mkdir(parents=True, exist_ok=True)
    before = _count_recos(guid)
    shutil.copy2(src_large, dest)
    # 2. Met à jour episode JSON (modèle + source)
    try:
        ep_path = find_episode_by_guid(SOURCE_ID, guid)
        ep = read_json(ep_path)
        if ep.get("transcriptStatus") != "validated":
            ep["transcriptStatus"] = "auto"
        ep["transcriptModel"] = "large-v3"
        ep["transcriptSource"] = "youtube"
        write_json_if_changed(ep_path, ep)
    except FileNotFoundError as exc:
        log.warning("episode JSON non trouvé pour %s : %s", guid, exc)
    # 3. Extractions séquentielles (évite la race condition observée)
    for prov in ("anthropic", "openai"):
        rc = _run_extract(prov, guid)
        if rc != 0:
            log.warning("extract %s pour %s en échec (rc=%d)", prov, guid, rc)
    after = _count_recos(guid)
    delta = {k: after[k] - before[k] for k in after}
    log.info("📊 %s : before=%s after=%s delta=%s", guid, before, after, delta)
    return {"before": before, "after": after, "delta": delta}


def main() -> None:
    expected = _expected_guids()
    progress = _load_progress()
    done = set(progress["done"])
    log.info("📋 %d épisodes attendus, %d déjà traités",
             len(expected), len(done))
    while True:
        remote = _list_remote_transcripts()
        # Garde l'ordre du dispatch (plus récent en tête).
        ready = [g for g in expected
                 if g not in done and f"{g}.txt" in remote]
        log.info("⏳ %d transcripts rapatriables, %d total attendus",
                 len(ready), len(expected))
        for guid in ready:
            log.info("─── traitement %s ───", guid)
            stats = _process(guid, remote)
            if stats is not None:
                progress["stats"][guid] = stats
                progress["done"].append(guid)
                done.add(guid)
                _save_progress(progress)
            else:
                log.warning("skip %s (download fail)", guid)
        if len(done) >= len(expected):
            log.info("🏁 Tous les épisodes attendus sont traités.")
            break
        log.info("💤 sleep %ds avant prochain poll…", POLL_SECONDS)
        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        log.info("interruption clavier — état sauvegardé dans %s",
                 PROGRESS_FILE)
