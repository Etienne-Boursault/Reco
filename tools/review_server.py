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
import html
import re
import urllib.parse
from functools import partial
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

from common import (
    list_episode_files,
    load_source,
    log,
    read_json,
    recos_dir_for,
    write_json_if_changed,
)

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
    keys_to_drop = [k for k in _RECO_PATH_CACHE if k[0] == source_id]
    for k in keys_to_drop:
        del _RECO_PATH_CACHE[k]
    _RECO_PATH_CACHE.update(new_cache)


def _reco_path(source_id: str, reco_id: str) -> Path | None:
    """Retrouve le fichier JSON d'une reco par son id (cache mémoire)."""
    key = (source_id, reco_id)
    cached = _RECO_PATH_CACHE.get(key)
    if cached and cached.exists():
        return cached
    # Cache miss ou fichier disparu : on reconstruit pour cette source.
    _rebuild_reco_path_cache(source_id)
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


def _yt_id(url: str) -> str:
    """Identifiant de la vidéo depuis une URL YouTube (vide si absent)."""
    m = re.search(r"[?&]v=([A-Za-z0-9_-]+)", url or "")
    return m.group(1) if m else ""


def _embed_url(video_url: str, start_seconds: int) -> str:
    """URL d'embed YouTube positionnée à `start_seconds`, prête à jouer."""
    vid = _yt_id(video_url)
    return (f"https://www.youtube.com/embed/{vid}?start={start_seconds}&autoplay=1"
            if vid else "")


from functools import lru_cache  # noqa: E402


@lru_cache(maxsize=None)
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
    """Lignes du transcript autour d'un timecode cible (±n lignes)."""
    if not items:
        return []
    idx = min(range(len(items)), key=lambda i: abs(items[i][0] - target_sec))
    start = max(0, idx - n_before)
    end = min(len(items), idx + n_after + 1)
    return [items[i] for i in range(start, end)]


_ORDER = {"draft": 0, "validated": 1, "discarded": 2}

_STYLE = """
  body{font-family:system-ui,sans-serif;background:#0e0e10;color:#f6f4ee;margin:0;padding:1.5rem;}
  h1{font-size:1.4rem;} .meta{color:#9a99a3;}
  .back{color:#9a99a3;text-decoration:none;font-weight:600;font-size:.9rem;}
  .back:hover{color:#ffd23f;}
  .ep{max-width:820px;margin:1.2rem auto;}
  .eph{font-size:1rem;border-bottom:1px solid #2a2a30;padding-bottom:.4rem;margin:0 0 .4rem;}
  .eph a{color:#f6f4ee;text-decoration:none;} .eph a:hover{color:#ffd23f;}
  .cnt{color:#9a99a3;font-size:.75rem;font-weight:400;}
  .gallery{display:grid;grid-template-columns:repeat(auto-fill,minmax(160px,1fr));gap:.7rem;max-width:920px;margin:1rem auto 2rem;}
  .thumb{position:relative;aspect-ratio:16/9;border-radius:10px;background:#17171c;background-size:cover;background-position:center;border:1px solid #2a2a30;text-decoration:none;overflow:hidden;display:flex;flex-direction:column;justify-content:space-between;}
  .thumb:hover{outline:2px solid #ffd23f;outline-offset:1px;}
  .thumb.done{opacity:.4;}
  .thumb.empty{opacity:.55;outline:1px dashed #7a4d00;}
  .thumb.empty .tcount{color:#ffb74d;}
  .tbadge{align-self:flex-start;background:rgba(14,14,16,.8);color:#ffd23f;font-size:.72rem;font-weight:700;padding:.15em .55em;border-radius:0 0 6px 0;}
  .tcount{background:rgba(14,14,16,.8);color:#f6f4ee;font-size:.72rem;padding:.2em .55em;text-align:center;}
  ul{list-style:none;padding:0;margin:0;}
  .row{background:#17171c;border:1px solid #2a2a30;border-left:3px solid #ffd23f;border-radius:10px;padding:.7rem 1rem;margin:.5rem 0;}
  .row.done{border-left-color:#3a3a40;opacity:.55;}
  .row.discarded{border-left-color:#6b3a3a;opacity:.45;}
  .discard{background:transparent;color:#9a99a3;border:1px solid #3a3a40;}
  .discard:hover{border-color:#6b3a3a;color:#d88;}
  .hd{display:flex;align-items:baseline;flex-wrap:wrap;gap:.4rem;}
  .type{color:#ffd23f;font-size:.7rem;text-transform:uppercase;font-weight:700;letter-spacing:.05em;}
  .st{margin-left:auto;color:#9a99a3;font-size:.7rem;text-transform:uppercase;}
  .conf{background:#1f1c0a;color:#ffd23f;border:1px solid #ffd23f55;border-radius:6px;padding:.05em .45em;font-size:.7rem;font-weight:600;}
  .conf.solo{background:transparent;color:#7a7a82;border-color:#3a3a40;font-weight:400;text-transform:uppercase;}
  .player{position:fixed;top:.6rem;right:.6rem;width:min(360px,32vw);aspect-ratio:16/9;border:0;border-radius:8px;background:#000;z-index:100;box-shadow:0 8px 24px rgba(0,0,0,.6);}
  .context{font-size:.82rem;color:#bfbcb3;background:#0e0e10;border:1px dashed #2a2a30;border-radius:8px;padding:.5em .8em;margin:.4rem 0;line-height:1.5;}
  .ctx{opacity:.65;}
  .ctx-here{color:#ffd23f;font-weight:600;}
  .tc{color:#ffd23f;font-weight:600;text-decoration:none;} .tc.off{color:#9a99a3;}
  .dur{color:#8a8a92;font-size:.78rem;}
  .epnum{color:#ffd23f;background:#0e0e10;border:1px solid #2a2a30;border-radius:6px;padding:.05em .4em;font-size:.78rem;}
  .q{font-style:italic;color:#cfcdc6;font-size:.88rem;margin:.4rem 0;}
  .who{display:flex;flex-wrap:wrap;gap:.5rem;align-items:center;margin-top:.4rem;}
  label{background:#0e0e10;border:1px solid #2a2a30;border-radius:999px;padding:.25em .7em;font-size:.85rem;cursor:pointer;}
  input[type=text]{background:#0e0e10;border:1px solid #2a2a30;color:#f6f4ee;border-radius:999px;padding:.3em .7em;}
  button{background:#ffd23f;color:#0e0e10;border:0;border-radius:999px;padding:.35em 1em;font-weight:700;cursor:pointer;}
"""


def _shell(source_title: str, subtitle: str, inner: str) -> str:
    """Gabarit HTML commun (en-tête, style, titre)."""
    return (
        '<!doctype html><html lang="fr"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        f"<title>Relecture — {html.escape(source_title)}</title>"
        f"<style>{_STYLE}</style></head><body>"
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
        conf_badge = f'<span class="conf" title="Confirmée par {", ".join(extractors)}">⭐ {len(extractors)} LLMs</span>'
    elif extractors:
        conf_badge = f'<span class="conf solo" title="Trouvée par {extractors[0]} uniquement">{extractors[0]}</span>'
    else:
        conf_badge = ""
    return f"""
    <li class="row {cls}">
      <div class="hd"><span class="type">{html.escape(r.get('type',''))}</span>
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
    episodes = {read_json(p)["guid"]: read_json(p) for p in list_episode_files(source_id)}
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
    player = '<iframe name="ytplayer" class="player" allowfullscreen></iframe>'
    inner = (f'{back}{player}<section class="ep">'
             f'{_ep_header(ep, recs)}<ul>{cards}</ul></section>')
    return _shell(source.get("title", source_id), "Relecture d'un épisode.", inner)


class Handler(BaseHTTPRequestHandler):
    def __init__(self, *args, source_id: str = "", **kwargs):
        self.source_id = source_id
        super().__init__(*args, **kwargs)

    def _send(self, code: int, body: str = "", headers: dict | None = None) -> None:
        self.send_response(code)
        for k, v in (headers or {"Content-Type": "text/html; charset=utf-8"}).items():
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
        data = urllib.parse.parse_qs(self.rfile.read(length).decode("utf-8"))
        reco_id = (data.get("id") or [""])[0]
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
            write_json_if_changed(path, reco)
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
