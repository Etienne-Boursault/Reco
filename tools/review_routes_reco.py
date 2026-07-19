"""review_routes_reco.py — Routes de cycle de vie d'une reco (create/delete).

Extrait de review_routes.py (#M4 : garder chaque fichier sous 500 lignes).
`RecoCrudRoutesMixin` regroupe les routes /add-reco et /delete-reco (+ le
garde-fou backup) ; `review_routes.Handler` en hérite. Les deux fonctions
module `_allocate_new_reco` / `_assert_under_recos` vivent ici (utilisées par
/add-reco) ; `_allocate_new_reco` reste ré-exporté par review_routes pour la
compat des tests et de review_server.

Mixin pur : les méthodes s'appuient sur `self.source_id` + les helpers de
réponse de `BaseHandler` (`_send`, `_send_redirect`). Aucun état propre.
"""

from __future__ import annotations

import json as _json
import urllib.parse
from pathlib import Path

from common import (
    atomic_write_text,
    log,
    read_json,
    reco_prefix,
    recos_dir_for,
)
from reco_dedup_merge import BACKUP_DIR
from review_handler_base import (
    _RE_GUID,
    _RE_RECO_ID,
    _invalidates_reco_cache,
    _reco_path,
)
from review_render import _load_groups


def _allocate_new_reco(source_id: str, episode_guid: str) -> tuple[str, Path]:
    """Crée un fichier reco stub minimal pour une saisie manuelle.

    Calcule le prochain ID (max ubm-NNNN + 1), écrit un JSON draft minimal
    et retourne (id, path). Le statut reste `draft` : l'utilisateur·rice
    devra explicitement Valider après l'avoir complétée.

    Single-threaded : pas de race ID-collision possible (cf. docs/yagni.md).
    """
    d = recos_dir_for(source_id)
    d.mkdir(parents=True, exist_ok=True)
    prefix = reco_prefix(source_id)
    max_n = 0
    for p in d.glob("*.json"):
        try:
            rid = read_json(p).get("id", "")
        except (OSError, ValueError):
            continue
        if rid.startswith(f"{prefix}-"):
            try:
                max_n = max(max_n, int(rid[len(prefix) + 1:]))
            except ValueError:
                pass
    new_n = max_n + 1
    new_id = f"{prefix}-{new_n:04d}"
    new_file = d / f"{new_n:04d}.json"
    stub = {
        "id": new_id,
        "sourceId": source_id,
        "episodeGuid": episode_guid,
        "title": "Nouvelle reco",
        "types": ["autre"],
        "status": "draft",
        "extractors": ["manual"],
    }
    # #atomic — passe par atomic_write_text pour qu'un lecteur concurrent
    # (le pipeline ou un autre handler) ne voie jamais un fichier tronqué.
    atomic_write_text(
        new_file,
        _json.dumps(stub, ensure_ascii=False, indent=2),
    )
    return new_id, new_file


def _assert_under_recos(path: Path, source_id: str) -> bool:
    """#7 sécu — True si `path` résout sous `recos_dir_for(source_id)`.

    Defense in depth : nos chemins viennent déjà de `_reco_path` ou
    `_allocate_new_reco`, mais on garde la vérification explicite pour
    blinder contre une régression future (ex. user-supplied path).
    """
    try:
        root = recos_dir_for(source_id).resolve()
        return path.resolve().is_relative_to(root)
    except (OSError, ValueError):
        return False


class RecoCrudRoutesMixin:
    """Routes create/delete d'une reco (+ garde-fou backup au delete).

    Suppose `self.source_id` + les helpers de réponse de `BaseHandler`
    (`_send`, `_send_redirect`). Hérité par review_routes.Handler.
    """

    # Renseigné par BaseHandler.__init__ — déclaré ici pour les type-checkers.
    source_id: str

    @_invalidates_reco_cache
    def _handle_add_reco(self, data: dict) -> None:
        """POST /add-reco : crée un stub de reco vide rattaché à un épisode.

        #6 sécu — `guid` validé via `_RE_GUID` AVANT toute lecture épisode.
        """
        guid = (data.get("guid") or [""])[0].strip()
        if not guid or not _RE_GUID.match(guid):
            log.warning("POST /add-reco : guid manquant ou invalide « %s »", guid)
            self._send_redirect("/")
            return
        _source, episodes, _g = _load_groups(self.source_id)
        if guid not in episodes:
            self._send_redirect("/")
            return
        # m2 (revue 2026-07-19) : reco_prefix() lève FileNotFoundError si la
        # config source est absente. Sans garde, /add-reco renvoyait un 500 +
        # stacktrace brute. On flashe un message actionnable à la place.
        try:
            new_id, new_path = _allocate_new_reco(self.source_id, guid)
        except FileNotFoundError as exc:
            log.warning("add-reco : config source introuvable — %s", exc)
            self._send_redirect(
                f"/ep?guid={urllib.parse.quote(guid)}"
                f"&flash={urllib.parse.quote(f'Config source introuvable : {exc}')}"
                f"&kind=error"
            )
            return
        # #7 sécu — defense in depth : le nouveau fichier doit être sous
        # recos_dir_for(source_id). Si pas le cas, on supprime et on abort.
        if not _assert_under_recos(new_path, self.source_id):
            log.warning("add-reco : path hors recos_root (%s), abort", new_path)
            try:
                new_path.unlink()
            except OSError:
                pass
            self._send_redirect("/")
            return
        log.info("Reco manuelle créée : %s (episode %s)", new_id, guid)
        loc = (f"/ep?guid={urllib.parse.quote(guid)}"
               f"&edit={urllib.parse.quote(new_id)}"
               f"&flash={urllib.parse.quote('Reco créée — complète les champs puis Sauvegarder.')}"
               f"&kind=info")
        self._send_redirect(loc)

    @_invalidates_reco_cache
    def _handle_delete_reco(self, data: dict) -> None:
        """POST /delete-reco : supprime DÉFINITIVEMENT le fichier JSON.

        #19 sécu — path containment : on vérifie que le chemin résout
        bien à l'intérieur du dossier reco de la source (defense in depth
        — `_reco_path` ne peut renvoyer qu'un fichier de ce dossier de
        toute façon, mais on garde la garde explicite).

        #13 sécu — un manifest récent référençant cet id peut faire
        "ressusciter" la reco via un undo postérieur. On le flash en
        warning si on détecte le cas.
        """
        reco_id = (data.get("id") or [""])[0]
        if not _RE_RECO_ID.match(reco_id):
            self._send_redirect("/")
            return
        path = _reco_path(self.source_id, reco_id)
        if path is None or not path.exists():
            self._send_redirect("/")
            return
        # #19 sécu — assert le path est bien sous recos_dir_for(source_id).
        recos_root = recos_dir_for(self.source_id).resolve()
        try:
            if not path.resolve().is_relative_to(recos_root):
                log.warning("delete-reco refusé : path hors recos_root (%s)", path)
                self._send(403, "Forbidden")
                return
        except (OSError, ValueError) as exc:
            log.warning("delete-reco : resolve %s a échoué : %s", path, exc)
            self._send_redirect("/")
            return
        try:
            guid = read_json(path).get("episodeGuid", "") or ""
        except (OSError, ValueError):
            guid = ""
        try:
            path.unlink()
        except OSError as exc:
            log.warning("Suppression refusée %s : %s", reco_id, exc)
            self._send_redirect("/")
            return
        log.info("Reco supprimée définitivement : %s", reco_id)
        flash_msg = f"Reco {reco_id} supprimée."
        # #13 sécu — warning si un backup récent référence cet id.
        if self._reco_id_in_recent_backup(reco_id):
            flash_msg += (" ⚠ Un backup récent référence cet id — "
                          "un undo postérieur pourrait la ressusciter.")
            kind = "warning"
        else:
            kind = "success"
        if guid:
            loc = (f"/ep?guid={urllib.parse.quote(guid)}"
                   f"&flash={urllib.parse.quote(flash_msg)}"
                   f"&kind={kind}")
        else:
            loc = "/"
        self._send_redirect(loc)

    def _reco_id_in_recent_backup(self, reco_id: str) -> bool:
        """#13 + #8 sécu — True si l'un des 20 derniers backups référence reco_id.

        Limiter aux 20 plus récents borne le coût pour les sources actives
        (sinon : O(N_backups) à chaque suppression de reco).
        """
        if not BACKUP_DIR.exists():
            return False
        dirs = sorted(
            (d for d in BACKUP_DIR.iterdir() if d.is_dir()), reverse=True,
        )[:20]
        for d in dirs:
            mf = d / "manifest.json"
            if not mf.exists():
                continue
            try:
                m = _json.loads(mf.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if m.get("source_id") != self.source_id:
                continue
            if reco_id == m.get("keep_id") or reco_id in (m.get("loser_ids") or []):
                return True
        return False
