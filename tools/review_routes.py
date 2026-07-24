"""review_routes.py — Handlers HTTP métier du serveur de relecture.

Helpers _xxx sont privés au module. Exports publics dans __all__ uniquement.
La plomberie HTTP (sécurité, réponses, cache) vit dans review_handler_base.
"""

from __future__ import annotations

import urllib.parse
from pathlib import Path

from common import (
    log,
    read_json,
    recos_dir_for,
    write_json_if_changed,
)
from reco_dedup_merge import BACKUP_DIR
from review_edit import apply_edit, apply_reenrich
from review_guests import handle_rename_guest as _handle_rename_guest_fn
from review_handler_base import (
    BaseHandler,
    _MAX_POST_BYTES,
    _RE_GUID,
    _RE_RECO_ID,
    _invalidate_reco_path_cache,
    _parse_post_data,
    _reco_path,
)
from review_render import _load_groups, _reco_card, _render_episode, _render_index
from review_routes_merge import MergeRoutesMixin
# _allocate_new_reco ré-exporté pour la compat (review_server + tests l'importent
# depuis review_routes) ; RecoCrudRoutesMixin fournit /add-reco et /delete-reco.
from review_routes_reco import (  # noqa: F401
    RecoCrudRoutesMixin,
    _allocate_new_reco,
)

__all__ = [
    "Handler",
    "_allocate_new_reco",
    "_cleanup_orphan_tmp_files",
]

# m4 (revue 2026-07-19) — actions POST /save autorisées. Toute autre valeur est
# rejetée (avant : retombait en `validate` silencieux). m3 — message de
# confirmation synthétisé par action (toast JSON + flash non-JS).
_SAVE_ACTIONS: frozenset[str] = frozenset(
    {"validate", "discard", "citation", "guest-work"})
_SAVE_FLASH: dict[str, str] = {
    "validate": "Validée.",
    "discard": "Écartée.",
    "citation": "Citation enregistrée.",
    "guest-work": "Marquée « leur œuvre ».",
}


def _cleanup_orphan_tmp_files(source_id: str) -> int:
    """#E + sécu #13 — Au démarrage, supprime les `*.tmp` orphelins.

    Un _atomic_write_json interrompu (crash, Ctrl+C) peut laisser un tmp
    derrière. On nettoie le dossier reco ET le dossier backup pour éviter
    qu'ils s'accumulent. Retourne le nombre de fichiers supprimés.
    """
    n = 0
    dirs_to_clean: list[Path] = []
    d = recos_dir_for(source_id)
    if d.exists():
        dirs_to_clean.append(d)
    if BACKUP_DIR.exists():
        dirs_to_clean.append(BACKUP_DIR)
    for d in dirs_to_clean:
        for p in d.rglob("*.tmp"):
            try:
                p.unlink()
                n += 1
            except OSError as exc:
                log.warning("Cleanup tmp %s impossible : %s", p, exc)
    if n:
        log.info("Cleanup démarrage : %d fichier(s) .tmp orphelin(s) supprimé(s)", n)
    return n


class Handler(MergeRoutesMixin, RecoCrudRoutesMixin, BaseHandler):
    """Handler HTTP métier — assemble GET/POST sur les routes du review_server.

    Hérite de :
    - `MergeRoutesMixin` (routes /merge-recos et /undo-merge — review_routes_merge) ;
    - `RecoCrudRoutesMixin` (routes /add-reco et /delete-reco — review_routes_reco) ;
    - `BaseHandler` (plomberie : sécurité, réponses, cache).

    Ces mixins ont été extraits pour tenir chaque fichier sous 500 lignes (M4).
    """

    def do_GET(self) -> None:  # noqa: N802
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/":
            self._send(200, _render_index(self.source_id))
            return
        if parsed.path == "/doutes":
            # File de validation des incertitudes agent (cf. review_doubts).
            # `?edit=<id>` rend le formulaire d'édition inline dans la file
            # (retour à /doutes après save via #M3). L'id n'est utilisé qu'en
            # comparaison d'égalité (jamais réinjecté brut) → pas de risque XSS.
            from review_doubts import render_doubts  # noqa: PLC0415
            qs = urllib.parse.parse_qs(parsed.query)
            edit_id = qs.get("edit", [None])[0]
            # Refonte perf 2026-07-21 : `?ep=<guid>` → un seul épisode ; sans
            # ce param → l'index léger des épisodes à revoir.
            ep_guid = qs.get("ep", [None])[0]
            # rev-render m3 — propager flash/kind (POST /save depuis /doutes
            # redirige avec ces params ; sans JS, la bannière est le seul retour).
            flash = qs.get("flash", [""])[0] or None
            kind = qs.get("kind", [""])[0]
            if kind not in ("success", "warning", "error", "info"):
                kind = "info"
            self._send(200, render_doubts(
                self.source_id, ep=ep_guid, edit_id=edit_id,
                flash=flash, flash_kind=kind))
            return
        if parsed.path == "/doublons":
            # Page de consolidation MANUELLE des doublons (cf. review_dedup_page).
            from review_dedup_page import render_dedup_page  # noqa: PLC0415
            qs = urllib.parse.parse_qs(parsed.query)
            flash = qs.get("flash", [""])[0] or None
            kind = qs.get("kind", [""])[0]
            if kind not in ("success", "warning", "error", "info"):
                kind = "info"
            self._send(200, render_dedup_page(self.source_id, flash=flash,
                                              flash_kind=kind))
            return
        if parsed.path == "/ep":
            self._handle_get_episode(parsed.query)
            return
        if parsed.path == "/card":
            # Fragment HTML d'une seule carte — pour le rafraîchissement
            # partiel côté JS après /edit ou /reenrich.
            qs = urllib.parse.parse_qs(parsed.query)
            reco_id = qs.get("id", [""])[0]
            self._send_card_fragment(reco_id)
            return
        if parsed.path == "/doubt-frag":
            # Fragment /doutes d'UNE reco (signalement OU formulaire d'édition)
            # pour swap AJAX in-place — « Corriger » sans recharger la page (le
            # lecteur vidéo garde sa pause). Retour utilisateur 2026-07-23.
            qs = urllib.parse.parse_qs(parsed.query)
            reco_id = qs.get("id", [""])[0]
            if not _RE_RECO_ID.match(reco_id):
                self._send_404()
                return
            edit = qs.get("edit", ["0"])[0] == "1"
            from review_doubts import render_doubt_fragment  # noqa: PLC0415
            self._send(200, render_doubt_fragment(self.source_id, reco_id, edit))
            return
        self._send_404()

    def _handle_get_episode(self, query: str) -> None:
        qs = urllib.parse.parse_qs(query)
        guid = qs.get("guid", [""])[0]
        # m2 (revue 2026-07-19) : valider le FORMAT du guid en amont (défense en
        # profondeur). Un guid non vide au format invalide (espaces, >256 chars,
        # caractères d'injection) est rejeté avant tout rendu. Un guid vide passe
        # (comportement historique : page « épisode introuvable ») et un guid de
        # bon format mais inconnu suit son cours (rendu « introuvable »).
        if guid and not _RE_GUID.match(guid):
            log.warning("GET /ep : guid format invalide « %s »", guid)
            self._send_404()
            return
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

    def _send_card_fragment(self, reco_id: str) -> None:
        """Renvoie le HTML d'une carte seule (200) ou 404."""
        # #12 sécu — un Handler sans source_id ne devrait jamais arriver ici
        # (BaseHandler.__init__ raise déjà ValueError), mais on garde l'assert
        # explicite pour les tests qui poke directement la méthode.
        assert self.source_id, "_send_card_fragment requires source_id"
        if not _RE_RECO_ID.match(reco_id):
            self._send_404()
            return
        path = _reco_path(self.source_id, reco_id)
        if path is None:
            self._send_404()
            return
        reco = read_json(path)
        source, episodes, _groups = _load_groups(self.source_id)
        ep = episodes.get(reco.get("episodeGuid", ""))
        if not ep:
            self._send_404()
            return
        hosts = source.get("hosts", [])
        siblings = _groups.get(reco.get("episodeGuid", ""), [])
        self._send(200, _reco_card(
            reco, ep, hosts, self.source_id, siblings=siblings,
        ))

    def do_POST(self) -> None:  # noqa: N802
        if not self._is_same_origin():
            log.warning("POST refusé : Origin/Referer cross-site (%s)",
                        self.headers.get("Origin") or self.headers.get("Referer"))
            self._send(403, "Forbidden (cross-site)")
            return
        # #26 sécu — Content-Length peut être absent ou non-numérique.
        try:
            length = int(self.headers.get("Content-Length", 0))
        except ValueError:
            log.warning("POST refusé : Content-Length non-numérique")
            self._send(400, "Bad Content-Length")
            return
        if length < 0:
            self._send(400, "Bad Content-Length")
            return
        if length > _MAX_POST_BYTES:
            log.warning("POST refusé : Content-Length=%d > %d", length, _MAX_POST_BYTES)
            self._send(413, "Payload too large")
            return
        data = _parse_post_data(self.rfile.read(length))
        route = urllib.parse.urlparse(self.path).path
        if route == "/rename-guest":
            self._handle_rename_guest(data)
            return
        if route == "/add-reco":
            self._handle_add_reco(data)
            return
        if route == "/delete-reco":
            self._handle_delete_reco(data)
            return
        if route == "/merge-recos":
            self._handle_merge_recos(data)
            return
        if route == "/undo-merge":
            self._handle_undo_merge(data)
            return
        if route == "/consolidate":
            self._handle_consolidate(data)
            return
        # M1 (revue 2026-07-19) : router les routes « reco » EXPLICITEMENT. Sans
        # ça, TOUTE route POST inconnue (même `POST /`) tombait dans le
        # `else: _save_status` → action par défaut `validate` → mutation
        # silencieuse de la reco `id=…` du body.
        if route not in ("/edit", "/reenrich", "/save"):
            self._send_404()
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
            guid, flash, kind = self._dispatch_edit(path, reco_id, data)
        elif route == "/reenrich":
            guid, flash, kind = apply_reenrich(path, reco_id)
            _invalidate_reco_path_cache(self.source_id)
        else:
            guid, flash, kind = self._save_status(path, reco_id, data)
        self._reply_post(guid, flash, kind, flash, reco_id)

    def _dispatch_edit(self, path: Path, reco_id: str,
                       data: dict) -> tuple[str, str, str]:
        """Branche /edit : applique + log + flash succès/erreur."""
        ok, guid = apply_edit(path, data)
        if not ok:
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
            return guid, flash, "error"
        _invalidate_reco_path_cache(self.source_id)
        # Sur /doutes, « Corriger » est une décision humaine TERMINALE : la reco
        # corrigée doit QUITTER la file (comme Valider/Écarter). Le formulaire
        # d'édition depuis /doutes porte des radios de TYPE (name="action") :
        # « Sauvegarder » applique alors ce type (Reco/Citation/Leur œuvre/Pas une
        # reco) EN PLUS de la correction — retour utilisateur 2026-07-24. À défaut
        # de radio (édition depuis /ep, ou ancien client), on pose juste le
        # marqueur reviewedByHuman quand on venait de /doutes (sinon la reco
        # réapparaîtrait au rechargement malgré la correction, retour 2026-07-21).
        action = (data.get("action") or [None])[0]
        from_doutes = self._referer_path() == "/doutes"
        if action in _SAVE_ACTIONS or from_doutes:
            try:
                reco = read_json(path)
                if action in _SAVE_ACTIONS:
                    recby = str(reco.get("recommendedBy") or "").strip()
                    self._apply_save_action(reco, action, recby, reco_id)
                else:
                    reco.setdefault("agentReview", {})["reviewedByHuman"] = True
                write_json_if_changed(path, reco)
                from review_render import _GROUPS_CACHE  # noqa: PLC0415
                _GROUPS_CACHE.pop(self.source_id, None)
            except (OSError, ValueError) as exc:
                log.warning("post-édition %s : %s", reco_id, exc)
        log.info("Édité : %s", reco_id)
        return guid, "Modifications enregistrées.", "success"

    def _referer_path(self) -> str:
        """Path du header Referer (ou "" si absent/illisible).

        #M3 — sert à `_reply_post` : quand un POST /save a été initié depuis la
        file des doutes (/doutes), on y retourne au lieu d'être éjecté vers /ep.
        Le Referer est déjà validé same-origin par `_is_same_origin` en amont
        du dispatch POST.
        """
        ref = self.headers.get("Referer")
        if not ref:
            return ""
        try:
            return urllib.parse.urlparse(ref).path
        except ValueError:
            return ""

    def _reply_post(self, guid: str, flash: str, kind: str,
                    message: str, reco_id: str) -> None:
        """Termine un POST : JSON si Accept JSON, sinon 303 PRG (fallback non-JS).

        #M3 — si le POST a été initié depuis /doutes (Referer path == /doutes),
        on redirige vers /doutes (avec flash) plutôt que vers /ep : la file des
        doutes se traite ainsi en un seul passage, sans éjection vers l'épisode
        à chaque validation. `/save` ne produit pas de flash propre → on en
        synthétise un pour confirmer que la reco a bien quitté la file.
        """
        if self._wants_json():
            self._send_json_post(guid, kind or "info", message, reco_id)
            return
        if guid and self._referer_path() == "/doutes":
            # Refonte perf 2026-07-21 : on retourne à l'ÉPISODE en cours
            # (/doutes?ep=<guid>), pas à l'index global — on enchaîne les
            # doutes d'un même épisode sans recharger toute la file.
            doubt_flash = flash or "Traité — reco suivante."
            doubt_kind = kind or "success"
            loc = (f"/doutes?ep={urllib.parse.quote(guid)}"
                   f"&flash={urllib.parse.quote(doubt_flash)}"
                   f"&kind={urllib.parse.quote(doubt_kind)}")
            self._send_redirect(loc)
            return
        if guid:
            loc = f"/ep?guid={urllib.parse.quote(guid)}"
            if flash:
                loc += (f"&flash={urllib.parse.quote(flash)}"
                        f"&kind={urllib.parse.quote(kind)}")
        else:
            loc = "/"
        self._send_redirect(loc)

    def _send_json_post(self, guid: str, kind: str, message: str,
                        reco_id: str) -> None:
        """Réponse JSON pour fetch côté client. Inclut le HTML de la carte
        fraîche pour permettre l'update partiel sans rechargement."""
        import json as _json  # noqa: PLC0415
        card_html = ""
        # rev-render m4 (revue 2026-07-19) : dériver l'edit_origin du Referer.
        # Sans ça, la carte fraîche renvoyée à un fetch initié depuis /doutes
        # pointait son bouton Éditer vers /ep (au lieu de /doutes inline) —
        # incohérent avec le retour #M3.
        edit_origin = "/doutes" if self._referer_path() == "/doutes" else "/ep"
        path = _reco_path(self.source_id, reco_id)
        if path and guid:
            try:
                reco = read_json(path)
                source, episodes, groups = _load_groups(self.source_id)
                ep = episodes.get(reco.get("episodeGuid", ""))
                if ep:
                    # #29 review — passer `siblings` pour que les candidates
                    # "recommendedBy" reflètent le contexte épisode.
                    siblings = groups.get(reco.get("episodeGuid", ""), [])
                    card_html = _reco_card(
                        reco, ep, source.get("hosts", []), self.source_id,
                        siblings=siblings, edit_origin=edit_origin,
                    )
            except (OSError, ValueError, KeyError) as exc:
                # #12 sécu — différencier les erreurs "normales" (rebuild
                # silencieux, on renvoie kind/message seulement) des erreurs
                # imprévues (relance pour 500).
                log.warning("Rebuild card_html pour %s : %s", reco_id, exc)
        body = _json.dumps({
            "kind": kind, "message": message, "card_html": card_html,
        }, ensure_ascii=False)
        self._send_json(body)

    def _save_status(self, path: Path, reco_id: str,
                     data: dict) -> tuple[str, str, str]:
        """POST /save : validate / discard / citation / guest-work.

        Retourne `(guid, flash, kind)` :
          - `guid` : pour la redirection PRG (ou le contexte JSON) ;
          - `flash`/`kind` : message de confirmation (m3) ou d'erreur (m4).

        #2 review — pas de @_invalidates_reco_cache : on mute le contenu
        d'un fichier existant (même path, même id), donc le cache reste valide.
        """
        # #14 sécu / #17 — single-pass : combine who/other et strip une fois.
        names = [n.strip() for n in (data.get("who", []) + data.get("other", []))
                 if n.strip()]
        recommended = " & ".join(dict.fromkeys(names))
        action = (data.get("action") or ["validate"])[0]
        reco = read_json(path)
        guid = reco.get("episodeGuid", "")
        # m4 (revue 2026-07-19) : whitelist l'action. Une action inconnue ne
        # retombe PLUS en `validate` silencieux (mutation non désirée) — on
        # rejette avec un flash d'erreur SANS toucher la reco.
        if action not in _SAVE_ACTIONS:
            log.warning("POST /save refusé : action inconnue « %s »", action)
            return guid, "Action de sauvegarde inconnue.", "error"
        self._apply_save_action(reco, action, recommended, reco_id)
        write_json_if_changed(path, reco)
        # Note : pas d'invalidation du cache reco_id→Path — voir docstring
        # (#2 review : le path n'a pas changé). On invalide quand même le
        # cache groups (contenu muté → un nouveau render doit voir le statut
        # mis à jour, indépendamment de la granularité mtime du FS).
        from review_render import _GROUPS_CACHE  # noqa: PLC0415
        _GROUPS_CACHE.pop(self.source_id, None)
        # m3 (revue 2026-07-19) : synthétiser un flash succès — sinon le POST
        # /save en JSON (fetch) ne renvoyait aucun toast, et la redirection
        # non-JS ne confirmait rien à l'utilisateur·rice.
        return guid, _SAVE_FLASH[action], "success"

    @staticmethod
    def _apply_save_action(reco: dict, action: str, recommended: str,
                           reco_id: str) -> None:
        """#16 review — mute `reco` selon `action` (discard/citation/guest-work/validate).

        Extrait de `_save_status` pour clarté (chaque branche = une action).
        """
        # Une décision humaine (quelle qu'elle soit) sort la reco de la file des
        # doutes : `_section_for` ignore désormais les recos `reviewedByHuman`.
        # Sans ça, une reco validée mais encore porteuse de flags (ou de faible
        # confiance) réapparaissait dans /doutes au rechargement (retour
        # utilisateur 2026-07-21).
        reco.setdefault("agentReview", {})["reviewedByHuman"] = True
        if action == "discard":
            reco["status"] = "discarded"
            # On préserve `kind` ET `guestWork` à dessein : un humain a
            # peut-être déjà qualifié l'item (citation, œuvre d'invité) puis
            # change d'avis sur la pertinence globale. Réinitialiser ces
            # marqueurs effacerait cette info de re-qualification.
            log.info("Écarté : %s", reco_id)
            return
        if action == "citation":
            if recommended:
                reco["recommendedBy"] = recommended
            elif "recommendedBy" in reco:
                del reco["recommendedBy"]
            reco["status"] = "validated"
            reco["kind"] = "citation"
            # Re-qualifier en citation retire le marqueur « œuvre d'invité ».
            reco.pop("guestWork", None)
            log.info("Citation : %s -> %s", reco_id, recommended or "(personne)")
            return
        if action == "guest-work":
            # Œuvre présentée par un·e invité·e (auto-promo) : c'est une vraie
            # reco (kind=reco) mais marquée pour ne pas polluer les vraies
            # recommandations côté site. recommendedBy géré comme validate.
            if recommended:
                reco["recommendedBy"] = recommended
            elif "recommendedBy" in reco:
                del reco["recommendedBy"]
            reco["status"] = "validated"
            reco["kind"] = "reco"
            reco["guestWork"] = True
            log.info("Œuvre d'invité : %s -> %s", reco_id, recommended or "(personne)")
            return
        # default = validate
        if recommended:
            reco["recommendedBy"] = recommended
        elif "recommendedBy" in reco:
            del reco["recommendedBy"]
        reco["status"] = "validated"
        # Ré-affirme qu'une validation classique = vraie reco, et retire un
        # éventuel marqueur « œuvre d'invité » (re-qualification).
        reco["kind"] = "reco"
        reco.pop("guestWork", None)
        log.info("Validé : %s -> %s", reco_id, recommended or "(personne)")

    def _handle_consolidate(self, data: dict) -> None:
        """POST /consolidate (page /doublons) : garde les recos COCHÉES du cluster
        (avec leur type + titre corrigé), écarte les autres. reviewedByHuman posé
        partout (décision humaine). Le recommendedBy existant est préservé."""
        members = data.get("member", [])
        keep = set(data.get("keep", []))
        n_keep = n_disc = 0
        for rid in members:
            if not _RE_RECO_ID.match(rid):
                continue
            path = _reco_path(self.source_id, rid)
            if path is None:
                continue
            reco = read_json(path)
            if rid in keep:
                new_title = (data.get(f"title_{rid}") or [""])[0].strip()
                if new_title:
                    reco["title"] = new_title
                action = (data.get(f"type_{rid}") or ["validate"])[0]
                if action not in _SAVE_ACTIONS or action == "discard":
                    action = "validate"
                existing = str(reco.get("recommendedBy") or "").strip()
                self._apply_save_action(reco, action, existing, rid)
                n_keep += 1
            else:
                self._apply_save_action(reco, "discard", "", rid)
                n_disc += 1
            write_json_if_changed(path, reco)
        from review_render import _GROUPS_CACHE  # noqa: PLC0415
        _GROUPS_CACHE.pop(self.source_id, None)
        log.info("Consolidé : %d gardée(s), %d écartée(s)", n_keep, n_disc)
        flash = f"Consolidé : {n_keep} gardée(s), {n_disc} écartée(s)."
        self._send_redirect(
            f"/doublons?flash={urllib.parse.quote(flash)}&kind=success")

    def _handle_rename_guest(self, data: dict) -> None:
        """POST /rename-guest : délègue à review_guests.handle_rename_guest.

        #11 sécu — la validation du guid est faite côté handler métier
        (`_GUID_RE.match`), pas la peine de la dupliquer ici.
        """
        loc = _handle_rename_guest_fn(
            self.source_id, data,
            load_groups=_load_groups,
            reco_path=_reco_path,
            invalidate_cache=_invalidate_reco_path_cache,
        )
        self._send_redirect(loc)
