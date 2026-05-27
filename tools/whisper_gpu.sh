#!/usr/bin/env bash
# whisper_gpu.sh — Compile whisper.cpp avec CUDA pour la GTX 950M (archi 5.0)
# et benchmark sur ~/clip.mp3 (extrait de 5 min déjà téléchargé). Ubuntu.
#
# faster-whisper ne supporte pas Maxwell ; whisper.cpp, compilé pour l'archi 50,
# si. Usage : bash whisper_gpu.sh
set -e

echo "== 1/7 Dépendances de compilation + CUDA toolkit (gros téléchargement) =="
sudo apt-get update -qq
sudo apt-get install -y -qq build-essential cmake git ffmpeg nvidia-cuda-toolkit gcc-12 g++-12

echo "== 2/7 Récupération de whisper.cpp =="
cd ~
[ -d whisper.cpp ] || git clone --depth 1 https://github.com/ggml-org/whisper.cpp
cd whisper.cpp

echo "== 3/7 Swap anti-OOM + compilation CUDA (archi 5.0, gcc-12, -j1) =="
# Compiler les kernels CUDA en parallèle sature la RAM (OOM) sur ce portable.
# -> swap de secours + compilation EN SÉRIE (-j1). La compil reprend à ~80%.
if ! swapon --show=NAME --noheadings 2>/dev/null | grep -q /swapfile; then
  echo "  ajout d'un swap de 8 Go…"
  sudo fallocate -l 8G /swapfile 2>/dev/null || sudo dd if=/dev/zero of=/swapfile bs=1M count=8192
  sudo chmod 600 /swapfile && sudo mkswap /swapfile >/dev/null && sudo swapon /swapfile
fi
free -h
cmake -B build -DGGML_CUDA=1 -DCMAKE_CUDA_ARCHITECTURES=50 \
      -DCMAKE_CUDA_HOST_COMPILER=/usr/bin/gcc-12 -DCMAKE_BUILD_TYPE=Release
cmake --build build -j1 --config Release

echo "== 4/7 Modèle small (ggml) =="
[ -f models/ggml-small.bin ] || bash ./models/download-ggml-model.sh small

echo "== 5/7 Conversion de l'extrait en WAV 16 kHz =="
ffmpeg -y -loglevel error -i ~/clip.mp3 -ar 16000 -ac 1 ~/clip.wav

echo "== 6/7 Binaire whisper =="
BIN=$(find build -type f \( -name 'whisper-cli' -o -name 'main' \) | head -1)
echo "   $BIN"

echo "== 7/7 Benchmark GPU =="
START=$SECONDS
if ! "$BIN" -m models/ggml-small.bin -l fr -f ~/clip.wav > ~/clip_out.txt 2> ~/clip_err.txt; then
  echo ">>> ECHEC — fin du log d'erreur :"; tail -8 ~/clip_err.txt; exit 1
fi
DT=$((SECONDS - START))
echo ""
awk -v dt="$DT" 'BEGIN{ if (dt<1) dt=1; printf(">>> RESULTAT : %d s pour 5 min audio — %.1fx temps reel\n", dt, 300.0/dt) }'
echo "(début de la transcription :)"
grep -m3 -E "\]" ~/clip_out.txt || head -3 ~/clip_out.txt
echo "(le GPU a-t-il été utilisé ?)"
grep -i -m1 "CUDA\|GPU" ~/clip_err.txt || echo "  (pas de mention GPU — vérifier)"
