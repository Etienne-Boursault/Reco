#!/usr/bin/env bash
# Transcrire S5E32 sur le portable (GPU whisper.cpp).
set -e
GUID=6a10a31516a6aa135ed729e1
URL='https://www.youtube.com/watch?v=-lGjDOH7qPw'
TRANS_DIR="$HOME/transcripts/un-bon-moment"
mkdir -p "$TRANS_DIR" ~/yt_tmp
cd ~/yt_tmp
export PATH="$HOME/.deno/bin:$PATH"
source ~/wh/bin/activate

echo "== 1/4 yt-dlp =="
rm -f s5e32.*
yt-dlp -q -x --audio-format mp3 -o s5e32.mp3 "$URL" </dev/null

echo "== 2/4 ffmpeg =="
ffmpeg -nostdin -y -loglevel error -i s5e32.mp3 -ar 16000 -ac 1 s5e32.wav </dev/null

echo "== 3/4 whisper-cli (GPU) =="
~/whisper.cpp/build/bin/whisper-cli -m ~/whisper.cpp/models/ggml-small.bin -l fr -oj -of s5e32 s5e32.wav </dev/null

echo "== 4/4 JSON -> txt =="
GUID="$GUID" TRANS_DIR="$TRANS_DIR" python3 - <<'PY'
import json, os
guid = os.environ["GUID"]; trans_dir = os.environ["TRANS_DIR"]
data = json.load(open("s5e32.json", encoding="utf-8", errors="replace"))
lines = []
for t in data.get("transcription", []):
    ms = t["offsets"]["from"]; s = ms // 1000
    h, rem = divmod(s, 3600); m, ss = divmod(rem, 60)
    lines.append(f"[{h:02d}:{m:02d}:{ss:02d}] {t['text'].strip()}")
open(f"{trans_dir}/{guid}.txt", "w", encoding="utf-8").write("\n".join(lines) + "\n")
print("OK", len(lines), "segments")
PY
echo "DONE"
