"""Récupère un transcript depuis cur.json côté portable (à exécuter sur le portable)."""
import json, sys
src = sys.argv[1]
dst = sys.argv[2]
data = json.load(open(src, encoding="utf-8", errors="replace"))
lines = []
for t in data.get("transcription", []):
    ms = t["offsets"]["from"]
    s = ms // 1000
    h = s // 3600
    m = (s // 60) % 60
    ss = s % 60
    lines.append(f"[{h:02d}:{m:02d}:{ss:02d}] {t['text'].strip()}")
open(dst, "w", encoding="utf-8").write("\n".join(lines) + "\n")
print(f"OK {len(lines)} segments -> {dst}")
