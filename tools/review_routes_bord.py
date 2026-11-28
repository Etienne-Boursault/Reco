"""review_routes_bord.py — les routes du tableau de bord d'admin de Reco V1.

Décision : tableau de bord, R2 B du 27/11/2026 ; TB-1 C du 28/11/2026 (plan
`pr-tableau-de-bord.md`, § 1, § 5 et § 6, tranche 1e). Sur le modèle de
`review_routes_table` : `BordRoutesMixin` porte les handlers,
`review_routes.Handler` en hérite et garde le dispatch.

- `GET  /bord`          — la page (`bord_rendu.rendre_bord`), avec le message
  d'une redirection (`?flash=…&kind=…`) ; l'audience vient du cache de
  `bord_distant.lire()` (tranche 2c), jamais d'un appel réseau pendant le rendu ; de
  même GitHub (`bord_github.lire()`) ; coûts, modèles et image par `bord_systeme.lire()`
  (tranche 3d-1) ;
- `POST /bord/reseau`   — coche ou décoche une case des réseaux
  (`bord_reseaux.cocher`) ; JSON `{kind, message}` pour le script de la page,
  sinon une redirection 303 vers `/bord` ;
- `GET  /polices/<nom>` — Bebas Neue et Inter, copiées de `@fontsource` dans
  `review_polices/` (licence OFL jointe) : la CSP refuse Google Fonts.

Sécurité : le POST passe par la garde des hôtes (`BaseHandler.parse_request`),
l'anti-CSRF et la limite de taille de `Handler.do_POST`, hors du journal de
relecture (aucune reco n'y change). Il n'écrit que `reseaux.json`, pour un
réseau de la liste et l'un des 3 derniers épisodes publiés. Une police n'est
servie que si son nom est dans une liste fixe : `../` n'atteint rien.
"""
from __future__ import annotations

import json
import urllib.parse
from pathlib import Path

import bord_afaire
import bord_chaine
import bord_distant
import bord_github
import bord_rendu
import bord_reseaux
import bord_systeme
import review_render
import review_render_page
from common import log
from review_handler_base import _SECURITY_HEADERS

__all__ = ["BordRoutesMixin"]

_POLICES_DIR = Path(__file__).parent / "review_polices"
#: Les seuls fichiers servis sous `/polices/` (nommés dans `review_bord.css`).
_POLICES = frozenset({
    "bebas-neue-latin-400-normal.woff2",
    "inter-latin-400-normal.woff2",
    "inter-latin-600-normal.woff2",
    "inter-latin-700-normal.woff2",
})
_GENRES = ("success", "warning", "error", "info")


def _premier(data: dict, cle: str) -> str:
    return (data.get(cle) or [""])[0]


class BordRoutesMixin:
    """Handlers de `/bord`, `/bord/reseau` et `/polices/…`."""

    source_id: str

    def _handle_get_bord(self, parsed: urllib.parse.ParseResult) -> None:
        if parsed.path.startswith("/polices/"):
            self._send_police(parsed.path.removeprefix("/polices/"))
            return
        qs = urllib.parse.parse_qs(parsed.query)
        kind = qs.get("kind", [""])[0]
        source, episodes, groups = review_render._load_groups(self.source_id)
        recents = bord_reseaux.episodes_recents(
            self.source_id, review_render_page._pipeline_state(self.source_id), episodes)
        try:
            coches = bord_reseaux.lire()
        except bord_reseaux.EtatIllisible as exc:
            log.warning("bord : %s", exc)
            coches = None  # la page le signale ; aucune case ne s'y écrira
        # Le cache seul, jamais le réseau : un rafraîchissement part détaché (2b).
        audience = bord_distant.lire()
        github = bord_github.lire()  # de même (3a)
        systeme = bord_systeme.lire(self.source_id)  # disque local, rien d'écrit (3b)
        self._send(200, bord_rendu.rendre_bord(
            titre=source.get("title", self.source_id),
            afaire=bord_afaire.a_faire(
                episodes=episodes, groups=groups, recents=recents, coches=coches,
                signalements=bord_afaire.lignes_signalements(audience)),
            audience=audience, github=github, systeme=systeme,
            chaine=bord_chaine.etat_chaine(self.source_id), recents=recents,
            coches=coches, flash=qs.get("flash", [""])[0] or None,
            flash_kind=kind if kind in _GENRES else "info"))

    def _handle_bord_reseau(self, data: dict) -> None:
        guid, reseau, fait = _premier(data, "guid"), _premier(data, "reseau"), \
            _premier(data, "fait") == "1"
        try:
            bord_reseaux.cocher(review_render_page._pipeline_state(self.source_id),
                                guid, reseau, fait)
            code, kind = 200, "success"
            message = f"{bord_reseaux.LIBELLES[reseau]} : {'fait' if fait else 'à faire'}."
        except ValueError as exc:
            log.warning("POST /bord/reseau refusé : %s", exc)
            code, kind, message = 400, "error", "Case refusée : épisode ou réseau inconnu."
        except bord_reseaux.EtatIllisible as exc:
            log.error("POST /bord/reseau : %s, rien n'est écrit", exc)
            code, kind, message = 500, "error", ("Le fichier des cases est illisible : "
                                                 "rien n'a été écrit.")
        except OSError as exc:
            log.error("POST /bord/reseau : écriture de %s/%s impossible (%s)",
                      guid[:60], reseau[:40], exc)
            code, kind, message = 500, "error", "La case n'a pas pu être enregistrée."
        if self._wants_json():
            self._send_json(json.dumps({"kind": kind, "message": message},
                                       ensure_ascii=False), code=code)
            return
        self._send_redirect(f"/bord?flash={urllib.parse.quote(message)}"
                            f"&kind={kind}#bord-reseaux")

    def _send_police(self, nom: str) -> None:
        try:
            corps = (_POLICES_DIR / nom).read_bytes() if nom in _POLICES else None
        except OSError as exc:
            log.error("Police %s illisible : %s", nom, exc)
            corps = None
        if corps is None:
            self._send_404()
            return
        self.send_response(200)
        for k, v in {**_SECURITY_HEADERS, "Content-Type": "font/woff2",
                     "Content-Length": str(len(corps)),
                     "Cache-Control": "max-age=604800"}.items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(corps)
