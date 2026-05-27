"""Génère docs/inventaire-un-bon-moment.md — tableau de bord complet."""
from __future__ import annotations
import json, collections
from pathlib import Path

EP_DIR = Path("src/content/episodes/un-bon-moment")
TR_DIR = Path("tools/output/transcripts/un-bon-moment")
RECO_DIR = Path("src/content/recos/un-bon-moment")

# Guids en cours de re-transcription depuis l'audio YouTube (le worker portable
# remplace progressivement le transcript Acast actuel par un transcript YT
# aligné sur la vidéo).
YT_RETRANSCRIBE_GUIDS = {
    "61cb19444f2d030012ddd82a", "6302667b4913bd00126c374c", "6550c05703445c0011dd8343",
    "6550c2836b767e0012a65d8d", "9536da14-4023-4a5b-b6e3-d6a73a405eb1",
    "6c166c4a-6617-4176-a9ad-5bcf874c9b6b", "712ea7fc-593d-472e-99ae-9ca35fcd2a05",
    "7870d7fa-cb20-4051-8458-27dbf903dbe8", "652406c019376d001282c4d8",
    "65240e1c5d8481001225962c",
    "6584658132930b0016c5272b", "6599de12076e6c001696556a", "65c7a2673210d00017783f8b",
    "bf76185c-2ca0-4324-9adf-a7977d745a2d", "8fea089a-4ebc-4aff-a90a-9ed6a94a30be",
    "6322de1f35ce9e001229f98a", "633b305f3ca1cc001201a861",
    "65240aefc8996500127ede97", "65240f8a7a4ced00123481d1",
    "6a10a31516a6aa135ed729e1", "633b2f213ca1cc001201a69f",
    "cbfadce5-1677-43ec-8665-8b47daeda6b7",
}
# Sous-ensemble : ceux dont le transcript Acast a été préservé en backup (.acast.txt).
ACAST_BACKUP_GUIDS = {
    "61cb19444f2d030012ddd82a", "6302667b4913bd00126c374c", "6550c05703445c0011dd8343",
    "6550c2836b767e0012a65d8d", "9536da14-4023-4a5b-b6e3-d6a73a405eb1",
    "6c166c4a-6617-4176-a9ad-5bcf874c9b6b", "712ea7fc-593d-472e-99ae-9ca35fcd2a05",
    "7870d7fa-cb20-4051-8458-27dbf903dbe8", "652406c019376d001282c4d8",
    "65240e1c5d8481001225962c",
    "6584658132930b0016c5272b", "6599de12076e6c001696556a", "65c7a2673210d00017783f8b",
    "bf76185c-2ca0-4324-9adf-a7977d745a2d",
    "6a10a31516a6aa135ed729e1", "633b2f213ca1cc001201a69f",
    "cbfadce5-1677-43ec-8665-8b47daeda6b7",
}

def fmt_dur(secs):
    if not secs:
        return "—"
    secs = int(secs)
    m = secs // 60
    s = secs % 60
    return f"{m}mn{s:02d}"

eps = []
for p in EP_DIR.glob("*.json"):
    with open(p, encoding="utf-8") as f:
        eps.append((p, json.load(f)))

recos_by_guid = collections.Counter()
for r in RECO_DIR.glob("*.json"):
    with open(r, encoding="utf-8") as f:
        recos_by_guid[json.load(f).get("episodeGuid", "")] += 1

eps.sort(key=lambda item: (item[1].get("season") or 0, item[1].get("number") or 9999))

n_total = len(eps)
n_extracts = sum(1 for _, d in eps
                 if (d.get("youtubeDuration") or 0) < 1800
                 and (d.get("audioDuration") or 0) >= 1800)
n_with_recos = sum(1 for _, d in eps if recos_by_guid[d["guid"]] > 0)
n_with_transcript = sum(1 for _, d in eps if (TR_DIR / f"{d['guid']}.txt").exists())
total_recos = sum(recos_by_guid.values())

n_yt_retranscribe = len(YT_RETRANSCRIBE_GUIDS)
n_acast_backup = len(ACAST_BACKUP_GUIDS)

lines = [
    "# Inventaire complet — un-bon-moment",
    "",
    f"_Généré le 2026-05-26. Total : {n_total} épisodes._",
    "",
    (f"**Résumé** : {n_with_recos}/{n_total} avec recos · "
     f"{n_with_transcript}/{n_total} transcrits · "
     f"{total_recos} recos extraites · "
     f"⚠️ **{n_extracts} épisodes avec lien YT vers un extrait <30min**"),
    "",
    "## Source des transcripts",
    "",
    "Trois cas selon l'origine de l'audio transcrit (les timecodes du transcript "
    "s'alignent sur cet audio, ce qui détermine l'exactitude du lien « ▶ vérifier "
    "à HH:MM:SS ») :",
    "",
    "- ✅ **YT** : audio téléchargé depuis la vidéo YouTube via yt-dlp. Timecodes "
    "  alignés sur la vidéo, lien de relecture exact. État cible.",
    f"- 🔄 **Acast → YT en cours** : {n_yt_retranscribe} épisodes étaient transcrits "
    "  depuis l'audio Acast (timecodes décalés par rapport à la vidéo YT à cause "
    "  du montage). Le worker portable refait la transcription depuis l'audio YT. "
    f"  {n_acast_backup} d'entre eux ont une **sauvegarde** `{{guid}}.acast.txt` "
    "  pour cross-valider les nouvelles recos contre les anciennes.",
    "- 🎧 **Acast (volontaire)** : pour les épisodes dont aucune vidéo YT complète "
    "  n'existe sur la chaîne (ex. #18 « Alice DAVID et BÉRENGÈRE KRIEF »). Seul "
    "  l'audio Acast est disponible.",
    "",
    "## Plan de cross-validation des recos (post re-transcription YT)",
    "",
    "1. Re-extraction LLM (Anthropic + OpenAI) sur le nouveau transcript YT → "
    "   nouvelles recos avec timestamps alignés vidéo.",
    "2. Pour les épisodes avec backup Acast : comparer les nouvelles recos YT aux "
    "   recos Acast existantes. Le champ `extractors` s'enrichit alors avec des "
    "   marqueurs additionnels (`anthropic-yt`, `anthropic-acast`, etc.).",
    "3. Une reco présente dans les **deux sources** (Acast et YT) ET extraite par "
    "   les **deux LLMs** est un signal de robustesse maximal (⭐⭐).",
    "",
    "## Tableau",
    "",
    "| # | Titre | Audio | Lien YT | YT dur | Recos | Source transcript | Backup Acast | Recos | Miniature |",
    "|---|---|---:|---|---:|---:|:-:|:-:|:-:|:-:|",
]

for _, d in eps:
    g = d["guid"]
    s = d.get("season")
    n = d.get("number")
    if s and n:
        label = f"**S{s}E{n}**"
    elif n:
        label = f"**#{n}**"
    else:
        label = "—"
    title = (d.get("title") or "").replace("|", "／")
    if len(title) > 65:
        title = title[:62] + "…"
    aud = fmt_dur(d.get("audioDuration"))
    ytd = fmt_dur(d.get("youtubeDuration"))
    yt = d.get("youtubeUrl") or ""
    is_extract = (d.get("youtubeDuration") or 0) < 1800 and (d.get("audioDuration") or 0) >= 1800
    yt_cell = f"[lien]({yt})" if yt else "—"
    if is_extract:
        yt_cell += " ⚠️"
    nr = recos_by_guid[g]
    has_t = (TR_DIR / f"{g}.txt").exists()
    has_acast_backup = (TR_DIR / f"{g}.acast.txt").exists()
    # Source du transcript actuel
    if g in YT_RETRANSCRIBE_GUIDS:
        if has_t:
            source_cell = "🔄 Acast → YT"
        else:
            source_cell = "⏳ en cours"
    elif has_t:
        source_cell = "✅ YT" if yt else "🎧 Acast"
    else:
        source_cell = "❌"
    backup_cell = "✅" if has_acast_backup else ("—" if g not in YT_RETRANSCRIBE_GUIDS else "—")
    if nr > 0:
        recos_cell = "✅"
    elif not has_t:
        recos_cell = "⏳"
    else:
        recos_cell = "❌"
    thumb_cell = "✅" if yt else "❌"
    lines.append(f"| {label} | {title} | {aud} | {yt_cell} | {ytd} | {nr} | {source_cell} | {backup_cell} | {recos_cell} | {thumb_cell} |")

out = Path("docs/inventaire-un-bon-moment.md")
out.parent.mkdir(exist_ok=True)
out.write_text("\n".join(lines), encoding="utf-8", newline="\n")
print(f"Écrit : {out} ({len(lines)} lignes)")
