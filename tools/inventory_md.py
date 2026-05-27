"""Génère docs/inventaire-<source>.md — tableau de bord complet d'une source.

Usage :
    python inventory_md.py --source un-bon-moment
"""
from __future__ import annotations

import argparse
import collections
from datetime import date
from pathlib import Path

from common import (
    EPISODES_DIR,
    PROJECT_ROOT,
    RECOS_DIR,
    TRANSCRIPTS_DIR,
    log,
    read_json,
)

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

# Seuil pour décider qu'une vidéo est un épisode complet (vs un extrait).
FULL_EPISODE_SECONDS = 1800  # 30 min


def fmt_dur(secs: int | float | None) -> str:
    """Formate une durée en secondes vers « MmnSS ». 0/None → « — »."""
    if not secs:
        return "—"
    secs = int(secs)
    minutes = secs // 60
    seconds = secs % 60
    return f"{minutes}mn{seconds:02d}"


def _load_episodes(ep_dir: Path) -> list[tuple[Path, dict]]:
    eps: list[tuple[Path, dict]] = []
    for path in ep_dir.glob("*.json"):
        eps.append((path, read_json(path)))
    eps.sort(key=lambda item: (item[1].get("season") or 0,
                               item[1].get("number") or 9999))
    return eps


def _count_recos(reco_dir: Path) -> collections.Counter:
    counts: collections.Counter = collections.Counter()
    if not reco_dir.exists():
        return counts
    for path in reco_dir.glob("*.json"):
        counts[read_json(path).get("episodeGuid", "")] += 1
    return counts


def _episode_label(season: int | None, number: int | None) -> str:
    if season and number:
        return f"**S{season}E{number}**"
    if number:
        return f"**#{number}**"
    return "—"


def _truncate_title(title: str, limit: int = 65) -> str:
    title = (title or "").replace("|", "／")
    if len(title) > limit:
        return title[:limit - 3] + "…"
    return title


def _source_cell(guid: str, has_transcript: bool, has_youtube: bool) -> str:
    if guid in YT_RETRANSCRIBE_GUIDS:
        return "🔄 Acast → YT" if has_transcript else "⏳ en cours"
    if has_transcript:
        return "✅ YT" if has_youtube else "🎧 Acast"
    return "❌"


def _recos_cell(n_recos: int, has_transcript: bool) -> str:
    if n_recos > 0:
        return "✅"
    if not has_transcript:
        return "⏳"
    return "❌"


def generate(source_id: str) -> Path:
    """Produit `docs/inventaire-<source_id>.md`. Renvoie le chemin écrit."""
    ep_dir = EPISODES_DIR / source_id
    transcripts_dir = TRANSCRIPTS_DIR / source_id
    reco_dir = RECOS_DIR / source_id

    eps = _load_episodes(ep_dir)
    recos_by_guid = _count_recos(reco_dir)

    n_total = len(eps)
    n_extracts = sum(
        1 for _, d in eps
        if (d.get("youtubeDuration") or 0) < FULL_EPISODE_SECONDS
        and (d.get("audioDuration") or 0) >= FULL_EPISODE_SECONDS
    )
    n_with_recos = sum(1 for _, d in eps if recos_by_guid[d["guid"]] > 0)
    n_with_transcript = sum(
        1 for _, d in eps if (transcripts_dir / f"{d['guid']}.txt").exists()
    )
    total_recos = sum(recos_by_guid.values())
    n_yt_retranscribe = len(YT_RETRANSCRIBE_GUIDS)
    n_acast_backup = len(ACAST_BACKUP_GUIDS)

    today = date.today().isoformat()
    lines: list[str] = [
        f"# Inventaire complet — {source_id}",
        "",
        f"_Généré le {today}. Total : {n_total} épisodes._",
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
        guid = d["guid"]
        season = d.get("season")
        ep_number = d.get("number")
        label = _episode_label(season, ep_number)
        title = _truncate_title(d.get("title") or "")
        aud_dur = fmt_dur(d.get("audioDuration"))
        yt_dur = fmt_dur(d.get("youtubeDuration"))
        yt_url = d.get("youtubeUrl") or ""
        is_extract = (
            (d.get("youtubeDuration") or 0) < FULL_EPISODE_SECONDS
            and (d.get("audioDuration") or 0) >= FULL_EPISODE_SECONDS
        )
        yt_cell = f"[lien]({yt_url})" if yt_url else "—"
        if is_extract:
            yt_cell += " ⚠️"
        n_recos = recos_by_guid[guid]
        has_transcript = (transcripts_dir / f"{guid}.txt").exists()
        has_acast_backup = (transcripts_dir / f"{guid}.acast.txt").exists()
        source_cell = _source_cell(guid, has_transcript, bool(yt_url))
        backup_cell = "✅" if has_acast_backup else "—"
        recos_cell = _recos_cell(n_recos, has_transcript)
        thumb_cell = "✅" if yt_url else "❌"
        lines.append(
            f"| {label} | {title} | {aud_dur} | {yt_cell} | {yt_dur} | "
            f"{n_recos} | {source_cell} | {backup_cell} | {recos_cell} | {thumb_cell} |"
        )

    out = PROJECT_ROOT / "docs" / f"inventaire-{source_id}.md"
    out.parent.mkdir(exist_ok=True)
    out.write_text("\n".join(lines), encoding="utf-8", newline="\n")
    log.info("Écrit : %s (%d lignes)", out, len(lines))
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True,
                        help="Identifiant de la source (ex: un-bon-moment).")
    args = parser.parse_args()
    generate(args.source)


if __name__ == "__main__":
    main()
