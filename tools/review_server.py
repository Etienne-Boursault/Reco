"""review_server.py — Outil de relecture LOCAL (hors site public).

Sert une page web locale (http.server stdlib, sans dépendance) pour valider /
écarter / éditer / ré-enrichir les recos extraites par IA.

Usage : ``python review_server.py --source un-bon-moment [--port 8000]``
"""

from __future__ import annotations

import argparse
import bisect
import html
import re
import threading
import urllib.parse
from functools import lru_cache, partial
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

from dotenv import load_dotenv

from common import (
    TOOLS_DIR,
    extract_youtube_id,
    list_episode_files,
    load_source,
    log,
    read_json,
    recos_dir_for,
    write_json_if_changed,
)
from review_edit import apply_edit, apply_reenrich, is_reenrichable, render_edit_form

# Limite max sur les requêtes POST (en octets) — anti-DoS.
_MAX_POST_BYTES = 1 << 20  # 1 MiB

# Format conventionnel des reco_id POST : minuscules alphanum + tirets/underscores.
_RE_RECO_ID = re.compile(r"^[a-z0-9_-]+$")

# Security headers (CSP autorise l'iframe YouTube et les miniatures).
_SECURITY_HEADERS: dict[str, str] = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Content-Security-Policy": (
        "default-src 'self'; "
        "img-src 'self' data: https://i.ytimg.com; "
        "style-src 'unsafe-inline'; "
        "frame-src https://www.youtube.com https://www.youtube-nocookie.com; "
        # 'unsafe-inline' nécessaire pour le petit JS embarqué (toast + AJAX
        # partiel). Le serveur est strictement local (127.0.0.1) donc le risque
        # XSS est confiné — toutes les entrées sont déjà html.escape côté Py.
        "script-src 'unsafe-inline'; base-uri 'none'; form-action 'self'"
    ),
}

# Mots qui marquent la fin de la liste de noms dans un titre descriptif.
_STOP = re.compile(
    r"\b(nous|sont|ont|donnent|hackent|prennent|font|se|racontent|parlent|"
    r"multiplient|reviennent|en mode|episode|épisode|special|spécial|imbattables|"
    r"incollables|sans)\b|[:(!?]",
    re.IGNORECASE,
)


def _parse_guests(title: str, hosts: list[str]) -> list[str]:
    """Devine les invités d'un épisode depuis son titre (heuristique)."""
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


# Cache reco_id → Path, invalidé après chaque écriture (évite scan O(n) à chaque POST).
_RECO_PATH_CACHE: dict[tuple[str, str], Path] = {}
_RECO_CACHE_LOCK = threading.Lock()


def _rebuild_reco_path_cache(source_id: str) -> None:
    """(Re)construit le cache reco_id → Path pour une source."""
    new_cache: dict[tuple[str, str], Path] = {}
    for p in recos_dir_for(source_id).glob("*.json"):
        try:
            rid = read_json(p).get("id")
        except (OSError, ValueError):
            continue
        if rid:
            new_cache[(source_id, rid)] = p
    with _RECO_CACHE_LOCK:
        for k in [k for k in _RECO_PATH_CACHE if k[0] == source_id]:
            del _RECO_PATH_CACHE[k]
        _RECO_PATH_CACHE.update(new_cache)


def _invalidate_reco_path_cache(source_id: str) -> None:
    """Vide les entrées de cache d'une source (après une écriture)."""
    with _RECO_CACHE_LOCK:
        for k in [k for k in _RECO_PATH_CACHE if k[0] == source_id]:
            del _RECO_PATH_CACHE[k]


def _reco_path(source_id: str, reco_id: str) -> Path | None:
    """Retrouve le fichier JSON d'une reco par son id (cache mémoire)."""
    key = (source_id, reco_id)
    with _RECO_CACHE_LOCK:
        cached = _RECO_PATH_CACHE.get(key)
    if cached and cached.exists():
        return cached
    _rebuild_reco_path_cache(source_id)  # cache miss ou fichier disparu
    with _RECO_CACHE_LOCK:
        return _RECO_PATH_CACHE.get(key)


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
_CSS_PATH = Path(__file__).parent / "review_server.css"


@lru_cache(maxsize=1)
def _style() -> str:
    """Feuille de style (cachée pour éviter l'I/O répété)."""
    try:
        return _CSS_PATH.read_text(encoding="utf-8")
    except OSError:
        return ""


def _shell(source_title: str, subtitle: str, inner: str) -> str:
    """Gabarit HTML commun (en-tête, style, titre).

    Inclut :
      - le container `#toast-zone` pour le macaron de feedback en bas à droite,
      - un petit JS qui intercepte les clics sur `.btn-reenrich` et les submits
        sur les formulaires `/edit` pour faire des requêtes AJAX (fetch JSON)
        et remplacer la carte ciblée sans recharger toute la page. Le formulaire
        garde son `action`/`method` natif : si JS est désactivé, le serveur
        retombe sur le 303 + bandeau classique (rétrocompat).
    """
    return (
        '<!doctype html><html lang="fr"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        f"<title>Relecture — {html.escape(source_title)}</title>"
        f"<style>{_style()}</style></head><body>"
        f"<h1>Relecture — {html.escape(source_title)}</h1>"
        f'<p class="meta">{subtitle}</p>{inner}'
        '<div id="toast-zone" aria-live="polite" aria-atomic="true"></div>'
        f"<script>{_client_script()}</script>"
        "</body></html>"
    )


_CLIENT_JS = r"""
(() => {
  // Toast bas-droite, auto-disparait après 4s.
  function toast(message, kind) {
    const zone = document.getElementById('toast-zone');
    if (!zone) return;
    const el = document.createElement('div');
    el.className = 'toast toast-' + (kind || 'info');
    el.textContent = message;
    zone.appendChild(el);
    requestAnimationFrame(() => el.classList.add('show'));
    setTimeout(() => {
      el.classList.remove('show');
      setTimeout(() => el.remove(), 300);
    }, 4000);
  }

  // Remplace la carte (li.row) qui contient la reco_id par le HTML reçu.
  function replaceCard(reco_id, html) {
    if (!html) return;
    const current = document.querySelector('input[name="id"][value="' + CSS.escape(reco_id) + '"]');
    const li = current && current.closest('li.row');
    if (!li) return;
    const tmpl = document.createElement('template');
    tmpl.innerHTML = html.trim();
    const fresh = tmpl.content.firstElementChild;
    if (fresh) li.replaceWith(fresh);
  }

  async function ajaxPost(action, formData, reco_id) {
    try {
      const r = await fetch(action, {
        method: 'POST',
        headers: { 'Accept': 'application/json' },
        body: new URLSearchParams(formData),
      });
      const data = await r.json();
      if (data.card_html) replaceCard(reco_id, data.card_html);
      if (data.message) toast(data.message, data.kind || 'info');
    } catch (err) {
      toast('Erreur réseau : ' + err.message, 'error');
    }
  }

  // Délégation : intercepte les submits sur les formulaires AJAX-able.
  document.addEventListener('submit', (e) => {
    const form = e.target;
    if (!(form instanceof HTMLFormElement)) return;
    const action = form.getAttribute('action') || '';
    if (action !== '/edit' && action !== '/reenrich') return;
    e.preventDefault();
    const fd = new FormData(form);
    const reco_id = fd.get('id');
    if (!reco_id) return;
    ajaxPost(action, fd, reco_id);
  });
})();
"""


def _client_script() -> str:
    return _CLIENT_JS


def _reco_card(r: dict, ep: dict, hosts: list, source_id: str,
               edit_id: str | None = None) -> str:
    """Carte d'une reco : timecode vidéo embarquable, contexte, candidats."""
    if edit_id and r.get("id") == edit_id:
        return render_edit_form(r, ep)
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
    boxes = "".join(
        f'<label><input type="checkbox" name="who" value="{html.escape(c)}"'
        f'{" checked" if c in current else ""}> {html.escape(c)}</label>'
        for c in hosts + _parse_guests(ep.get("title", ""), hosts)
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
      <div class="hd"><span class="type">{html.escape(", ".join(r.get('types', [])))}</span>
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


def _ep_header(ep: dict, recs: list[dict]) -> str:
    """En-tête d'épisode : numéro, titre YT, durées, compteur."""
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
    return (f'<h2 class="eph">{badge}{title_html} '
            f'<span class="cnt">{len(recs)} recos · {n_draft} à valider</span> {dur}</h2>')


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
        # .done = tout validated (grisé) · .empty = aucune reco (orange).
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
    # `edit_id` inconnu de l'épisode → _reco_card ignore et rend la carte normale.
    cards = "".join(_reco_card(r, ep, hosts, source_id, edit_id) for r in recs)
    player = ('<iframe name="ytplayer" class="player" title="Lecteur YouTube" '
              'allowfullscreen></iframe>')
    banner = _flash_banner(flash, flash_kind)
    inner = (f'{back}{banner}{player}<section class="ep">'
             f'{_ep_header(ep, recs)}<ul>{cards}</ul></section>')
    return _shell(source.get("title", source_id), "Relecture d'un épisode.", inner)


class Handler(BaseHTTPRequestHandler):
    def __init__(self, *args, source_id: str = "", **kwargs):
        self.source_id = source_id
        super().__init__(*args, **kwargs)

    def _send(self, code: int, body: str = "", headers: dict | None = None) -> None:
        # Headers explicites (Location pour 3xx) priment sur les défauts.
        self.send_response(code)
        out = {"Content-Type": "text/html; charset=utf-8", **_SECURITY_HEADERS}
        if headers:
            out.update(headers)
        for k, v in out.items():
            self.send_header(k, v)
        self.end_headers()
        if body:
            self.wfile.write(body.encode("utf-8"))

    def do_GET(self) -> None:  # noqa: N802
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/":
            self._send(200, _render_index(self.source_id))
        elif parsed.path == "/ep":
            qs = urllib.parse.parse_qs(parsed.query)
            guid = qs.get("guid", [""])[0]
            edit_id = qs.get("edit", [""])[0] or None
            if edit_id and not _RE_RECO_ID.match(edit_id):
                edit_id = None  # garde-fou : format invalide → mode normal
            flash = qs.get("flash", [""])[0] or None
            kind = qs.get("kind", [""])[0]
            if kind not in ("success", "warning", "error", "info"):
                kind = "info"
            self._send(200, _render_episode(
                self.source_id, guid, edit_id, flash=flash, flash_kind=kind,
            ))
        elif parsed.path == "/card":
            # Fragment HTML d'une seule carte — pour le rafraîchissement
            # partiel côté JS après /edit ou /reenrich.
            qs = urllib.parse.parse_qs(parsed.query)
            reco_id = qs.get("id", [""])[0]
            self._send_card_fragment(reco_id)
        else:
            self._send(404, "Not found")

    def _send_card_fragment(self, reco_id: str) -> None:
        """Renvoie le HTML d'une carte seule (200) ou 404."""
        if not _RE_RECO_ID.match(reco_id):
            self._send(404, "Not found")
            return
        path = _reco_path(self.source_id, reco_id)
        if path is None:
            self._send(404, "Not found")
            return
        reco = read_json(path)
        source, episodes, _groups = _load_groups(self.source_id)
        ep = episodes.get(reco.get("episodeGuid", ""))
        if not ep:
            self._send(404, "Not found")
            return
        hosts = source.get("hosts", [])
        self._send(200, _reco_card(reco, ep, hosts, self.source_id))

    def _wants_json(self) -> bool:
        """True si le client réclame du JSON (côté JS via fetch)."""
        return "application/json" in (self.headers.get("Accept") or "")

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length", 0))
        if length > _MAX_POST_BYTES:
            log.warning("POST refusé : Content-Length=%d > %d", length, _MAX_POST_BYTES)
            self._send(413, "Payload too large")
            return
        data = urllib.parse.parse_qs(
            self.rfile.read(length).decode("utf-8"), keep_blank_values=True
        )
        reco_id = (data.get("id") or [""])[0]
        if not _RE_RECO_ID.match(reco_id):
            log.warning("POST refusé : reco_id invalide « %s »", reco_id)
            self._reply_post("", "", "error", "ID invalide.", reco_id)
            return
        route = urllib.parse.urlparse(self.path).path
        path = _reco_path(self.source_id, reco_id)
        guid, flash, kind = "", "", ""
        if path is None:
            pass  # path inconnu → redirige vers /
        elif route == "/edit":
            ok, guid = apply_edit(path, data)
            if not ok:
                log.warning("Edit refusé : payload invalide pour %s", reco_id)
                guid = ""  # redirige vers /
            else:
                _invalidate_reco_path_cache(self.source_id)
                log.info("Édité : %s", reco_id)
                flash, kind = "Modifications enregistrées.", "success"
        elif route == "/reenrich":
            guid, flash, kind = apply_reenrich(path, reco_id)
            _invalidate_reco_path_cache(self.source_id)
        else:
            guid = self._save_status(path, reco_id, data)
        self._reply_post(guid, flash, kind, flash, reco_id)

    def _reply_post(self, guid: str, flash: str, kind: str,
                    message: str, reco_id: str) -> None:
        """Termine un POST : JSON si Accept JSON, sinon 303 PRG (fallback non-JS)."""
        if self._wants_json():
            self._send_json_post(guid, kind or "info", message, reco_id)
            return
        if guid:
            loc = f"/ep?guid={urllib.parse.quote(guid)}"
            if flash:
                loc += (f"&flash={urllib.parse.quote(flash)}"
                        f"&kind={urllib.parse.quote(kind)}")
        else:
            loc = "/"
        self._send(303, headers={"Location": loc})

    def _send_json_post(self, guid: str, kind: str, message: str,
                        reco_id: str) -> None:
        """Réponse JSON pour fetch côté client. Inclut le HTML de la carte
        fraîche pour permettre l'update partiel sans rechargement."""
        import json as _json  # noqa: PLC0415
        card_html = ""
        path = _reco_path(self.source_id, reco_id)
        if path and guid:
            try:
                reco = read_json(path)
                source, episodes, _g = _load_groups(self.source_id)
                ep = episodes.get(reco.get("episodeGuid", ""))
                if ep:
                    card_html = _reco_card(
                        reco, ep, source.get("hosts", []), self.source_id
                    )
            except Exception as exc:  # noqa: BLE001
                log.warning("Rebuild card_html pour %s : %s", reco_id, exc)
        body = _json.dumps({
            "kind": kind, "message": message, "card_html": card_html,
        }, ensure_ascii=False)
        self._send(200, body, headers={"Content-Type": "application/json; charset=utf-8"})

    def _save_status(self, path: Path, reco_id: str, data: dict) -> str:
        """POST /save : validate ou discard. Retourne le guid pour la redirection."""
        names = data.get("who", []) + [n for n in data.get("other", []) if n.strip()]
        recommended = " & ".join(dict.fromkeys(n.strip() for n in names if n.strip()))
        action = (data.get("action") or ["validate"])[0]
        reco = read_json(path)
        guid = reco.get("episodeGuid", "")
        if action == "discard":
            reco["status"] = "discarded"
            log.info("Écarté : %s", reco_id)
        else:
            if recommended:
                reco["recommendedBy"] = recommended
            elif "recommendedBy" in reco:
                del reco["recommendedBy"]
            reco["status"] = "validated"
            log.info("Validé : %s -> %s", reco_id, recommended or "(personne)")
        if write_json_if_changed(path, reco):
            _invalidate_reco_path_cache(self.source_id)
        return guid

    def log_message(self, *args):  # silence le log HTTP par défaut.
        pass


def main() -> None:
    parser = argparse.ArgumentParser(description="Outil de relecture local des recos.")
    parser.add_argument("--source", default="un-bon-moment")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()

    # Charge tools/.env pour que TMDB_API_KEY / SPOTIFY_* soient disponibles
    # dans os.environ — le bouton « Ré-enrichir » en a besoin.
    load_dotenv(TOOLS_DIR / ".env")

    handler = partial(Handler, source_id=args.source)
    server = HTTPServer(("127.0.0.1", args.port), handler)
    log.info("Relecture sur http://localhost:%d  (Ctrl+C pour arrêter)", args.port)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        log.info("Arrêt.")


if __name__ == "__main__":
    main()
