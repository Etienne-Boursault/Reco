"""review_handler_base.py — Plomberie HTTP du serveur de relecture.

Helpers _xxx sont privés au module. Exports publics dans __all__ uniquement.
Contient toute la couche transport / sécurité réutilisable. Aucune logique
métier (cf. review_routes.py pour les handlers GET/POST).
"""

from __future__ import annotations

import re
import urllib.parse
from functools import wraps
from http.server import BaseHTTPRequestHandler
from pathlib import Path

from common import log, read_json, recos_dir_for

__all__ = [
    "BaseHandler",
    "_MAX_POST_BYTES",
    "_RE_RECO_ID",
    "_RE_GUID",
    "_SECURITY_HEADERS",
    "_RECO_PATH_CACHE",
    "_rebuild_reco_path_cache",
    "_invalidate_reco_path_cache",
    "_invalidates_reco_cache",
    "_reco_path",
    "_parse_post_data",
]

# Limite max sur les requêtes POST (en octets) — anti-DoS.
_MAX_POST_BYTES = 1 << 20  # 1 MiB

# Format conventionnel des reco_id POST : minuscules alphanum + tirets/underscores.
_RE_RECO_ID = re.compile(r"^[a-z0-9_-]+$")
# #18 sécu — format permissif pour les guid (RSS guid, slug…). 256 chars max.
# GARDE : ne JAMAIS utiliser un guid (même validé) en path direct — toujours
# passer par episodes.get(guid) ou un dispatcher qui ne touche pas au disque.
# La regex accepte `.` et `/` pour compat RSS, ce qui rend le path traversal
# possible si on l'oublie. Quand on doit dériver un nom de fichier d'un guid,
# utiliser `slugify(guid)` (cf. common.transcript_path_for).
_RE_GUID = re.compile(r"^[A-Za-z0-9_:.\-/@]{1,256}$")

# Security headers (CSP autorise l'iframe YouTube et les miniatures).
_SECURITY_HEADERS: dict[str, str] = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    # `strict-origin-when-cross-origin` (et pas `no-referrer`) : l'embed YouTube
    # exige un referer valide, sinon erreur 153 « Erreur de configuration du
    # lecteur vidéo ». On envoie l'origine (pas le chemin) — privacy-safe.
    "Referrer-Policy": "strict-origin-when-cross-origin",
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


# Cache source_id → {reco_id → Path}. Single-threaded : pas de lock.
# Structure imbriquée (#1 review) : invalidation O(1) par source au lieu de O(N).
_RECO_PATH_CACHE: dict[str, dict[str, Path]] = {}


def _rebuild_reco_path_cache(source_id: str) -> None:
    """(Re)construit le cache reco_id → Path pour une source.

    Tolère les JSON illisibles (corrompus) en log.warning — précédemment
    silencieux, c'était une source de bugs invisibles (#5 sécu).
    """
    new_cache: dict[str, Path] = {}
    for p in recos_dir_for(source_id).glob("*.json"):
        try:
            rid = read_json(p).get("id")
        except (OSError, ValueError) as exc:
            log.warning("Reco JSON illisible %s : %s", p, exc)
            continue
        if rid:
            new_cache[rid] = p
    _RECO_PATH_CACHE[source_id] = new_cache


def _invalidate_reco_path_cache(source_id: str) -> None:
    """Vide les entrées de cache d'une source (après une écriture). O(1).

    Invalide aussi `_GROUPS_CACHE` (review_render) — pour qu'une mutation
    du serveur soit immédiatement visible au prochain `_load_groups` sans
    dépendre de la granularité mtime du FS (NTFS 100ns vs macOS HFS+ 1s).
    Import paresseux pour éviter un cycle (review_render importe ce module).
    """
    _RECO_PATH_CACHE.pop(source_id, None)
    try:
        from review_render import _GROUPS_CACHE  # noqa: PLC0415
        _GROUPS_CACHE.pop(source_id, None)
    except ImportError:
        # En early bootstrap (import circulaire) — pas grave : à ce moment
        # _GROUPS_CACHE est vide de toute façon.
        pass


def _invalidates_reco_cache(func):
    """#20 review — décorateur : invalide le cache après tout handler mutant.

    Discipline centralisée : on n'a plus à se rappeler manuellement d'appeler
    `_invalidate_reco_path_cache(source_id)` dans chaque handler de mutation.
    Le décorateur s'applique aux méthodes du Handler qui mutent le disque ;
    `self.source_id` est utilisé comme clé.
    """
    @wraps(func)
    def wrapper(self, *args, **kwargs):
        try:
            return func(self, *args, **kwargs)
        finally:
            # #20 sécu — `source_id` peut être absent en test/mock ; fallback "".
            _invalidate_reco_path_cache(getattr(self, "source_id", ""))
    return wrapper


def _reco_path(source_id: str, reco_id: str) -> Path | None:
    """Retrouve le fichier JSON d'une reco par son id (cache mémoire)."""
    bucket = _RECO_PATH_CACHE.get(source_id)
    if bucket is not None:
        cached = bucket.get(reco_id)
        if cached and cached.exists():
            return cached
    _rebuild_reco_path_cache(source_id)  # cache miss ou fichier disparu
    return _RECO_PATH_CACHE.get(source_id, {}).get(reco_id)


def _parse_post_data(body: bytes) -> dict[str, list[str]]:
    """Parse un body POST urlencoded en dict[str, list[str]].

    Wrapper centralisé sur urllib.parse.parse_qs (keep_blank_values=True).
    """
    # M2 (revue 2026-07-19) : errors="replace" — un body POST non-UTF-8 ne doit
    # pas lever d'UnicodeDecodeError hors de do_POST (BaseHTTPRequestHandler ne
    # l'entoure d'aucun try/except → connexion coupée sans réponse HTTP propre).
    return urllib.parse.parse_qs(
        body.decode("utf-8", errors="replace"), keep_blank_values=True)


class BaseHandler(BaseHTTPRequestHandler):
    """Plomberie HTTP partagée : sécurité, réponses, parse POST.

    Les sous-classes ajoutent do_GET / do_POST avec la logique métier.
    Instance attribute `source_id` doit être posé par les sous-classes ou
    via partial() au niveau de l'instanciation du serveur.
    """

    source_id: str = ""

    def __init__(self, *args, source_id: str = "", **kwargs):
        # #3 sécu — source_id obligatoire : sans ça, les helpers de cache,
        # les chemins reco et le décorateur d'invalidation opèrent sur "" et
        # peuvent ouvrir une fenêtre de confusion entre sources.
        if not source_id:
            raise ValueError("source_id requis pour BaseHandler")
        self.source_id = source_id
        super().__init__(*args, **kwargs)

    # ---- Réponses --------------------------------------------------------
    @staticmethod
    def _content_type_for(body: str) -> str:
        """#4 review — `text/plain` pour body sans HTML, `text/html` sinon.

        Les messages d'erreur courts (« Not found », « Forbidden ») n'ont
        rien d'HTML : envoyer `text/html` est trompeur pour les clients.
        """
        return ("text/html; charset=utf-8" if "<" in body
                else "text/plain; charset=utf-8")

    def _send(self, code: int, body: str = "", headers: dict | None = None) -> None:
        # Headers explicites (Location pour 3xx) priment sur les défauts.
        self.send_response(code)
        out = {"Content-Type": self._content_type_for(body), **_SECURITY_HEADERS}
        if headers:
            out.update(headers)
        for k, v in out.items():
            self.send_header(k, v)
        self.end_headers()
        if body:
            self.wfile.write(body.encode("utf-8"))

    def _send_json(self, payload: str, code: int = 200) -> None:
        """Réponse JSON (Content-Type application/json)."""
        self._send(code, payload,
                   headers={"Content-Type": "application/json; charset=utf-8"})

    def _send_redirect(self, location: str) -> None:
        """303 PRG (POST-Redirect-Get)."""
        self._send(303, headers={"Location": location})

    def _send_404(self, body: str = "Not found") -> None:
        self._send(404, body)

    # ---- Sécurité --------------------------------------------------------
    def _wants_json(self) -> bool:
        """True si le client réclame du JSON (côté JS via fetch)."""
        return "application/json" in (self.headers.get("Accept") or "")

    def _is_same_origin(self) -> bool:
        """Anti-CSRF + DNS-rebinding (#C, #D, #6 sécu) :

        - **DNS-rebinding** (#C) : refuse si l'IP client n'est pas locale
          (127.0.0.1 / ::1). Empêche un site malveillant de résoudre un nom
          de domaine vers 127.0.0.1 et de relayer ses POST.
        - **Origin / Referer présents** : doivent matcher localhost ; sinon
          la requête est rejetée (CSRF classique).
        - **Origin/Referer ABSENTS** (#D) : refusé par défaut, sauf si le
          client est local ET envoie un header custom `X-Reco-CSRF: 1`
          (compatible curl/tests qui ne posent pas d'origine).
        """
        # #C — DNS rebinding guard : tout client non-local est refusé,
        # même si Origin pointe localhost.
        if self.client_address[0] not in ("127.0.0.1", "::1"):
            return False

        origin = self.headers.get("Origin") or self.headers.get("Referer")
        if not origin:
            # #D — pas d'origine fournie → exiger l'opt-in custom header.
            return self.headers.get("X-Reco-CSRF") == "1"
        try:
            parsed = urllib.parse.urlparse(origin)
        except ValueError:
            return False
        if parsed.scheme not in ("http", "https"):
            return False
        host = (parsed.hostname or "").lower()
        if host not in ("127.0.0.1", "localhost"):
            return False
        # #5 sécu — vérifier le port aussi : un attaquant qui contrôle un
        # autre service local (ex. dev server sur :3000) ne doit pas pouvoir
        # CSRF nos POSTs. parsed.port=None signifie « port par défaut » → on
        # ne peut pas en déduire grand-chose, on accepte (compat curl/tests).
        try:
            expected_port = self.server.server_address[1]
        except (AttributeError, IndexError, TypeError):
            return True  # tests sans server attaché → on n'échoue pas dur.
        return parsed.port in (None, expected_port)

    # ---- Misc ------------------------------------------------------------
    def log_message(self, *args):  # silence le log HTTP par défaut.
        pass
