"""review_routes_merge.py — Handlers HTTP de fusion/cluster (mixin).

Extrait de review_routes.py (#M4 : garder chaque fichier sous 500 lignes).
`MergeRoutesMixin` regroupe la plomberie des routes /merge-recos (dispatcher
pick/preview/merge/cancel) et /undo-merge ; `review_routes.Handler` en hérite.

Mixin pur : les méthodes s'appuient sur `self.source_id` et les helpers de
réponse fournis par `BaseHandler` (`_send`, `_send_redirect`, `_send_404`).
Aucun état propre — pas de `__init__`.
"""

from __future__ import annotations

import urllib.parse

from common import log, read_json
from reco_dedup import Cluster, is_cluster_compatible, restore_last_backup
from reco_dedup_merge import merge_cluster
from review_handler_base import (
    _RE_GUID,
    _RE_RECO_ID,
    _invalidates_reco_cache,
    _reco_path,
)
from review_render_cluster import render_merge_preview, render_pick_canonical


class MergeRoutesMixin:
    """Routes de fusion manuelle de doublons (pick/preview/merge/cancel + undo).

    Suppose `self.source_id` + les helpers de réponse de `BaseHandler`
    (`_send`, `_send_redirect`, `_send_404`). Hérité par review_routes.Handler.
    """

    # Renseigné par BaseHandler.__init__ — déclaré ici pour les type-checkers.
    source_id: str

    def _validate_merge_input(
        self, data: dict,
    ) -> tuple[str, str, str, list[str]] | None:
        """#19 review — Valide la requête /merge-recos.

        Renvoie (guid, action, keep_id, cluster_ids) ou None si une réponse
        d'erreur a déjà été envoyée. #18 sécu — guid validé via _RE_GUID.
        """
        guid = (data.get("guid") or [""])[0].strip()
        action = (data.get("action") or [""])[0].strip()
        keep_id = (data.get("keep_id") or [""])[0].strip()
        cluster_ids_raw = (data.get("cluster_ids") or [""])[0].strip()
        cluster_ids = [x for x in cluster_ids_raw.split(",") if x]
        if not cluster_ids or not all(_RE_RECO_ID.match(i) for i in cluster_ids):
            log.warning("POST /merge-recos : cluster_ids invalides")
            self._send_redirect("/")
            return None
        if keep_id and not _RE_RECO_ID.match(keep_id):
            self._send_redirect("/")
            return None
        if guid and not _RE_GUID.match(guid):
            log.warning("POST /merge-recos : guid format invalide « %s »", guid)
            self._send_redirect("/")
            return None
        return guid, action, keep_id, cluster_ids

    def _resolve_expected_kind(
        self, keep_id: str,
        by_id: dict[str, dict] | None = None,
    ) -> str | None:
        """#8 — Lit le `kind` du keep_id (None si absent/illisible).

        #17 — Si `by_id` (membres déjà chargés) fourni, évite l'I/O disque.
        """
        if not keep_id:
            return None
        if by_id is not None and keep_id in by_id:
            return by_id[keep_id].get("kind") or "reco"
        keep_path = _reco_path(self.source_id, keep_id)
        if keep_path is None:
            return None
        try:
            return read_json(keep_path).get("kind") or "reco"
        except (OSError, ValueError):
            return None

    def _handle_merge_recos(self, data: dict) -> None:
        """POST /merge-recos : dispatcher (action ∈ pick/preview/merge/cancel)."""
        validated = self._validate_merge_input(data)
        if validated is None:
            return
        guid, action, keep_id, cluster_ids = validated

        if action == "cancel":
            self._action_cancel(guid)
            return

        if not guid:
            log.warning("POST /merge-recos : guid manquant")
            self._send(400, "guid manquant")
            return

        expected_kind = self._resolve_expected_kind(keep_id)
        members, missing, _by_id = self._load_cluster_members(
            cluster_ids,
            expected_guid=guid,
            expected_kind=expected_kind,
        )
        if missing:
            log.info(
                "merge-recos : %d recos rejetées (épisode différent, "
                "discarded, kind incohérent) : %s",
                len(missing), ",".join(missing),
            )

        if action == "pick":
            self._action_pick(members, guid, missing=missing)
            return

        # preview/merge : besoin de ≥ 2 membres + keep_id valide ∈ cluster.
        if len(members) < 2 or not keep_id:
            if action == "merge" and not keep_id:
                msg = "Sélectionne une version à conserver avant de fusionner."
                loc = (f"/ep?guid={urllib.parse.quote(guid)}"
                       f"&flash={urllib.parse.quote(msg)}&kind=error")
                self._send_redirect(loc)
                return
            self._send_404("Cluster invalid")
            return
        if keep_id not in {m.get("id") for m in members}:
            self._send_404("keep_id absent du cluster")
            return

        if action == "preview":
            self._action_preview(members, keep_id, guid)
            return
        if action == "merge":
            self._action_merge(members, keep_id, guid)
            return
        self._send(400, "Action inconnue")

    def _load_cluster_members(
        self, cluster_ids: list[str], *,
        expected_guid: str | None = None,
        expected_kind: str | None = None,
    ) -> tuple[list[dict], list[str], dict[str, dict]]:
        """Charge les membres d'un cluster depuis disque (source de vérité).

        #17 — Retourne `(members, missing, by_id)` ; `by_id` mappe rid → reco
        pour les membres conservés, permettant de réutiliser les données sans
        re-lire le disque (utile pour `_resolve_expected_kind`).
        """
        raw: list[tuple[str, dict]] = []
        missing: list[str] = []
        for rid in cluster_ids:
            p = _reco_path(self.source_id, rid)
            if p is None:
                missing.append(rid)
                continue
            try:
                raw.append((rid, read_json(p)))
            except (OSError, ValueError):
                missing.append(rid)

        if expected_guid is None:
            members = [r for _, r in raw]
            by_id = {rid: r for rid, r in raw}
            return members, missing, by_id

        ref_kind = expected_kind
        if ref_kind is None:
            for _rid, r in raw:
                if (r.get("episodeGuid") == expected_guid
                        and r.get("status") != "discarded"):
                    ref_kind = r.get("kind") or "reco"
                    break
        if ref_kind is None:
            ref_kind = "reco"

        kept: list[dict] = []
        by_id: dict[str, dict] = {}
        for rid, r in raw:
            if is_cluster_compatible(
                r, expected_guid=expected_guid, expected_kind=ref_kind,
            ):
                kept.append(r)
                by_id[rid] = r
            else:
                missing.append(rid)
        return kept, missing, by_id

    def _action_cancel(self, guid: str) -> None:
        """Action `cancel` : flash info, pas de mutation."""
        loc = (f"/ep?guid={urllib.parse.quote(guid)}"
               f"&flash={urllib.parse.quote('Cluster ignoré pour cette session.')}"
               f"&kind=info") if guid else "/"
        self._send_redirect(loc)

    def _action_pick(self, members: list[dict], guid: str,
                     *, missing: list[str] | None = None) -> None:
        """Action `pick` : page de sélection canonical (avant preview).

        #10 review — si moins de 2 membres, on flash + redirect plutôt
        qu'un 404 brut. Si des recos ont été FILTRÉES (kind différent,
        épisode différent, discarded), on surface l'info dans le flash
        pour éviter le message trompeur « sélectionne au moins 2 ».
        """
        if len(members) < 2:
            n_rejected = len(missing or [])
            if n_rejected > 0:
                msg = (f"{n_rejected} reco(s) rejetée(s) : kind différent "
                       f"(reco vs citation), autre épisode, ou écartée. "
                       f"Pour fusionner, les recos doivent partager le même "
                       f"type et le même épisode.")
            else:
                msg = "Sélectionne au moins 2 recos pour fusionner."
            loc = (f"/ep?guid={urllib.parse.quote(guid)}"
                   f"&flash={urllib.parse.quote(msg)}&kind=warning") if guid else "/"
            self._send_redirect(loc)
            return
        self._send(200, render_pick_canonical(members, guid))

    def _action_preview(self, members: list[dict], keep_id: str, guid: str) -> None:
        """Action `preview` : diff lisible avant le merge final."""
        self._send(200, render_merge_preview(members, keep_id, guid))

    @_invalidates_reco_cache
    def _action_merge(self, members: list[dict], keep_id: str, guid: str) -> None:
        """Action `merge` : exécute la fusion via reco_dedup.merge_cluster.

        #14 sécu — on capture le `kind` pré-merge du keep_id pour le
        remonter dans le flash undo (utile si un edit ultérieur a changé
        le kind : l'utilisateur sait à quel état il revient).
        """
        # #17 — réutilise les membres déjà chargés pour récupérer le kind.
        by_id = {m.get("id"): m for m in members}
        kept_pre_merge_kind = self._resolve_expected_kind(keep_id, by_id=by_id) or "reco"
        cluster = Cluster(canonical_id=keep_id, members=members)
        try:
            merge_cluster(cluster, keep_id=keep_id, source_id=self.source_id)
        except Exception as exc:  # noqa: BLE001
            # m5 (revue 2026-07-19) : catch large. Une fusion est une opération
            # best-effort déclenchée par l'utilisateur·rice ; toute défaillance
            # (y compris un KeyError/TypeError sur un JSON malformé, pas
            # seulement ValueError/OSError) doit produire un flash d'erreur
            # actionnable et non un 500 + stacktrace brute. log.exception garde
            # la trace complète côté serveur pour le diagnostic.
            log.exception("Fusion échouée : %s", exc)
            loc = (f"/ep?guid={urllib.parse.quote(guid)}"
                   f"&flash={urllib.parse.quote('Fusion échouée: ' + str(exc))}"
                   f"&kind=error")
            self._send_redirect(loc)
            return
        n = len(members) - 1
        msg = (f"{n} doublon(s) fusionné(s) dans {keep_id} "
               f"(kind={kept_pre_merge_kind}). Undo possible.")
        loc = (f"/ep?guid={urllib.parse.quote(guid)}"
               f"&flash={urllib.parse.quote(msg)}&kind=success&undo=1")
        self._send_redirect(loc)

    @_invalidates_reco_cache
    def _handle_undo_merge(self, data: dict) -> None:
        """POST /undo-merge : restaure le dernier backup, retour à l'épisode.

        #18 sécu — guid validé via _RE_GUID.
        """
        guid = (data.get("guid") or [""])[0].strip()
        if guid and not _RE_GUID.match(guid):
            log.warning("POST /undo-merge : guid format invalide « %s »", guid)
            self._send_redirect("/")
            return
        result = restore_last_backup(self.source_id)
        n = result["n_restored"]
        n_failed = result.get("n_failed", 0)
        if n == 0:
            msg = "Aucun backup à restaurer."
            kind = "warning"
        elif n_failed > 0:
            # #10 sécu — restauration partielle : signaler distinctement.
            msg = (f"{n} fichier(s) restauré(s), {n_failed} échec(s). "
                   "Vérifie le log.")
            kind = "warning"
        else:
            msg = f"{n} fichier(s) restauré(s) depuis le dernier backup."
            kind = "success"
        loc = "/"
        if guid:
            loc = (f"/ep?guid={urllib.parse.quote(guid)}"
                   f"&flash={urllib.parse.quote(msg)}&kind={kind}")
        self._send_redirect(loc)
