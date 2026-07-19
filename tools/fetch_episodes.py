"""
fetch_episodes.py — Étape 1 du pipeline « Reco ».

Récupère la liste des épisodes depuis le flux RSS Acast d'une source
(URL `rssUrl` lue dans `src/content/sources/<id>.json`), parse le flux avec
feedparser et produit *un fichier JSON par épisode* dans
`src/content/episodes/<sourceId>/`, conforme au schéma Episode.

Champs produits :
  - sourceId          : l'identifiant de la source
  - guid              : identifiant stable issu du <guid> RSS
  - number            : numéro d'épisode si déductible (titre, balise itunes)
  - title             : titre de l'épisode
  - date              : date de publication au format ISO « YYYY-MM-DD »
  - audioUrl          : URL de l'enclosure audio (mp3…)
  - description       : description / résumé
  - guests            : laissé vide ([]) — l'extraction des invités n'est pas fiable ici
  - transcriptStatus  : "none" (aucune transcription au moment de la collecte)

Idempotent : un épisode déjà présent et inchangé n'est pas réécrit. Si l'épisode
existe déjà avec un transcriptStatus "auto"/"validated", celui-ci est *préservé*
(on ne régresse pas l'état du pipeline).

Usage :
    python fetch_episodes.py --source un-bon-moment [--limit N] [--rss URL]
"""

from __future__ import annotations

import argparse
import html
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import feedparser  # type: ignore
import requests

from common import (
    episodes_dir_for,
    list_episode_files,
    load_source,
    log,
    read_json,
    slugify,
    write_json_if_changed,
)

# Certains hébergeurs (Acast, libsyn…) refusent les User-Agent vides ou
# « python-urllib » par défaut. On force un UA navigateur générique.
_HTTP_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; reco-fetch/1.0)"}

# Valeurs « durées » qui sont en réalité des années (présentes dans des
# tags <itunes:episode> mal renseignés, ex. « 2024 »).
_YEAR_MIN = 1990
_YEAR_MAX = 2100


def _parse_date(entry: Any) -> str | None:
    """Extrait une date ISO « YYYY-MM-DD » depuis l'entrée RSS, si possible."""
    parsed = getattr(entry, "published_parsed", None) or getattr(
        entry, "updated_parsed", None
    )
    if parsed is not None:
        # struct_time -> datetime UTC -> date ISO.
        # L3 (revue 2026-07-19) : un struct_time mal formé (mois=0, jour=0…,
        # vu sur des flux RSS bancals) ferait lever datetime(). On renvoie None
        # plutôt que de propager l'erreur et casser tout le fetch.
        try:
            dt = datetime(*parsed[:6], tzinfo=timezone.utc)
        except (ValueError, TypeError):
            return None
        return dt.date().isoformat()
    return None


def _extract_number(entry: Any) -> int | None:
    """
    Déduit un numéro d'épisode :
      1. balise <itunes:episode> si présente ;
      2. sinon, premier entier « plausible » trouvé dans le titre
         (motifs « #312 », « Ep 312 », « Épisode 312 »).
    """
    itunes_ep = entry.get("itunes_episode") if isinstance(entry, dict) else None
    if itunes_ep:
        try:
            n = int(str(itunes_ep).strip())
        except (TypeError, ValueError):
            n = None
        if n is not None and not _YEAR_MIN <= n <= _YEAR_MAX:
            return n
        # Sinon (année plausible ou parsing échoué) : on tente le titre.

    title = entry.get("title", "") or ""
    # Motifs explicites prioritaires.
    m = re.search(r"(?:#|ep(?:isode|\.)?\s*|épisode\s*)(\d{1,4})", title, re.IGNORECASE)
    if m:
        n = int(m.group(1))
        if _YEAR_MIN <= n <= _YEAR_MAX:
            return None  # année probable, pas un numéro d'épisode
        return n
    return None


def _parse_duration(raw: Any) -> int | None:
    """Convertit une durée itunes (« H:MM:SS », « MM:SS » ou secondes) en secondes.

    Renvoie None pour 0 / négatif / non-parsable : une durée nulle ou négative
    n'a pas de sens et trahit un tag itunes manquant.
    """
    if not raw:
        return None
    raw = str(raw).strip()
    if ":" in raw:
        try:
            nums = [int(p) for p in raw.split(":")]
        except ValueError:
            return None
        seconds = 0
        for n in nums:
            seconds = seconds * 60 + n
        return seconds if seconds > 0 else None
    if raw.isdigit():
        seconds = int(raw)
        return seconds if seconds > 0 else None
    return None


def _extract_audio_url(entry: Any) -> str | None:
    """Renvoie l'URL de l'enclosure audio (premier enclosure de type audio)."""
    for enc in entry.get("enclosures", []) or []:
        url = enc.get("href") or enc.get("url")
        etype = (enc.get("type") or "").lower()
        if url and (etype.startswith("audio") or not etype):
            return url
    # Repli : certains flux mettent le média dans links rel="enclosure".
    for link in entry.get("links", []) or []:
        if link.get("rel") == "enclosure" and link.get("href"):
            return link["href"]
    return None


def _stable_guid(entry: Any) -> str | None:
    """
    Renvoie un guid STABLE pour l'épisode :
      - <guid> RSS si présent (id feedparser) ;
      - sinon repli sur le lien ou le titre (slugifié) pour rester déterministe.
    """
    guid = entry.get("id") or entry.get("guid")
    if guid:
        return str(guid).strip()
    link = entry.get("link")
    if link:
        return str(link).strip()
    title = entry.get("title")
    if title:
        return f"title-{slugify(title)}"
    return None


def _existing_index(source_id: str) -> dict[str, Path]:
    """Indexe les fichiers d'épisodes existants par guid (pour idempotence)."""
    index: dict[str, Path] = {}
    for path in list_episode_files(source_id):
        try:
            data = read_json(path)
        except Exception as exc:  # noqa: BLE001 — fichier corrompu : on l'ignore.
            log.warning("Fichier corrompu ignoré : %s (%s)", path, exc)
            continue
        guid = data.get("guid")
        if guid:
            index[guid] = path
    return index


def _clean_description(raw: str) -> str:
    """
    Nettoie une description RSS : retire le pied de page Acast, supprime le HTML
    et décode les entités, pour obtenir un texte lisible.
    """
    # 1. Retire le pied de page Acast (« Hébergé par Acast… »), souvent après un <hr>.
    text = re.split(r"<hr\s*/?>", raw, maxsplit=1)[0]
    text = re.sub(
        r"<p[^>]*>\s*H[ée]berg[ée]\s+par\s+Acast.*?</p>",
        "",
        text,
        flags=re.IGNORECASE | re.DOTALL,
    )
    # 2. Transforme les fins de bloc en sauts de ligne, puis retire les balises.
    text = re.sub(r"</p\s*>|<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    # 3. Décode les entités HTML (&amp;, &eacute;, &#39;…).
    text = html.unescape(text)
    # 4. Normalise les blancs : trim par ligne, au plus une ligne vide.
    lines = [ln.strip() for ln in text.splitlines()]
    text = re.sub(r"\n{3,}", "\n\n", "\n".join(lines))
    return text.strip()


def _build_episode(source_id: str, entry: Any) -> dict[str, Any] | None:
    """Construit le dict Episode conforme au schéma depuis une entrée RSS."""
    guid = _stable_guid(entry)
    if not guid:
        return None

    episode: dict[str, Any] = {
        "sourceId": source_id,
        "guid": guid,
        "title": (entry.get("title") or "Sans titre").strip(),
        "guests": [],
        "transcriptStatus": "none",
    }

    number = _extract_number(entry)
    if number is not None:
        episode["number"] = number

    # Saison/épisode si le titre contient le motif « SX-EX » (ex. « S5-E3 »).
    se = re.search(r"\bS(\d+)\s*[-–·.]?\s*E(\d+)\b", episode["title"], re.IGNORECASE)
    if se:
        episode["season"] = int(se.group(1))
        episode["number"] = int(se.group(2))

    date = _parse_date(entry)
    if date:
        episode["date"] = date

    audio_url = _extract_audio_url(entry)
    if audio_url:
        episode["audioUrl"] = audio_url

    duration = _parse_duration(entry.get("itunes_duration"))
    if duration:
        episode["audioDuration"] = duration

    description = entry.get("summary") or entry.get("description")
    if description:
        cleaned = _clean_description(description)
        if cleaned:
            episode["description"] = cleaned

    return episode


def _filename_for(episode: dict[str, Any]) -> str:
    """
    Nom de fichier déterministe et lisible pour un épisode.
    Préfère « ep-<number>.json », sinon repli sur le guid slugifié.
    """
    number = episode.get("number")
    if isinstance(number, int):
        return f"ep-{number:03d}.json"
    return f"{slugify(episode['guid'])}.json"


def fetch_episodes(source_id: str, limit: int | None = None,
                   rss_override: str | None = None) -> int:
    """
    Récupère et écrit les épisodes d'une source. Renvoie le nombre de fichiers
    réellement écrits ou mis à jour.
    """
    source = load_source(source_id)
    rss_url = rss_override or source.get("rssUrl")
    if not rss_url:
        raise ValueError(
            f"La source « {source_id} » n'a pas de rssUrl. "
            f"Renseigne-le dans le JSON de la source ou passe --rss."
        )

    if not isinstance(rss_url, str) or not rss_url.startswith(("http://", "https://")):
        raise ValueError(
            f"URL RSS invalide pour « {source_id} » : {rss_url!r}. "
            "Doit commencer par http:// ou https://."
        )

    log.info("Lecture du flux RSS : %s", rss_url)
    try:
        resp = requests.get(rss_url, timeout=30, headers=_HTTP_HEADERS)
        resp.raise_for_status()
        # M2 (revue 2026-07-19) : passer les OCTETS, pas resp.text. Sur un flux
        # text/xml sans charset, requests décode en ISO-8859-1 (défaut RFC 2616)
        # → mojibake des accents (« Bérengère » → « BÃ©rengÃ¨re ») AVANT feedparser.
        # feedparser sniffe l'encodage depuis la déclaration XML sur des bytes.
        feed = feedparser.parse(resp.content)
    except requests.RequestException as exc:
        raise RuntimeError(f"Téléchargement RSS échoué : {exc}") from exc
    if feed.bozo and not feed.entries:
        raise RuntimeError(
            f"Échec du parsing RSS ({getattr(feed, 'bozo_exception', 'inconnu')})."
        )

    entries = feed.entries
    if limit is not None:
        entries = entries[:limit]
    log.info("%d épisode(s) à traiter (sur %d dans le flux).",
             len(entries), len(feed.entries))

    existing = _existing_index(source_id)
    target_dir = episodes_dir_for(source_id)
    written = 0

    for entry in entries:
        episode = _build_episode(source_id, entry)
        if episode is None:
            log.warning("Entrée RSS sans guid exploitable — ignorée.")
            continue

        guid = episode["guid"]
        existing_path = existing.get(guid)

        if existing_path is not None:
            # L'épisode existe déjà : on PRÉSERVE l'état du pipeline (statut de
            # transcription, invités saisis à la main) et on ne met à jour que
            # les métadonnées issues du flux.
            current = read_json(existing_path)
            merged = dict(current)
            merged.update(episode)
            # On ne régresse jamais le statut de transcription.
            if current.get("transcriptStatus") in ("auto", "validated"):
                merged["transcriptStatus"] = current["transcriptStatus"]
            # On conserve invités / youtubeUrl saisis manuellement s'ils existent.
            if current.get("guests"):
                merged["guests"] = current["guests"]
            if current.get("youtubeUrl"):
                merged["youtubeUrl"] = current["youtubeUrl"]
            if write_json_if_changed(existing_path, merged):
                written += 1
                log.info("Mis à jour : %s", existing_path.name)
            continue

        # Nouvel épisode.
        path = target_dir / _filename_for(episode)
        # Évite les collisions de nom de fichier (numéros dupliqués).
        if path.exists() and read_json(path).get("guid") != guid:
            path = target_dir / f"{slugify(guid)}.json"
        if write_json_if_changed(path, episode):
            written += 1
            log.info("Créé : %s", path.name)

    log.info("Terminé : %d fichier(s) écrit(s)/mis à jour.", written)
    return written


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Récupère les épisodes d'un podcast depuis son flux RSS Acast."
    )
    parser.add_argument("--source", required=True,
                        help="Identifiant de la source (ex: un-bon-moment).")
    parser.add_argument("--limit", type=int, default=None,
                        help="Limite le nombre d'épisodes traités (les plus récents).")
    parser.add_argument("--rss", default=None,
                        help="URL RSS à utiliser (sinon lue depuis la source).")
    args = parser.parse_args()

    fetch_episodes(args.source, limit=args.limit, rss_override=args.rss)


if __name__ == "__main__":
    main()
