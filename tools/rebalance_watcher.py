"""
rebalance_watcher.py — Watcher de coordination main (CPU) ⇄ portable (GPU).

Tourne sur la machine principale et fait deux choses :

  1. **Rapatriement périodique** : toutes les 10 min, pull tous les .txt nouveaux
     depuis le portable (par défaut http://llm.local:8002) vers le dossier
     projet. Ainsi, un guid déjà transcrit par le portable apparaît localement
     et la transcribe en cours sur main le saute automatiquement (cache par
     existence de fichier).

  2. **Rééquilibrage** : dès que le portable a fini sa liste initiale (49 .txt
     servis), réécrit `dispatch/laptop_guids.txt` avec ~75 % de ce qu'il reste
     à faire côté main (la queue arrière, là où main n'est pas près d'arriver
     → pas de double traitement). Il suffit alors de relancer `worker_gpu.sh`
     sur le portable : il pull la nouvelle liste et continue.

S'arrête quand tous les épisodes (ayant une vidéo YT) ont leur transcription
localement sur la machine principale.

Usage :
    python rebalance_watcher.py --source un-bon-moment

Configurable par variables d'environnement (optionnel) :
    LAPTOP_URL  (défaut: http://llm.local:8002)
    SSH_HOST    (défaut: llm@llm.local)
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path

from common import list_episode_files, log, read_json, transcript_path_for

# --- Configuration --------------------------------------------------------
# Surchargeable par env pour adapter à un autre setup sans toucher au code.
LAPTOP_URL = os.environ.get("LAPTOP_URL", "http://llm.local:8002")
SSH_HOST = os.environ.get("SSH_HOST", "llm@llm.local")

DISPATCH = Path(__file__).resolve().parent / "dispatch"
PORTABLE_INITIAL = 49        # taille de la liste laptop_guids.txt initiale
POLL_SECONDS = 600           # 10 min
HANDOVER_RATIO = 0.75        # part du restant main donnée au portable
HANG_THRESHOLD = 45 * 60     # 45 min sans nouveau transcript -> kill+relance

# Clé SSH : ~/.ssh/reco_laptop, en gérant Windows (USERPROFILE) et POSIX (HOME).
_HOME = os.environ.get("USERPROFILE") or os.environ.get("HOME") or "."
SSH_KEY = Path(_HOME) / ".ssh" / "reco_laptop"
SSH_OPTS = ["-i", str(SSH_KEY), "-o", "StrictHostKeyChecking=accept-new",
            "-o", "BatchMode=yes", "-o", "ConnectTimeout=10"]


def transcripts_dir_for(source_id: str) -> Path:
    """Dossier des transcripts d'une source (sur la machine principale)."""
    return Path(__file__).resolve().parent / "output" / "transcripts" / source_id


def laptop_transcripts() -> set[str] | None:
    """Liste les .txt servis par le portable (None si injoignable)."""
    try:
        with urllib.request.urlopen(LAPTOP_URL + "/", timeout=10) as r:
            html = r.read().decode("utf-8", errors="ignore")
        return set(re.findall(r'href="([^"]+\.txt)"', html))
    except urllib.error.URLError:
        return None


def pull_missing(remote_files: set[str], transcripts_dir: Path) -> int:
    """Télécharge les fichiers absents en local. Renvoie le nombre récupéré."""
    transcripts_dir.mkdir(parents=True, exist_ok=True)
    new = 0
    for fname in remote_files:
        target = transcripts_dir / fname
        if target.exists():
            continue
        try:
            with urllib.request.urlopen(LAPTOP_URL + "/" + fname, timeout=30) as r:
                target.write_bytes(r.read())
            new += 1
        except urllib.error.URLError as e:
            log.warning("pull %s : %s", fname, e)
    return new


def main_remaining_guids(source_id: str) -> list[str]:
    """Guids de main_guids.txt qui n'ont PAS encore de transcript local."""
    raw = (DISPATCH / "main_guids.txt").read_text(encoding="utf-8").splitlines()
    pending = []
    for guid in (g.strip() for g in raw):
        if guid and not transcript_path_for(source_id, guid).exists():
            pending.append(guid)
    return pending


def _ssh(cmd: str, timeout: int = 30) -> subprocess.CompletedProcess:
    """Exécute une commande sur le portable via SSH."""
    return subprocess.run(
        ["ssh", *SSH_OPTS, SSH_HOST, cmd],
        capture_output=True, text=True, timeout=timeout,
    )


def laptop_worker_running() -> bool:
    """Vrai si un worker_gpu.sh est en cours d'exécution sur le portable."""
    r = _ssh("pgrep -f 'bash.*worker_gpu' >/dev/null && echo YES || echo NO")
    return r.stdout.strip() == "YES"


def relaunch_worker_on_laptop() -> bool:
    """Lance worker_gpu.sh sur le portable, détaché (nohup). Renvoie le succès."""
    cmd = ("nohup bash ~/worker_gpu.sh > ~/worker.log 2>&1 < /dev/null "
           "& disown ; sleep 1 ; pgrep -f 'bash.*worker_gpu' >/dev/null && echo OK")
    r = _ssh(cmd)
    if "OK" in r.stdout:
        log.info("Worker portable RELANCÉ via SSH (log: ~/worker.log).")
        return True
    log.error("Échec relance SSH : rc=%s, stdout=%s, stderr=%s",
              r.returncode, r.stdout.strip(), r.stderr.strip())
    return False


def rebalance(source_id: str) -> int:
    """Réécrit laptop_guids.txt avec la queue arrière de main. Renvoie taille."""
    pending = main_remaining_guids(source_id)
    if not pending:
        return 0
    n = max(1, int(round(len(pending) * HANDOVER_RATIO)))
    handover = pending[-n:]  # la fin = ce que main n'a pas encore commencé
    (DISPATCH / "laptop_guids.txt").write_text(
        "\n".join(handover) + "\n", encoding="utf-8", newline="\n",
    )
    log.info("REBALANCE : portable récupère %d épisodes (queue arrière de main).", n)

    # On attend que l'ancien worker soit bien terminé (la liste de 49 est finie).
    if laptop_worker_running():
        log.info("L'ancien worker tourne encore — on attend la prochaine boucle.")
        return n
    relaunch_worker_on_laptop()
    return n


def global_missing(source_id: str) -> int:
    """Compte les épisodes (avec YT) sans transcript local."""
    missing = 0
    for path in list_episode_files(source_id):
        ep = read_json(path)
        if ep.get("youtubeUrl") and not transcript_path_for(source_id, ep["guid"]).exists():
            missing += 1
    return missing


def watch_loop(source_id: str) -> None:
    """Boucle principale du watcher (sortie quand plus rien à transcrire)."""
    transcripts_dir = transcripts_dir_for(source_id)
    guids_written = False     # nouvelle laptop_guids.txt déjà écrite
    worker_kicked = False     # nouveau worker portable lancé
    last_count = -1           # dernier nb de transcripts vus côté portable
    last_change = time.time() # quand le compteur a bougé pour la dernière fois
    log.info("Watcher de rééquilibrage démarré (poll %ds, %s).",
             POLL_SECONDS, LAPTOP_URL)
    while True:
        remote = laptop_transcripts()
        if remote is None:
            log.warning("portable injoignable (%s), je retente dans 60 s",
                        LAPTOP_URL)
            time.sleep(60)
            continue

        new = pull_missing(remote, transcripts_dir)
        if new:
            log.info("pull : %d nouveau(x) transcript(s) rapatrié(s)", new)

        # Détection du « hang » : pas de nouveau transcript depuis HANG_THRESHOLD ?
        if len(remote) != last_count:
            last_count = len(remote)
            last_change = time.time()
        elif time.time() - last_change > HANG_THRESHOLD and global_missing(source_id) > 0:
            mins = int((time.time() - last_change) / 60)
            log.warning("HANG détecté : aucun nouveau transcript depuis %d min — "
                        "je tue et relance le worker portable.", mins)
            _ssh("pkill -f 'bash.*worker_gpu' ; sleep 2 ; pkill -9 -f 'bash.*worker_gpu' ; true")
            time.sleep(2)
            if relaunch_worker_on_laptop():
                last_change = time.time()  # on laisse une nouvelle fenêtre

        # Seuil atteint : on (re)bascule la queue arrière de main au portable.
        if len(remote) >= PORTABLE_INITIAL:
            if not guids_written:
                log.info("Portable a terminé sa liste initiale (%d transcripts servis).",
                         len(remote))
                rebalance(source_id)
                guids_written = True
                worker_kicked = laptop_worker_running()
            elif not worker_kicked:
                if not laptop_worker_running():
                    worker_kicked = relaunch_worker_on_laptop()

        missing = global_missing(source_id)
        log.info("État : portable=%d transcripts, à faire (global)=%d",
                 len(remote), missing)
        if missing == 0:
            log.info("Tout est transcrit. Fin du watcher.")
            return
        time.sleep(POLL_SECONDS)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True,
                        help="Identifiant de la source (ex: un-bon-moment).")
    args = parser.parse_args()
    watch_loop(args.source)


if __name__ == "__main__":
    main()
