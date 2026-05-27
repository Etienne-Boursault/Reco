"""
extract_from_acast_backups.py — Restaure les recos Acast supprimées par
erreur en utilisant les backups `{guid}.acast.txt`.

Pour chaque épisode ciblé qui a un backup Acast :
  1. Sauve le transcript YT actuel `{guid}.txt` en `{guid}.yt.tmp.txt`.
  2. Renomme le backup `{guid}.acast.txt` en `{guid}.txt` (transcript actif).
  3. Lance extract_recos.py --provider anthropic puis --provider openai.
  4. Restaure : `{guid}.txt` → `{guid}.acast.txt` ; `{guid}.yt.tmp.txt` → `{guid}.txt`.

Idempotent : si un swap est interrompu, relancer répare l'état initial.

Usage :
    python extract_from_acast_backups.py --source un-bon-moment --guids-file <fichier>
"""
from __future__ import annotations

import argparse
import shlex
import subprocess
import sys
from pathlib import Path

from common import TRANSCRIPTS_DIR, log


def _swap(src: Path, dst: Path) -> None:
    """Renomme src → dst (échec si dst existe déjà)."""
    if dst.exists():
        raise FileExistsError(f"{dst} existe déjà ; refus d'écraser.")
    src.rename(dst)


def restore_initial(guid: str, trans_dir: Path) -> None:
    """Restaure l'état initial (transcript YT actif, backup .acast en backup)."""
    txt = trans_dir / f"{guid}.txt"
    yt_tmp = trans_dir / f"{guid}.yt.tmp.txt"
    acast = trans_dir / f"{guid}.acast.txt"
    # Si l'état actuel est le swap (txt = acast content, yt en .tmp), inverser.
    if yt_tmp.exists():
        if txt.exists():
            # txt contient l'Acast (renvoyer en .acast.txt)
            if not acast.exists():
                txt.rename(acast)
            else:
                txt.unlink()
        yt_tmp.rename(txt)


def run_extraction(guid: str, source: str, provider: str) -> None:
    """Lance extract_recos.py pour un guid donné via subprocess."""
    cmd = [sys.executable, str(Path(__file__).parent / "extract_recos.py"),
           "--source", source, "--guid", guid, "--provider", provider]
    log.info("  → %s", shlex.join(cmd))
    result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
    if result.returncode != 0:
        log.error("    échec : %s", result.stderr.strip()[-300:])
    else:
        # Garder les 2 dernières lignes (résumé)
        last = result.stdout.strip().splitlines()[-2:]
        for line in last:
            log.info("    %s", line)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True)
    parser.add_argument("--guids-file", required=True)
    args = parser.parse_args()

    trans_dir = TRANSCRIPTS_DIR / args.source
    guids = [g.strip() for g in Path(args.guids_file).read_text(encoding="utf-8").splitlines() if g.strip()]
    log.info("%d guid(s) ciblés.", len(guids))

    for i, guid in enumerate(guids, 1):
        acast_backup = trans_dir / f"{guid}.acast.txt"
        if not acast_backup.exists():
            log.warning("[%d/%d] %s : pas de backup .acast.txt, skip.", i, len(guids), guid)
            continue

        txt = trans_dir / f"{guid}.txt"
        yt_tmp = trans_dir / f"{guid}.yt.tmp.txt"

        log.info("\n[%d/%d] === %s ===", i, len(guids), guid)
        try:
            # 1) Sauver le YT actif en .yt.tmp.txt (s'il existe)
            if txt.exists():
                _swap(txt, yt_tmp)
            # 2) Faire de l'Acast backup le transcript actif
            _swap(acast_backup, txt)

            # 3) Extraction Acast (Anthropic + OpenAI)
            run_extraction(guid, args.source, "anthropic")
            run_extraction(guid, args.source, "openai")
        finally:
            # 4) Restaurer l'état initial même en cas d'erreur
            try:
                if txt.exists() and not acast_backup.exists():
                    txt.rename(acast_backup)
                if yt_tmp.exists():
                    yt_tmp.rename(txt)
            except OSError as exc:  # noqa: BLE001 — on log et on continue.
                log.warning("Restauration de l'état initial pour %s échouée : %s",
                            guid, exc)

    log.info("\nTerminé.")


if __name__ == "__main__":
    main()
