"""review_routes_table.py — Routes du tableau de pilotage (/tableau).

Extrait de `review_routes.py` (règle du dépôt : un fichier sous 500 lignes),
sur le même modèle que `review_routes_merge` et `review_routes_reco` :
`TableRoutesMixin` porte les handlers, `review_routes.Handler` en hérite et
garde le dispatch.

Trois routes :

- `GET  /tableau`      — la page (rendu dans `review_table`) ;
- `POST /curation`     — pose commentaire et/ou coche dans le sidecar ;
- `POST /accept-type`  — accepte la proposition de reclassement d'une reco.

Discipline de sécurité : ces handlers sont appelés APRÈS le contrôle
same-origin et la limite de taille de `Handler.do_POST` — on ne les
contourne pas. Chaque `id` reçu est re-validé (`_RE_RECO_ID`) puis résolu par
`_reco_path` : rien n'est écrit pour une reco qui n'existe pas.

`/accept-type` ne fait PAS confiance aux types postés par le client : il relit
la proposition côté serveur et n'applique que des types du vocabulaire
(`RECO_TYPES`). Le formulaire n'est donc pas une porte d'écriture arbitraire
dans les JSON de recos.
"""
from __future__ import annotations

import json as _json
import urllib.parse

from common import log, read_json, write_json_if_changed
from review_curation import load_type_proposals, set_annotation
from review_edit import RECO_TYPES, TYPE_LABELS
from review_handler_base import (
    _RE_RECO_ID,
    _invalidate_reco_path_cache,
    _reco_path,
)
from review_table import render_table_page

__all__ = ["TableRoutesMixin"]

_FLASH_KINDS = ("success", "warning", "error", "info")

#: Valeurs de `checked` interprétées comme « décoché ». Tout le reste coche —
#: le client envoie "1"/"0", on reste tolérant pour le repli sans JavaScript.
_FALSY = frozenset({"", "0", "false", "off", "no"})


class TableRoutesMixin:
    """Routes du tableau de pilotage. Suppose `self.source_id` + les helpers
    de réponse de `BaseHandler`."""

    # Renseigné par BaseHandler.__init__ — déclaré ici pour les type-checkers.
    source_id: str

    # ---- GET ---------------------------------------------------------------
    def _handle_get_table(self, query: str) -> None:
        """GET /tableau — la page complète (tri côté client, pas de pagination)."""
        qs = urllib.parse.parse_qs(query)
        flash = qs.get("flash", [""])[0] or None
        kind = qs.get("kind", [""])[0]
        if kind not in _FLASH_KINDS:
            kind = "info"
        self._send(200, render_table_page(
            self.source_id, flash=flash, flash_kind=kind))

    # ---- Réponse commune ---------------------------------------------------
    def _reply_table(self, code: int, kind: str, message: str,
                     extra: dict | None = None) -> None:
        """JSON si le client en demande (fetch), sinon 303 PRG vers /tableau.

        Le repli non-JS existe pour la même raison qu'ailleurs dans cet outil :
        sans lui, un POST sans JavaScript laisse l'utilisateur·rice devant une
        page blanche, sans savoir si l'écriture a eu lieu.
        """
        if self._wants_json():
            payload = {"kind": kind, "message": message}
            payload.update(extra or {})
            self._send_json(_json.dumps(payload, ensure_ascii=False), code)
            return
        self._send_redirect(
            f"/tableau?flash={urllib.parse.quote(message)}"
            f"&kind={urllib.parse.quote(kind)}")

    def _resolve_reco(self, data: dict, route: str):
        """(reco_id, path) validés, ou (id, None) si l'un des deux est refusé.

        Répond elle-même (400 / 404) dans les cas de refus : l'appelant n'a
        qu'à sortir quand `path` est None.
        """
        reco_id = (data.get("id") or [""])[0]
        if not _RE_RECO_ID.match(reco_id):
            log.warning("POST %s refusé : reco_id invalide « %s »", route, reco_id)
            self._reply_table(400, "error", "ID de reco invalide.")
            return reco_id, None
        path = _reco_path(self.source_id, reco_id)
        if path is None:
            self._reply_table(404, "error", f"Reco {reco_id} introuvable.")
        return reco_id, path

    # ---- POST /curation ----------------------------------------------------
    def _handle_curation(self, data: dict) -> None:
        """POST /curation — enregistre commentaire et/ou coche dans le sidecar.

        Les deux champs sont indépendants : n'envoyer que `comment` laisse la
        coche intacte, et réciproquement. C'est ce qui rend deux onglets
        ouverts inoffensifs l'un pour l'autre (cf. `review_curation`).
        """
        reco_id, path = self._resolve_reco(data, "/curation")
        if path is None:
            return
        comment = data["comment"][0] if "comment" in data else None
        checked = (data["checked"][0].strip().lower() not in _FALSY
                   if "checked" in data else None)
        if comment is None and checked is None:
            self._reply_table(400, "error", "Rien à enregistrer.")
            return
        entry = set_annotation(self.source_id, reco_id,
                               comment=comment, checked=checked)
        self._reply_table(200, "success", "Annotation enregistrée.", {
            "id": reco_id,
            "comment": entry["comment"],
            "checked": entry["checked"],
            "updatedAt": entry["updatedAt"],
        })

    # ---- POST /accept-type -------------------------------------------------
    def _handle_accept_type(self, data: dict) -> None:
        """POST /accept-type — applique la proposition de reclassement.

        Contrairement au reste du tableau, ceci MUTE une reco : on n'accepte
        donc que ce que le serveur a lui-même lu dans le fichier de
        propositions, et seulement des types du vocabulaire.
        """
        reco_id, path = self._resolve_reco(data, "/accept-type")
        if path is None:
            return
        prop = load_type_proposals().get(reco_id) or {}
        types = [t for t in prop.get("types", []) if t in RECO_TYPES]
        if not types:
            self._reply_table(
                404, "error", f"Aucune proposition applicable pour {reco_id}.")
            return
        try:
            reco = read_json(path)
            reco["types"] = types
            write_json_if_changed(path, reco)
        except (OSError, ValueError) as exc:
            log.warning("accept-type %s : écriture impossible — %s", reco_id, exc)
            self._reply_table(500, "error", f"Écriture impossible pour {reco_id}.")
            return
        _invalidate_reco_path_cache(self.source_id)
        labels = ", ".join(TYPE_LABELS.get(t, t) for t in types)
        log.info("Type accepté depuis /tableau : %s -> %s", reco_id, types)
        self._reply_table(200, "success", f"Type mis à jour : {labels}.", {
            "id": reco_id, "types": types, "labels": labels,
        })
