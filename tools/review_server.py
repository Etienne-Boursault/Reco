"""review_server.py — Outil de relecture LOCAL (hors site public).

Sert une page web locale (http.server stdlib, sans dépendance) pour valider /
écarter / éditer / ré-enrichir les recos extraites par IA.

Usage : ``python review_server.py --source un-bon-moment [--port 8000]``
"""

from __future__ import annotations

import argparse
import re
import threading
import urllib.parse
from functools import partial
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

from dotenv import load_dotenv

from common import (
    TOOLS_DIR,
    log,
    read_json,
    recos_dir_for,
    write_json_if_changed,
)
from review_edit import apply_edit, apply_reenrich
from review_guests import handle_rename_guest as _handle_rename_guest_fn
from review_render import (
    _CLIENT_JS,
    _CSS_PATH,
    _STOP,
    _ep_header,
    _embed_url,
    _flash_banner,
    _fmt,
    _load_groups,
    _load_transcript,
    _parse_guests,
    _reco_card,
    _render_episode,
    _render_index,
    _shell,
    _style,
    _ts_seconds,
    _yt_id,
    _context_around,
)

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


# Cache reco_id → Path, invalidé après chaque écriture (évite scan O(n) à chaque POST).
_RECO_PATH_CACHE: dict[tuple[str, str], Path] = {}
_RECO_CACHE_LOCK = threading.Lock()


def _rebuild_reco_path_cache(source_id: str) -> None:
    """(Re)construit le cache reco_id → Path pour une source.

    Tolère les JSON illisibles (corrompus) en log.warning — précédemment
    silencieux, c'était une source de bugs invisibles (L5).
    """
    new_cache: dict[tuple[str, str], Path] = {}
    for p in recos_dir_for(source_id).glob("*.json"):
        try:
            rid = read_json(p).get("id")
        except (OSError, ValueError) as exc:
            log.warning("Reco JSON illisible %s : %s", p, exc)
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
        siblings = _groups.get(reco.get("episodeGuid", ""), [])
        self._send(200, _reco_card(
            reco, ep, hosts, self.source_id, siblings=siblings,
        ))

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
        route = urllib.parse.urlparse(self.path).path
        if route == "/rename-guest":
            self._handle_rename_guest(data)
            return
        reco_id = (data.get("id") or [""])[0]
        if not _RE_RECO_ID.match(reco_id):
            log.warning("POST refusé : reco_id invalide « %s »", reco_id)
            self._reply_post("", "", "error", "ID invalide.", reco_id)
            return
        path = _reco_path(self.source_id, reco_id)
        guid, flash, kind = "", "", ""
        if path is None:
            pass  # path inconnu → redirige vers /
        elif route == "/edit":
            ok, guid = apply_edit(path, data)
            if not ok:
                # H6 : on veut un feedback explicite côté UI (pas un retour
                # silencieux à /). On utilise le guid de la reco existante
                # pour rediriger vers son épisode et afficher le flash.
                try:
                    existing = read_json(path)
                except (OSError, ValueError):
                    existing = {}
                guid = existing.get("episodeGuid", "") or ""
                title_raw = (data.get("title") or [""])[0].strip()
                if not title_raw:
                    flash = "Modification refusée : titre vide."
                else:
                    flash = ("Modification refusée : type manquant ou "
                             "inconnu (sélectionne au moins un type).")
                kind = "error"
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

    def _handle_rename_guest(self, data: dict) -> None:
        """POST /rename-guest : délègue à review_guests.handle_rename_guest."""
        loc = _handle_rename_guest_fn(
            self.source_id, data,
            load_groups=_load_groups,
            reco_path=_reco_path,
            invalidate_cache=_invalidate_reco_path_cache,
        )
        self._send(303, headers={"Location": loc})

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
