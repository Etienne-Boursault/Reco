"""
review_telemetrie.py — journal des actions de relecture et temps actif.

Journal. Chaque POST de la page de relecture passe par `_journal_revue` : les
recos de l'épisode concerné sont relues sur disque AVANT et APRÈS l'action, et
seul ce qui a réellement changé est enregistré (`review_events`). Une action
refusée, un formulaire ouvert, un aperçu de fusion n'écrivent rien : ils ne
changent aucun fichier. Le journal ne connaît donc que des écritures réussies.

Acteur : un clic de la page = `human`. `apply_verdicts.py` (verdicts d'un
agent) écrit les siens en `agent`. Un verdict d'agent ne crée jamais de temps
humain.

Champs modifiés : leurs NOMS seulement, jamais leurs valeurs. Les catégories de
correction (`reassign_speaker`, `timestamp_corrected`, `type_corrected`,
`external_link_corrected`…) en sont DÉRIVÉES : ce n'est pas une seconde action.

Temps actif. Un battement (`POST /activite`) part toutes les 15 s tant que
l'onglet est visible ET qu'il y a eu une interaction depuis moins de 60 s
(`review_client_activite.js`). Chaque battement vaut au plus 15 s ; un
battement trop rapproché du précédent (même session) est ignoré. Le temps se
calcule au rapport, par union des intervalles : deux onglets ouverts ensemble
ne comptent pas double. Sans battement : temps `NULL`, jamais 0.

Une panne de télémétrie n'interrompt jamais la relecture.
"""
from __future__ import annotations

import contextlib
import json
import logging
import re
import time
import uuid
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import telemetry
from common import read_json

log = logging.getLogger("reco.telemetry")

#: Intervalle des battements, fixé côté serveur : le client n'en décide pas.
INTERVALLE_MS = 15_000
#: Battements plus rapprochés : ignorés (double envoi, onglet dupliqué).
ECART_MIN_MS = 10_000
_SESSION = re.compile(r"^[A-Za-z0-9-]{8,64}$")
_PAGE = re.compile(r"^/[a-z-]{0,32}$")
_GUID = re.compile(r"^[A-Za-z0-9_.:-]{1,128}$")
COOKIE = "reco_revue_session"
# Un handler par requête : le dernier battement de chaque session vit ici.
_DERNIERS_BATTEMENTS: dict[str, float] = {}

DERIVEES = {"recommendedBy": "reassign_speaker", "timestamp": "timestamp_corrected",
            "types": "type_corrected", "links": "external_link_corrected",
            "linksRejected": "external_link_corrected", "title": "title_corrected",
            "creator": "creator_corrected", "year": "year_corrected",
            "quote": "quote_corrected", "kind": "kind_changed"}
_ACTIONS_ROUTE = {"/edit": "edit", "/reenrich": "reenrich", "/undo-save": "undo",
                  "/undo-merge": "undo", "/merge-recos": "merge", "/retirer-lien": "edit",
                  "/accept-type": "edit", "/rename-guest": "edit", "/add-reco": "add",
                  "/delete-reco": "delete"}
_DECISION = {"validated": "validate", "discarded": "discard"}


def champs_modifies(avant: dict[str, Any] | None, apres: dict[str, Any] | None) -> list[str]:
    avant, apres = avant or {}, apres or {}
    return sorted(k for k in set(avant) | set(apres) if avant.get(k) != apres.get(k))


def categories(champs: list[str]) -> list[str]:
    return sorted({DERIVEES[c] for c in champs if c in DERIVEES})


def _premier(data: dict, cle: str) -> str:
    return ((data.get(cle) or [""])[0] or "").strip()


def action_pour(route: str, data: dict, avant: dict | None, apres: dict | None) -> str:
    if avant is None and apres is not None:
        return "undo" if route.startswith("/undo") else "add"
    if apres is None:
        return "merge" if route == "/merge-recos" else "delete"
    if route == "/save":
        return _premier(data, "action") or "validate"
    if route == "/consolidate":
        return _DECISION.get(str(apres.get("status")), "edit")
    return _ACTIONS_ROUTE.get(route, route.strip("/") or "inconnue")


def _attribution(recorder: Any, source_id: str, guid: str | None) -> tuple[str | None, str]:
    """La tentative d'extraction d'où vient la reco, si elle est démontrable.

    Une seule extraction réussie de l'épisode dans la base : attribution
    `inferred`. Plusieurs (reprise, expérience) ou aucune : `unknown` — jamais
    « la dernière » par défaut.
    """
    if not guid:
        return None, "unknown"
    reussies = [a for a in recorder.prior_attempts(source_id, guid, "extract")
                if a["status"] == "succeeded"]
    return (reussies[0]["id"], "inferred") if len(reussies) == 1 else (None, "unknown")


def enregistrer_evenement(source_id: str, reco_id: str, action: str,
                          avant: dict[str, Any] | None, apres: dict[str, Any] | None, *,
                          actor_kind: str, session: str | None = None,
                          metadata: dict[str, Any] | None = None) -> bool:
    """Une décision de relecture, après l'écriture. Jamais bloquant."""
    try:
        recorder = telemetry.get_recorder()
        guid = (apres or avant or {}).get("episodeGuid")
        attempt, qualite = _attribution(recorder, source_id, guid)
        champs = champs_modifies(avant, apres)
        return recorder.record_review_event({
            "id": str(uuid.uuid4()), "source_id": source_id, "episode_guid": guid,
            "reco_id": reco_id, "source_stage_attempt_id": attempt, "actor_kind": actor_kind,
            "actor_id_hash": None, "action": action, "changed_fields_json": champs,
            "derived_categories_json": categories(champs), "review_session_id": session,
            "active_duration_ms": None,
            "status_before": (avant or {}).get("status"), "status_after": (apres or {}).get("status"),
            "occurred_at": telemetry.now_iso(), "provenance_quality": qualite,
            "metadata_json": metadata or {}})
    except Exception as exc:  # noqa: BLE001 — la relecture passe avant la mesure.
        log.error("Télémétrie de relecture : %s (%s)", type(exc).__name__, exc)
        return False


class Photo:
    def __init__(self, chemins: dict[str, Path], fichiers: set[str]) -> None:
        self.chemins, self.fichiers = chemins, fichiers


def _lire(chemin: Path) -> dict[str, Any] | None:
    try:
        return read_json(chemin) if chemin.exists() else None
    except (OSError, ValueError):
        return None


class ReviewJournalMixin:
    """`_journal_revue` (avant/après de chaque POST) et `POST /activite`."""

    source_id: str
    headers: Any

    # --- quelles recos photographier ---------------------------------------
    def _ids_vises(self, route: str, data: dict) -> set[str]:
        ids = {i for cle in ("id", "member", "keep", "keep_id") for i in data.get(cle, []) if i}
        ids |= {i for i in _premier(data, "cluster_ids").split(",") if i}
        if route == "/undo-save":
            import review_undo
            entrees = review_undo._entries(self.source_id)
            if entrees:
                with contextlib.suppress(OSError, ValueError):
                    ids.add(json.loads(entrees[-1].read_text(encoding="utf-8")).get("reco_id", ""))
        return {i for i in ids if i}

    def _photo_avant(self, route: str, data: dict) -> Photo:
        """Les recos visées, lues sur disque, et la liste des fichiers du dossier.

        Jamais de relecture complète des ~3 000 recos : seulement les fichiers
        visés par le formulaire. Les recos apparues (ajout, annulation d'une
        fusion) se repèrent APRÈS au listage du dossier, sans le lire.
        """
        from review_handler_base import _reco_path
        ids = self._ids_vises(route, data)
        if route == "/rename-guest":
            # Le renommage touche les recos d'un épisode : celles du cache de la page.
            from review_render import _load_groups
            groupes = _load_groups(self.source_id)[2]
            ids |= {r.get("id") for r in groupes.get(_premier(data, "guid"), []) if r.get("id")}
        chemins = {rid: _reco_path(self.source_id, rid) for rid in ids}
        return Photo({rid: c for rid, c in chemins.items() if c is not None},
                     self._fichiers())

    def _fichiers(self) -> set[str]:
        from common import recos_dir_for
        dossier = recos_dir_for(self.source_id)
        return {p.name for p in dossier.glob("*.json")} if dossier.exists() else set()

    def _photo_apres(self, photo: Photo) -> dict[str, dict[str, Any] | None]:
        from common import recos_dir_for
        apres = {rid: _lire(chemin) for rid, chemin in photo.chemins.items()}
        for nom in sorted(self._fichiers() - photo.fichiers):
            reco = _lire(recos_dir_for(self.source_id) / nom)
            if reco and reco.get("id"):
                apres[reco["id"]] = reco
        return apres

    def _session(self) -> str | None:
        for morceau in (self.headers.get("Cookie") or "").split(";"):
            nom, _, valeur = morceau.strip().partition("=")
            if nom == COOKIE and _SESSION.match(valeur):
                return valeur
        return None

    @contextlib.contextmanager
    def _journal_revue(self, route: str, data: dict) -> Iterator[None]:
        try:
            photo = self._photo_avant(route, data)
            avant = {rid: _lire(chemin) for rid, chemin in photo.chemins.items()}
        except Exception as exc:  # noqa: BLE001
            log.error("Télémétrie de relecture (avant) : %s", exc)
            yield
            return
        yield
        try:
            apres = self._photo_apres(photo)
        except Exception as exc:  # noqa: BLE001
            log.error("Télémétrie de relecture (après) : %s", exc)
            return
        session = self._session()
        meta = {"route": route}
        if route == "/merge-recos":
            meta["keep_id"] = _premier(data, "keep_id")
        for rid in sorted(set(avant) | set(apres)):
            a, b = avant.get(rid), apres.get(rid)
            if a == b:
                continue
            enregistrer_evenement(self.source_id, rid, action_pour(route, data, a, b), a, b,
                                  actor_kind="human", session=session, metadata=meta)

    # --- battements ----------------------------------------------------------
    def _handle_activite(self, data: dict) -> None:
        session = _premier(data, "session")
        page = _premier(data, "page").split("?")[0]
        guid = _premier(data, "guid")
        if not _SESSION.match(session) or not _PAGE.match(page) or (guid and not _GUID.match(guid)):
            self._send(400, "Battement invalide")  # type: ignore[attr-defined]
            return
        maintenant = time.monotonic()
        precedent = _DERNIERS_BATTEMENTS.get(session)
        if precedent is None or (maintenant - precedent) * 1000 >= ECART_MIN_MS:
            _DERNIERS_BATTEMENTS[session] = maintenant
            try:
                telemetry.get_recorder().record_activity({
                    "id": str(uuid.uuid4()), "source_id": self.source_id,
                    "session_id": session, "received_at": telemetry.now_iso(),
                    "page": page, "episode_guid": guid or None,
                    "interval_ms": INTERVALLE_MS})
            except Exception as exc:  # noqa: BLE001
                log.error("Télémétrie d'activité : %s", exc)
        self._send(204, "")  # type: ignore[attr-defined]
