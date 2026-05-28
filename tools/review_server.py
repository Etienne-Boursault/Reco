"""
review_server.py — Outil de relecture LOCAL (hors site public).

Sert une page web locale pour valider rapidement les recos extraites :
  - timecode cliquable (ouvre la vidéo YouTube de l'épisode au bon moment) ;
  - citation (contexte) ;
  - boutons des participants probables (hôtes + invité déduit du titre) +
    champ libre → on coche qui a recommandé, on valide.

Valider écrit `recommendedBy` et passe `status` à « validated » dans le JSON.
Aucune dépendance externe (http.server de la stdlib).

Usage :
    python review_server.py --source un-bon-moment [--port 8000]
    puis ouvrir http://localhost:8000
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

from common import (
    extract_youtube_id,
    list_episode_files,
    load_source,
    log,
    read_json,
    recos_dir_for,
    write_json_if_changed,
)

# Limite max sur les requêtes POST (en octets) — protège contre l'épuisement RAM.
_MAX_POST_BYTES = 1 << 20  # 1 MiB

# Valide les identifiants de reco postés (cf. `id` POST). Format conventionnel :
# minuscules alphanumériques + tirets/underscores (ex. « ubm-0042 »).
_RE_RECO_ID = re.compile(r"^[a-z0-9_-]+$")

# Security headers ajoutés à chaque réponse HTML (sans casser l'iframe YouTube).
_SECURITY_HEADERS: dict[str, str] = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    # CSP : permet l'iframe YouTube (player) et les miniatures i.ytimg.com.
    "Content-Security-Policy": (
        "default-src 'self'; "
        "img-src 'self' data: https://i.ytimg.com; "
        "style-src 'unsafe-inline'; "
        "frame-src https://www.youtube.com https://www.youtube-nocookie.com; "
        "script-src 'none'; base-uri 'none'; form-action 'self'"
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


# Cache reco_id → Path, invalidé après chaque écriture (cf. _persist_reco_status).
# Évite un scan O(n) de tous les JSON à chaque POST de validation : pour 1000
# recos, ça transforme un O(1000) en un O(1) après le premier appel.
_RECO_PATH_CACHE: dict[tuple[str, str], Path] = {}
# Verrou pour les modifications du cache (les tests et les requêtes HTTP peuvent
# y accéder depuis plusieurs threads).
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
    # Remplace en bloc les entrées de cette source (évite les états transitoires).
    with _RECO_CACHE_LOCK:
        keys_to_drop = [k for k in _RECO_PATH_CACHE if k[0] == source_id]
        for k in keys_to_drop:
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
    # Cache miss ou fichier disparu : on reconstruit pour cette source.
    _rebuild_reco_path_cache(source_id)
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
    """Identifiant de la vidéo depuis une URL YouTube (vide si absent).

    Wrapper qui s'appuie sur `common.extract_youtube_id` (renvoie "" plutôt que
    None pour rester compatible avec le rendu HTML existant).
    """
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
    """Lignes du transcript autour d'un timecode cible (±n lignes).

    Cherche l'index le plus proche par bissection (O(log n)) puis ajuste en
    comparant le voisin précédent (les timecodes sont monotones croissants).
    """
    if not items:
        return []
    times = [it[0] for it in items]
    pos = bisect.bisect_left(times, target_sec)
    # Choix du voisin le plus proche entre pos et pos-1.
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

# CSS externalisé pour ne pas alourdir ce module et faciliter l'édition visuelle.
_CSS_PATH = Path(__file__).parent / "review_server.css"


@lru_cache(maxsize=1)
def _style() -> str:
    """Charge la feuille de style (cachée pour éviter l'I/O répété)."""
    try:
        return _CSS_PATH.read_text(encoding="utf-8")
    except OSError:
        return ""


def _shell(source_title: str, subtitle: str, inner: str) -> str:
    """Gabarit HTML commun (en-tête, style, titre)."""
    return (
        '<!doctype html><html lang="fr"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        f"<title>Relecture — {html.escape(source_title)}</title>"
        f"<style>{_style()}</style></head><body>"
        f"<h1>Relecture — {html.escape(source_title)}</h1>"
        f'<p class="meta">{subtitle}</p>{inner}</body></html>'
    )


def _reco_card(r: dict, ep: dict, hosts: list, source_id: str) -> str:
    """Carte d'une reco : timecode vidéo embarquable, contexte, candidats."""
    secs = _ts_seconds(r.get("timestamp"))
    yt = ep.get("youtubeUrl")
    if yt and secs is not None:
        tv = max(0, secs)
        embed = _embed_url(yt, tv)
        # target="ytplayer" charge dans l'iframe partagée au lieu d'un onglet.
        link = (f'<a class="tc" target="ytplayer" href="{html.escape(embed)}">'
                f'▶ {_fmt(tv)}</a>')
    elif r.get("timestamp"):
        link = f'<span class="tc off">⏱ {html.escape(r.get("timestamp", ""))}</span>'
    else:
        link = ""

    # Contexte : ±3 lignes du transcript autour du timecode → permet de juger
    # rapidement si la reco est valide sans ouvrir la vidéo.
    ctx_html = ""
    if secs is not None:
        ctx = _context_around(_load_transcript(source_id, ep.get("guid", "")), secs)
        if ctx:
            spans = []
            for sec, txt in ctx:
                tag = "ctx-here" if abs(sec - secs) < 3 else "ctx"
                spans.append(f'<span class="{tag}">{html.escape(txt)}</span>')
            ctx_html = f'<div class="context">{" ".join(spans)}</div>'
    current = r.get("recommendedBy", "")
    boxes = "".join(
        f'<label><input type="checkbox" name="who" value="{html.escape(c)}"'
        f'{" checked" if c in current else ""}> {html.escape(c)}</label>'
        for c in hosts + _parse_guests(ep.get("title", ""), hosts)
    )
    status = r.get("status", "draft")
    cls = {"validated": "done", "discarded": "discarded"}.get(status, "")
    extractors = r.get("extractors") or []
    if len(extractors) >= 2:
        joined = html.escape(", ".join(extractors))
        conf_badge = (
            f'<span class="conf" title="Confirmée par {joined}">'
            f'⭐ {len(extractors)} LLMs</span>'
        )
    elif extractors:
        first = html.escape(extractors[0])
        conf_badge = (
            f'<span class="conf solo" title="Trouvée par {first} uniquement">'
            f'{first}</span>'
        )
    else:
        conf_badge = ""
    return f"""
    <li class="row {cls}">
      <div class="hd"><span class="type">{html.escape(", ".join(r.get('types', [])))}</span>
        <b>{html.escape(r.get('title',''))}</b>
        {f"<i>· {html.escape(r['creator'])}</i>" if r.get('creator') else ''}
        {link}
        {conf_badge}
        <span class="st">{html.escape(status)}</span></div>
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
    # Tri : par statut (drafts en 1er), puis confirmées-par-2 en tête de la
    # tranche draft pour qu'elles surgissent en premier dans la relecture.
    for g in groups.values():
        g.sort(key=lambda r: (_ORDER.get(r.get("status", "draft"), 0),
                              -len(r.get("extractors") or [])))
    return source, episodes, groups


def _render_index(source_id: str) -> str:
    """Page d'accueil : galerie de miniatures, TOUS les épisodes à leur emplacement."""
    source, episodes, groups = _load_groups(source_id)

    def _key(guid: str):
        # Tri par emplacement chronologique : saison puis numéro.
        # Pré-S5 = season=None → groupe 0 ; S5 = groupe 5. Sans-numéro = 9999.
        ep = episodes.get(guid, {})
        return (ep.get("season") or 0, ep.get("number") or 9999)

    thumbs = []
    todo = 0
    # Itérer sur tous les épisodes connus, pas seulement ceux ayant des recos
    for guid in sorted(episodes.keys(), key=_key):
        ep = episodes.get(guid, {})
        recs = groups.get(guid, [])
        n_draft = sum(1 for r in recs if r.get("status", "draft") == "draft")
        todo += n_draft
        season, num = ep.get("season"), ep.get("number")
        ep_num = f"S{season}·E{num}" if season and num else (f"#{num}" if num else "?")
        vid = _yt_id(ep.get("youtubeUrl", ""))
        style = f'style="background-image:url(https://i.ytimg.com/vi/{vid}/mqdefault.jpg)"' if vid else ""
        # États visuels :
        #   .done   = toutes les recos sont validated → grisé
        #   .empty  = aucune reco (extraction LLM n'a rien trouvé ou épisode-jeu)
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


def _render_episode(source_id: str, guid: str) -> str:
    """Page d'un épisode : son en-tête + ses recos à relire."""
    source, episodes, groups = _load_groups(source_id)
    hosts = source.get("hosts", [])
    ep = episodes.get(guid)
    recs = groups.get(guid, [])
    back = '<a class="back" href="/">← tous les épisodes</a>'
    if not ep:
        return _shell(source.get("title", source_id), "Épisode introuvable.", back)
    cards = "".join(_reco_card(r, ep, hosts, source_id) for r in recs)
    # Iframe partagée : clique sur un timecode -> la vidéo charge ici (pas
    # d'onglet, pas de re-chargement YouTube intermédiaire).
    player = ('<iframe name="ytplayer" class="player" title="Lecteur YouTube" '
              'allowfullscreen></iframe>')
    inner = (f'{back}{player}<section class="ep">'
             f'{_ep_header(ep, recs)}<ul>{cards}</ul></section>')
    return _shell(source.get("title", source_id), "Relecture d'un épisode.", inner)


class Handler(BaseHTTPRequestHandler):
    def __init__(self, *args, source_id: str = "", **kwargs):
        self.source_id = source_id
        super().__init__(*args, **kwargs)

    def _send(self, code: int, body: str = "", headers: dict | None = None) -> None:
        self.send_response(code)
        # Headers explicites (Location pour 3xx, etc.) priment sur les défauts.
        out_headers = {"Content-Type": "text/html; charset=utf-8"}
        out_headers.update(_SECURITY_HEADERS)
        if headers:
            out_headers.update(headers)
        for k, v in out_headers.items():
            self.send_header(k, v)
        self.end_headers()
        if body:
            self.wfile.write(body.encode("utf-8"))

    def do_GET(self) -> None:  # noqa: N802
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/":
            self._send(200, _render_index(self.source_id))
        elif parsed.path == "/ep":
            guid = urllib.parse.parse_qs(parsed.query).get("guid", [""])[0]
            self._send(200, _render_episode(self.source_id, guid))
        else:
            self._send(404, "Not found")

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length", 0))
        # Garde-fou : refuse les payloads anormalement gros (DoS / mauvais client).
        if length > _MAX_POST_BYTES:
            log.warning("POST refusé : Content-Length=%d > %d", length, _MAX_POST_BYTES)
            self._send(413, "Payload too large")
            return
        data = urllib.parse.parse_qs(self.rfile.read(length).decode("utf-8"))
        reco_id = (data.get("id") or [""])[0]
        # Valide le format de l'id avant tout I/O (rejette les chemins exotiques).
        if not _RE_RECO_ID.match(reco_id):
            log.warning("POST refusé : reco_id invalide « %s »", reco_id)
            self._send(303, headers={"Location": "/"})
            return
        names = data.get("who", []) + [n for n in data.get("other", []) if n.strip()]
        recommended = " & ".join(dict.fromkeys(n.strip() for n in names if n.strip()))

        action = (data.get("action") or ["validate"])[0]
        guid = ""
        path = _reco_path(self.source_id, reco_id)
        if path:
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
                # Le contenu a changé : on jette le cache pour cette source
                # (l'id ne bouge pas mais on reste prudent face à un éventuel
                # déplacement de fichier).
                _invalidate_reco_path_cache(self.source_id)
        # PRG : on revient sur la page de l'épisode pour enchaîner ses recos.
        loc = f"/ep?guid={urllib.parse.quote(guid)}" if guid else "/"
        self._send(303, headers={"Location": loc})

    def log_message(self, *args):  # silence le log HTTP par défaut.
        pass


def main() -> None:
    parser = argparse.ArgumentParser(description="Outil de relecture local des recos.")
    parser.add_argument("--source", default="un-bon-moment")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()

    handler = partial(Handler, source_id=args.source)
    server = HTTPServer(("127.0.0.1", args.port), handler)
    log.info("Relecture sur http://localhost:%d  (Ctrl+C pour arrêter)", args.port)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        log.info("Arrêt.")


if __name__ == "__main__":
    main()
