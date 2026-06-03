"""review_render.py — Présentation HTML (cartes, index, épisode, shell).

Extrait de review_server.py pour isoler le rendu HTML de la couche transport
HTTP. Les fonctions sont pures : elles consomment des dicts en entrée et
retournent des chaînes HTML. Le serveur reste responsable du routage et des
mutations.
"""
from __future__ import annotations

import bisect
import html
import re
import urllib.parse
from functools import lru_cache
from pathlib import Path

from common import (
    extract_youtube_id,
    list_episode_files,
    load_source,
    log,
    read_json,
    recos_dir_for,
)
from review_edit import is_reenrichable, render_edit_form, render_type_badges
from review_guests import (
    is_placeholder as _is_placeholder,
    render_guests_panel as _render_guests_panel,
    split_names as _split_names,
)

_TOOLS_DIR = Path(__file__).parent

# Mots qui marquent la fin de la liste de noms dans un titre descriptif.
_STOP = re.compile(
    r"\b(nous|sont|ont|donnent|hackent|prennent|font|se|racontent|parlent|"
    r"multiplient|reviennent|en mode|episode|épisode|special|spécial|imbattables|"
    r"incollables|sans)\b|[:(!?]",
    re.IGNORECASE,
)


def _parse_guests(title: str, hosts: list[str]) -> list[str]:
    """Devine les invités d'un épisode depuis son titre (heuristique).

    Limitations : un titre type « Une étoile et la lune » avec le séparateur
    ` et ` peut générer des faux positifs ; on filtre par longueur (≤ 4 mots)
    et présence de lettres latines.
    """
    t = (title or "").strip()
    m = re.search(r"\bavec\b(.+)", t, re.IGNORECASE)
    seg = m.group(1) if m else t
    seg = _STOP.split(seg)[0]
    parts = re.split(r"\s+et\s+|,|&|/", seg, flags=re.IGNORECASE)

    hosts_low = {h.lower() for h in hosts}
    guests: list[str] = []
    for p in parts:
        name = p.strip(" .\"'»«")
        if not name or len(name.split()) > 4 or not re.search(r"[A-Za-zÀ-ÿ]", name):
            continue
        name = name.title() if name.isupper() else name
        if name.lower() not in hosts_low and name not in guests:
            guests.append(name)
    return guests


def _ts_seconds(ts: str | None) -> int | None:
    if not ts:
        return None
    try:
        parts = [int(x) for x in ts.split(":")]
    except ValueError:
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
    return (f"https://www.youtube.com/embed/{vid}?start={start_seconds}&autoplay=1"
            if vid else "")


@lru_cache(maxsize=128)
def _load_transcript(source_id: str, guid: str) -> tuple[tuple[int, str], ...]:
    """Renvoie la transcription parsée : tuple de (seconde_de_début, texte)."""
    from common import transcript_path_for  # noqa: PLC0415 — import paresseux.
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


_ORDER = {"draft": 0, "validated": 1, "discarded": 2}
_CSS_PATH = _TOOLS_DIR / "review_server.css"


@lru_cache(maxsize=1)
def _style() -> str:
    """Feuille de style (cachée pour éviter l'I/O répété)."""
    try:
        return _CSS_PATH.read_text(encoding="utf-8")
    except OSError:
        return ""


try:
    _CLIENT_JS = (_TOOLS_DIR / "review_client.js").read_text(encoding="utf-8")
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


def _reco_card(r: dict, ep: dict, hosts: list, source_id: str,
               edit_id: str | None = None,
               siblings: list[dict] | None = None) -> str:
    """Carte d'une reco : timecode vidéo embarquable, contexte, candidats."""
    if edit_id and r.get("id") == edit_id:
        return render_edit_form(r, ep, siblings, hosts)
    secs = _ts_seconds(r.get("timestamp"))
    yt = ep.get("youtubeUrl")
    if yt and secs is not None:
        tv = max(0, secs)
        link = (f'<a class="tc" target="ytplayer" href="{html.escape(_embed_url(yt, tv))}">'
                f'▶ {_fmt(tv)}</a>')
    elif r.get("timestamp"):
        link = f'<span class="tc off">⏱ {html.escape(r.get("timestamp", ""))}</span>'
    else:
        link = ""
    ctx_html = ""
    if secs is not None:
        ctx = _context_around(_load_transcript(source_id, ep.get("guid", "")), secs)
        if ctx:
            spans = [
                f'<span class="{"ctx-here" if abs(sec - secs) < 3 else "ctx"}">'
                f'{html.escape(txt)}</span>' for sec, txt in ctx
            ]
            ctx_html = f'<div class="context">{" ".join(spans)}</div>'
    current = r.get("recommendedBy", "")
    # Candidats : hôtes + invités parsés du titre + tous les noms déjà saisis
    # sur cette reco ET sur les autres recos du même épisode. Un nom ajouté
    # à la main devient ainsi sélectionnable sur les autres cartes.
    candidates = list(hosts) + _parse_guests(ep.get("title", ""), hosts)
    for n in ep.get("guests") or []:
        if not _is_placeholder(n) and not any(n.casefold() == c.casefold() for c in candidates):
            candidates.append(n)
    for src in [current, *(s.get("recommendedBy", "") for s in (siblings or []))]:
        for n in _split_names(src):
            if _is_placeholder(n):
                continue
            if not any(n.casefold() == c.casefold() for c in candidates):
                candidates.append(n)
    boxes = "".join(
        f'<label><input type="checkbox" name="who" value="{html.escape(c)}"'
        f'{" checked" if c in current else ""}> {html.escape(c)}</label>'
        for c in candidates
    )
    status = r.get("status", "draft")
    cls = {"validated": "done", "discarded": "discarded"}.get(status, "")
    reco_id_esc = html.escape(r.get("id", ""))
    guid_q = urllib.parse.quote(ep.get("guid", ""))
    edit_btn = (f'<a class="btn-edit" href="/ep?guid={guid_q}&edit='
                f'{urllib.parse.quote(r.get("id", ""))}">✎ Éditer</a>')
    reenrich_btn = (
        f'<form method="post" action="/reenrich" class="reenrich-form">'
        f'<input type="hidden" name="id" value="{reco_id_esc}">'
        f'<button type="submit" class="btn-reenrich">🔄 Ré-enrichir</button>'
        f'</form>'
    ) if is_reenrichable(r) else ""
    extractors = r.get("extractors") or []
    if len(extractors) >= 2:
        conf_badge = (f'<span class="conf" title="Confirmée par '
                      f'{html.escape(", ".join(extractors))}">'
                      f'⭐ {len(extractors)} LLMs</span>')
    elif extractors:
        first = html.escape(extractors[0])
        conf_badge = (f'<span class="conf solo" title="Trouvée par {first} '
                      f'uniquement">{first}</span>')
    else:
        conf_badge = ""
    return f"""
    <li class="row {cls}">
      <div class="hd"><span class="type">{render_type_badges(r.get('types', []))}</span>
        <b>{html.escape(r.get('title',''))}</b>
        {f"<i>· {html.escape(r['creator'])}</i>" if r.get('creator') else ''}
        {link}
        {conf_badge}
        <span class="st">{html.escape(status)}</span>
        {edit_btn}
        {reenrich_btn}</div>
      {ctx_html}
      {f'<p class="q">« {html.escape(r["quote"])} »</p>' if r.get('quote') else ''}
      <form method="post" action="/save">
        <input type="hidden" name="id" value="{html.escape(r.get('id',''))}">
        <div class="who">{boxes}
          <input type="text" name="other" placeholder="autre nom…" value="">
          <button type="submit" name="action" value="validate">Valider</button>
          <button type="submit" name="action" value="discard" class="discard">Pas une reco</button>
        </div>
      </form>
    </li>"""


def _ep_nav_link(side: str, guid: str | None) -> str:
    """Flèche prev/next ou placeholder désactivé (pour garder l'alignement)."""
    arrow = "←" if side == "prev" else "→"
    label = "Épisode précédent" if side == "prev" else "Épisode suivant"
    cls = f"eph-arrow eph-arrow-{side}"
    if guid:
        href = f"/ep?guid={urllib.parse.quote(guid)}"
        return (f'<a class="{cls}" href="{href}" title="{label}" '
                f'aria-label="{label}">{arrow}</a>')
    return f'<span class="{cls} disabled" aria-hidden="true">{arrow}</span>'


def _ep_header(
    ep: dict, recs: list[dict],
    *, prev_guid: str | None = None, next_guid: str | None = None,
) -> str:
    """En-tête d'épisode : numéro, titre YT, durées, compteur, navigation."""
    season, num = ep.get("season"), ep.get("number")
    ep_num = f"S{season}·E{num}" if season and num else (f"#{num}" if num else "")
    badge = f'<b class="epnum">{ep_num}</b> ' if ep_num else ""
    title = html.escape(ep.get("youtubeTitle") or ep.get("title", "?"))
    yt = ep.get("youtubeUrl")
    title_html = f'<a href="{html.escape(yt)}" target="_blank">{title}</a>' if yt else title
    ad, vd = ep.get("audioDuration"), ep.get("youtubeDuration")
    dur = ""
    if ad or vd:
        diff = f" Δ{vd - ad:+d}s" if (ad and vd) else ""
        warn = ' style="color:#e08a8a"' if (ad and vd and abs(vd - ad) > 300) else ""
        dur = f'<span class="dur"{warn}>🎧 {_fmt(ad) if ad else "?"} · ▶ {_fmt(vd) if vd else "?"}{diff}</span>'
    n_draft = sum(1 for r in recs if r.get("status", "draft") == "draft")
    prev_a = _ep_nav_link("prev", prev_guid)
    next_a = _ep_nav_link("next", next_guid)
    return (f'<div class="eph-row">{prev_a}'
            f'<h2 class="eph">{badge}{title_html} '
            f'<span class="cnt">{len(recs)} recos · {n_draft} à valider</span> {dur}</h2>'
            f'{next_a}</div>')


def _load_groups(source_id: str):
    """Renvoie (source, episodes_par_guid, recos_par_guid triés)."""
    source = load_source(source_id)
    episodes: dict[str, dict] = {}
    for p in list_episode_files(source_id):
        ep = read_json(p)
        episodes[ep["guid"]] = ep
    recos = [read_json(p) for p in sorted(recos_dir_for(source_id).glob("*.json"))]
    groups: dict[str, list[dict]] = {}
    for r in recos:
        groups.setdefault(r.get("episodeGuid", ""), []).append(r)
    # Tri : drafts en 1er, puis confirmées-par-N en tête de la tranche draft.
    for g in groups.values():
        g.sort(key=lambda r: (_ORDER.get(r.get("status", "draft"), 0),
                              -len(r.get("extractors") or [])))
    return source, episodes, groups


def _render_index(source_id: str) -> str:
    """Page d'accueil : galerie de miniatures, tous les épisodes."""
    source, episodes, groups = _load_groups(source_id)

    def _key(guid: str):
        ep = episodes.get(guid, {})
        return (ep.get("season") or 0, ep.get("number") or 9999)

    thumbs = []
    todo = 0
    for guid in sorted(episodes.keys(), key=_key):
        ep = episodes.get(guid, {})
        recs = groups.get(guid, [])
        n_draft = sum(1 for r in recs if r.get("status", "draft") == "draft")
        todo += n_draft
        season, num = ep.get("season"), ep.get("number")
        ep_num = f"S{season}·E{num}" if season and num else (f"#{num}" if num else "?")
        vid = _yt_id(ep.get("youtubeUrl", ""))
        style = f'style="background-image:url(https://i.ytimg.com/vi/{vid}/mqdefault.jpg)"' if vid else ""
        cls = "thumb"
        if not recs:
            cls += " empty"
        elif n_draft == 0:
            cls += " done"
        href = f"/ep?guid={urllib.parse.quote(guid)}"
        count_label = f"{n_draft} à valider" if recs else "0 reco"
        thumbs.append(
            f'<a class="{cls}" href="{href}" {style}>'
            f'<span class="tbadge">{ep_num}</span>'
            f'<span class="tcount">{count_label}</span></a>'
        )

    inner = (f'<div class="gallery">{"".join(thumbs)}</div>' if thumbs
             else "<p>Aucune reco — lance l’extraction d’abord.</p>")
    n_with = sum(1 for g in episodes if g in groups)
    subtitle = (f"<b>{todo}</b> recos à valider · {len(episodes)} épisodes ({n_with} avec recos). "
                "Clique une miniature.")
    return _shell(source.get("title", source_id), subtitle, inner)


def _flash_banner(flash: str | None, kind: str) -> str:
    """Bandeau de feedback en haut de page (après PRG depuis /edit ou /reenrich)."""
    if not flash:
        return ""
    safe_kind = kind if kind in ("success", "warning", "error", "info") else "info"
    return (f'<div class="flash flash-{safe_kind}" role="status">'
            f'{html.escape(flash)}</div>')


def _render_episode(
    source_id: str, guid: str, edit_id: str | None = None,
    *, flash: str | None = None, flash_kind: str = "info",
) -> str:
    """Page d'un épisode : son en-tête + ses recos à relire."""
    source, episodes, groups = _load_groups(source_id)
    hosts = source.get("hosts", [])
    ep = episodes.get(guid)
    recs = groups.get(guid, [])
    back = '<a class="back" href="/">← tous les épisodes</a>'
    if not ep:
        return _shell(source.get("title", source_id), "Épisode introuvable.", back)
    # Navigation prev/next dans l'ordre (saison, numéro) — même tri que la
    # galerie d'index pour rester cohérent.
    def _key(g: str):
        e = episodes.get(g, {})
        return (e.get("season") or 0, e.get("number") or 9999)
    ordered = sorted(episodes.keys(), key=_key)
    idx = ordered.index(guid) if guid in ordered else -1
    prev_guid = ordered[idx - 1] if idx > 0 else None
    next_guid = ordered[idx + 1] if 0 <= idx < len(ordered) - 1 else None
    guests_panel = _render_guests_panel(guid, ep, recs, hosts)
    cards = "".join(
        _reco_card(r, ep, hosts, source_id, edit_id, siblings=recs) for r in recs
    )
    player = ('<iframe name="ytplayer" class="player" title="Lecteur YouTube" '
              'allowfullscreen></iframe>')
    banner = _flash_banner(flash, flash_kind)
    inner = (f'{back}{banner}{player}<section class="ep">'
             f'{_ep_header(ep, recs, prev_guid=prev_guid, next_guid=next_guid)}'
             f'{guests_panel}<ul>{cards}</ul></section>')
    return _shell(source.get("title", source_id), "Relecture d'un épisode.", inner)
