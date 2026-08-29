#!/usr/bin/env bash
# gpu_test.sh — Benchmark faster-whisper sur GPU (Ubuntu / GTX 950M).
# La GTX 950M (Maxwell) ne supporte QUE float32. yt-dlp a besoin de deno.
#
# Usage : bash gpu_test.sh ["<url youtube>"]
set -e

VIDEO="${1:-https://www.youtube.com/watch?v=Uo_03B3Q8Ag}"

echo "== 1/6 Paquets système =="
sudo apt-get update -qq
sudo apt-get install -y -qq python3-venv ffmpeg curl

echo "== 2/6 Runtime JS (deno) pour yt-dlp =="
# On installe le binaire d'une version figée, dont on vérifie l'empreinte, au
# lieu de passer par `deno.land/install.sh`. Ce script-là change sans préavis :
# impossible d'en figer une empreinte, et le tuyauter dans `sh` exécutait à
# l'aveugle ce que le CDN renvoyait ce jour-là.
#
# L'URL de release GitHub est immuable, et l'empreinte est comparée avant toute
# exécution. Limite assumée : le `.sha256sum` vient de la même origine que
# l'archive, donc ceci ne protège pas d'un compromis de GitHub lui-même. Cela
# couvre le reste — altération après publication, interception réseau,
# téléchargement tronqué, substitution de version.
#
# Pour monter de version : changer DENO_VERSION, puis relever l'empreinte sur
#   https://github.com/denoland/deno/releases/download/<version>/deno-x86_64-unknown-linux-gnu.zip.sha256sum
# Épingler une version, c'est aussi épingler une architecture : `install.sh`
# choisissait l'archive selon la machine, plus maintenant. On refuse donc
# explicitement ce qu'on ne sait pas installer, plutôt que de déposer un binaire
# x86_64 qui échouerait plus loin sur un « format incorrect » incompréhensible.
# Le reste du script suppose de toute façon Ubuntu + CUDA (cf. en-tête).
DENO_VERSION="v2.9.6"
DENO_SHA256="394f07f4da2bebe6ce6f1e7ce0fa16429b29b08c35e3fac3fe25972676dff4b2"

arch=$(uname -m)
if [ "$arch" != "x86_64" ]; then
  echo "ERREUR : architecture $arch non prise en charge (x86_64 attendu)." >&2
  echo "  Pour l'ajouter : relever l'empreinte de l'archive deno correspondante sur" >&2
  echo "  https://github.com/denoland/deno/releases/tag/${DENO_VERSION}" >&2
  exit 1
fi

if ! command -v deno >/dev/null 2>&1; then
  deno_tmp=$(mktemp -d)
  # Nettoyage garanti même si curl, l'empreinte ou unzip échouent : `set -e`
  # ferait sinon sortir le script en laissant l'archive derrière lui.
  trap 'rm -rf "$deno_tmp"' EXIT

  sudo apt-get install -y -qq unzip
  curl -fsSL -o "$deno_tmp/deno.zip" \
    "https://github.com/denoland/deno/releases/download/${DENO_VERSION}/deno-x86_64-unknown-linux-gnu.zip"

  echo "${DENO_SHA256}  ${deno_tmp}/deno.zip" | sha256sum -c - || {
    echo "ERREUR : l'empreinte de l'archive deno ne correspond pas. Installation interrompue." >&2
    exit 1
  }

  mkdir -p "$HOME/.deno/bin"
  unzip -oq "$deno_tmp/deno.zip" -d "$HOME/.deno/bin"
  chmod +x "$HOME/.deno/bin/deno"

  rm -rf "$deno_tmp"
  trap - EXIT
fi
export PATH="$HOME/.deno/bin:$PATH"

echo "== 3/6 Env Python + faster-whisper + libs CUDA =="
python3 -m venv ~/wh
source ~/wh/bin/activate
pip install -q -U pip faster-whisper yt-dlp nvidia-cublas-cu12 nvidia-cudnn-cu12

echo "== 4/6 Chemins cuDNN/cuBLAS (via find) =="
CUBLAS_DIR=$(dirname "$(find ~/wh -name 'libcublas.so*' | head -1)")
CUDNN_DIR=$(dirname "$(find ~/wh -name 'libcudnn.so*' | head -1)")
export LD_LIBRARY_PATH="$CUBLAS_DIR:$CUDNN_DIR:$LD_LIBRARY_PATH"
echo "   $LD_LIBRARY_PATH"

echo "== 5/6 Extrait de 5 min (si absent) =="
[ -f clip.mp3 ] || yt-dlp -q -x --audio-format mp3 --download-sections "*0-300" -o clip.mp3 "$VIDEO"
ls -la clip.mp3

echo "== 6/6 Benchmark GPU (float32) =="
python - <<'PY'
import time
from faster_whisper import WhisperModel
try:
    m = WhisperModel("small", device="cuda", compute_type="float32")
    t = time.time()
    segs, info = m.transcribe("clip.mp3", language="fr", vad_filter=True, beam_size=5)
    n = sum(1 for _ in segs)
    dt = time.time() - t
    print(f"\n>>> RESULTAT : OK float32 — 5 min audio en {dt:.0f}s — {300/dt:.1f}x temps reel — {n} segments\n")
except Exception as e:
    print(f"\n>>> ECHEC : {type(e).__name__}: {e}\n")
PY
