"""review_render_common.py — Helpers de rendu partagés entre modules.

Extrait de `review_render.py` pour briser les dépendances circulaires entre
`review_render.py` et `review_render_cluster.py`. Ces deux modules importent
maintenant depuis ce common (pas l'un de l'autre).

Helpers purs : pas d'I/O sauf `_load_transcript` (cachée) et `_style`,
`_CLIENT_JS` (lecture au démarrage).
"""
from __future__ import annotations

import bisect
import html
import re
import urllib.parse
from functools import lru_cache
from pathlib import Path
from typing import NamedTuple

from common import extract_youtube_id

_TOOLS_DIR = Path(__file__).parent

# Mots qui marquent la fin de la liste de noms dans un titre descriptif.
_STOP = re.compile(
    r"\b(nous|sont|ont|donnent|hackent|prennent|font|se|racontent|parlent|"
    r"multiplient|reviennent|en mode|episode|épisode|special|spécial|imbattables|"
    r"incollables|sans)\b|[:(!?]",
    re.IGNORECASE,
)

_CSS_PATH = _TOOLS_DIR / "review_server.css"


# ---- Schémas URL sûrs (#5 — XSS via youtubeUrl:javascript:…) -----------------
_SAFE_URL_RE = re.compile(r"^https?://", re.IGNORECASE)


def _safe_url(url: str | None) -> str | None:
    """Retourne `url` si elle commence par http(s)://, sinon None.

    Bloque les schémas dangereux (`javascript:`, `data:`, `vbscript:`) injectés
    dans des données utilisateur (ex. `youtubeUrl` éditable). À utiliser avant
    toute interpolation en attribut HTML href / src.

    #16 — Refuse aussi les caractères de contrôle (NUL, CR, LF, TAB) qui
    permettent en théorie d'injecter des headers ou des séparateurs en
    contexte navigateur fragile.
    """
    if not url or not isinstance(url, str):
        return None
    stripped = url.strip()
    if any(c in stripped for c in "\x00\r\n\t"):
        return None
    return url if _SAFE_URL_RE.match(stripped) else None


# ---- Timecodes & formats -----------------------------------------------------
def _ts_seconds(ts: str | None) -> int | None:
    """« HH:MM:SS » → secondes (None si invalide / absent).

    Unique implémentation partagée (#22) — auparavant dupliquée dans
    review_render.py, reco_dedup.py et review_render_cluster.py.
    """
    if not ts:
        return None
    try:
        parts = [int(x) for x in ts.split(":")]
    except (ValueError, AttributeError):
        return None
    s = 0
    for p in parts:
        s = s * 60 + p
    return s


def _fmt(seconds: int) -> str:
    """Formate des secondes en « HH:MM:SS »."""
    h, rem = divmod(int(seconds), 3600)
    m, s = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def _yt_id(url: str | None) -> str:
    """Id YouTube depuis une URL (chaîne vide si absent — compat HTML)."""
    return extract_youtube_id(url) or ""


def _embed_url(video_url: str, start_seconds: int) -> str:
    """URL d'embed YouTube positionnée à `start_seconds`, prête à jouer."""
    vid = _yt_id(video_url)
    return (f"https://www.youtube-nocookie.com/embed/{vid}"
            f"?start={start_seconds}&autoplay=1&rel=0&playsinline=1"
            if vid else "")


# ---- Timecode link (#4 : retourne (secs, html)) ------------------------------
class TimecodeLink(NamedTuple):
    """Sortie de `_yt_timecode_link_parts` :

    - `secs`: secondes du timecode après offset (None si pas de timecode utile).
    - `html`: fragment HTML prêt à interpoler (ou chaîne vide).
    """
    secs: int | None
    html: str


def _yt_timecode_link_parts(r: dict, ep: dict) -> TimecodeLink:
    """Version structurée de `_yt_timecode_link` (#4).

    Retourne `(secs, html)` :
      - `secs` = secondes du timestamp brut (sans offset). Utile aux callers
        qui veulent réutiliser cette valeur (ex. `_reco_card` pour le
        contexte transcript).
      - `html` = lien <a class="tc"> cliquable, ou <span class="tc off">
        statique si pas de YT, ou chaîne vide si pas de timestamp.

    L'offset YT n'est appliqué que pour `transcriptSource=acast` (intro YT
    absente du podcast). Fallback `acast` pour les vieilles recos sans champ.
    `youtubeDuration` peut arriver en string (#23) : cast safe.
    """
    secs = _ts_seconds(r.get("timestamp"))
    yt_raw = ep.get("youtubeUrl")
    yt = _safe_url(yt_raw)  # #5 : XSS guard
    reco_src = r.get("transcriptSource") or "acast"
    if reco_src == "acast":
        # #39 — _safe_int : un youtubeDuration mal formé ne doit pas planter.
        yd = _safe_int(ep.get("youtubeDuration"))
        ad = _safe_int(ep.get("audioDuration"))
        yt_offset = max(0, yd - ad)
    else:
        yt_offset = 0
    if yt and secs is not None:
        tv = max(0, secs + yt_offset)
        html_out = (f'<a class="tc" target="ytplayer" '
                    f'href="{html.escape(_embed_url(yt, tv))}">'
                    f'▶ {_fmt(secs)}</a>')
        return TimecodeLink(secs=secs, html=html_out)
    if r.get("timestamp"):
        return TimecodeLink(
            secs=secs,
            html=f'<span class="tc off">⏱ {html.escape(r.get("timestamp", ""))}</span>',
        )
    return TimecodeLink(secs=secs, html="")


def _yt_timecode_link(r: dict, ep: dict) -> str:
    """Wrapper rétro-compatible — retourne uniquement le HTML (#4)."""
    return _yt_timecode_link_parts(r, ep).html


# ---- Extractors badge (#3 : duplication entre _reco_card et _dedup_cluster_card)
def _extractors_badge(extractors_list: list[str]) -> str:
    """Badge ⭐ N LLMs / solo / vide selon la liste d'extractors."""
    if not extractors_list:
        return ""
    if len(extractors_list) >= 2:
        return (f'<span class="conf" title="Confirmée par '
                f'{html.escape(", ".join(extractors_list))}">'
                f'⭐ {len(extractors_list)} LLMs</span>')
    first = html.escape(extractors_list[0])
    return (f'<span class="conf solo" title="Trouvée par {first} '
            f'uniquement">{first}</span>')


# ---- Quotes (#12 : strip guillemets français déjà présents) ------------------
# #8 — Constantes en frozenset (set immutable) — sémantique correcte (test
# d'appartenance) et O(1) lookup.
_QUOTE_OPENERS = frozenset({'«', '"', '“', '”'})
_QUOTE_CLOSERS = frozenset({'»', '"', '“', '”'})


def _strip_french_quotes(s: str) -> str:
    """Retire les guillemets «», "" , "" présents en début/fin (#12).

    Évite l'affichage « « foo » » quand la quote a déjà été stockée avec
    ses propres guillemets.
    """
    if not s:
        return s
    s = s.strip()
    while s and s[0] in _QUOTE_OPENERS:
        s = s[1:].lstrip()
    while s and s[-1] in _QUOTE_CLOSERS:
        s = s[:-1].rstrip()
    return s


# ---- Conversion safe (#39) ---------------------------------------------------
def _safe_int(x, default: int = 0) -> int:
    """Cast int tolérant (str numérique, None…) → fallback `default`.

    Utilisé en hot-path de rendu (`_yt_timecode_link_parts`, `_ep_header`)
    où `youtubeDuration` peut arriver en str depuis le JSON et où on ne
    veut surtout pas planter un rendu pour un mauvais format.
    Note : ne supporte PAS les float-string (`int("1.5")` lève ValueError →
    on retourne `default`).
    """
    try:
        return int(x)
    except (TypeError, ValueError):
        return default


# ---- Guests parsing ----------------------------------------------------------
def _parse_guests(title: str, hosts: list[str]) -> list[str]:
    """Devine les invités d'un épisode depuis son titre (heuristique)."""
    t = (title or "").strip()
    m = re.search(r"\bavec\b(.+)", t, re.IGNORECASE)
    seg = m.group(1) if m else t
    seg = _STOP.split(seg)[0]
    parts = re.split(r"\s+et\s+|,|&|/", seg, flags=re.IGNORECASE)

    hosts_low = {h.casefold() for h in hosts}
    guests: list[str] = []
    seen: set[str] = set()
    for p in parts:
        name = p.strip(" .\"'»«")
        if not name or len(name.split()) > 4 or not re.search(r"[A-Za-zÀ-ÿ]", name):
            continue
        name = name.title() if name.isupper() else name
        key = name.casefold()
        if key not in hosts_low and key not in seen:
            seen.add(key)
            guests.append(name)
    return guests


# ---- Transcript --------------------------------------------------------------
@lru_cache(maxsize=128)
def _load_transcript(source_id: str, guid: str) -> tuple[tuple[int, str], ...]:
    """Renvoie la transcription parsée : tuple de (seconde_de_début, texte)."""
    from common import transcript_path_for  # noqa: PLC0415
    path = transcript_path_for(source_id, guid)
    if not path.exists():
        return ()
    items: list[tuple[int, str]] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        m = re.match(r"\[(\d{2}):(\d{2}):(\d{2})\]\s*(.*)", line)
        if m:
            h, mn, s = int(m.group(1)), int(m.group(2)), int(m.group(3))
            items.append((h * 3600 + mn * 60 + s, m.group(4)))
    return tuple(items)


def _context_around(items: tuple[tuple[int, str], ...], target_sec: int,
                    n_before: int = 3, n_after: int = 4) -> list[tuple[int, str]]:
    """Lignes du transcript autour d'un timecode cible (bissection O(log n))."""
    if not items:
        return []
    times = [it[0] for it in items]
    pos = bisect.bisect_left(times, target_sec)
    if pos >= len(items):
        idx = len(items) - 1
    elif pos == 0:
        idx = 0
    else:
        idx = pos if abs(items[pos][0] - target_sec) < abs(items[pos - 1][0] - target_sec) else pos - 1
    start = max(0, idx - n_before)
    end = min(len(items), idx + n_after + 1)
    return [items[i] for i in range(start, end)]


# ---- HTML shell --------------------------------------------------------------
@lru_cache(maxsize=1)
def _style() -> str:
    """Feuille de style (cachée pour éviter l'I/O répété)."""
    try:
        return _CSS_PATH.read_text(encoding="utf-8")
    except OSError:
        return ""


# M4 découpe — le JS client vit en 4 fichiers ≤ 500 lignes, concaténés dans
# CET ORDRE : le core publie window.__reco.{initOnReady,toast} que les trois
# suivants consomment (chaque fichier est une IIFE avec son gate propre).
_CLIENT_JS_FILES = (
    "review_client.js",           # core : toast, AJAX, flash, merge bar, player
    "review_client_cluster.js",   # ajout/retrait manuel de cluster
    "review_client_keyboard.js",  # nav clavier, carte active, YT, recherche
    "review_client_toolbar.js",   # tri + repli des traités
)
try:
    _CLIENT_JS = "\n".join(
        (_TOOLS_DIR / name).read_text(encoding="utf-8")
        for name in _CLIENT_JS_FILES
    )
except OSError:
    _CLIENT_JS = ""


def _shell(source_title: str, subtitle: str, inner: str) -> str:
    """Gabarit HTML commun (en-tête, style, titre)."""
    return (
        '<!doctype html><html lang="fr"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        f"<title>Relecture — {html.escape(source_title)}</title>"
        f"<style>{_style()}</style></head><body>"
        f"<h1>Relecture — {html.escape(source_title)}</h1>"
        f'<p class="meta">{subtitle}</p>{inner}'
        '<div id="toast-zone" aria-live="polite" aria-atomic="true"></div>'
        f"<script>{_CLIENT_JS}</script>"
        "</body></html>"
    )


def _flash_banner(flash: str | None, kind: str) -> str:
    """Bandeau de feedback en haut de page."""
    if not flash:
        return ""
    safe_kind = kind if kind in ("success", "warning", "error", "info") else "info"
    return (f'<div class="flash flash-{safe_kind}" role="status">'
            f'{html.escape(flash)}</div>')


# Compat namespace pour les modules qui importent depuis common
__all__ = [
    "TimecodeLink",
    "_CLIENT_JS",
    "_CSS_PATH",
    "_STOP",
    "_context_around",
    "_embed_url",
    "_extractors_badge",
    "_flash_banner",
    "_fmt",
    "_load_transcript",
    "_parse_guests",
    "_safe_int",
    "_safe_url",
    "_shell",
    "_strip_french_quotes",
    "_style",
    "_ts_seconds",
    "_yt_id",
    "_yt_timecode_link",
    "_yt_timecode_link_parts",
]
